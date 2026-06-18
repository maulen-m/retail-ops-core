#!/usr/bin/env python3
"""Publish the G-CASH-04 liquidation-proceeds redeployment discipline report."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "redeployment_discipline.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_cash04_redeployment_discipline"

LEDGER_COLUMNS = [
    "ledger_id",
    "tranche_id",
    "owner_decision_id",
    "proceeds_event_ref",
    "proceeds_amount_kzt",
    "proceeds_received_date",
    "redeployment_decision",
    "redeployment_amount_kzt",
    "redeployment_ref",
    "gate_snapshot",
    "allowed",
    "notes",
]

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).strip() or "0")
    except ValueError:
        return 0.0


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "allowed"}


def _ident(value: str) -> str:
    text = str(value or "").strip()
    if not IDENT_RE.match(text):
        raise ValueError(f"invalid SQL identifier: {value!r}")
    return text


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _count_rows(conn: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(conn, table):
        return None
    table_name = _ident(table)
    return int(conn.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}").fetchone()["cnt"])


def _load_scoreboard(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            status = str(row.get("status") or row.get("state") or "").strip().upper()
            if gate_id and status:
                states[gate_id] = status
    return states


def _load_dashboard_gate_states(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    match = re.search(r"window\.GP\s*=\s*(\{.*\});\s*$", text, re.S)
    if not match:
        return {}
    payload = json.loads(match.group(1))
    states: dict[str, str] = {}
    for row in payload.get("gates", []):
        gate_id = str(row.get("id") or "").strip()
        status = str(row.get("status") or "").strip().upper()
        if gate_id and status:
            states[gate_id] = status
    return states


def _load_ledger(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], [f"ledger_missing:{path}"]
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [{key: str(value or "") for key, value in row.items()} for row in reader]
    missing = [column for column in LEDGER_COLUMNS if column not in fieldnames]
    blockers = [f"ledger_missing_columns:{','.join(missing)}"] if missing else []
    return rows, blockers


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _cashflow_search_count(
    conn: sqlite3.Connection,
    *,
    effective_date: str,
    search_terms: list[str],
) -> int | None:
    if not _table_exists(conn, "fact_cashflow_events"):
        return None
    if not search_terms:
        return 0
    haystack = """
        lower(
            coalesce(event_type, '') || ' ' ||
            coalesce(ref_type, '') || ' ' ||
            coalesce(ref_id, '') || ' ' ||
            coalesce(notes, '') || ' ' ||
            coalesce(source, '')
        )
    """
    where_terms = " OR ".join([f"{haystack} LIKE ?" for _ in search_terms])
    params = [f"%{term.lower()}%" for term in search_terms]
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS cnt
        FROM fact_cashflow_events
        WHERE date(event_date) >= date(?)
          AND ({where_terms})
        """,
        [effective_date, *params],
    ).fetchone()
    return int(row["cnt"] or 0)


