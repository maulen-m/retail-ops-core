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
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple

import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_db
from core.ingest.sales_ingest import normalize_store_code
from core.utils.sku_map import extract_kaspi_name_core


DEFAULT_WORKBOOK = Path("excel_ui/SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_DB = Path("db/app.db")
DEFAULT_OUTPUT_ROOT = Path("exports/validation/workbook_catalog_offer_map_sync")
DEFAULT_BACKUP_ROOT = Path("runtime/backups")
WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"
LINE61_PREFIX = "OF_SUIT-61_BLK_"
LINE61_SKU_KEY = "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
LINE61_CORE = "6в1_Черный_+Сумка"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm_article(value: Any) -> str:
    article = _clean(value)
    article = re.sub(r"^[\d\s]+", "", article).strip()
    return article.upper()


def build_core_majority_map(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], str]:
    counts: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        store = _clean(row.get("store_code"))
        core = _clean(row.get("kaspi_name_core"))
        sku = _clean(row.get("sku_key"))
        if not core or not sku:
            continue
        counts[(store, core)][sku] += 1

    out: Dict[Tuple[str, str], str] = {}
    for key, sku_counts in counts.items():
        chosen = sorted(sku_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        out[key] = chosen
    return out


def _choose_best_text(rows: List[Dict[str, Any]], field_name: str) -> str:
    counts: Dict[str, float] = defaultdict(float)
    for row in rows:
        value = _clean(row.get(field_name))
        if not value:
            continue
        counts[value] += float(row.get("weight") or 1.0)
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def choose_best_identity(article: str, rows: List[Dict[str, Any]]) -> Dict[str, str]:
    chosen_offer = _choose_best_text(rows, "kaspi_offer_name")
    if article.upper().startswith(LINE61_PREFIX):
        return {
            "sku_key": LINE61_SKU_KEY,
            "kaspi_name_core": LINE61_CORE,
            "kaspi_offer_name": chosen_offer,
        }

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
                return {"sku_key": "", "kaspi_name_core": core, "kaspi_offer_name": chosen_offer}
        return {"sku_key": "", "kaspi_name_core": "", "kaspi_offer_name": chosen_offer}

    chosen_sku = sorted(by_sku.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    core_candidates = [(k, w) for k, w in by_core.items() if k[0] == chosen_sku]
    if core_candidates:
        chosen_core = sorted(core_candidates, key=lambda kv: (-kv[1], kv[0][1]))[0][0][1]
    else:
        chosen_core = ""

    return {"sku_key": chosen_sku, "kaspi_name_core": chosen_core, "kaspi_offer_name": chosen_offer}


def _load_rows_from_crm(workbook: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(workbook, sheet_name=sheet)


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    import sqlite3

    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_crm_identity_rebuild_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _build_report_paths(*, output_root: Path, as_of: date) -> tuple[Path, Path]:
    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "crm_identity_rebuild.json", out_dir / "crm_identity_rebuild.md"


def rebuild_identity_map(
    workbook: Path,
    sheet: str,
    dry_run: bool = True,
    *,
    db_path: Path = DEFAULT_DB,
    as_of: date | None = None,
    output_root: Path | None = None,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
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

    normalized_rows: List[Dict[str, Any]] = []
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
        normalized_rows.append(
            {
                "store_code": store_code,
                "kaspi_article": article,
                "sku_key": sku_key,
                "kaspi_name_core": core,
                "kaspi_offer_name": _clean(row.get(offer_col)) if offer_col else "",
                "weight": 1.0,
            }
        )

    core_majority = build_core_majority_map(normalized_rows)
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in normalized_rows:
        sku_key = row["sku_key"] or core_majority.get((row["store_code"], row["kaspi_name_core"])) or ""
        grouped[(row["store_code"], row["kaspi_article"])].append(
            {
                "kaspi_article": row["kaspi_article"],
                "sku_key": sku_key,
                "kaspi_name_core": row["kaspi_name_core"],
                "kaspi_offer_name": row["kaspi_offer_name"],
                "weight": row["weight"],
            }
        )

    inserted = 0
    updated = 0
    skipped = 0
    skipped_fk = 0
    backup_path: Path | None = None
    report_json: Path | None = None
    report_md: Path | None = None

    if not dry_run and str(os.environ.get(WRITE_ENV_GATE) or "").strip() != "1":
        raise RuntimeError(f"{WRITE_ENV_GATE}=1 is required with --apply")
    if as_of and output_root:
        report_json, report_md = _build_report_paths(output_root=output_root, as_of=as_of)

    with get_db(db_path) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone()
        if not has_table:
            raise RuntimeError("dim_kaspi_article_map missing")
        if not dry_run:
            backup_path = _backup_db(db_path, backup_root)
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
            offer_name = _clean(chosen.get("kaspi_offer_name"))
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
                SELECT id, sku_key, kaspi_name_core, kaspi_offer_name
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
                old_offer_name = _clean(existing["kaspi_offer_name"])
                if old_sku == sku_key and old_core == core and old_offer_name == offer_name:
                    skipped += 1
                    continue
                if not dry_run:
                    conn.execute(
                        """
                        UPDATE dim_kaspi_article_map
                        SET sku_key = ?, kaspi_name_core = ?, kaspi_offer_name = ?, source = 'crm_historical_patch'
                        WHERE id = ?
                        """,
                        (sku_key or old_sku, core or old_core, offer_name or old_offer_name, existing["id"]),
                    )
                updated += 1
                continue

            if not dry_run:
                conn.execute(
                    """
                    INSERT INTO dim_kaspi_article_map (
                        store_code, kaspi_article, kaspi_offer_name, kaspi_name_core, sku_key, source
                    ) VALUES (?, ?, ?, ?, ?, 'crm_historical_patch')
                    """,
                    (store_code, article, offer_name, core, sku_key),
                )
            inserted += 1

    report = {
        "grouped_keys": len(grouped),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "skipped_fk": skipped_fk,
        "status": "APPLIED" if not dry_run else "DRY_RUN",
        "workbook": str(Path(workbook).resolve()),
        "sheet": sheet,
        "db_path": str(Path(db_path).resolve()),
        "backup_path": str(backup_path) if backup_path else "",
        "report_json": str(report_json) if report_json else "",
        "report_md": str(report_md) if report_md else "",
    }
    if report_json:
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report_md:
        lines = [
            "# CRM Identity Rebuild",
            "",
            f"- workbook: `{Path(workbook).resolve()}`",
            f"- sheet: `{sheet}`",
            f"- status: `{report['status']}`",
            f"- grouped_keys: `{report['grouped_keys']}`",
            f"- inserted: `{inserted}`",
            f"- updated: `{updated}`",
            f"- skipped: `{skipped}`",
            f"- skipped_fk: `{skipped_fk}`",
        ]
        if backup_path:
            lines.append(f"- backup_path: `{backup_path}`")
        report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rebuild Kaspi article identity map from CRM history")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    p.add_argument("--sheet", default=DEFAULT_SHEET)
    p.add_argument("--as-of", default=None)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    p.add_argument("--apply", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    stats = rebuild_identity_map(
        args.workbook,
        args.sheet,
        dry_run=not args.apply,
        db_path=args.db,
        as_of=date.fromisoformat(args.as_of) if args.as_of else None,
        output_root=args.output_root,
        backup_root=args.backup_root,
    )
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Kaspi identity rebuild {mode}")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
