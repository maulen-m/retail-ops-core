#!/usr/bin/env python3
"""Repair stale delivered sales rows from same-store lifecycle evidence.

Dry-run is the default. Apply requires ENABLE_SALES_FACT_V2_LIFECYCLE_REPAIR=1.
Production DB apply also requires ALLOW_PRODUCTION_SALES_FACT_V2_LIFECYCLE_REPAIR=1.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from scripts.backup_db import backup_database

ENV_GATE = "ENABLE_SALES_FACT_V2_LIFECYCLE_REPAIR"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_SALES_FACT_V2_LIFECYCLE_REPAIR"

DELIVERED_SALES_STATUSES = {"COMPLETED", "DELIVERED", "SOLD"}
COMPLETED_STAGES = {"COMPLETED", "DELIVERED"}
CANCELLED_STAGES = {"CANCELLED"}
RETURNED_STAGES = {"RETURNED", "RETURN", "REFUND", "CANCELLED_AFTER_DELIVERY", "CANCELLED_DELIVERED"}
TERMINAL_STAGES = CANCELLED_STAGES | RETURNED_STAGES


@dataclass(frozen=True)
class LifecycleRepairPlan:
    summary: dict[str, Any]
    repair_rows: list[dict[str, Any]]
    blocked_rows: list[dict[str, Any]]
    conflict_rows: list[dict[str, Any]]

    @property
    def is_safe_to_apply(self) -> bool:
        return bool(self.repair_rows)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


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
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _date_part(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text else None


def _hash_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _store_clause(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"UPPER(COALESCE({prefix}store_code, 'UNIVERSAL'))"


def _sales_where(conn: sqlite3.Connection, *, alias: str = "", as_of: str | None = None) -> str:
    prefix = f"{alias}." if alias else ""
    cols = _columns(conn, "sales_fact_v2")
    delivered = ",".join(repr(status) for status in sorted(DELIVERED_SALES_STATUSES))
    clauses = [f"UPPER(COALESCE({prefix}status, '')) IN ({delivered})"]
    if "return_flag" in cols:
        clauses.append(f"COALESCE({prefix}return_flag, 0) = 0")
    if as_of and "order_date" in cols:
        clauses.append(f"date({prefix}order_date) <= date('{as_of}')")
    return " AND ".join(clauses)


def _candidate_rows(conn: sqlite3.Connection, *, as_of: str | None) -> list[sqlite3.Row]:
    where = _sales_where(conn, alias="sf", as_of=as_of)
    completed = ",".join(repr(stage) for stage in sorted(COMPLETED_STAGES))
    completed_pairs = {
        (_upper(row["store_code"]) or "UNIVERSAL", str(row["order_id"] or "").strip())
        for row in conn.execute(
            f"""
            SELECT store_code, order_id
            FROM order_status_event
            WHERE UPPER(COALESCE(stage_code, '')) IN ({completed})
            """
        ).fetchall()
        if str(row["order_id"] or "").strip()
    }
    rows = conn.execute(
        f"""
        SELECT
            sf.rowid AS row_id,
            sf.order_id,
            COALESCE(sf.store_code, 'UNIVERSAL') AS store_code,
            sf.order_date,
            sf.sku_key,
            sf.sku_id,
            sf.status AS old_status,
            COALESCE(sf.return_flag, 0) AS old_return_flag,
            sf.return_date AS old_return_date,
            sf.source_file
        FROM sales_fact_v2 sf
        WHERE {where}
        ORDER BY sf.rowid
        """
    ).fetchall()
    return [
        row
        for row in rows
        if (
            _upper(row["store_code"]) or "UNIVERSAL",
            str(row["order_id"] or "").strip(),
        )
        not in completed_pairs
    ]


def _event_evidence(conn: sqlite3.Connection, *, order_id: str, store_code: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "order_status_event"):
        return None
    terminal = ",".join(repr(stage) for stage in sorted(TERMINAL_STAGES))
    row = conn.execute(
        f"""
        SELECT
            event_id AS source_row_id,
            stage_code,
            event_ts,
            source,
            raw_status,
            source_row_hash
        FROM order_status_event
        WHERE order_id = ?
          AND {_store_clause()} = UPPER(?)
          AND UPPER(COALESCE(stage_code, '')) IN ({terminal})
        ORDER BY datetime(event_ts) DESC, event_id DESC
        LIMIT 1
        """,
        (order_id, store_code),
    ).fetchone()
    if row is None:
        return None
    stage_code = _upper(row["stage_code"])
    return {
        "source_table": "order_status_event",
        "source_row_id": row["source_row_id"],
        "stage_code": stage_code,
        "event_ts": row["event_ts"],
        "source": row["source"],
        "raw_status": row["raw_status"],
        "source_row_hash": row["source_row_hash"],
    }


def _orders_evidence(conn: sqlite3.Connection, *, order_id: str, store_code: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "fact_orders_kaspi"):
        return None
    cols = _columns(conn, "fact_orders_kaspi")
    wanted = [
        "id",
        "internal_status",
        "kaspi_status",
        "kaspi_status_detail",
        "status_updated_at",
        "updated_at",
        "imported_at",
        "created_at",
    ]
    select_cols = [col for col in wanted if col in cols]
    if not select_cols:
        return None
    row = conn.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM fact_orders_kaspi
        WHERE order_id = ?
          AND {_store_clause()} = UPPER(?)
        ORDER BY datetime(COALESCE(status_updated_at, updated_at, imported_at, created_at)) DESC,
                 id DESC
        LIMIT 1
        """,
        (order_id, store_code),
    ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    status_text = " ".join(
        _upper(payload.get(key))
        for key in ("internal_status", "kaspi_status", "kaspi_status_detail")
        if payload.get(key) is not None
    )
    if "RETURN" in status_text:
        stage_code = "RETURNED"
    elif "CANCEL" in status_text:
        stage_code = "CANCELLED"
    else:
        return None
    event_ts = (
        payload.get("status_updated_at")
        or payload.get("updated_at")
        or payload.get("imported_at")
        or payload.get("created_at")
    )
    return {
        "source_table": "fact_orders_kaspi",
        "source_row_id": payload.get("id"),
        "stage_code": stage_code,
        "event_ts": event_ts,
        "source": "fact_orders_kaspi",
        "raw_status": status_text,
        "source_row_hash": _hash_json({"source_table": "fact_orders_kaspi", **payload}),
    }


