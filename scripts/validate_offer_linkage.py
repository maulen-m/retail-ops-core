#!/usr/bin/env python3
"""Fail-closed validator for offer linkage publication readiness."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_TABLE = "fact_offer_stock_mapper_current"
DEFAULT_ARTICLE_MAP = "dim_kaspi_article_map"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _pick_column(columns: set[str], candidates: list[str]) -> str | None:
    for name in candidates:
        if name in columns:
            return name
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def validate_offer_linkage(
    *,
    db_path: Path = DEFAULT_DB,
    mapper_table: str = DEFAULT_TABLE,
    article_map_table: str = DEFAULT_ARTICLE_MAP,
) -> dict[str, Any]:
    errors: list[str] = []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, mapper_table):
            return {
                "ok": False,
                "errors": [f"mapper table missing: {mapper_table}"],
                "metrics": {},
            }

        mapper_cols = _table_columns(conn, mapper_table)
        token_col = _pick_column(
            mapper_cols,
            [
                "kaspi_article",
                "offer_id",
                "kaspi_offer_id",
                "merchant_sku_key",
                "offer_article",
                "article",
            ],
        )
        sku_col = _pick_column(mapper_cols, ["sku_key"])
        method_col = _pick_column(mapper_cols, ["mapping_method"])
        ambiguous_col = _pick_column(mapper_cols, ["is_ambiguous"])

        if not token_col or not sku_col or not method_col:
            missing = []
            if not token_col:
                missing.append("offer/article token")
            if not sku_col:
                missing.append("sku_key")
            if not method_col:
                missing.append("mapping_method")
            return {
                "ok": False,
                "errors": [f"mapper table missing required columns: {', '.join(missing)}"],
                "metrics": {},
            }

        ambiguous_expr = f"COALESCE({ambiguous_col}, 0)" if ambiguous_col else "0"

        unresolved_rows = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM {mapper_table}
            WHERE COALESCE({method_col}, '') = 'unresolved'
               OR COALESCE(TRIM({sku_col}), '') = ''
            """
        ).fetchone()["c"]

        ambiguous_rows = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM {mapper_table}
            WHERE {ambiguous_expr} = 1
            """
        ).fetchone()["c"]

        resolved_rows = conn.execute(
            f"""
            SELECT {token_col} AS offer_token, {sku_col} AS sku_key
            FROM {mapper_table}
            WHERE COALESCE({method_col}, '') != 'unresolved'
              AND {ambiguous_expr} = 0
              AND COALESCE(TRIM({sku_col}), '') != ''
              AND COALESCE(TRIM({token_col}), '') != ''
            """
        ).fetchall()

        resolved_count = len(resolved_rows)

        if unresolved_rows > 0:
            errors.append(f"unresolved linkage rows present: {unresolved_rows}")
        if ambiguous_rows > 0:
            errors.append(f"ambiguous linkage rows present: {ambiguous_rows}")

        if not _table_exists(conn, article_map_table):
            errors.append(f"article map table missing: {article_map_table}")
            mapped_pairs: set[tuple[str, str]] = set()
        else:
            map_cols = _table_columns(conn, article_map_table)
            map_token_col = _pick_column(
                map_cols,
                ["kaspi_article", "kaspi_offer_id", "offer_id", "article"],
            )
            map_sku_col = _pick_column(map_cols, ["sku_key"])
            if not map_token_col or not map_sku_col:
                errors.append(
                    "article map table missing required columns for bidirectional check"
                )
                mapped_pairs = set()
            else:
                mapped_rows = conn.execute(
                    f"""
                    SELECT {map_token_col} AS offer_token, {map_sku_col} AS sku_key
                    FROM {article_map_table}
                    WHERE COALESCE(TRIM({map_token_col}), '') != ''
                      AND COALESCE(TRIM({map_sku_col}), '') != ''
                    """
                ).fetchall()
                mapped_pairs = {
                    (_norm(row["offer_token"]).upper(), _norm(row["sku_key"]))
                    for row in mapped_rows
                }

        missing_bidirectional: list[str] = []
        for row in resolved_rows:
            pair = (_norm(row["offer_token"]).upper(), _norm(row["sku_key"]))
            if pair not in mapped_pairs:
                missing_bidirectional.append(f"{pair[0]} -> {pair[1]}")

        if missing_bidirectional:
            preview = ", ".join(missing_bidirectional[:10])
            errors.append(
                "bidirectional linkage missing for resolved offers: " + preview
            )

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "metrics": {
                "resolved_rows": resolved_count,
                "unresolved_rows": int(unresolved_rows or 0),
                "ambiguous_rows": int(ambiguous_rows or 0),
                "missing_bidirectional_rows": len(missing_bidirectional),
            },
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate offer linkage strict publication readiness")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--mapper-table", type=str, default=DEFAULT_TABLE)
    parser.add_argument("--article-map-table", type=str, default=DEFAULT_ARTICLE_MAP)
    args = parser.parse_args()

    report = validate_offer_linkage(
        db_path=args.db,
        mapper_table=args.mapper_table,
        article_map_table=args.article_map_table,
    )
    metrics = report.get("metrics", {})
    print(
        "offer_linkage: "
        f"ok={report['ok']} resolved={metrics.get('resolved_rows', 0)} "
        f"unresolved={metrics.get('unresolved_rows', 0)} "
        f"ambiguous={metrics.get('ambiguous_rows', 0)} "
        f"missing_bidirectional={metrics.get('missing_bidirectional_rows', 0)}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: offer linkage strict gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
