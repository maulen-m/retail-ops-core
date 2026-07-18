#!/usr/bin/env python3
"""Plan and apply an exact copied-DB sales truth-view refresh.

Planning is read-only and emits a reviewed JSON plan plus deterministic CSV
deltas. Applying is copy-only, backup-first, explicitly gated, and limited to
publication-binding schema installation plus the six canonical truth views.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.publication_binding import install_publication_binding_schema  # noqa: E402
from core.sales.publication_prerequisites import (  # noqa: E402
    build_minimal_publication_schema_contract,
    require_minimal_publication_schema,
)
from core.sales.truth_view_contract import (  # noqa: E402
    TRACKED_VIEWS,
    build_truth_view_contract,
    require_manifest_build_compatible,
    require_post_refresh_stored_sql,
)
from core.sales.truth_views import ensure_sales_truth_views  # noqa: E402
from scripts.build_sales_publication_binding_manifest import (  # noqa: E402
    OLD_PUBLIC_COLUMNS,
)


PRODUCTION_DB = (PROJECT_ROOT / "db" / "app.db").resolve()
PLAN_SCHEMA_VERSION = "sales_truth_view_refresh_plan_v1"
WRITE_ENV_GATE = "ENABLE_COPIED_SALES_TRUTH_VIEW_REFRESH_WRITE"
BINDING_SCHEMA_OBJECTS = {
    "fact_sales_publication_binding_header",
    "fact_sales_publication_binding_line",
    "ux_sales_publication_binding_active",
}


class SalesTruthViewRefreshError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _applier_code_pin() -> dict[str, str]:
    path = Path(__file__).resolve()
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "file_sha256": sha256_file(path),
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _sidecars(path: Path) -> list[Path]:
    return [
        candidate
        for candidate in (
            Path(str(path) + "-wal"),
            Path(str(path) + "-shm"),
            Path(str(path) + "-journal"),
        )
        if candidate.exists()
    ]


def _assert_copied_target(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SalesTruthViewRefreshError(f"DB does not exist: {resolved}")
    if resolved == PRODUCTION_DB:
        raise SalesTruthViewRefreshError("refusing canonical production DB")
    if PRODUCTION_DB.exists() and os.path.samefile(resolved, PRODUCTION_DB):
        raise SalesTruthViewRefreshError("refusing production DB hardlink or alias")
    if "/runs/tmux_orchestration/" not in str(resolved):
        raise SalesTruthViewRefreshError(
            "truth-view refresh target must be inside runs/tmux_orchestration"
        )
    sidecars = _sidecars(resolved)
    if sidecars:
        raise SalesTruthViewRefreshError(
            "refusing copied DB with SQLite sidecars: " + ", ".join(map(str, sidecars))
        )
    return resolved


def _connect_read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _integrity_conn(conn: sqlite3.Connection) -> str:
    return str(conn.execute("PRAGMA integrity_check").fetchone()[0])


def _integrity_path(path: Path) -> str:
    conn = _connect_read_only(path)
    try:
        return _integrity_conn(conn)
    finally:
        conn.close()


def _selected_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [
        dict(row)
        for row in conn.execute(
            f"SELECT {','.join(OLD_PUBLIC_COLUMNS)} FROM view_sales_line_truth"
        ).fetchall()
    ]


def _row_counter(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(_json_bytes(row).decode("utf-8") for row in rows)


def _expand(counter: Counter[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for encoded, count in sorted(counter.items()):
        result.extend(json.loads(encoded) for _ in range(count))
    return result


def _rows_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    encoded = sorted(_json_bytes(row).decode("utf-8") for row in rows)
    return {"row_count": len(rows), "multiset_sha256": canonical_sha256(encoded)}


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=OLD_PUBLIC_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                column: "" if row.get(column) is None else str(row.get(column))
                for column in OLD_PUBLIC_COLUMNS
            }
        )
    return stream.getvalue().encode("utf-8")


def _table_fingerprints(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    tables = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        columns = [
            str(row[1]) for row in conn.execute(f"PRAGMA table_info({quoted})").fetchall()
        ]
        row_hashes = [
            canonical_sha256(dict(zip(columns, row)))
            for row in conn.execute(f"SELECT * FROM {quoted}").fetchall()
        ]
        result[table] = {
            "columns": columns,
            "row_count": len(row_hashes),
            "row_multiset_sha256": canonical_sha256(sorted(row_hashes)),
        }
    return result


def _schema_objects(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(name): {
            "type": str(kind),
            "sql_sha256": hashlib.sha256(str(sql or "").encode("utf-8")).hexdigest(),
        }
        for kind, name, sql in conn.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    }


def _probe_refreshed_state(db_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ab_sales_truth_refresh_") as tmp:
        probe_path = Path(tmp) / "probe.db"
        source = _connect_read_only(db_path)
        probe = sqlite3.connect(str(probe_path))
        probe.row_factory = sqlite3.Row
        try:
            source.backup(probe)
            before_tables = _table_fingerprints(probe)
            before_schema = _schema_objects(probe)
            before_rows = _selected_rows(probe)
            install_publication_binding_schema(probe)
            ensure_sales_truth_views(probe)
            probe.commit()
            if _integrity_conn(probe).lower() != "ok":
                raise SalesTruthViewRefreshError("temporary refreshed probe integrity failed")
            after_tables = _table_fingerprints(probe)
            after_schema = _schema_objects(probe)
            after_rows = _selected_rows(probe)
        finally:
            probe.close()
            source.close()
        post_contract = build_truth_view_contract(probe_path)
        require_manifest_build_compatible(post_contract)
        return {
            "before_tables": before_tables,
            "before_schema": before_schema,
            "before_rows": before_rows,
            "after_tables": after_tables,
            "after_schema": after_schema,
            "after_rows": after_rows,
            "post_contract": post_contract,
        }


def _validate_schema_delta(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    changed = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    allowed = BINDING_SCHEMA_OBJECTS | set(TRACKED_VIEWS)
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        raise SalesTruthViewRefreshError(
            f"unexpected truth-view refresh schema objects: {unexpected}"
        )
    return changed


def _validate_preexisting_tables(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    changed = sorted(
        table for table, fingerprint in before.items() if after.get(table) != fingerprint
    )
    if changed:
        raise SalesTruthViewRefreshError(
            f"pre-existing table rows changed in refresh probe: {changed}"
        )
    added = sorted(set(after) - set(before))
    unexpected = sorted(set(added) - {
        "fact_sales_publication_binding_header",
        "fact_sales_publication_binding_line",
    })
    if unexpected:
        raise SalesTruthViewRefreshError(
            f"unexpected additive table set: {unexpected}"
        )
    return added


def build_refresh_plan(db_path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    db_path = _assert_copied_target(db_path)
    pre_sha = sha256_file(db_path)
    if _integrity_path(db_path).lower() != "ok":
        raise SalesTruthViewRefreshError("source DB integrity_check failed")

    conn = _connect_read_only(db_path)
    try:
        minimal_contract = build_minimal_publication_schema_contract(conn)
    finally:
        conn.close()
    require_minimal_publication_schema(minimal_contract)
    legacy_contract = build_truth_view_contract(db_path)
    probe = _probe_refreshed_state(db_path)
    added_tables = _validate_preexisting_tables(
        probe["before_tables"], probe["after_tables"]
    )
    changed_schema = _validate_schema_delta(
        probe["before_schema"], probe["after_schema"]
    )

    before_rows = probe["before_rows"]
    after_rows = probe["after_rows"]
    before_counter = _row_counter(before_rows)
    after_counter = _row_counter(after_rows)
    only_before = _expand(before_counter - after_counter)
    only_after = _expand(after_counter - before_counter)
    only_before_bytes = _csv_bytes(only_before)
    only_after_bytes = _csv_bytes(only_after)
    body: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "applier_code_pin": _applier_code_pin(),
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "minimal_publication_schema_contract": minimal_contract,
        "legacy_truth_view_contract": legacy_contract,
        "expected_post_truth_view_contract": probe["post_contract"],
        "before_schema_objects": probe["before_schema"],
        "after_schema_objects": probe["after_schema"],
        "changed_schema_objects": changed_schema,
        "before_table_fingerprints": probe["before_tables"],
        "after_table_fingerprints": probe["after_tables"],
        "added_tables": added_tables,
        "selected_rows_before": _rows_summary(before_rows),
        "selected_rows_after": _rows_summary(after_rows),
        "only_before": _rows_summary(only_before),
        "only_after": _rows_summary(only_after),
        "evidence_files": {
            "only_before": {
                "filename": "sales_truth_view_only_before.csv",
                "sha256": hashlib.sha256(only_before_bytes).hexdigest(),
            },
            "only_after": {
                "filename": "sales_truth_view_only_after.csv",
                "sha256": hashlib.sha256(only_after_bytes).hexdigest(),
            },
        },
    }
    body["plan_sha256"] = canonical_sha256(body)
    return body, only_before_bytes, only_after_bytes


def _validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise SalesTruthViewRefreshError("unsupported truth-view refresh plan schema")
    expected = str(plan.get("plan_sha256") or "")
    body = dict(plan)
    body.pop("plan_sha256", None)
    if not expected or canonical_sha256(body) != expected:
        raise SalesTruthViewRefreshError("truth-view refresh plan internal hash mismatch")
    if plan.get("applier_code_pin") != _applier_code_pin():
        raise SalesTruthViewRefreshError(
            "truth-view refresh applier code differs from reviewed plan"
        )


def write_plan(
    *, db_path: Path, plan_path: Path, evidence_dir: Path | None = None
) -> dict[str, Any]:
    if plan_path.exists():
        raise SalesTruthViewRefreshError(f"plan already exists: {plan_path}")
    plan, only_before_bytes, only_after_bytes = build_refresh_plan(db_path)
    output_dir = (evidence_dir or plan_path.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, content in (
        ("only_before", only_before_bytes),
        ("only_after", only_after_bytes),
    ):
        item = plan["evidence_files"][key]
        path = output_dir / item["filename"]
        if path.exists():
            raise SalesTruthViewRefreshError(f"evidence file already exists: {path}")
        path.write_bytes(content)
        if sha256_file(path) != item["sha256"]:
            raise SalesTruthViewRefreshError(f"evidence hash mismatch after write: {path}")
    plan["evidence_directory"] = str(output_dir)
    body = dict(plan)
    body.pop("plan_sha256", None)
    plan["plan_sha256"] = canonical_sha256(body)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan


def _plan_without_output_location(plan: dict[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    result.pop("evidence_directory", None)
    result.pop("plan_sha256", None)
    return result


def _verify_idempotent_replay_in_transaction(
    conn: sqlite3.Connection,
    *,
    pinned_contract: dict[str, Any],
    expected_tables: dict[str, Any],
    expected_schema: dict[str, Any],
    expected_rows: list[dict[str, Any]],
) -> None:
    install_publication_binding_schema(conn)
    ensure_sales_truth_views(conn)
    require_post_refresh_stored_sql(conn, pinned_contract=pinned_contract)
    if (
        _table_fingerprints(conn) != expected_tables
        or _schema_objects(conn) != expected_schema
        or _selected_rows(conn) != expected_rows
    ):
        raise SalesTruthViewRefreshError(
            "truth-view refresh is not logically idempotent"
        )


def _verify_post_commit_state(
    db_path: Path,
    *,
    expected_contract: dict[str, Any],
) -> dict[str, Any]:
    post_contract = build_truth_view_contract(db_path)
    require_manifest_build_compatible(post_contract)
    if post_contract != expected_contract:
        raise SalesTruthViewRefreshError(
            "post-refresh truth-view contract differs from plan"
        )
    if _integrity_path(db_path).lower() != "ok":
        raise SalesTruthViewRefreshError("post-commit integrity_check failed")
    return post_contract


def _restore_verified_backup(
    *, db_path: Path, backup_path: Path, expected_sha256: str
) -> str:
    if _sidecars(db_path):
        raise SalesTruthViewRefreshError(
            "cannot restore copied DB while SQLite sidecars exist"
        )
    shutil.copy2(backup_path, db_path)
    restored_sha = sha256_file(db_path)
    if restored_sha != expected_sha256 or _integrity_path(db_path).lower() != "ok":
        raise SalesTruthViewRefreshError(
            "post-commit failure restore did not reproduce exact preimage"
        )
    return restored_sha


def apply_reviewed_plan(
    *,
    db_path: Path,
    reviewed_plan_path: Path,
    expected_plan_file_sha256: str,
    expected_pre_sha256: str,
    backup_dir: Path,
    report_path: Path,
) -> dict[str, Any]:
    db_path = _assert_copied_target(db_path)
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise SalesTruthViewRefreshError(f"{WRITE_ENV_GATE}=1 is required")
    if report_path.exists():
        raise SalesTruthViewRefreshError(f"report already exists: {report_path}")
    if sha256_file(reviewed_plan_path) != expected_plan_file_sha256:
        raise SalesTruthViewRefreshError("reviewed plan file SHA-256 mismatch")
    plan = json.loads(reviewed_plan_path.read_text(encoding="utf-8"))
    _validate_plan(plan)
    if Path(str(plan.get("db_path") or "")).resolve() != db_path:
        raise SalesTruthViewRefreshError("reviewed plan targets a different DB path")
    pre_sha = sha256_file(db_path)
    if pre_sha != expected_pre_sha256 or pre_sha != plan.get("pre_sha256"):
        raise SalesTruthViewRefreshError("copied DB pre-SHA differs from reviewed plan")

    evidence_dir = Path(str(plan.get("evidence_directory") or reviewed_plan_path.parent))
    for item in plan["evidence_files"].values():
        evidence_path = evidence_dir / str(item["filename"])
        if not evidence_path.is_file() or sha256_file(evidence_path) != item["sha256"]:
            raise SalesTruthViewRefreshError(
                f"reviewed delta evidence missing or changed: {evidence_path}"
            )

    current_plan, _before_csv, _after_csv = build_refresh_plan(db_path)
    if _plan_without_output_location(plan) != _plan_without_output_location(current_plan):
        raise SalesTruthViewRefreshError(
            "truth-view refresh plan drifted; regenerate and re-review before apply"
        )

    no_op = (
        not plan["changed_schema_objects"]
        and plan["only_before"]["row_count"] == 0
        and plan["only_after"]["row_count"] == 0
        and bool(plan["legacy_truth_view_contract"].get("compatible"))
    )
    if no_op:
        report = {
            "status": "PASS",
            "mode": "APPLY_NOOP_ALREADY_REFRESHED",
            "write_applied": False,
            "db_path": str(db_path),
            "pre_sha256": pre_sha,
            "post_sha256": pre_sha,
            "reviewed_plan_path": str(reviewed_plan_path.resolve()),
            "reviewed_plan_file_sha256": expected_plan_file_sha256,
            "plan_sha256": plan["plan_sha256"],
            "backup_created": False,
            "idempotent": True,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{db_path.stem}.before_truth_view_refresh_{pre_sha[:12]}_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    if sha256_file(backup_path) != pre_sha or _integrity_path(backup_path).lower() != "ok":
        raise SalesTruthViewRefreshError("byte-valid pre-refresh backup verification failed")

    rollback_path = backup_dir / f"ROLLBACK_SALES_TRUTH_VIEW_REFRESH_{stamp}.json"
    rollback: dict[str, Any] = {
        "operation": "RESTORE_PRE_REFRESH_COPIED_DB",
        "status": "PREPARED_BEFORE_TRANSACTION",
        "target_path": str(db_path),
        "target_pre_sha256": pre_sha,
        "target_post_sha256": None,
        "backup_path": str(backup_path),
        "backup_sha256": pre_sha,
        "restore_verified": False,
        "command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(db_path))}",
    }
    _write_json_atomic(rollback_path, rollback)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        locked_tables_before = _table_fingerprints(conn)
        locked_schema_before = _schema_objects(conn)
        locked_rows_before = _selected_rows(conn)
        if locked_tables_before != plan["before_table_fingerprints"]:
            raise SalesTruthViewRefreshError("table fingerprints drifted after write lock")
        if locked_schema_before != plan["before_schema_objects"]:
            raise SalesTruthViewRefreshError("schema objects drifted after write lock")
        if _rows_summary(locked_rows_before) != plan["selected_rows_before"]:
            raise SalesTruthViewRefreshError("selected rows drifted after write lock")

        install_publication_binding_schema(conn)
        ensure_sales_truth_views(conn)
        require_post_refresh_stored_sql(
            conn, pinned_contract=plan["expected_post_truth_view_contract"]
        )
        locked_tables_after = _table_fingerprints(conn)
        locked_schema_after = _schema_objects(conn)
        locked_rows_after = _selected_rows(conn)
        if locked_tables_after != plan["after_table_fingerprints"]:
            raise SalesTruthViewRefreshError("post-refresh table fingerprints differ from plan")
        if locked_schema_after != plan["after_schema_objects"]:
            raise SalesTruthViewRefreshError("post-refresh schema objects differ from plan")
        if _rows_summary(locked_rows_after) != plan["selected_rows_after"]:
            raise SalesTruthViewRefreshError("post-refresh selected rows differ from plan")
        before_counter = _row_counter(locked_rows_before)
        after_counter = _row_counter(locked_rows_after)
        if _rows_summary(_expand(before_counter - after_counter)) != plan["only_before"]:
            raise SalesTruthViewRefreshError("post-refresh only-before delta differs from plan")
        if _rows_summary(_expand(after_counter - before_counter)) != plan["only_after"]:
            raise SalesTruthViewRefreshError("post-refresh only-after delta differs from plan")
        _verify_idempotent_replay_in_transaction(
            conn,
            pinned_contract=plan["expected_post_truth_view_contract"],
            expected_tables=locked_tables_after,
            expected_schema=locked_schema_after,
            expected_rows=locked_rows_after,
        )
        integrity = _integrity_conn(conn)
        if integrity.lower() != "ok":
            raise SalesTruthViewRefreshError(f"post-refresh integrity failed: {integrity}")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        rollback.update(
            {
                "status": "TRANSACTION_ROLLED_BACK",
                "restore_verified": sha256_file(db_path) == pre_sha,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        raise
    finally:
        conn.close()

    try:
        post_contract = _verify_post_commit_state(
            db_path,
            expected_contract=plan["expected_post_truth_view_contract"],
        )
        post_sha = sha256_file(db_path)
        rollback.update(
            {
                "status": "READY",
                "target_post_sha256": post_sha,
                "restore_verified": False,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        report = {
            "status": "PASS",
            "mode": "APPLY",
            "write_applied": True,
            "db_path": str(db_path),
            "pre_sha256": pre_sha,
            "post_sha256": post_sha,
            "reviewed_plan_path": str(reviewed_plan_path.resolve()),
            "reviewed_plan_file_sha256": expected_plan_file_sha256,
            "plan_sha256": plan["plan_sha256"],
            "applier_code_pin": plan["applier_code_pin"],
            "backup_path": str(backup_path),
            "backup_sha256": pre_sha,
            "rollback_path": str(rollback_path),
            "integrity_check": integrity,
            "only_before": plan["only_before"],
            "only_after": plan["only_after"],
            "changed_schema_objects": plan["changed_schema_objects"],
            "preexisting_tables_unchanged": True,
            "idempotent_replay": True,
            "post_truth_view_contract": post_contract,
        }
        _write_json_atomic(report_path, report)
        return report
    except BaseException as exc:
        try:
            restored_sha = _restore_verified_backup(
                db_path=db_path,
                backup_path=backup_path,
                expected_sha256=pre_sha,
            )
        except BaseException as restore_exc:
            rollback.update(
                {
                    "status": "RESTORE_FAILED_AFTER_POST_COMMIT_FAILURE",
                    "failure": f"{type(exc).__name__}: {exc}",
                    "restore_failure": f"{type(restore_exc).__name__}: {restore_exc}",
                }
            )
            try:
                _write_json_atomic(rollback_path, rollback)
            except Exception:
                pass
            raise SalesTruthViewRefreshError(
                "AMBIGUOUS: post-commit failure and verified restore failed; "
                f"use prepared backup {backup_path}"
            ) from restore_exc
        rollback.update(
            {
                "status": "RESTORED_AFTER_POST_COMMIT_FAILURE",
                "failure": f"{type(exc).__name__}: {exc}",
                "target_post_sha256": None,
                "restore_verified": True,
                "restored_sha256": restored_sha,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        report_path.unlink(missing_ok=True)
        raise SalesTruthViewRefreshError(
            "post-commit verification or evidence finalization failed; "
            "copied DB restored to exact preimage"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--reviewed-plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.apply:
            if args.plan is None:
                raise SalesTruthViewRefreshError("--plan is required in plan mode")
            plan = write_plan(
                db_path=args.db,
                plan_path=args.plan,
                evidence_dir=args.evidence_dir,
            )
            output = {
                "status": "PASS",
                "mode": "PLAN",
                "write_applied": False,
                "plan_path": str(args.plan.resolve()),
                "plan_sha256": plan["plan_sha256"],
                "only_before_count": plan["only_before"]["row_count"],
                "only_after_count": plan["only_after"]["row_count"],
            }
        else:
            missing = [
                name
                for name, value in (
                    ("--reviewed-plan", args.reviewed_plan),
                    ("--expected-plan-sha256", args.expected_plan_sha256),
                    ("--expected-pre-sha256", args.expected_pre_sha256),
                    ("--backup-dir", args.backup_dir),
                    ("--report", args.report),
                )
                if not value
            ]
            if missing:
                raise SalesTruthViewRefreshError(
                    "missing required apply arguments: " + ", ".join(missing)
                )
            report = apply_reviewed_plan(
                db_path=args.db,
                reviewed_plan_path=args.reviewed_plan,
                expected_plan_file_sha256=str(args.expected_plan_sha256),
                expected_pre_sha256=str(args.expected_pre_sha256),
                backup_dir=args.backup_dir,
                report_path=args.report,
            )
            output = {
                "status": report["status"],
                "mode": report["mode"],
                "write_applied": report["write_applied"],
                "post_sha256": report["post_sha256"],
                "plan_sha256": report["plan_sha256"],
            }
    except (
        SalesTruthViewRefreshError,
        OSError,
        sqlite3.Error,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