def _observation_evidence(conn: sqlite3.Connection, *, order_id: str, store_code: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "fact_order_status_observations"):
        return None
    row = conn.execute(
        f"""
        SELECT id, status_internal, observed_at, source, ledger_run_id, source_detail
        FROM fact_order_status_observations
        WHERE order_id = ?
          AND {_store_clause()} = UPPER(?)
        ORDER BY datetime(observed_at) DESC, id DESC
        LIMIT 1
        """,
        (order_id, store_code),
    ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    status = _upper(payload.get("status_internal"))
    if status in CANCELLED_STAGES:
        stage_code = "CANCELLED"
    elif status in RETURNED_STAGES:
        stage_code = "RETURNED"
    else:
        return None
    return {
        "source_table": "fact_order_status_observations",
        "source_row_id": payload.get("id"),
        "stage_code": stage_code,
        "event_ts": payload.get("observed_at"),
        "source": payload.get("source"),
        "raw_status": payload.get("status_internal"),
        "source_row_hash": _hash_json({"source_table": "fact_order_status_observations", **payload}),
    }


def _terminal_evidence(conn: sqlite3.Connection, *, order_id: str, store_code: str) -> dict[str, Any] | None:
    sources = [
        _event_evidence(conn, order_id=order_id, store_code=store_code),
        _orders_evidence(conn, order_id=order_id, store_code=store_code),
        _observation_evidence(conn, order_id=order_id, store_code=store_code),
    ]
    candidates = [source for source in sources if source is not None]
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: str(row.get("event_ts") or ""), reverse=True)[0]


def _latest_same_store_stage(conn: sqlite3.Connection, *, order_id: str, store_code: str) -> str | None:
    if not _table_exists(conn, "order_status_event"):
        return None
    row = conn.execute(
        f"""
        SELECT stage_code
        FROM order_status_event
        WHERE order_id = ?
          AND {_store_clause()} = UPPER(?)
        ORDER BY datetime(event_ts) DESC, event_id DESC
        LIMIT 1
        """,
        (order_id, store_code),
    ).fetchone()
    return _upper(row["stage_code"]) if row else None


