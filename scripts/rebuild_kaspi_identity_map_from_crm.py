#!/usr/bin/env python3
"""
Rebuild dim_kaspi_article_map from historical CRM rows.

This is a deterministic fallback-map patcher:
- scans SALES_KSP_CRM_1 history
- chooses canonical (sku_key, kaspi_name_core) per kaspi article
- upserts into dim_kaspi_article_map
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_db
from core.ingest.sales_ingest import normalize_store_code
from core.utils.sku_map import extract_kaspi_name_core


DEFAULT_WORKBOOK = Path("excel_ui/SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
LINE61_PREFIX = "OF_SUIT-61_BLK_"
LINE61_SKU_KEY = "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
LINE61_CORE = "6в1_Черный_+Сумка"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm_article(value: Any) -> str:
    return _clean(value).upper()


def choose_best_identity(article: str, rows: List[Dict[str, Any]]) -> Dict[str, str]:
    if article.upper().startswith(LINE61_PREFIX):
        return {"sku_key": LINE61_SKU_KEY, "kaspi_name_core": LINE61_CORE}

    by_sku: Dict[str, float] = defaultdict(float)
    by_core: Dict[Tuple[str, str], float] = defaultdict(float)

    for row in rows:
        sku_key = _clean(row.get("sku_key"))
        core = _clean(row.get("kaspi_name_core"))
        weight = float(row.get("weight") or 1.0)
        if not sku_key:
            continue
        by_sku[sku_key] += weight
        if core:
            by_core[(sku_key, core)] += weight

    if not by_sku:
        # fallback: use any extracted core if present
        for row in rows:
            core = _clean(row.get("kaspi_name_core"))
            if core:
                return {"sku_key": "", "kaspi_name_core": core}
        return {"sku_key": "", "kaspi_name_core": ""}

    chosen_sku = sorted(by_sku.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    core_candidates = [(k, w) for k, w in by_core.items() if k[0] == chosen_sku]
    if core_candidates:
        chosen_core = sorted(core_candidates, key=lambda kv: (-kv[1], kv[0][1]))[0][0][1]
    else:
        chosen_core = ""

    return {"sku_key": chosen_sku, "kaspi_name_core": chosen_core}


def _load_rows_from_crm(workbook: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(workbook, sheet_name=sheet)


def rebuild_identity_map(
    workbook: Path,
    sheet: str,
    dry_run: bool = True,
) -> Dict[str, int]:
    df = _load_rows_from_crm(workbook, sheet)
    cols = {str(c).strip().lower(): c for c in df.columns}
    article_col = cols.get("артикул")
    sku_key_col = cols.get("sku_key")
    core_col = cols.get("kaspi_name_core")
    offer_col = cols.get("название товара в kaspi магазине")
    store_col = cols.get("store_name")

    if not article_col or not sku_key_col:
        raise RuntimeError("Required columns missing: Артикул, SKU_key")

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for _, row in df.iterrows():
        article = _norm_article(row.get(article_col))
        if not article:
            continue
        store = _clean(row.get(store_col))
        store_code = normalize_store_code(store) if store else ""
        sku_key = _clean(row.get(sku_key_col))
        core = _clean(row.get(core_col)) if core_col else ""
        if not core and offer_col:
            core = extract_kaspi_name_core(_clean(row.get(offer_col)))
        grouped[(store_code, article)].append(
            {
                "kaspi_article": article,
                "sku_key": sku_key,
                "kaspi_name_core": core,
                "weight": 1.0,
            }
        )

    inserted = 0
    updated = 0
    skipped = 0
    skipped_fk = 0

    with get_db() as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone()
        if not has_table:
            raise RuntimeError("dim_kaspi_article_map missing")
        valid_store_codes = {
            str(r[0]).strip()
            for r in conn.execute("SELECT store_code FROM dim_store").fetchall()
            if str(r[0]).strip()
        }
        valid_sku_keys = {
            str(r[0]).strip()
            for r in conn.execute("SELECT sku_key FROM dim_sku").fetchall()
            if str(r[0]).strip()
        }

        for (store_code, article), rows in grouped.items():
            chosen = choose_best_identity(article, rows)
            sku_key = _clean(chosen.get("sku_key"))
            core = _clean(chosen.get("kaspi_name_core"))
            if not sku_key and not core:
                skipped += 1
                continue
            if store_code and store_code not in valid_store_codes:
                skipped_fk += 1
                continue
            if sku_key and sku_key not in valid_sku_keys:
                skipped_fk += 1
                continue

            existing = conn.execute(
                """
                SELECT id, sku_key, kaspi_name_core
                FROM dim_kaspi_article_map
                WHERE store_code = ? AND kaspi_article = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (store_code, article),
            ).fetchone()

            if existing:
                old_sku = _clean(existing["sku_key"])
                old_core = _clean(existing["kaspi_name_core"])
                if old_sku == sku_key and old_core == core:
                    skipped += 1
                    continue
                if not dry_run:
                    conn.execute(
                        """
                        UPDATE dim_kaspi_article_map
                        SET sku_key = ?, kaspi_name_core = ?, source = 'crm_historical_patch'
                        WHERE id = ?
                        """,
                        (sku_key or old_sku, core or old_core, existing["id"]),
                    )
                updated += 1
                continue

            if not dry_run:
                conn.execute(
                    """
                    INSERT INTO dim_kaspi_article_map (
                        store_code, kaspi_article, kaspi_name_core, sku_key, source
                    ) VALUES (?, ?, ?, ?, 'crm_historical_patch')
                    """,
                    (store_code, article, core, sku_key),
                )
            inserted += 1

    return {
        "grouped_keys": len(grouped),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "skipped_fk": skipped_fk,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rebuild Kaspi article identity map from CRM history")
    p.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    p.add_argument("--sheet", default=DEFAULT_SHEET)
    p.add_argument("--apply", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    stats = rebuild_identity_map(args.workbook, args.sheet, dry_run=not args.apply)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Kaspi identity rebuild {mode}")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
