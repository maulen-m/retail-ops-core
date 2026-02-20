#!/usr/bin/env python3
"""
Fix invalid CL size tokens in sales tables by inferring size from offer name.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import VALID_SIZES, normalize_size, infer_size_from_sku_id


SIZE_PATTERN = re.compile(r"(\\b(\\d+XL|XXXL|XXL|XL|XS|L|M|S|\\d{2})\\b)", re.IGNORECASE)
NUMERIC_TO_LETTER = {
    "44": "S",
    "46": "M",
    "48": "L",
    "50": "L",
    "52": "XL",
    "54": "2XL",
    "56": "3XL",
    "58": "4XL",
}

CYRILLIC_SIZE_MAP = str.maketrans({
    "М": "M",
    "Х": "X",
    "С": "S",
    "Л": "L",
})


def infer_size_from_offer(offer_name: str | None) -> str | None:
    if not offer_name:
        return None
    normalized = offer_name.upper().translate(CYRILLIC_SIZE_MAP)
    tokens = [t for t in re.split(r"[^0-9A-Z]+", normalized) if t]
    if not tokens:
        return None
    # scan from end (size usually at end)
    for token in reversed(tokens):
        token = token.strip().upper()
        mapped = NUMERIC_TO_LETTER.get(token, token)
        size = normalize_size(mapped, "CL")
        if size and size in VALID_SIZES:
            return size
    return None


def _fix_table(conn, table: str, apply: bool) -> int:
    rows = conn.execute(
        f"""
        SELECT rowid as rid, sku_key, sku_id, my_size, kaspi_offer_name
        FROM {table}
        WHERE sku_key LIKE 'CL%'
          AND (my_size IS NULL OR my_size = '' OR my_size NOT IN ({','.join('?' for _ in VALID_SIZES)}))
        """,
        tuple(sorted(VALID_SIZES)),
    ).fetchall()

    fixed = 0
    for row in rows:
        sku_key = row["sku_key"]
        current_size = row["my_size"]

        size = infer_size_from_offer(row["kaspi_offer_name"])
        if not size:
            size = infer_size_from_sku_id(row["sku_id"])
        if not size:
            continue

        new_sku_id = f"{sku_key}_{size}"

        if apply:
            if table in {"fact_sales", "sales_fact_v2"}:
                existing = conn.execute(
                    f"""
                    SELECT rowid as rid, quantity
                    FROM {table}
                    WHERE order_id = (SELECT order_id FROM {table} WHERE rowid = ?)
                      AND kaspi_offer_name = (SELECT kaspi_offer_name FROM {table} WHERE rowid = ?)
                      AND store_code = (SELECT store_code FROM {table} WHERE rowid = ?)
                      AND sku_id = ?
                      AND rowid != ?
                    """,
                    (row["rid"], row["rid"], row["rid"], new_sku_id, row["rid"]),
                ).fetchone()
                if existing:
                    if table == "fact_sales":
                        current = conn.execute(
                            f"SELECT quantity, line_net_rev, cogs_line, profit_line FROM {table} WHERE rowid = ?",
                            (row["rid"],),
                        ).fetchone()
                        existing_vals = conn.execute(
                            f"SELECT line_net_rev, cogs_line, profit_line FROM {table} WHERE rowid = ?",
                            (existing["rid"],),
                        ).fetchone()
                        new_qty = int(existing["quantity"] or 0) + int(current["quantity"] or 0)
                        new_line_net = float(existing_vals["line_net_rev"] or 0) + float(current["line_net_rev"] or 0)
                        new_cogs = float(existing_vals["cogs_line"] or 0) + float(current["cogs_line"] or 0)
                        new_profit_line = float(existing_vals["profit_line"] or 0) + float(current["profit_line"] or 0)
                        conn.execute(
                            f"""
                            UPDATE {table}
                            SET quantity = ?, line_net_rev = ?, cogs_line = ?, profit_line = ?, my_size = ?, sku_id = ?
                            WHERE rowid = ?
                            """,
                            (
                                new_qty,
                                new_line_net,
                                new_cogs,
                                new_profit_line,
                                size,
                                new_sku_id,
                                existing["rid"],
                            ),
                        )
                    else:
                        current = conn.execute(
                            f"SELECT quantity, net_rev, profit, cogs FROM {table} WHERE rowid = ?",
                            (row["rid"],),
                        ).fetchone()
                        existing_vals = conn.execute(
                            f"SELECT net_rev, profit, cogs FROM {table} WHERE rowid = ?",
                            (existing["rid"],),
                        ).fetchone()
                        new_qty = int(existing["quantity"] or 0) + int(current["quantity"] or 0)
                        new_net = float(existing_vals["net_rev"] or 0) + float(current["net_rev"] or 0)
                        new_profit = float(existing_vals["profit"] or 0) + float(current["profit"] or 0)
                        new_cogs = float(existing_vals["cogs"] or 0) + float(current["cogs"] or 0)
                        conn.execute(
                            f"""
                            UPDATE {table}
                            SET quantity = ?, net_rev = ?, profit = ?, cogs = ?, my_size = ?, sku_id = ?
                            WHERE rowid = ?
                            """,
                            (
                                new_qty,
                                new_net,
                                new_profit,
                                new_cogs,
                                size,
                                new_sku_id,
                                existing["rid"],
                            ),
                        )
                    conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (row["rid"],))
                    fixed += 1
                    continue

            conn.execute(
                f"UPDATE {table} SET my_size = ?, sku_id = ? WHERE rowid = ?",
                (size, new_sku_id, row["rid"]),
            )
        fixed += 1

    return fixed


def _ensure_dim_sku_size(conn, sku_key: str, my_size: str) -> None:
    existing = conn.execute(
        "SELECT sku_id FROM dim_sku_size WHERE sku_key = ? AND my_size = ?",
        (sku_key, my_size),
    ).fetchone()
    if existing:
        return
    sku_id = f"{sku_key}_{my_size}"
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag) VALUES (?, ?, ?, 1)",
        (sku_id, sku_key, my_size),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix invalid CL sizes in sales tables")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default: dry-run)")
    args = parser.parse_args()

    with get_db(args.db) as conn:
        if args.apply:
            conn.execute("PRAGMA foreign_keys = OFF")

        fixed_fact = _fix_table(conn, "fact_sales", args.apply)
        fixed_sales = _fix_table(conn, "sales_fact_v2", args.apply)

        if args.apply:
            # Ensure dim_sku_size rows for any new sizes
            rows = conn.execute(
                """
                SELECT DISTINCT sku_key, my_size
                FROM fact_sales
                WHERE sku_key LIKE 'CL%' AND my_size IN ({})
                """.format(",".join("?" for _ in VALID_SIZES)),
                tuple(sorted(VALID_SIZES)),
            ).fetchall()
            for row in rows:
                _ensure_dim_sku_size(conn, row["sku_key"], row["my_size"])
            conn.commit()
        else:
            conn.rollback()

    print(f"fact_sales fixed: {fixed_fact}")
    print(f"sales_fact_v2 fixed: {fixed_sales}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