def _other_store_completed_count(conn: sqlite3.Connection, *, order_id: str, store_code: str) -> int:
    if not _table_exists(conn, "order_status_event"):
        return 0
    completed = ",".join(repr(stage) for stage in sorted(COMPLETED_STAGES))
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM order_status_event
            WHERE order_id = ?
              AND {_store_clause()} <> UPPER(?)
              AND UPPER(COALESCE(stage_code, '')) IN ({completed})
            """,
            (order_id, store_code),
        ).fetchone()[0]
        or 0
    )


def build_lifecycle_repair_plan(
    conn: sqlite3.Connection,
    *,
    as_of: str,
    run_id: str,
) -> LifecycleRepairPlan:
    candidates = _candidate_rows(conn, as_of=as_of)
    repair_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []

    for row in candidates:
        order_id = str(row["order_id"] or "").strip()
        store_code = str(row["store_code"] or "UNIVERSAL").strip().upper()
        evidence = _terminal_evidence(conn, order_id=order_id, store_code=store_code)
        latest_stage = _latest_same_store_stage(conn, order_id=order_id, store_code=store_code)
        other_completed = _other_store_completed_count(conn, order_id=order_id, store_code=store_code)
        base = {
            "row_id": row["row_id"],
            "order_id": order_id,
            "store_code": store_code,
            "order_date": row["order_date"],
            "sku_key": row["sku_key"],
            "sku_id": row["sku_id"],
            "old_status": row["old_status"],
            "old_return_flag": row["old_return_flag"],
            "old_return_date": row["old_return_date"],
            "source_file": row["source_file"],
            "latest_same_store_stage": latest_stage,
            "other_store_completed_stage_count": other_completed,
            "run_id": run_id,
        }
        if other_completed:
            conflict_rows.append(
                {
                    **base,
                    "same_store_stage_code": latest_stage,
                    "other_store_completed_stage_count": other_completed,
                }
            )
        if evidence is None:
            blocked_rows.append({**base, "block_reason": "NO_SAME_STORE_TERMINAL_SOURCE_EVIDENCE"})
            continue
        stage_code = _upper(evidence["stage_code"])
        if stage_code in RETURNED_STAGES:
            new_status = "RETURNED"
            new_return_flag = 1
            new_return_date = _date_part(evidence.get("event_ts"))
        elif stage_code in CANCELLED_STAGES:
            new_status = "CANCELLED"
            new_return_flag = 0
            new_return_date = None
        else:
            blocked_rows.append({**base, "block_reason": f"UNSUPPORTED_STAGE_{stage_code}"})
            continue
        repair_rows.append(
            {
                **base,
                "new_status": new_status,
                "new_return_flag": new_return_flag,
                "new_return_date": new_return_date,
                "source_table": evidence.get("source_table"),
                "source_row_id": evidence.get("source_row_id"),
                "source_stage_code": stage_code,
                "source_event_ts": evidence.get("event_ts"),
                "source": evidence.get("source"),
                "source_raw_status": evidence.get("raw_status"),
                "source_row_hash": evidence.get("source_row_hash"),
            }
        )

    by_status: dict[str, int] = {}
    for row in repair_rows:
        by_status[row["new_status"]] = by_status.get(row["new_status"], 0) + 1
    summary = {
        "run_id": run_id,
        "as_of": as_of,
        "candidate_count": len(candidates),
        "repairable_count": len(repair_rows),
        "blocked_count": len(blocked_rows),
        "store_conflict_count": len(conflict_rows),
        "repair_status_counts": by_status,
    }
    return LifecycleRepairPlan(
        summary=summary,
        repair_rows=repair_rows,
        blocked_rows=blocked_rows,
        conflict_rows=conflict_rows,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _assert_apply_allowed(db_path: Path, *, env_gate_value: str | None) -> None:
    value = env_gate_value if env_gate_value is not None else os.environ.get(ENV_GATE)
    if value != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for apply")
    if db_path.resolve() == DEFAULT_DB_PATH.resolve() and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise RuntimeError(f"{PRODUCTION_ENV_GATE}=1 is required for production DB apply")


def repair_sales_fact_v2_lifecycle_residual(
    *,
    db_path: Path,
    as_of: str,
    run_id: str,
    output_root: Path,
    apply: bool = False,
    env_gate_value: str | None = None,
) -> dict[str, Any]:
    backup_path: Path | None = None
    if apply:
        _assert_apply_allowed(db_path, env_gate_value=env_gate_value)
        backup_path = backup_database(db_path, output_root / "backups", compress=False)

    with _connect(db_path) as conn:
        plan = build_lifecycle_repair_plan(conn, as_of=as_of, run_id=run_id)
        applied_count = 0
        if apply:
            for row in plan.repair_rows:
                cursor = conn.execute(
                    """
                    UPDATE sales_fact_v2
                    SET status = ?,
                        return_flag = ?,
                        return_date = ?
                    WHERE rowid = ?
                    """,
                    (
                        row["new_status"],
                        row["new_return_flag"],
                        row["new_return_date"],
                        row["row_id"],
                    ),
                )
                applied_count += max(cursor.rowcount, 0)
            conn.commit()

    summary = {**plan.summary, "applied": apply, "applied_count": applied_count}
    payload = {
        "summary": summary,
        "db_path": str(db_path),
        "backup_path": str(backup_path) if backup_path else None,
        "outputs": {
            "repair_ledger_csv": str(output_root / "lifecycle_repair_ledger.csv"),
            "blocked_ledger_csv": str(output_root / "lifecycle_repair_blocked.csv"),
            "store_conflicts_csv": str(output_root / "lifecycle_repair_store_conflicts.csv"),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "lifecycle_repair_summary.json", payload)
    _write_csv(output_root / "lifecycle_repair_ledger.csv", plan.repair_rows)
    _write_csv(output_root / "lifecycle_repair_blocked.csv", plan.blocked_rows)
    _write_csv(output_root / "lifecycle_repair_store_conflicts.csv", plan.conflict_rows)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair sales_fact_v2 lifecycle residual from source evidence")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = repair_sales_fact_v2_lifecycle_residual(
            db_path=args.db,
            as_of=args.as_of,
            run_id=args.run_id,
            output_root=args.output_root,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
