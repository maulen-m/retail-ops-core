#!/usr/bin/env python3
"""Build fact_sales_v16 from API-native order entries with fail-closed mapping checks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_GAPS_JSON = PROJECT_ROOT / "exports" / "validation" / "fact_sales_v16_gaps.json"
DEFAULT_GAPS_MD = PROJECT_ROOT / "exports" / "validation" / "fact_sales_v16_gaps.md"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _load_article_map(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    cols = _table_columns(conn, "dim_kaspi_article_map")
    where_clause = ""
    if "active_flag" in cols:
        where_clause = "WHERE active_flag IS NULL OR active_flag = 1"
    rows = conn.execute(
        f"""
        SELECT store_code, kaspi_article, sku_key, sku_id
        FROM dim_kaspi_article_map
        {where_clause}
        """
    ).fetchall()
    return {(row[0], row[1]): {"sku_key": row[2], "sku_id": row[3]} for row in rows}


def _write_gap_reports(
    *,
    gaps_json_path: Path,
    gaps_md_path: Path,
    run_id: str,
    missing_rows: list[dict[str, Any]],
) -> None:
    gaps_json_path.parent.mkdir(parents=True, exist_ok=True)
    gaps_md_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "missing_count": len(missing_rows),
        "missing_entries": missing_rows,
    }
    gaps_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# fact_sales_v16 mapping gaps",
        "",
        f"- run_id: `{run_id}`",
        f"- missing_count: `{len(missing_rows)}`",
        "",
    ]
    if missing_rows:
        lines.append("## Missing entries")
        lines.append("")
        for row in missing_rows[:200]:
            lines.append(
                f"- entry_id={row['entry_id']} order_id={row['order_id']} store={row['store_code']} offer={row['offer_id']}"
            )
    else:
        lines.append("No mapping gaps.")
    gaps_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_fact_sales_v16_from_api(
    *,
    db_path: Path,
    apply: bool,
    run_id: str,
    gaps_json_path: Path = DEFAULT_GAPS_JSON,
    gaps_md_path: Path = DEFAULT_GAPS_MD,
    strict: bool = True,
    max_missing: int = 0,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if apply and os.environ.get("ENABLE_FACT_SALES_V16_WRITE") != "1":
        raise RuntimeError("ENABLE_FACT_SALES_V16_WRITE=1 is required for --apply")
    if max_missing < 0:
        raise RuntimeError("max_missing must be >= 0")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_order_entries_kaspi"):
            raise RuntimeError("fact_order_entries_kaspi missing")
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi missing")
        if not _table_exists(conn, "fact_sales_v16"):
            raise RuntimeError("fact_sales_v16 missing; run migrate_021_fact_sales_v16.py")

        article_map = _load_article_map(conn)
        entries = conn.execute(
            """
            SELECT entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
            FROM fact_order_entries_kaspi
            """
        ).fetchall()

        order_cols = _table_columns(conn, "fact_orders_kaspi")
        select_delivery_for_seller = (
            "delivery_cost_for_seller"
            if "delivery_cost_for_seller" in order_cols
            else "NULL as delivery_cost_for_seller"
        )
        select_delivery_cost = "delivery_cost" if "delivery_cost" in order_cols else "NULL as delivery_cost"
        orders = conn.execute(
            f"""
            SELECT order_id, store_code, sku_key, sku_id,
                   {select_delivery_for_seller}, {select_delivery_cost}
            FROM fact_orders_kaspi
            """
        ).fetchall()
        orders_by_id = {(row["order_id"], row["store_code"]): row for row in orders}

        totals_by_order: dict[tuple[str, str], float] = {}
        counts_by_order: dict[tuple[str, str], int] = {}
        for row in entries:
            key = (row["order_id"], row["store_code"])
            totals_by_order[key] = totals_by_order.get(key, 0.0) + float(row["total_price_kzt"] or 0.0)
            counts_by_order[key] = counts_by_order.get(key, 0) + 1

        rows_to_upsert: list[dict[str, Any]] = []
        missing_rows: list[dict[str, Any]] = []

        for row in entries:
            order_key = (row["order_id"], row["store_code"])
            order = orders_by_id.get(order_key)
            order_total = totals_by_order.get(order_key, 0.0)
            entry_total = float(row["total_price_kzt"] or 0.0)

            delivery_fee = 0.0
            if order is not None:
                fee = order["delivery_cost_for_seller"]
                if fee is None:
                    fee = order["delivery_cost"]
                fee = float(fee or 0.0)
                if order_total > 0:
                    delivery_fee = fee * (entry_total / order_total)
                else:
                    delivery_fee = fee
            net_rev = entry_total - delivery_fee

            mapping = article_map.get((row["store_code"], row["offer_id"]))
            sku_key = mapping.get("sku_key") if mapping else None
            sku_id = mapping.get("sku_id") if mapping else None

            if not sku_key and order is not None and counts_by_order.get(order_key, 0) == 1:
                sku_key = order["sku_key"]
                sku_id = order["sku_id"]

            if not sku_key:
                missing_rows.append(
                    {
                        "entry_id": row["entry_id"],
                        "order_id": row["order_id"],
                        "store_code": row["store_code"],
                        "offer_id": row["offer_id"],
                    }
                )

            rows_to_upsert.append(
                {
                    "entry_id": row["entry_id"],
                    "order_id": row["order_id"],
                    "store_code": row["store_code"],
                    "offer_id": row["offer_id"],
                    "sku_key": sku_key,
                    "sku_id": sku_id,
                    "quantity": float(row["quantity"] or 0.0),
                    "unit_price_kzt": float(row["unit_price_kzt"] or 0.0),
                    "total_price_kzt": entry_total,
                    "delivery_fee_kzt": round(delivery_fee, 2),
                    "net_rev_kzt": round(net_rev, 2),
                    "source": "API_ENTRIES",
                    "run_id": run_id,
                }
            )

        _write_gap_reports(
            gaps_json_path=gaps_json_path,
            gaps_md_path=gaps_md_path,
            run_id=run_id,
            missing_rows=missing_rows,
        )

        if strict and len(missing_rows) > max_missing:
            raise RuntimeError(
                f"missing mappings exceed threshold: missing mappings={len(missing_rows)} max_missing={max_missing}"
            )

        inserted = 0
        if apply:
            for payload in rows_to_upsert:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fact_sales_v16 (
                        entry_id, order_id, store_code, offer_id, sku_key, sku_id,
                        quantity, unit_price_kzt, total_price_kzt, delivery_fee_kzt,
                        net_rev_kzt, source, run_id
                    ) VALUES (
                        :entry_id, :order_id, :store_code, :offer_id, :sku_key, :sku_id,
                        :quantity, :unit_price_kzt, :total_price_kzt, :delivery_fee_kzt,
                        :net_rev_kzt, :source, :run_id
                    )
                    """,
                    payload,
                )
                inserted += 1
            conn.commit()
        else:
            inserted = len(rows_to_upsert)

    return {
        "inserted": inserted,
        "missing": len(missing_rows),
        "gaps_json_path": str(gaps_json_path),
        "gaps_md_path": str(gaps_md_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fact_sales_v16 from API order entries")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--gaps-json", type=Path, default=DEFAULT_GAPS_JSON)
    parser.add_argument("--gaps-md", type=Path, default=DEFAULT_GAPS_MD)
    parser.add_argument("--strict", action="store_true", default=False)
    parser.add_argument("--max-missing", type=int, default=0)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    result = build_fact_sales_v16_from_api(
        db_path=args.db,
        apply=args.apply,
        run_id=run_id,
        gaps_json_path=args.gaps_json,
        gaps_md_path=args.gaps_md,
        strict=args.strict,
        max_missing=args.max_missing,
    )
    print(f"inserted={result['inserted']}")
    print(f"missing={result['missing']}")
    print(f"gaps_json_path={result['gaps_json_path']}")
    print(f"gaps_md_path={result['gaps_md_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