def _po_commitment_count(
    conn: sqlite3.Connection,
    *,
    effective_date: str,
    commitment_types: list[str],
) -> tuple[int | None, float]:
    if not _table_exists(conn, "fact_cashflow_commitments"):
        return None, 0.0
    if not commitment_types:
        return 0, 0.0
    placeholders = ",".join("?" for _ in commitment_types)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_kzt), 0) AS amount_kzt
        FROM fact_cashflow_commitments
        WHERE date(commit_date) >= date(?)
          AND commit_type IN ({placeholders})
        """,
        [effective_date, *commitment_types],
    ).fetchone()
    return int(row["cnt"] or 0), float(row["amount_kzt"] or 0)


def _build_ledger_review(
    rows: list[dict[str, str]],
    *,
    redeployment_allowed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    review_rows: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        amount = _as_float(row.get("redeployment_amount_kzt"))
        allowed_flag = _truthy(row.get("allowed"))
        decision = str(row.get("redeployment_decision") or "").strip() or "UNSPECIFIED"
        row_id = str(row.get("ledger_id") or f"row-{index}")
        violation_reasons: list[str] = []
        if amount > 0 and not redeployment_allowed:
            violation_reasons.append("redeployment_amount_positive_while_required_gates_not_green")
        if amount > 0 and not allowed_flag:
            violation_reasons.append("ledger_allowed_flag_not_true_for_positive_redeployment")
        status = "VIOLATION" if violation_reasons else "OK"
        review = {
            "ledger_id": row_id,
            "tranche_id": row.get("tranche_id", ""),
            "owner_decision_id": row.get("owner_decision_id", ""),
            "redeployment_decision": decision,
            "redeployment_amount_kzt": amount,
            "allowed": allowed_flag,
            "status": status,
            "violation_reasons": ";".join(violation_reasons),
        }
        review_rows.append(review)
        if violation_reasons:
            violations.append(review)
    return review_rows, violations


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-CASH-04 Redeployment Discipline Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Redeployment allowed: {report['redeployment_allowed']}",
        "",
        "## Gate Stack",
        "",
        f"- Liquidation execution gate: {report['liquidation_gate']}={report['liquidation_gate_status']}",
    ]
    for gate_id, status in report["required_gate_statuses"].items():
        lines.append(f"- {gate_id}: {status}")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Ledger rows: {report['proceeds_ledger_rows']}",
            f"- Ungated redeployments: {report['ungated_redeployment_count']}",
            f"- Cashflow liquidation/proceeds text hits after effective date: {report['db_probes']['cashflow_liquidation_text_hits_after_effective']}",
            f"- PO drafts: {report['db_probes']['fact_po_draft_rows']}",
            f"- PO executions: {report['db_probes']['fact_po_execution_rows']}",
            f"- PO payment commitments after effective date: {report['db_probes']['po_payment_commitments_after_effective_count']}",
            "",
            "## Blockers",
            "",
        ]
    )
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Violations", ""])
    if report["ungated_redeployments"]:
        for row in report["ungated_redeployments"]:
            lines.append(f"- {row['ledger_id']}: {row['violation_reasons']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_redeployment_discipline_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    config = _load_json(config_path)
    db_path = _resolve_path(config["db_path"])
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    ledger_path = _resolve_path(config["ledger_path"])
    effective_at = str(config["effective_at"])
    effective_date = effective_at[:10]
    liquidation_gate = str(config["liquidation_execution_gate"])
    required_gates = [str(value) for value in config.get("required_green_before_redeployment", [])]
    search_terms = [str(value) for value in config.get("search_terms", [])]
    commitment_types = [str(value) for value in config.get("po_commitment_types", [])]

    generated_at = _now_almaty()
    run_id = generated_at.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    scoreboard_states = _load_dashboard_gate_states(dashboard_path)
    scoreboard_states.update(_load_scoreboard(scoreboard_path))
    ledger_rows, ledger_blockers = _load_ledger(ledger_path)
    liquidation_status = scoreboard_states.get(liquidation_gate, "MISSING")
    required_statuses = {gate_id: scoreboard_states.get(gate_id, "MISSING") for gate_id in required_gates}
    all_required_green = all(status == "GREEN" for status in required_statuses.values())
    liquidation_green = liquidation_status == "GREEN"
    redeployment_allowed = liquidation_green and all_required_green

    blockers: list[str] = []
    if not liquidation_green:
        blockers.append(f"liquidation_gate_not_green:{liquidation_gate}={liquidation_status}")
    for gate_id, status in required_statuses.items():
        if status != "GREEN":
            blockers.append(f"required_gate_not_green:{gate_id}={status}")
    blockers.extend(ledger_blockers)

    ledger_review, ledger_violations = _build_ledger_review(
        ledger_rows,
        redeployment_allowed=redeployment_allowed,
    )

    with _connect_ro(db_path) as conn:
        cashflow_hits = _cashflow_search_count(
            conn,
            effective_date=effective_date,
            search_terms=search_terms,
        )
        po_commitment_count, po_commitment_amount = _po_commitment_count(
            conn,
            effective_date=effective_date,
            commitment_types=commitment_types,
        )
        db_probes = {
            "db_path": str(db_path),
            "db_open_mode": "ro",
            "cashflow_liquidation_text_hits_after_effective": cashflow_hits,
            "fact_po_draft_rows": _count_rows(conn, "fact_po_draft"),
            "fact_po_execution_rows": _count_rows(conn, "fact_po_execution"),
            "fact_po_lines_rows": _count_rows(conn, "fact_po_lines"),
            "fact_cash_ledger_rows": _count_rows(conn, "fact_cash_ledger"),
            "po_payment_commitments_after_effective_count": po_commitment_count,
            "po_payment_commitments_after_effective_amount_kzt": round(po_commitment_amount, 2),
        }

    runtime_violations: list[str] = []
    if not redeployment_allowed:
        if (db_probes["fact_po_draft_rows"] or 0) > 0:
            runtime_violations.append("fact_po_draft_rows_positive_while_redeployment_not_allowed")
        if (db_probes["fact_po_execution_rows"] or 0) > 0:
            runtime_violations.append("fact_po_execution_rows_positive_while_redeployment_not_allowed")
        if (db_probes["po_payment_commitments_after_effective_count"] or 0) > 0:
            runtime_violations.append("po_payment_commitments_after_effective_while_redeployment_not_allowed")

    proceeds_rows = sum(
        1
        for row in ledger_rows
        if _as_float(row.get("proceeds_amount_kzt")) > 0 or str(row.get("proceeds_event_ref") or "").strip()
    )

    if ledger_violations or runtime_violations:
        gate = "RED"
    elif redeployment_allowed and proceeds_rows > 0 and not blockers:
        gate = "GREEN"
    else:
        gate = "ARMED"

    if redeployment_allowed and proceeds_rows == 0:
        blockers.append("no_proceeds_ledger_review_rows_yet")

    ledger_review_path = out_dir / "redeployment_ledger_review.csv"
    _write_csv(
        ledger_review_path,
        ledger_review,
        [
            "ledger_id",
            "tranche_id",
            "owner_decision_id",
            "redeployment_decision",
            "redeployment_amount_kzt",
            "allowed",
            "status",
            "violation_reasons",
        ],
    )

    report: dict[str, Any] = {
        "contract_id": config.get("contract_id"),
        "gate_id": config.get("gate_id", "G-CASH-04"),
        "gate": gate,
        "generated_at": generated_at,
        "effective_at": effective_at,
        "config_path": str(config_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "ledger_path": str(ledger_path),
        "liquidation_gate": liquidation_gate,
        "liquidation_gate_status": liquidation_status,
        "required_gate_statuses": required_statuses,
        "redeployment_allowed": redeployment_allowed,
        "proceeds_ledger_rows": proceeds_rows,
        "ledger_review_rows": len(ledger_review),
        "ungated_redeployment_count": len(ledger_violations),
        "ungated_redeployments": ledger_violations,
        "runtime_guard_violations": runtime_violations,
        "blockers": blockers,
        "db_probes": db_probes,
        "ledger_review_csv": str(ledger_review_path),
    }
    json_path = out_dir / "redeployment_discipline_report.json"
    md_path = out_dir / "redeployment_discipline_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_redeployment_discipline_report(
        config_path=args.config,
        output_root=args.output_root,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
