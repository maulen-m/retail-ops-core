#!/usr/bin/env python3
"""Sync external Kaspi marketing spend into app DB sidecar tables."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_ADS_DB = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/"
    "Kaspi_marketing/db/kaspi_marketing.db"
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _norm_token(value: str | None) -> str:
    txt = str(value or "").strip().upper()
    if not txt:
        return ""
    txt = txt.replace(" ", "_")
    return re.sub(r"__+", "_", txt)


def _trim_numeric_suffix(token: str) -> str:
    if not token:
        return token
    return re.sub(r"_\d+$", "", token)


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ensure_sidecar_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ads_spend_sidecar_daily_sku (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT,
            ads_cost_kzt REAL NOT NULL DEFAULT 0,
            mapped INTEGER NOT NULL DEFAULT 0,
            ads_sku_key TEXT,
            merchant_sku_key TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            source_db TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, store_code, sku_key, ads_sku_key, merchant_sku_key, campaign_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ads_spend_sidecar_daily (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            mapped_cost_kzt REAL NOT NULL DEFAULT 0,
            unmapped_cost_kzt REAL NOT NULL DEFAULT 0,
            total_cost_kzt REAL NOT NULL DEFAULT 0,
            mapped_rows INTEGER NOT NULL DEFAULT 0,
            unmapped_rows INTEGER NOT NULL DEFAULT 0,
            mapping_coverage_pct REAL NOT NULL DEFAULT 0,
            source_db TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, store_code)
        )
        """
    )


