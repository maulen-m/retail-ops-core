#!/usr/bin/env python3
"""Validate that recent orders have fresh order entries for identity-bearing ingestion."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import (
    DEFAULT_ACTIVE_STORES,
    StatusError,
    parse_iso_date,
    write_json,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _entry_required(row: sqlite3.Row, *, as_of: date) -> bool:
    status_detail = str(row["kaspi_status_detail"] or "").strip().upper()
    internal_status = str(row["internal_status"] or "").strip().upper()
    kaspi_status = str(row["kaspi_status"] or "").strip().upper()

    if status_detail in {"CANCELLED", "RETURNED"}:
        return False
    if internal_status in {"CANCELLED", "RETURNED"}:
        return False

    pending_like = {"ACCEPTED_BY_MERCHANT", "APPROVED_BY_BANK", "NEW", "ASSEMBLY"}
    if (
        status_detail in pending_like
        or internal_status in {"NEW", "ACCEPTED", "READY"}
        or kaspi_status in {"NEW", "ASSEMBLY"}
    ):
        created_text = str(row["created_at"] or "").strip()
        created_date = created_text[:10] if len(created_text) >= 10 else ""
        if created_date <= as_of.isoformat():
            return False

    return True


def validate_order_entries_freshness(
    *,
    db_path: Path,
    as_of: date,
    lookback_days: int,
    stores: tuple[str, ...],
    min_entries_coverage_pct: float,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    if lookback_days <= 0:
        raise StatusError("IDENTITY_COVERAGE_FAIL", "lookback_days must be > 0")

    start_day = as_of - timedelta(days=lookback_days - 1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        order_cols = _table_columns(conn, "fact_orders_kaspi")
        detail_expr = "COALESCE(kaspi_status_detail,'')" if "kaspi_status_detail" in order_cols else "''"
        internal_expr = "COALESCE(internal_status,'')" if "internal_status" in order_cols else "''"
        kaspi_expr = "COALESCE(kaspi_status,'')" if "kaspi_status" in order_cols else "''"
        order_rows = conn.execute(
            """
            SELECT order_id,
                   UPPER(COALESCE(store_code,'')) AS store_code,
                   COALESCE(created_at,'') AS created_at,
                   {detail_expr} AS kaspi_status_detail,
                   {internal_expr} AS internal_status,
                   {kaspi_expr} AS kaspi_status
            FROM fact_orders_kaspi
            WHERE date(created_at) BETWEEN ? AND ?
              AND UPPER(COALESCE(store_code,'')) IN ({})
            """.format(",".join(["?"] * len(stores)), detail_expr=detail_expr, internal_expr=internal_expr, kaspi_expr=kaspi_expr),
            (start_day.isoformat(), as_of.isoformat(), *stores),
        ).fetchall()

        entry_rows = conn.execute(
            """
            SELECT DISTINCT order_id, UPPER(COALESCE(store_code,'')) AS store_code
            FROM fact_order_entries_kaspi
            WHERE date(updated_at) BETWEEN ? AND ?
              AND UPPER(COALESCE(store_code,'')) IN ({})
            """.format(",".join(["?"] * len(stores))),
            (start_day.isoformat(), as_of.isoformat(), *stores),
        ).fetchall()
    finally:
        conn.close()

    entry_keys = {f"{str(r['store_code']).upper()}:{str(r['order_id'])}" for r in entry_rows}

    per_store: dict[str, dict[str, Any]] = {
        s: {
            "store_code": s,
            "orders_total": 0,
            "orders_with_entries": 0,
            "orders_missing_entries": 0,
            "entries_coverage_pct": 0.0,
        }
        for s in stores
    }
    missing_rows: list[dict[str, str]] = []

    for row in order_rows:
        if not _entry_required(row, as_of=as_of):
            continue
        store = str(row["store_code"] or "").strip().upper()
        order_id = str(row["order_id"] or "").strip()
        key = f"{store}:{order_id}"
        p = per_store[store]
        p["orders_total"] += 1
        if key in entry_keys:
            p["orders_with_entries"] += 1
        else:
            p["orders_missing_entries"] += 1
            missing_rows.append(
                {
                    "store_code": store,
                    "order_id": order_id,
                    "created_at": str(row["created_at"] or "").strip(),
                    "reason": "missing_recent_entry_row",
                }
            )

    failing_stores: list[dict[str, Any]] = []
    for store in stores:
        p = per_store[store]
        total = int(p["orders_total"])
        if total > 0:
            p["entries_coverage_pct"] = round(100.0 * float(p["orders_with_entries"]) / float(total), 4)
        if total > 0 and float(p["entries_coverage_pct"]) < float(min_entries_coverage_pct):
            failing_stores.append(
                {
                    "store_code": store,
                    "entries_coverage_pct": float(p["entries_coverage_pct"]),
                    "min_entries_coverage_pct": float(min_entries_coverage_pct),
                    "orders_total": total,
                    "orders_missing_entries": int(p["orders_missing_entries"]),
                }
            )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "validate_order_entries_freshness.json"
    report_md = out_dir / "validate_order_entries_freshness.md"

    status = "PASS" if not failing_stores else "IDENTITY_COVERAGE_FAIL"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "lookback_days": int(lookback_days),
        "stores": list(stores),
        "min_entries_coverage_pct": float(min_entries_coverage_pct),
        "per_store": [per_store[s] for s in stores],
        "failing_stores": failing_stores,
        "missing_orders_sample": missing_rows[:200],
        "status": status,
        "error_code": "" if status == "PASS" else status,
    }
    write_json(report_json, payload)

    lines = [
        "# Order Entries Freshness",
        "",
        f"- as_of: `{as_of.isoformat()}`",
        f"- status: `{status}`",
        f"- lookback_days: `{lookback_days}`",
        "",
        "| store | orders_total | orders_with_entries | orders_missing_entries | entries_coverage_pct |",
        "|---|---:|---:|---:|---:|",
    ]
    for p in payload["per_store"]:
        lines.append(
            f"| `{p['store_code']}` | {p['orders_total']} | {p['orders_with_entries']} | "
            f"{p['orders_missing_entries']} | {p['entries_coverage_pct']:.4f} |"
        )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if strict and status != "PASS":
        raise StatusError(
            "IDENTITY_COVERAGE_FAIL",
            f"entries freshness below threshold for stores: {', '.join(x['store_code'] for x in failing_stores)}",
        )
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate recent order-entries freshness")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--stores", default=",".join(DEFAULT_ACTIVE_STORES))
    parser.add_argument("--min-entries-coverage-pct", type=float, default=95.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    stores = tuple(s.strip().upper() for s in str(args.stores).split(",") if s.strip())
    try:
        report = validate_order_entries_freshness(
            db_path=args.db,
            as_of=parse_iso_date(args.as_of, field="as_of"),
            lookback_days=int(args.lookback_days),
            stores=stores,
            min_entries_coverage_pct=float(args.min_entries_coverage_pct),
            output_root=args.output_root,
            strict=bool(args.strict),
        )
    except StatusError as exc:
        print(f"status={exc.code}")
        print(f"error_code={exc.code}")
        print(f"message={exc.message}")
        return 1
    except Exception as exc:  # pragma: no cover
        print("status=FAIL")
        print("error_code=FAIL")
        print(f"message={exc}")
        return 1

    print(f"order_entries_freshness_json={(args.output_root.resolve() / report['as_of'] / 'validate_order_entries_freshness.json')}")
    print(f"order_entries_freshness_md={(args.output_root.resolve() / report['as_of'] / 'validate_order_entries_freshness.md')}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
