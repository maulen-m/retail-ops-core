#!/usr/bin/env python3
"""
Reconcile residual INVENTORY_ON_DELIVERY_COST balances for settled orders.

Default: DRY RUN.
Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_db import backup_database  # noqa: E402
from core.integrations.kaspi_order_stage import (  # noqa: E402
    StageCode,
    classify_kaspi_stage_from_db_row,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
PROD_WRITE_ENV_GATE = "ENABLE_CASHFLOW_PROD_WRITE"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        conn.close()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RuntimeError(f"refusing production settlement apply while SQLite sidecars exist: {joined}")


def _is_production_db(db_path: Path) -> bool:
    return db_path.resolve() == DEFAULT_DB.resolve()


def _prepare_settlement_apply_guard(
    db_path: Path,
    *,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, object]:
    if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
        raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")

    production_apply = _is_production_db(db_path)
    metadata: dict[str, object] = {
        "production_apply": production_apply,
        "pre_sha256": _sha256_file(db_path),
    }
    if not production_apply:
        return metadata

    if os.environ.get(PROD_WRITE_ENV_GATE) != "1":
        raise RuntimeError(f"{PROD_WRITE_ENV_GATE}=1 is required for production settlement apply.")
    if not expected_pre_sha256:
        raise RuntimeError("--expected-pre-sha256 is required for production settlement apply.")
    if backup_dir is None:
        raise RuntimeError("--backup-dir is required for production settlement apply.")

    _fail_on_sqlite_sidecars(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise RuntimeError(f"production DB integrity_check failed before settlement apply: {pre_integrity}")
    pre_sha256 = str(metadata["pre_sha256"])
    if pre_sha256 != expected_pre_sha256:
        raise RuntimeError(
            "production DB SHA mismatch before settlement apply: "
            f"expected {expected_pre_sha256}, observed {pre_sha256}"
        )

    backup_path = backup_database(db_path, backup_dir, compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise RuntimeError(f"settlement backup integrity_check failed: {backup_integrity}")
    metadata.update(
        {
            "expected_pre_sha256": expected_pre_sha256,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "pre_integrity_check": pre_integrity,
            "backup_integrity_check": backup_integrity,
        }
    )
    return metadata


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _parse_date_maybe(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return None


def _event_hash(event: dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(event.get("event_date") or ""),
            str(event.get("event_type") or ""),
            str(event.get("account") or ""),
            f"{float(event.get('amount_kzt') or 0.0):.4f}",
            str(event.get("store_code") or ""),
            str(event.get("sku_key") or ""),
            str(event.get("sku_id") or ""),
            str(event.get("ref_type") or ""),
            str(event.get("ref_id") or ""),
            str(event.get("source") or ""),
            str(event.get("notes") or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_settlement_gaps(
    *,
    db_path: Path = DEFAULT_DB,
    since: str | None = None,
    until: str | None = None,
    tolerance_kzt: float = 1.0,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")

    since_date = date.fromisoformat(since) if since else None
    until_date = date.fromisoformat(until) if until else date.today()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi missing")
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing")

        order_cols = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        }
        date_col = next(
            (c for c in ("status_updated_at", "updated_at", "created_at", "order_date") if c in order_cols),
            None,
        )
        if date_col is None:
            date_filter = ""
            params: list[Any] = []
        else:
            date_filter = "AND date(COALESCE(" + date_col + ", '1970-01-01')) <= ?"
            params = [until_date.isoformat()]
            if since_date:
                date_filter += " AND date(COALESCE(" + date_col + ", '1970-01-01')) >= ?"
                params.append(since_date.isoformat())

        if "internal_status" not in order_cols and "status" not in order_cols:
            raise RuntimeError("fact_orders_kaspi status column missing (internal_status/status)")
        has_sku_cols = "sku_key" in order_cols or "sku_id" in order_cols
        if has_sku_cols:
            sku_expr = (
                "CASE WHEN ("
                "(COALESCE(TRIM(sku_key), '') <> '' AND UPPER(TRIM(sku_key)) NOT IN ('CL', 'UNKNOWN')) "
                "OR (COALESCE(TRIM(sku_key), '') = '' "
                "AND COALESCE(TRIM(sku_id), '') <> '' "
                "AND UPPER(TRIM(sku_id)) NOT IN ('CL', 'UNKNOWN'))"
                ") THEN 1 ELSE 0 END"
            )
        else:
            sku_expr = "1"
        rows = conn.execute(
            f"""
            SELECT DISTINCT *,
                {sku_expr} AS has_sku_identity
            FROM fact_orders_kaspi
            WHERE COALESCE(TRIM(order_id), '') <> ''
              {date_filter}
            """,
            tuple(params),
        ).fetchall()

        balances = conn.execute(
            """
            SELECT ref_id AS order_id, COALESCE(sku_id, '') AS sku_id, SUM(amount_kzt) AS balance_kzt
            FROM fact_cashflow_events
            WHERE account = 'INVENTORY_ON_DELIVERY_COST'
              AND ref_type = 'ORDER'
              AND date(event_date) <= ?
            GROUP BY ref_id, COALESCE(sku_id, '')
            """,
            (until_date.isoformat(),),
        ).fetchall()
        balance_map = {
            (str(r["order_id"]), str(r["sku_id"] or "")): float(r["balance_kzt"] or 0.0) for r in balances
        }
        order_balance_map: dict[str, float] = {}
        for row in balances:
            order_id = str(row["order_id"])
            order_balance_map[order_id] = order_balance_map.get(order_id, 0.0) + float(row["balance_kzt"] or 0.0)

        gaps: list[dict[str, Any]] = []
        seen_orders: set[str] = set()
        settled_stages = {
            StageCode.ISSUED_COMPLETED,
            StageCode.CANCELLED,
            StageCode.RETURNED,
        }
        for row in rows:
            order_id = str(row["order_id"])
            if order_id in seen_orders:
                continue
            stage = classify_kaspi_stage_from_db_row(dict(row))
            if stage not in settled_stages:
                continue
            sku_id = str(row["sku_id"] or "")
            has_identity = bool(int(row["has_sku_identity"] or 0))
            if not has_identity:
                continue
            bal = float(order_balance_map.get(order_id, 0.0))
            if abs(bal) <= float(tolerance_kzt):
                continue
            seen_orders.add(order_id)
            event_date = until_date.isoformat()
            if date_col and date_col in row.keys():
                parsed = _parse_date_maybe(row[date_col])
                if parsed:
                    event_date = parsed
            gaps.append(
                {
                    "order_id": order_id,
                    "store_code": row["store_code"],
                    "sku_key": row["sku_key"],
                    "sku_id": sku_id,
                    "status": stage.value,
                    "balance_kzt": round(bal, 2),
                    "event_date": event_date,
                }
            )

        gaps.sort(key=lambda g: (g["event_date"], g["order_id"], g["sku_id"]))
        return gaps
    finally:
        conn.close()


def reconcile_on_delivery_settlement(
    *,
    db_path: Path = DEFAULT_DB,
    since: str | None = None,
    until: str | None = None,
    tolerance_kzt: float = 1.0,
    apply: bool = False,
    run_id: str | None = None,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    gaps = find_settlement_gaps(
        db_path=db_path,
        since=since,
        until=until,
        tolerance_kzt=tolerance_kzt,
    )

    events: list[dict[str, Any]] = []
    run = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    for gap in gaps:
        amount = round(-float(gap["balance_kzt"]), 2)
        event = {
            "event_date": gap["event_date"],
            "event_type": "INVENTORY_SETTLEMENT",
            "account": "INVENTORY_ON_DELIVERY_COST",
            "amount_kzt": amount,
            "store_code": gap["store_code"],
            "sku_key": gap["sku_key"],
            "sku_id": gap["sku_id"],
            "ref_type": "ORDER",
            "ref_id": gap["order_id"],
            "notes": f"Auto settlement for {gap['status']} on-delivery balance",
            "source": "SYSTEM",
            "run_id": run,
        }
        event["event_hash"] = _event_hash(event)
        events.append(event)

    inserted = 0
    apply_metadata: dict[str, object] = {}
    with sqlite3.connect(str(db_path)) as conn:
        if apply:
            apply_metadata = _prepare_settlement_apply_guard(
                db_path,
                expected_pre_sha256=expected_pre_sha256,
                backup_dir=backup_dir,
            )

        existing = set()
        if events:
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(
                        ",".join("?" * len(events))
                    ),
                    [e["event_hash"] for e in events],
                ).fetchall()
            }

        new_events = [e for e in events if e["event_hash"] not in existing]
        if apply:
            for event in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_date"],
                        event["event_type"],
                        event["account"],
                        event["amount_kzt"],
                        event["store_code"],
                        event["sku_key"],
                        event["sku_id"],
                        event["ref_type"],
                        event["ref_id"],
                        event["notes"],
                        event["source"],
                        event["run_id"],
                        event["event_hash"],
                    ),
                )
            conn.commit()
            inserted = len(new_events)

    return {
        "candidates": len(events),
        "inserted": inserted,
        "apply": bool(apply),
        "run_id": run,
        "apply_metadata": apply_metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile on-delivery settlement gaps")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--until", type=str, default=None)
    parser.add_argument("--tolerance-kzt", type=float, default=1.0)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--expected-pre-sha256", type=str, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = reconcile_on_delivery_settlement(
        db_path=args.db,
        since=args.since,
        until=args.until,
        tolerance_kzt=args.tolerance_kzt,
        apply=args.apply,
        run_id=args.run_id,
        expected_pre_sha256=args.expected_pre_sha256,
        backup_dir=args.backup_dir,
    )
    print(f"candidates={result['candidates']}")
    print(f"inserted={result['inserted']}")
    metadata = result.get("apply_metadata") or {}
    if metadata.get("production_apply") is not None:
        print(f"production_apply={metadata.get('production_apply')}")
    if metadata.get("backup_path"):
        print(f"backup_path={metadata['backup_path']}")
    print("APPLY" if args.apply else "DRY RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
