from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.ops.operational_stock_integration_gates import (
    evaluate_operational_stock_integration_gates,
)
from scripts.migrate_028_operational_stock_truth_p0_schema import migrate
from scripts.validate_operational_stock_schema import validate_operational_stock_schema
from core.ops.policy_registry_c3 import (
    DEFAULT_POLICY_PATH as DEFAULT_C3_POLICY_PATH,
    validate_exception_queue_db,
    validate_manual_decision_approvals,
    validate_operational_decision_policy_registry,
    validate_policy_gate_results,
    validate_policy_registry_schema,
    validate_policy_source_freshness,
)


DEFAULT_REQUIRED_SOURCES = (
    ("fact_inventory_snapshot_size", "snapshot_date"),
    ("stock_ledger", "event_date"),
    ("sales_fact_v2", "order_date"),
    ("order_status_event", "event_ts"),
    ("fact_order_entries_kaspi", "updated_at"),
    ("ads_source_refresh_runs", "date_end"),
    ("ads_campaign_product_daily", "date"),
    ("fact_cashflow_events", "event_date"),
    ("fact_cashflow_daily", "date"),
)


@dataclass(frozen=True)
class DailyTruthRunReport:
    run_id: str
    as_of_date: str
    status: str
    owner_trust_status: str
    output_dir: str
    lineage_json_path: str
    exception_report_json_path: str
    exception_report_md_path: str
    owner_brief_path: str
    stock_snapshot_csv_path: str | None
    source_manifests: list[dict[str, Any]]
    validation_results: list[dict[str, Any]]
    exceptions: list[dict[str, Any]]
    exception_count_total: int
    release_gates: list[dict[str, Any]]
    db_backup_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_run_id(as_of: str) -> str:
    return f"OP_STOCK_DAILY_{as_of}_{_now_stamp()}"


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _add_validation(
    validation_results: list[dict[str, Any]],
    *,
    gate_name: str,
    status: str,
    severity: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    validation_results.append(
        {
            "gate_name": gate_name,
            "status": status,
            "severity": severity,
            "message": message,
            "evidence": evidence or {},
        }
    )


def _add_exception(
    exceptions: list[dict[str, Any]],
    *,
    run_id: str,
    domain: str,
    reason: str,
    severity: str = "ERROR",
    evidence: dict[str, Any] | None = None,
    limit: int | None = None,
) -> None:
    if limit is not None and len(exceptions) >= limit:
        return
    exception_id = _sha256_text(
        json.dumps(
            {
                "run_id": run_id,
                "domain": domain,
                "reason": reason,
                "evidence": evidence or {},
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )[:24]
    exceptions.append(
        {
            "exception_id": exception_id,
            "run_id": run_id,
            "domain": domain,
            "severity": severity,
            "status": "OPEN",
            "reason": reason,
            "evidence": evidence or {},
        }
    )


def _latest_c3_policy_gate(db_path: Path, gate_name: str) -> dict[str, Any] | None:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists(conn, "policy_gate_result"):
                return None
            row = conn.execute(
                """
                SELECT gate_name, status, severity, blocks_owner_publication,
                       message, evidence_json
                FROM v_policy_gate_latest
                WHERE gate_name=?
                """,
                (gate_name,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        evidence = json.loads(str(row["evidence_json"] or "{}"))
    except Exception:
        evidence = {}
    return {
        "gate_name": row["gate_name"],
        "status": row["status"],
        "severity": row["severity"],
        "blocks_owner_publication": int(row["blocks_owner_publication"] or 0),
        "message": row["message"],
        "evidence": evidence,
    }


def _add_c3_foundation_validations(
    *,
    db_path: Path,
    policy_path: Path,
    as_of: str,
    run_id: str,
    validation_results: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    max_exception_items: int,
) -> int:
    added = 0
    schema_errors = validate_policy_registry_schema(db_path)
    if schema_errors:
        _add_validation(
            validation_results,
            gate_name="c3_policy_registry",
            status="FAIL",
            severity="ERROR",
            message="C3 policy registry schema is missing or incomplete.",
            evidence={"errors": schema_errors},
        )
        _add_exception(
            exceptions,
            run_id=run_id,
            domain="c3_policy_registry",
            reason="C3_POLICY_REGISTRY_MISSING",
            evidence={"errors": schema_errors},
            limit=max_exception_items,
        )
        return 1

    exception_metadata_errors = validate_exception_queue_db(db_path, strict=True)
    exception_policy_gate = _latest_c3_policy_gate(db_path, "exception_queue")
    exception_semantic_errors: list[str] = []
    if exception_policy_gate and (
        str(exception_policy_gate["status"]).upper() not in {"PASS", "WARN"}
        or int(exception_policy_gate["blocks_owner_publication"] or 0) == 1
    ):
        exception_semantic_errors.append(
            "C3 policy gate exception_queue is "
            f"{exception_policy_gate['status']} and blocks owner publication"
        )

    checks = (
        (
            "c3_policy_registry",
            "C3_POLICY_REGISTRY_DRIFT",
            validate_operational_decision_policy_registry(db_path, policy_path),
            "C3 active policy registry does not match the YAML contract.",
        ),
        (
            "c3_source_freshness",
            "C3_SOURCE_FRESHNESS_FAIL",
            validate_policy_source_freshness(db_path, as_of=as_of),
            "C3 required source freshness is missing, stale, blocked, or unknown.",
        ),
        (
            "c3_policy_gate_results",
            "C3_POLICY_GATE_RESULT_FAIL",
            validate_policy_gate_results(db_path),
            "C3 required policy gate results are missing or blocking.",
        ),
        (
            "c3_exception_queue",
            "C3_EXCEPTION_QUEUE_FAIL",
            exception_metadata_errors + exception_semantic_errors,
            "C3 exception queue metadata or semantic policy gate blocks publication.",
        ),
        (
            "c3_manual_approvals",
            "C3_MANUAL_APPROVAL_FAIL",
            validate_manual_decision_approvals(db_path),
            "C3 manual approvals are missing evidence or attempt to override publication gates.",
        ),
    )
    for gate_name, reason, errors, message in checks:
        if errors:
            evidence: dict[str, Any] = {"errors": errors}
            if gate_name == "c3_exception_queue" and exception_policy_gate:
                evidence["metadata_only_validator_errors"] = exception_metadata_errors
                evidence["latest_policy_gate"] = exception_policy_gate
            _add_validation(
                validation_results,
                gate_name=gate_name,
                status="BLOCKED" if gate_name == "c3_exception_queue" else "FAIL",
                severity="ERROR",
                message=message,
                evidence=evidence,
            )
            _add_exception(
                exceptions,
                run_id=run_id,
                domain=gate_name,
                reason=reason,
                evidence=evidence,
                limit=max_exception_items,
            )
            added += 1
        else:
            evidence = {}
            if gate_name == "c3_exception_queue" and exception_policy_gate:
                evidence["metadata_only_validator_errors"] = []
                evidence["latest_policy_gate"] = exception_policy_gate
            _add_validation(
                validation_results,
                gate_name=gate_name,
                status="PASS",
                severity="INFO",
                message=f"{gate_name} is green for C3 foundation checks.",
                evidence=evidence,
            )
    return added


def _source_manifest_for_table(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    db_sha256: str,
    table: str,
    date_column: str,
    as_of: str,
    max_source_lag_days: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not _table_exists(conn, table):
        manifest = {
            "source_id": f"sqlite:{table}",
            "source_type": "sqlite_table",
            "source_path": str(db_path),
            "source_sha256": db_sha256,
            "table": table,
            "as_of_date": as_of,
            "freshness_status": "MISSING",
            "row_count": 0,
            "max_observed_date": None,
            "notes": "required table missing",
        }
        return manifest, {"reason": "SOURCE_MISSING", "table": table}

    row_count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
    cols = _columns(conn, table)
    max_observed_date: str | None = None
    notes = ""
    freshness_status = "FRESH"
    issue: dict[str, Any] | None = None

    if row_count <= 0:
        freshness_status = "EMPTY"
        issue = {"reason": "SOURCE_EMPTY", "table": table}
    elif date_column not in cols:
        freshness_status = "UNKNOWN"
        issue = {
            "reason": "SOURCE_DATE_COLUMN_MISSING",
            "table": table,
            "date_column": date_column,
        }
    else:
        raw_max = conn.execute(
            f"SELECT MAX(substr(CAST({date_column} AS TEXT), 1, 10)) FROM {table}"
        ).fetchone()[0]
        max_observed = _parse_iso_date(raw_max)
        max_observed_date = max_observed.isoformat() if max_observed else None
        as_of_date = _parse_iso_date(as_of)
        if max_observed is None or as_of_date is None:
            freshness_status = "UNKNOWN"
            issue = {
                "reason": "SOURCE_DATE_UNPARSEABLE",
                "table": table,
                "max_observed_date": raw_max,
            }
        elif max_observed > as_of_date:
            freshness_status = "FUTURE"
            issue = {
                "reason": "SOURCE_FUTURE_DATED",
                "table": table,
                "max_observed_date": max_observed.isoformat(),
                "as_of_date": as_of,
            }
        elif max_observed < as_of_date - timedelta(days=max_source_lag_days):
            freshness_status = "STALE"
            issue = {
                "reason": "SOURCE_STALE",
                "table": table,
                "max_observed_date": max_observed.isoformat(),
                "as_of_date": as_of,
                "max_source_lag_days": max_source_lag_days,
            }

    fingerprint = _sha256_text(
        json.dumps(
            {
                "db_sha256": db_sha256,
                "table": table,
                "row_count": row_count,
                "max_observed_date": max_observed_date,
                "freshness_status": freshness_status,
            },
            sort_keys=True,
        )
    )
    manifest = {
        "source_id": f"sqlite:{table}",
        "source_type": "sqlite_table",
        "source_path": str(db_path),
        "source_sha256": fingerprint,
        "database_sha256": db_sha256,
        "table": table,
        "as_of_date": as_of,
        "freshness_status": freshness_status,
        "row_count": row_count,
        "max_observed_date": max_observed_date,
        "notes": notes,
    }
    return manifest, issue


def _build_source_manifests(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    db_sha256: str,
    as_of: str,
    max_source_lag_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifests: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for table, date_column in DEFAULT_REQUIRED_SOURCES:
        manifest, issue = _source_manifest_for_table(
            conn,
            db_path=db_path,
            db_sha256=db_sha256,
            table=table,
            date_column=date_column,
            as_of=as_of,
            max_source_lag_days=max_source_lag_days,
        )
        manifests.append(manifest)
        if issue is not None:
            issues.append(issue)
    return manifests, issues


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_exception_markdown(path: Path, *, report: DailyTruthRunReport | None, payload: dict[str, Any]) -> None:
    lines = [
        "# Operational Stock Daily Truth Exceptions",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"As of: `{payload['as_of_date']}`",
        f"Status: `{payload['status']}`",
        f"Exception count total: `{payload['exception_count_total']}`",
        "",
        "## Counts By Reason",
        "",
    ]
    counts = payload.get("exception_counts_by_reason", {})
    if counts:
        for reason, count in sorted(counts.items()):
            lines.append(f"- `{reason}`: `{count}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Sample Open Exceptions", ""])
    for item in payload.get("exceptions", [])[:50]:
        lines.append(f"- `{item['reason']}` `{item['domain']}`: {item.get('evidence', {})}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_owner_brief(
    path: Path,
    *,
    run_id: str,
    as_of: str,
    owner_trust_status: str,
    status: str,
    validation_results: list[dict[str, Any]],
    exception_count_total: int,
    exception_counts: Counter[str],
    release_gates: list[dict[str, Any]],
    lineage_json_path: Path,
    exception_report_json_path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Operational Stock Daily Truth Brief",
        "",
        f"Trust banner: {owner_trust_status}",
        f"Run status: {status}",
        f"Run ID: `{run_id}`",
        f"As of: `{as_of}`",
        "",
    ]
    if owner_trust_status == "GREEN_DECISION_GRADE":
        lines.extend(
            [
                "Owner publication is decision-grade for this run.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Owner publication is blocked.",
                "No green release has been published.",
                "Use this brief as the owner-facing output until strict gates are green and green publication is explicitly authorized.",
                "",
            ]
        )

    lines.extend(["## Release Gates", ""])
    for gate in release_gates:
        lines.append(
            f"- `{gate['gate_name']}`: `{gate['status']}` - {gate['message']}"
        )

    lines.extend(["", "## Validation Results", ""])
    for result in validation_results:
        lines.append(
            f"- `{result['gate_name']}`: `{result['status']}` `{result['severity']}` - {result['message']}"
        )
        evidence = result.get("evidence") or {}
        for key in ("finding_counts", "issue_counts"):
            counts = evidence.get(key)
            if isinstance(counts, dict) and counts:
                for code, count in sorted(counts.items()):
                    lines.append(f"  - `{code}`: `{count}`")
        errors = evidence.get("errors")
        if isinstance(errors, list) and errors:
            for error in errors[:25]:
                lines.append(f"  - `{str(error)}`")
            if len(errors) > 25:
                lines.append(f"  - `{len(errors) - 25} more errors in run lineage`")

    lines.extend(["", "## Exception Counts", ""])
    lines.append(f"- Total open/blocking exceptions: `{exception_count_total}`")
    if exception_counts:
        for reason, count in sorted(exception_counts.items()):
            lines.append(f"- `{reason}`: `{count}`")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Run lineage JSON: `{lineage_json_path}`",
            f"- Exception report JSON: `{exception_report_json_path}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_stock_snapshot_csv(conn: sqlite3.Connection, path: Path, *, as_of: str) -> Path | None:
    if not _table_exists(conn, "fact_inventory_snapshot_size"):
        return None
    row = conn.execute(
        """
        SELECT MAX(snapshot_date) AS snapshot_date
        FROM fact_inventory_snapshot_size
        WHERE date(snapshot_date) <= date(?)
        """,
        (as_of,),
    ).fetchone()
    snapshot_date = row["snapshot_date"] if row and row["snapshot_date"] else None
    if snapshot_date is None:
        return None
    rows = conn.execute(
        """
        SELECT snapshot_date, sku_key, sku_id, my_size, current_stock, inbound_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        ORDER BY sku_key, my_size, sku_id
        """,
        (snapshot_date,),
    ).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["snapshot_date", "sku_key", "sku_id", "my_size", "current_stock", "inbound_stock"])
        for item in rows:
            writer.writerow(
                [
                    item["snapshot_date"],
                    item["sku_key"],
                    item["sku_id"],
                    item["my_size"],
                    item["current_stock"],
                    item["inbound_stock"],
                ]
            )
    return path


def _record_to_db(
    *,
    db_path: Path,
    report: DailyTruthRunReport,
    backup_dir: Path,
) -> Path:
    if os.environ.get("ENABLE_OPERATIONAL_STOCK_DAILY_DB_WRITE") != "1":
        raise RuntimeError("ENABLE_OPERATIONAL_STOCK_DAILY_DB_WRITE=1 is required for DB recording")
    if not db_path.exists():
        raise RuntimeError(f"DB does not exist: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"app_db_before_operational_stock_daily_{_now_stamp()}.db"
    shutil.copy2(db_path, backup_path)

    migrate(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_run (
                run_id, run_type, as_of_date, status, source_manifest_json,
                validation_status, exception_count, finished_at, notes
            ) VALUES (?, 'OPERATIONAL_STOCK_DAILY_TRUTH', ?, ?, ?, ?, ?, datetime('now'), ?)
            """,
            (
                report.run_id,
                report.as_of_date,
                report.status,
                json.dumps(report.source_manifests, ensure_ascii=False, sort_keys=True),
                report.owner_trust_status,
                report.exception_count_total,
                "Agent 8 strict daily truth runner.",
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO owner_report_snapshot (
                snapshot_id, run_id, report_date, trust_status, report_path,
                source_manifest_json, exception_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"OPERATIONAL_STOCK_DAILY_TRUTH_{report.as_of_date}",
                report.run_id,
                report.as_of_date,
                report.owner_trust_status,
                report.owner_brief_path,
                json.dumps(report.source_manifests, ensure_ascii=False, sort_keys=True),
                report.exception_count_total,
            ),
        )
        for item in report.validation_results:
            conn.execute(
                """
                INSERT INTO validation_result (
                    run_id, gate_name, status, severity, message, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.run_id,
                    item["gate_name"],
                    item["status"],
                    item["severity"],
                    item["message"],
                    json.dumps(item.get("evidence", {}), ensure_ascii=False, sort_keys=True),
                ),
            )
        for manifest in report.source_manifests:
            conn.execute(
                """
                INSERT OR REPLACE INTO source_manifest (
                    source_id, source_type, source_path, source_sha256, as_of_date,
                    freshness_status, row_count, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest["source_id"],
                    manifest["source_type"],
                    manifest["source_path"],
                    manifest["source_sha256"],
                    manifest["as_of_date"],
                    manifest["freshness_status"],
                    manifest["row_count"],
                    manifest.get("notes", ""),
                ),
            )
        for item in report.exceptions:
            conn.execute(
                """
                INSERT OR REPLACE INTO exception_queue (
                    exception_id, run_id, domain, severity, status, reason, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["exception_id"],
                    item["run_id"],
                    item["domain"],
                    item["severity"],
                    item["status"],
                    item["reason"],
                    json.dumps(item.get("evidence", {}), ensure_ascii=False, sort_keys=True),
                ),
            )
        conn.commit()

    return backup_path


def run_operational_stock_daily_truth(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path,
    run_id: str | None = None,
    allow_green_owner_output: bool = False,
    max_source_lag_days: int = 1,
    max_exception_items: int = 500,
    record_db: bool = False,
    backup_dir: Path | None = None,
    require_c3_policy: bool = False,
    policy_path: Path | None = None,
) -> DailyTruthRunReport:
    """Run the Agent 8 daily truth gate and write owner-facing artifacts.

    The runner is artifact-first and fail-closed. DB recording is optional and
    requires a write-enable environment gate plus a backup.
    """

    run_id = run_id or _safe_run_id(as_of)
    output_dir = output_root / as_of / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    validation_results: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    source_manifests: list[dict[str, Any]] = []
    release_gates: list[dict[str, Any]] = []
    exception_count_total = 0

    db_path = db_path.expanduser().resolve()
    if not db_path.exists():
        _add_validation(
            validation_results,
            gate_name="database_presence",
            status="FAIL",
            severity="ERROR",
            message="Operational DB is missing; daily truth cannot publish green.",
            evidence={"db_path": str(db_path)},
        )
        _add_exception(
            exceptions,
            run_id=run_id,
            domain="database",
            reason="DB_MISSING",
            evidence={"db_path": str(db_path)},
            limit=max_exception_items,
        )
        exception_count_total += 1
    else:
        db_sha256 = _sha256_file(db_path)
        schema_errors = validate_operational_stock_schema(db_path)
        if schema_errors:
            _add_validation(
                validation_results,
                gate_name="operational_schema",
                status="FAIL",
                severity="ERROR",
                message="Operational stock schema contract is not satisfied.",
                evidence={"errors": schema_errors},
            )
            for error in schema_errors:
                _add_exception(
                    exceptions,
                    run_id=run_id,
                    domain="schema",
                    reason="SCHEMA_CONTRACT_FAIL",
                    evidence={"error": error},
                    limit=max_exception_items,
                )
            exception_count_total += len(schema_errors)
        else:
            _add_validation(
                validation_results,
                gate_name="operational_schema",
                status="PASS",
                severity="INFO",
                message="Operational stock schema contract tables are present.",
                evidence={},
            )

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            manifests, source_issues = _build_source_manifests(
                conn,
                db_path=db_path,
                db_sha256=db_sha256,
                as_of=as_of,
                max_source_lag_days=max_source_lag_days,
            )
            source_manifests.extend(manifests)

            if source_issues:
                counts = Counter(issue["reason"] for issue in source_issues)
                _add_validation(
                    validation_results,
                    gate_name="source_freshness",
                    status="FAIL",
                    severity="ERROR",
                    message="One or more required operational sources are missing, empty, stale, future-dated, or unparseable.",
                    evidence={"issue_counts": dict(sorted(counts.items())), "issues": source_issues[:50]},
                )
                for issue in source_issues:
                    _add_exception(
                        exceptions,
                        run_id=run_id,
                        domain="source_manifest",
                        reason=issue["reason"],
                        evidence=issue,
                        limit=max_exception_items,
                    )
                exception_count_total += len(source_issues)
            else:
                _add_validation(
                    validation_results,
                    gate_name="source_freshness",
                    status="PASS",
                    severity="INFO",
                    message="Required operational source manifests are fresh for the configured lag window.",
                    evidence={"source_count": len(source_manifests)},
                )

            try:
                integration_report = evaluate_operational_stock_integration_gates(db_path, as_of=as_of)
            except Exception as exc:
                _add_validation(
                    validation_results,
                    gate_name="agent7_live_integration_gates",
                    status="FAIL",
                    severity="ERROR",
                    message="Agent 7 integration gate raised an exception; fail closed.",
                    evidence={"error": str(exc)},
                )
                _add_exception(
                    exceptions,
                    run_id=run_id,
                    domain="integration_gate",
                    reason="INTEGRATION_GATE_EXCEPTION",
                    evidence={"error": str(exc)},
                    limit=max_exception_items,
                )
                exception_count_total += 1
            else:
                finding_counts = Counter(finding.code for finding in integration_report.findings)
                if integration_report.status == "RED":
                    _add_validation(
                        validation_results,
                        gate_name="agent7_live_integration_gates",
                        status="FAIL",
                        severity="ERROR",
                        message="Agent 7 live integration gate is RED; owner/release outputs stay blocked.",
                        evidence={
                            "finding_count": len(integration_report.findings),
                            "finding_counts": dict(sorted(finding_counts.items())),
                        },
                    )
                    for finding in integration_report.findings:
                        _add_exception(
                            exceptions,
                            run_id=run_id,
                            domain="agent7_integration",
                            reason=finding.code,
                            evidence=finding.evidence,
                            limit=max_exception_items,
                        )
                    exception_count_total += len(integration_report.findings)
                else:
                    _add_validation(
                        validation_results,
                        gate_name="agent7_live_integration_gates",
                        status="PASS",
                        severity="INFO",
                        message="Agent 7 live integration gate is green for this as-of date.",
                        evidence={"finding_count": 0},
                    )

            if require_c3_policy:
                exception_count_total += _add_c3_foundation_validations(
                    db_path=db_path,
                    policy_path=policy_path or DEFAULT_C3_POLICY_PATH,
                    as_of=as_of,
                    run_id=run_id,
                    validation_results=validation_results,
                    exceptions=exceptions,
                    max_exception_items=max_exception_items,
                )

    blocking_results = [
        result
        for result in validation_results
        if result["severity"] == "ERROR" or result["status"] not in {"PASS", "WARN"}
    ]

    for result in validation_results:
        release_gates.append(
            {
                "gate_name": result["gate_name"],
                "status": "PASS" if result["status"] == "PASS" else "BLOCKED",
                "message": result["message"],
                "blocks_owner_publication": result["status"] != "PASS",
            }
        )

    if not allow_green_owner_output:
        _add_validation(
            validation_results,
            gate_name="green_owner_publication_authorization",
            status="BLOCKED",
            severity="ERROR",
            message="Green owner publication is not explicitly authorized for this fail-closed runner invocation.",
            evidence={"allow_green_owner_output": False},
        )
        release_gates.append(
            {
                "gate_name": "green_owner_publication_authorization",
                "status": "BLOCKED",
                "message": "Green owner publication requires explicit authorization and all live blockers cleared.",
                "blocks_owner_publication": True,
            }
        )
        _add_exception(
            exceptions,
            run_id=run_id,
            domain="release_gate",
            reason="GREEN_PUBLICATION_NOT_AUTHORIZED",
            evidence={"allow_green_owner_output": False},
            limit=max_exception_items,
        )
        exception_count_total += 1
        blocking_results.append(validation_results[-1])
    else:
        release_gates.append(
            {
                "gate_name": "green_owner_publication_authorization",
                "status": "PASS",
                "message": "Green owner publication flag was provided; live gates still decide final trust.",
                "blocks_owner_publication": False,
            }
        )

    status = "RED" if blocking_results else "GREEN"
    owner_trust_status = "GREEN_DECISION_GRADE" if status == "GREEN" else "RED_BLOCKED"

    exception_counts = Counter(item["reason"] for item in exceptions)
    lineage_path = output_dir / "run_lineage.json"
    exception_json_path = output_dir / "exception_report.json"
    exception_md_path = output_dir / "exception_report.md"
    owner_brief_path = output_dir / "owner_blocked_brief.md"
    stock_snapshot_csv_path: str | None = None

    if owner_trust_status == "GREEN_DECISION_GRADE" and db_path.exists():
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            snapshot_path = _write_stock_snapshot_csv(conn, output_dir / "owner_stock_snapshot.csv", as_of=as_of)
            stock_snapshot_csv_path = str(snapshot_path) if snapshot_path else None

    _write_owner_brief(
        owner_brief_path,
        run_id=run_id,
        as_of=as_of,
        owner_trust_status=owner_trust_status,
        status=status,
        validation_results=validation_results,
        exception_count_total=exception_count_total,
        exception_counts=exception_counts,
        release_gates=release_gates,
        lineage_json_path=lineage_path,
        exception_report_json_path=exception_json_path,
    )

    report = DailyTruthRunReport(
        run_id=run_id,
        as_of_date=as_of,
        status=status,
        owner_trust_status=owner_trust_status,
        output_dir=str(output_dir),
        lineage_json_path=str(lineage_path),
        exception_report_json_path=str(exception_json_path),
        exception_report_md_path=str(exception_md_path),
        owner_brief_path=str(owner_brief_path),
        stock_snapshot_csv_path=stock_snapshot_csv_path,
        source_manifests=source_manifests,
        validation_results=validation_results,
        exceptions=exceptions,
        exception_count_total=exception_count_total,
        release_gates=release_gates,
    )

    exception_payload = {
        "run_id": run_id,
        "as_of_date": as_of,
        "status": status,
        "owner_trust_status": owner_trust_status,
        "exception_count_total": exception_count_total,
        "exception_counts_by_reason": dict(sorted(exception_counts.items())),
        "exceptions": exceptions,
    }
    _write_json(exception_json_path, exception_payload)
    _write_exception_markdown(exception_md_path, report=report, payload=exception_payload)

    lineage_payload = {
        "run_id": run_id,
        "as_of_date": as_of,
        "status": status,
        "owner_trust_status": owner_trust_status,
        "generated_at": datetime.now().isoformat(),
        "source_manifests": source_manifests,
        "validation_results": validation_results,
        "release_gates": release_gates,
        "exception_report": {
            "exception_count_total": exception_count_total,
            "exception_counts_by_reason": dict(sorted(exception_counts.items())),
            "exception_report_json": str(exception_json_path),
            "exception_report_md": str(exception_md_path),
        },
        "owner_outputs": {
            "owner_brief_md": str(owner_brief_path),
            "stock_snapshot_csv": stock_snapshot_csv_path,
        },
    }
    _write_json(lineage_path, lineage_payload)

    if record_db:
        backup_path = _record_to_db(
            db_path=db_path,
            report=report,
            backup_dir=backup_dir or (db_path.parent.parent / "runtime" / "backups"),
        )
        report = DailyTruthRunReport(
            **{**report.to_dict(), "db_backup_path": str(backup_path)}
        )

    return report