def _load_sku_maps(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    sku_key_map: dict[str, str] = {}
    sku_id_map: dict[str, str] = {}
    model_hint: dict[str, str] = {}

    if _table_exists(conn, "dim_sku"):
        rows = conn.execute("SELECT sku_key FROM dim_sku").fetchall()
        for (sku_key,) in rows:
            token = _norm_token(sku_key)
            if token:
                sku_key_map[token] = str(sku_key)
            upper = str(sku_key or "").upper()
            if "LINE51" in upper and "LINE51" not in model_hint:
                model_hint["LINE51"] = str(sku_key)
            if "SUIT-61" in upper and "LINE61" not in model_hint:
                model_hint["LINE61"] = str(sku_key)

    if _table_exists(conn, "dim_sku_size"):
        rows = conn.execute("SELECT sku_id, sku_key FROM dim_sku_size").fetchall()
        for sku_id, sku_key in rows:
            token = _norm_token(sku_id)
            if token and token not in sku_id_map:
                sku_id_map[token] = str(sku_key)
            trimmed = _trim_numeric_suffix(token)
            if trimmed and trimmed not in sku_id_map:
                sku_id_map[trimmed] = str(sku_key)

    return {"sku_key": sku_key_map, "sku_id": sku_id_map, "model_hint": model_hint}


def _resolve_sku_key(
    *,
    ads_sku_key: str,
    merchant_sku: str,
    maps: dict[str, dict[str, str]],
) -> tuple[str | None, str]:
    sku_key_map = maps["sku_key"]
    sku_id_map = maps["sku_id"]
    model_hint = maps["model_hint"]

    ads_token = _norm_token(ads_sku_key)
    merchant_token = _norm_token(merchant_sku)
    candidates = [
        merchant_token,
        _trim_numeric_suffix(merchant_token),
        ads_token,
        _trim_numeric_suffix(ads_token),
    ]

    for token in candidates:
        if not token:
            continue
        if token in sku_key_map:
            return sku_key_map[token], "sku_key_exact"
        if token in sku_id_map:
            return sku_id_map[token], "sku_id_exact"

    merged = f"{merchant_token} {ads_token}"
    if "LINE51" in merged and model_hint.get("LINE51"):
        return model_hint["LINE51"], "model_hint_line51"
    if ("SUIT-61" in merged or "LINE61" in merged) and model_hint.get("LINE61"):
        return model_hint["LINE61"], "model_hint_line61"

    return None, "unmapped"


def sync_ads_sidecar(
    *,
    app_db: Path,
    ads_db: Path,
    since: str | None = None,
    until: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    ext = sqlite3.connect(str(ads_db))
    ext.row_factory = sqlite3.Row
    app = sqlite3.connect(str(app_db))
    app.row_factory = sqlite3.Row
    try:
        maps = _load_sku_maps(app)
        where = ["1=1"]
        params: list[Any] = []
        if since:
            where.append("date(date) >= date(?)")
            params.append(since)
        if until:
            where.append("date(date) <= date(?)")
            params.append(until)
        rows = ext.execute(
            f"""
            SELECT date, store_code, campaign_id, campaign_name, sku_key, json_merchant_sku, cost
            FROM campaign_product_daily_current
            WHERE {' AND '.join(where)}
            """,
            tuple(params),
        ).fetchall()

        mapped_rows = 0
        unmapped_rows = 0
        daily_key: dict[tuple[str, str], dict[str, float]] = {}
        sku_rows: list[tuple[Any, ...]] = []
        for row in rows:
            ads_cost = _to_float(row["cost"])
            if ads_cost <= 0:
                continue
            date_key = str(row["date"] or "")
            store_code = str(row["store_code"] or "ACMEWEAR")
            mapped_sku, mapping_method = _resolve_sku_key(
                ads_sku_key=str(row["sku_key"] or ""),
                merchant_sku=str(row["json_merchant_sku"] or ""),
                maps=maps,
            )
            is_mapped = 1 if mapped_sku else 0
            if is_mapped:
                mapped_rows += 1
            else:
                unmapped_rows += 1

            key = (date_key, store_code)
            daily = daily_key.setdefault(
                key,
                {
                    "mapped_cost_kzt": 0.0,
                    "unmapped_cost_kzt": 0.0,
                    "total_cost_kzt": 0.0,
                    "mapped_rows": 0.0,
                    "unmapped_rows": 0.0,
                },
            )
            if is_mapped:
                daily["mapped_cost_kzt"] += ads_cost
                daily["mapped_rows"] += 1
            else:
                daily["unmapped_cost_kzt"] += ads_cost
                daily["unmapped_rows"] += 1
            daily["total_cost_kzt"] += ads_cost

            sku_rows.append(
                (
                    date_key,
                    store_code,
                    mapped_sku,
                    round(ads_cost, 2),
                    is_mapped,
                    str(row["sku_key"] or ""),
                    str(row["json_merchant_sku"] or ""),
                    str(row["campaign_id"] or ""),
                    str(row["campaign_name"] or ""),
                    str(ads_db),
                )
            )

        daily_rows: list[tuple[Any, ...]] = []
        for (date_key, store_code), values in sorted(daily_key.items()):
            mapped_count = int(values["mapped_rows"])
            unmapped_count = int(values["unmapped_rows"])
            total_count = mapped_count + unmapped_count
            coverage = round((mapped_count / total_count) * 100.0, 2) if total_count else 0.0
            daily_rows.append(
                (
                    date_key,
                    store_code,
                    round(values["mapped_cost_kzt"], 2),
                    round(values["unmapped_cost_kzt"], 2),
                    round(values["total_cost_kzt"], 2),
                    mapped_count,
                    unmapped_count,
                    coverage,
                    str(ads_db),
                )
            )

        if apply:
            _ensure_sidecar_tables(app)
            if since or until:
                delete_where = ["1=1"]
                delete_params: list[Any] = []
                if since:
                    delete_where.append("date(date) >= date(?)")
                    delete_params.append(since)
                if until:
                    delete_where.append("date(date) <= date(?)")
                    delete_params.append(until)
                where_sql = " AND ".join(delete_where)
                app.execute(f"DELETE FROM ads_spend_sidecar_daily_sku WHERE {where_sql}", tuple(delete_params))
                app.execute(f"DELETE FROM ads_spend_sidecar_daily WHERE {where_sql}", tuple(delete_params))
            else:
                app.execute("DELETE FROM ads_spend_sidecar_daily_sku")
                app.execute("DELETE FROM ads_spend_sidecar_daily")

            if sku_rows:
                app.executemany(
                    """
                    INSERT INTO ads_spend_sidecar_daily_sku (
                        date, store_code, sku_key, ads_cost_kzt, mapped,
                        ads_sku_key, merchant_sku_key, campaign_id, campaign_name, source_db
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    sku_rows,
                )
            if daily_rows:
                app.executemany(
                    """
                    INSERT INTO ads_spend_sidecar_daily (
                        date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt,
                        mapped_rows, unmapped_rows, mapping_coverage_pct, source_db
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    daily_rows,
                )
            app.commit()

        return {
            "rows_total": mapped_rows + unmapped_rows,
            "rows_mapped": mapped_rows,
            "rows_unmapped": unmapped_rows,
            "days_total": len(daily_rows),
            "apply": bool(apply),
        }
    finally:
        ext.close()
        app.close()


def run_sync_ads_sidecar(
    *,
    app_db: Path,
    ads_db: Path,
    since: str | None,
    until: str | None,
    apply: bool,
) -> int:
    if apply and os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
        print("ERROR: ENABLE_CASHFLOW_WRITE=1 is required with --apply")
        return 1
    summary = sync_ads_sidecar(
        app_db=app_db,
        ads_db=ads_db,
        since=since,
        until=until,
        apply=apply,
    )
    print(summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync ads spend sidecar from external marketing DB")
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--ads-db", type=Path, default=DEFAULT_ADS_DB)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--until", type=str, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return run_sync_ads_sidecar(
        app_db=args.app_db,
        ads_db=args.ads_db,
        since=args.since,
        until=args.until,
        apply=args.apply,
    )


if __name__ == "__main__":
    raise SystemExit(main())
