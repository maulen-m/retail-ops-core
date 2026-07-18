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
    pre_sha256 = str(metadata["pre_sha256"])
    if expected_pre_sha256 and pre_sha256 != expected_pre_sha256:
        raise RuntimeError(
            "DB SHA mismatch before settlement apply: "
            f"expected {expected_pre_sha256}, observed {pre_sha256}"
        )
    if not production_apply:
        if expected_pre_sha256:
            metadata["expected_pre_sha256"] = expected_pre_sha256
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


def _normalize_order_id_allowlist(order_ids: set[str] | None) -> set[str] | None:
    if order_ids is None:
        return None
    normalized = {str(value).strip() for value in order_ids if str(value).strip()}
    if not normalized:
        raise RuntimeError("order-id allowlist is empty")
    return normalized


def _read_order_id_file(path: Path) -> set[str]:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"order-id file not found: {path}")
    return _normalize_order_id_allowlist(set(path.read_text(encoding="utf-8").splitlines())) or set()


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
    order_id_allowlist: set[str] | None = None,
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

        status_col = "internal_status" if "internal_status" in order_cols else "status"
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
        status_date_expr = f"{date_col} AS status_date_source" if date_col else "NULL AS status_date_source"
        rows = conn.execute(
            f"""
            SELECT DISTINCT
                order_id,
                store_code,
                sku_key,
                sku_id,
                UPPER(TRIM(COALESCE({status_col}, ''))) AS status,
                {sku_expr} AS has_sku_identity,
                {status_date_expr}
            FROM fact_orders_kaspi
            WHERE COALESCE(TRIM(order_id), '') <> ''
              AND UPPER(TRIM(COALESCE({status_col}, ''))) IN ('COMPLETED', 'CANCELLED', 'RETURNED')
              {date_filter}
            ORDER BY datetime(COALESCE(status_date_source, '1970-01-01')) DESC,
                     order_id,
                     sku_id
            """,
            tuple(params),
        ).fetchall()
        order_allowlist = _normalize_order_id_allowlist(order_id_allowlist)
        if order_allowlist is not None:
            rows = [row for row in rows if str(row["order_id"] or "").strip() in order_allowlist]

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
        for row in rows:
            order_id = str(row["order_id"])
            if order_id in seen_orders:
                continue
            sku_id = str(row["sku_id"] or "")
            has_identity = bool(int(row["has_sku_identity"] or 0))
            if not has_identity:
                continue
            bal = float(order_balance_map.get(order_id, 0.0))
            if abs(bal) <= float(tolerance_kzt):
                continue
            seen_orders.add(order_id)
            parsed = _parse_date_maybe(row["status_date_source"])
            if not parsed:
                raise RuntimeError(
                    f"{order_id}: missing or invalid terminal status timestamp from "
                    f"{date_col or 'no_supported_date_column'}"
                )
            event_date = parsed
            gaps.append(
                {
                    "order_id": order_id,
                    "store_code": row["store_code"],
                    "sku_key": row["sku_key"],
                    "sku_id": sku_id,
                    "status": row["status"],
                    "balance_kzt": round(bal, 2),
                    "event_date": event_date,
                    "event_date_source_column": date_col,
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
    order_id_allowlist: set[str] | None = None,
    expected_candidate_count: int | None = None,
) -> dict[str, Any]:
    order_allowlist = _normalize_order_id_allowlist(order_id_allowlist)
    if apply:
        if order_allowlist is None:
            raise RuntimeError("--order-id-file is required for settlement apply")
        if expected_candidate_count is None:
            raise RuntimeError("--expected-candidate-count is required for settlement apply")
        if not expected_pre_sha256:
            raise RuntimeError("--expected-pre-sha256 is required for every settlement apply")
        if int(expected_candidate_count) != len(order_allowlist):
            raise RuntimeError(
                "settlement allowlist/count mismatch: "
                f"allowlist={len(order_allowlist)} expected={int(expected_candidate_count)}"
            )
    gaps = find_settlement_gaps(
        db_path=db_path,
        since=since,
        until=until,
        tolerance_kzt=tolerance_kzt,
        order_id_allowlist=order_allowlist,
    )

    if expected_candidate_count is not None:
        if int(expected_candidate_count) < 0:
            raise RuntimeError("expected candidate count must be nonnegative")
        if len(gaps) != int(expected_candidate_count):
            raise RuntimeError(
                "settlement candidate count mismatch: "
                f"expected {int(expected_candidate_count)}, observed {len(gaps)}"
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
            if len(new_events) != int(expected_candidate_count):
                raise RuntimeError(
                    "new settlement event count mismatch: "
                    f"expected {int(expected_candidate_count)}, observed {len(new_events)}"
                )
            for event in new_events:
                cur = conn.execute(
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
                inserted += int(cur.rowcount or 0)
            if inserted != int(expected_candidate_count):
                conn.rollback()
                raise RuntimeError(
                    "inserted settlement event count mismatch: "
                    f"expected {int(expected_candidate_count)}, observed {inserted}"
                )
            conn.commit()

    return {
        "candidates": len(events),
        "candidate_order_ids": [str(event["ref_id"]) for event in events],
        "event_date_source_columns": sorted(
            {str(gap.get("event_date_source_column") or "") for gap in gaps}
        ),
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
    parser.add_argument("--order-id-file", type=Path, default=None)
    parser.add_argument("--expected-candidate-count", type=int, default=None)
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
        order_id_allowlist=_read_order_id_file(args.order_id_file) if args.order_id_file else None,
        expected_candidate_count=args.expected_candidate_count,
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
