#!/usr/bin/env python3
"""Materialize exact negative-ledger active-zero exceptions and owner repair queue."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NEGATIVE_LEDGER_EXCEPTION_ENV_GATE = "ENABLE_NEGATIVE_LEDGER_EXCEPTION_WRITE"
EXACT_BUCKET = "exact_owner_approved_active_zero_quarantine"
WEAK_BUCKET = "weak_family_overlap_not_auto_clearable"
UNRESOLVED_BUCKET = "unresolved_no_owner_policy_overlap"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_token(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text[:120] or "UNKNOWN"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _read_queue(source_csv: Path) -> list[dict[str, str]]:
    with source_csv.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _exception_row(
    row: dict[str, str],
    *,
    source_csv: Path,
    run_id: str,
    as_of: str,
) -> dict[str, Any] | None:
    bucket = str(row.get("action_bucket") or "").strip()
    if bucket not in {EXACT_BUCKET, WEAK_BUCKET, UNRESOLVED_BUCKET}:
        return None

    sku_id = str(row.get("sku_id") or "").strip()
    store_code = str(row.get("store_code") or "UNIVERSAL").strip().upper() or "UNIVERSAL"
    if not sku_id:
        return None

    if bucket == EXACT_BUCKET:
        prefix = "AGENT30_NEGATIVE_LEDGER_EXACT_ACTIVE_ZERO_QUARANTINE"
        reason = (
            "NEGATIVE_LEDGER_EXACT_OWNER_ACTIVE_ZERO_QUARANTINE: "
            f"{row.get('owner_policy_overlap') or 'owner_policy_overlap'}"
        )
        recommended_action = (
            "Accepted exact owner active-zero/quarantine control: keep active sellable stock at zero; "
            "do not clamp source ledger; wait for QC or owner superseding evidence."
        )
        policy_path = "stock_authority.quarantined_returns_and_cancels_are_active_stock"
    else:
        prefix = "AGENT30_NEGATIVE_LEDGER_OWNER_REPAIR_REQUIRED"
        reason = f"NEGATIVE_LEDGER_OWNER_REPAIR_REQUIRED: {bucket}"
        recommended_action = (
            row.get("recommended_next_action")
            or "Owner/ops repair source ledger or verify physical/QC evidence before publication."
        )
        policy_path = "stock_authority.negative_active_stock_action"

    exception_id = f"{prefix}:{_safe_token(store_code)}:{_safe_token(sku_id)}"
    evidence = {
        "as_of": as_of,
        "source_csv": str(source_csv),
        "sku_id": sku_id,
        "store_code": store_code,
        "ledger_balance_morning_2026_05_04": row.get("ledger_balance_morning_2026_05_04"),
        "owner_policy_overlap": row.get("owner_policy_overlap"),
        "action_bucket": bucket,
        "overlap_basis": row.get("overlap_basis"),
        "recent_events_before_2026_05_04": row.get("recent_events_before_2026_05_04"),
    }
    return {
        "exception_id": exception_id,
        "run_id": run_id,
        "domain": "STOCK",
        "severity": "HIGH",
        "status": "OPEN",
        "reason": reason,
        "evidence_json": _json(evidence),
        "owner": "business_owner",
        "recommended_action": recommended_action,
        "evidence_paths_json": _json([str(source_csv)]),
        "policy_path": policy_path,
        "policy_source_id": "src_ab_db_operational_truth",
        "due_at": f"{as_of}T23:59:59+05:00",
        "updated_at": _now_iso(),
    }


def _upsert_exception_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    applied = 0
    for row in rows:
        cursor = conn.execute(
            """
            INSERT INTO exception_queue (
                exception_id, run_id, domain, severity, status, reason,
                evidence_json, owner, recommended_action, evidence_paths_json,
                policy_path, policy_source_id, due_at, updated_at
            ) VALUES (
                :exception_id, :run_id, :domain, :severity, :status, :reason,
                :evidence_json, :owner, :recommended_action, :evidence_paths_json,
                :policy_path, :policy_source_id, :due_at, :updated_at
            )
            ON CONFLICT(exception_id) DO UPDATE SET
                run_id=excluded.run_id,
                domain=excluded.domain,
                severity=excluded.severity,
                status=excluded.status,
                reason=excluded.reason,
                evidence_json=excluded.evidence_json,
                owner=excluded.owner,
                recommended_action=excluded.recommended_action,
                evidence_paths_json=excluded.evidence_paths_json,
                policy_path=excluded.policy_path,
                policy_source_id=excluded.policy_source_id,
                due_at=excluded.due_at,
                updated_at=excluded.updated_at
            """,
            row,
        )
        applied += max(cursor.rowcount, 0)
    return applied


def materialize_negative_ledger_exceptions(
    *,
    db_path: Path,
    source_csv: Path,
    output_root: Path,
    as_of: str,
    run_id: str,
    apply: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if not source_csv.exists():
        raise FileNotFoundError(f"source CSV not found: {source_csv}")

    queue_rows = _read_queue(source_csv)
    exception_rows = [
        item
        for item in (
            _exception_row(row, source_csv=source_csv, run_id=run_id, as_of=as_of)
            for row in queue_rows
        )
        if item is not None
    ]
    counts = {
        "exact_owner_approved_active_zero_quarantine": sum(
            1 for row in queue_rows if row.get("action_bucket") == EXACT_BUCKET
        ),
        "weak_family_overlap_not_auto_clearable": sum(
            1 for row in queue_rows if row.get("action_bucket") == WEAK_BUCKET
        ),
        "unresolved_no_owner_policy_overlap": sum(
            1 for row in queue_rows if row.get("action_bucket") == UNRESOLVED_BUCKET
        ),
    }
    applied_rows = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "exception_queue"):
            raise RuntimeError("exception_queue table missing")
        if apply:
            if os.environ.get(NEGATIVE_LEDGER_EXCEPTION_ENV_GATE) != "1":
                raise RuntimeError(
                    f"{NEGATIVE_LEDGER_EXCEPTION_ENV_GATE}=1 is required for --apply"
                )
            applied_rows = _upsert_exception_rows(conn, exception_rows)
            conn.commit()

    summary = {
        "applied": apply,
        "db_path": str(db_path),
        "source_csv": str(source_csv),
        "as_of": as_of,
        "run_id": run_id,
        "input_row_count": len(queue_rows),
        "exception_row_count": len(exception_rows),
        "applied_rows": applied_rows,
        "counts": counts,
        "exact_exception_ids": [
            row["exception_id"]
            for row in exception_rows
            if row["exception_id"].startswith("AGENT30_NEGATIVE_LEDGER_EXACT")
        ],
        "owner_repair_exception_ids": [
            row["exception_id"]
            for row in exception_rows
            if row["exception_id"].startswith("AGENT30_NEGATIVE_LEDGER_OWNER_REPAIR")
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "negative_ledger_exception_materialization_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "negative_ledger_exception_rows.json").write_text(
        json.dumps(exception_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = materialize_negative_ledger_exceptions(
        db_path=args.db,
        source_csv=args.source_csv,
        output_root=args.output_root,
        as_of=args.as_of,
        run_id=args.run_id,
        apply=bool(args.apply),
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"applied={summary['applied']}")
        print(f"exception_row_count={summary['exception_row_count']}")
        print(f"applied_rows={summary['applied_rows']}")
        print(f"counts={summary['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
