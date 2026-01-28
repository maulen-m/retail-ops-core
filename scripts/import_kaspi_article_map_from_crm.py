#!/usr/bin/env python3
"""
Import Kaspi article/offer mapping from CRM workbook into dim_kaspi_article_map.

Default source sheet: M02_SKU_CATALOG_NC (SKU_ID_KSP + SKU_key + Store_name).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import sys

import pandas as pd
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db  # noqa: E402
from core.ingest.sales_ingest import normalize_store_code  # noqa: E402
from core.utils.sku_map import extract_kaspi_name_core  # noqa: E402
from core.utils.sku_normalize import normalize_size  # noqa: E402

DEFAULT_WORKBOOK = Path("excel_ui/SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "M02_SKU_CATALOG_NC"
DEFAULT_DB = Path("db/app.db")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _value_exists(conn, table: str, column: str, value: str | None) -> bool:
    if not value:
        return False
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1",
        (value,),
    ).fetchone()
    return row is not None


def _normalize_columns(df: pd.DataFrame) -> dict[str, str]:
    return {str(c).strip().lower(): c for c in df.columns}


def _pick_col(cols: dict[str, str], *names: str) -> str | None:
    for name in names:
        key = name.strip().lower()
        if key in cols:
            return cols[key]
    return None


def _clean_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text if text else None


def _load_merchant_ids() -> dict[str, str]:
    cfg = _load_yaml(Path("config/kaspi_stores.yaml"))
    stores = cfg.get("stores", {}) if isinstance(cfg, dict) else {}
    out: dict[str, str] = {}
    for store_code, info in stores.items():
        merchant_uid = None
        if isinstance(info, dict):
            merchant_uid = info.get("merchant_uid")
        if merchant_uid:
            out[store_code] = str(merchant_uid)
    return out


ADULT_SIZE_TOKENS = {
    "XS",
    "S",
    "M",
    "L",
    "XL",
    "2XL",
    "3XL",
    "4XL",
    "5XL",
}


def _parse_article_for_sku(kaspi_article: str) -> tuple[str | None, str | None, str | None]:
    if not kaspi_article:
        return None, None, None
    tokens = [t for t in str(kaspi_article).split("_") if t]
    if len(tokens) < 2:
        return None, None, None
    last = tokens[-1]
    size_token = None
    if last.isdigit() and len(tokens) >= 2:
        size_token = tokens[-2]
        sku_key = "_".join(tokens[:-2])
    else:
        size_token = tokens[-1]
        sku_key = "_".join(tokens[:-1])
    size_norm = normalize_size(size_token) if size_token else None
    if not sku_key or not size_norm:
        return None, None, None
    sku_id = f"{sku_key}_{size_norm}"
    return sku_key, sku_id, size_norm


def _maybe_kid_to_men(
    conn,
    sku_key: str | None,
    sku_id: str | None,
    my_size: str | None,
) -> tuple[str | None, str | None]:
    if not sku_key or "_KID_" not in sku_key:
        return sku_key, sku_id
    if not sku_id:
        return sku_key, sku_id
    size = my_size or sku_id.split("_")[-1]
    if size not in ADULT_SIZE_TOKENS:
        return sku_key, sku_id
    candidate_key = sku_key.replace("_KID_", "_MEN_")
    candidate_id = f"{candidate_key}_{size}"
    if _value_exists(conn, "dim_sku_size", "sku_id", candidate_id):
        return candidate_key, candidate_id
    return sku_key, sku_id


def import_map(
    db_path: Path,
    workbook: Path,
    sheet: str,
    store_filter: str | None,
    apply_changes: bool,
) -> None:
    if not workbook.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook}")

    df = pd.read_excel(workbook, sheet_name=sheet)
    cols = _normalize_columns(df)

    store_col = _pick_col(cols, "Store_name", "STORE_NAME")
    article_col = _pick_col(cols, "SKU_ID_KSP_v2", "SKU_ID_KSP")
    sku_key_col = _pick_col(cols, "SKU_key")
    sku_id_col = _pick_col(cols, "SKU_ID")
    size_col = _pick_col(cols, "MY_SIZE", "Size_kaspi")
    offer_col = _pick_col(cols, "Kaspi_offer_name", "KASPI_OFFER_NAME", "Kaspi_name_source")
    name_core_col = _pick_col(cols, "Kaspi_name_core")
    model_col = _pick_col(cols, "Model")
    brand_col = _pick_col(cols, "Brand")

    missing = [
        name for name, col in {
            "Store_name": store_col,
            "SKU_ID_KSP": article_col,
            "SKU_key": sku_key_col,
        }.items() if col is None
    ]
    if missing:
        raise ValueError(f"Missing required columns in sheet {sheet}: {missing}")

    merchant_ids = _load_merchant_ids()

    inserted = 0
    updated = 0
    skipped = 0
    missing_sku_key = 0
    missing_sku_id = 0

    with get_db(db_path) as conn:
        if not _table_exists(conn, "dim_kaspi_article_map"):
            raise RuntimeError("dim_kaspi_article_map not found. Run scripts/migrate_020_kaspi_article_map.py first.")

        for _, row in df.iterrows():
            store_name = _clean_str(row.get(store_col))
            if not store_name:
                skipped += 1
                continue
            store_code = normalize_store_code(store_name)
            if store_filter and store_code != store_filter:
                continue

            kaspi_article = _clean_str(row.get(article_col))
            sku_key = _clean_str(row.get(sku_key_col))
            if not kaspi_article or not sku_key:
                skipped += 1
                continue

            sku_id = _clean_str(row.get(sku_id_col)) if sku_id_col else None
            parsed_size = None
            if not sku_id:
                parsed_key, parsed_id, parsed_size = _parse_article_for_sku(kaspi_article)
                if parsed_key and parsed_id:
                    sku_key = sku_key or parsed_key
                    sku_id = parsed_id
            if not sku_id:
                raw_size = _clean_str(row.get(size_col)) if size_col else None
                norm_size = normalize_size(raw_size) if raw_size else None
                if norm_size:
                    sku_id = f"{sku_key}_{norm_size}"
                    parsed_size = norm_size

            kaspi_offer_name = _clean_str(row.get(offer_col)) if offer_col else None
            kaspi_name_core = _clean_str(row.get(name_core_col)) if name_core_col else None
            if not kaspi_name_core and kaspi_offer_name:
                kaspi_name_core = extract_kaspi_name_core(kaspi_offer_name)

            model = _clean_str(row.get(model_col)) if model_col else None
            brand = _clean_str(row.get(brand_col)) if brand_col else None
            merchant_id = merchant_ids.get(store_code)

            if sku_key and not _value_exists(conn, "dim_sku", "sku_key", sku_key):
                missing_sku_key += 1
                sku_key = None
            if sku_id and not _value_exists(conn, "dim_sku_size", "sku_id", sku_id):
                sku_key, sku_id = _maybe_kid_to_men(conn, sku_key, sku_id, parsed_size)
            if sku_id and not _value_exists(conn, "dim_sku_size", "sku_id", sku_id):
                if sku_key and _value_exists(conn, "dim_sku", "sku_key", sku_key):
                    my_size = parsed_size or sku_id.split("_")[-1]
                    if apply_changes:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO dim_sku_size (sku_id, sku_key, my_size)
                            VALUES (?, ?, ?)
                            """,
                            (sku_id, sku_key, my_size),
                        )
                    else:
                        pass
                if not _value_exists(conn, "dim_sku_size", "sku_id", sku_id):
                    missing_sku_id += 1
                    sku_id = None

            existing = conn.execute(
                "SELECT id FROM dim_kaspi_article_map WHERE store_code = ? AND kaspi_article = ?",
                (store_code, kaspi_article),
            ).fetchone()

            if existing:
                if apply_changes:
                    conn.execute(
                        """
                        UPDATE dim_kaspi_article_map
                        SET kaspi_offer_name = ?,
                            kaspi_name_core = ?,
                            sku_key = ?,
                            sku_id = ?,
                            model = ?,
                            brand = ?,
                            merchant_id = ?,
                            source = ?,
                            updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (
                            kaspi_offer_name,
                            kaspi_name_core,
                            sku_key,
                            sku_id,
                            model,
                            brand,
                            merchant_id,
                            f"CRM:{sheet}",
                            existing[0],
                        ),
                    )
                updated += 1
            else:
                if apply_changes:
                    conn.execute(
                        """
                        INSERT INTO dim_kaspi_article_map (
                            store_code, merchant_id, kaspi_article, kaspi_offer_name,
                            kaspi_name_core, sku_key, sku_id, model, brand, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            store_code,
                            merchant_id,
                            kaspi_article,
                            kaspi_offer_name,
                            kaspi_name_core,
                            sku_key,
                            sku_id,
                            model,
                            brand,
                            f"CRM:{sheet}",
                        ),
                    )
                inserted += 1

    print("Kaspi article map import")
    print(f"  Workbook: {workbook}")
    print(f"  Sheet: {sheet}")
    if store_filter:
        print(f"  Store filter: {store_filter}")
    print(f"  Inserted: {inserted}")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Missing sku_key (nullified): {missing_sku_key}")
    print(f"  Missing sku_id (nullified): {missing_sku_id}")
    if not apply_changes:
        print("  Dry-run only (no DB writes)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Kaspi article mapping from CRM workbook")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to sqlite DB")
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK), help="Path to CRM workbook")
    parser.add_argument("--sheet", default=DEFAULT_SHEET, help="Sheet name to import")
    parser.add_argument("--store", default=None, help="Optional store code filter (e.g., STOREB)")
    parser.add_argument("--apply", action="store_true", help="Apply changes to DB (default is dry-run)")
    args = parser.parse_args()

    import_map(
        db_path=Path(args.db),
        workbook=Path(args.workbook),
        sheet=args.sheet,
        store_filter=args.store,
        apply_changes=args.apply,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
