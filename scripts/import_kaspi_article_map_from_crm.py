#!/usr/bin/env python3
"""
Import Kaspi article mapping from CRM workbook catalog into dim_kaspi_article_map.

Primary workbook truth for this import is:
- SKU_ID_KSP
- SKU_key
- Kaspi_name_core

Store values in the workbook are treated as informational only. By default, catalog
rows are seeded for every configured store so future offers are mapped before sales appear.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Any
import sys

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db  # noqa: E402
from core.ingest.sales_ingest import normalize_store_code  # noqa: E402
from core.utils.sku_normalize import normalize_size  # noqa: E402

DEFAULT_WORKBOOK = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_ANCHORED_WORKBOOK = PROJECT_ROOT / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
DEFAULT_SHEET = "M02_SKU_CATALOG_NC"
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "workbook_catalog_offer_map_sync"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"


class WorkbookOfferMapSyncError(RuntimeError):
    """Raised when workbook offer mapping sync cannot proceed safely."""


def _resolve_default_workbook() -> Path:
    return DEFAULT_ANCHORED_WORKBOOK if DEFAULT_ANCHORED_WORKBOOK.exists() else DEFAULT_WORKBOOK


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


def _load_store_catalog() -> dict[str, dict[str, str | None]]:
    cfg = _load_yaml(PROJECT_ROOT / "config" / "kaspi_stores.yaml")
    stores = cfg.get("stores", {}) if isinstance(cfg, dict) else {}
    out: dict[str, dict[str, str | None]] = {}
    for raw_code, info in stores.items():
        store_code = normalize_store_code(str(raw_code))
        merchant_uid = None
        if isinstance(info, dict):
            merchant_uid = _clean_str(info.get("merchant_uid"))
        out[store_code] = {"merchant_id": merchant_uid}
    return out


def _target_stores(
    *,
    store_catalog: dict[str, dict[str, str | None]],
    row_store_name: str | None,
    store_filter: str | None,
) -> list[str]:
    if store_filter:
        return [normalize_store_code(store_filter)]
    configured = sorted(code for code in store_catalog if code)
    if configured:
        return configured
    if row_store_name:
        return [normalize_store_code(row_store_name)]
    raise WorkbookOfferMapSyncError("no target stores resolved from config/kaspi_stores.yaml or workbook row")


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    import sqlite3

    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_workbook_catalog_map_sync_{stamp}.sqlite"
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
    return out_dir / "workbook_catalog_offer_map_sync.json", out_dir / "workbook_catalog_offer_map_sync.md"


def import_map(
    db_path: Path,
    workbook: Path,
    sheet: str,
    store_filter: str | None,
    apply_changes: bool,
    *,
    as_of: date | None = None,
    output_root: Path | None = None,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
) -> dict[str, Any]:
    workbook = workbook.expanduser()
    if not workbook.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook}")

    df = pd.read_excel(workbook, sheet_name=sheet, dtype=str)
    cols = _normalize_columns(df)

    store_col = _pick_col(cols, "Store_name", "STORE_NAME")
    article_col = _pick_col(cols, "SKU_ID_KSP", "sku_id_ksp")
    article_v2_col = _pick_col(cols, "SKU_ID_KSP_v2", "sku_id_ksp_v2")
    sku_key_col = _pick_col(cols, "SKU_key", "sku_key")
    sku_id_col = _pick_col(cols, "SKU_ID", "sku_id")
    size_col = _pick_col(cols, "MY_SIZE", "Size_kaspi", "my_size", "size_kaspi")
    offer_col = _pick_col(cols, "Kaspi_offer_name", "KASPI_OFFER_NAME", "Kaspi_name_source")
    name_core_col = _pick_col(cols, "Kaspi_name_core", "kaspi_name_core")
    model_col = _pick_col(cols, "Model")
    brand_col = _pick_col(cols, "Brand")

    missing = [
        name
        for name, col in {
            "SKU_ID_KSP": article_col or article_v2_col,
            "SKU_key": sku_key_col,
        }.items()
        if col is None
    ]
    if missing:
        raise ValueError(f"Missing required columns in sheet {sheet}: {missing}")

    store_catalog = _load_store_catalog()

    if apply_changes and str(os.environ.get("ENABLE_KASPI_WORKBOOK_MAP_SYNC") or "").strip() != "1":
        raise WorkbookOfferMapSyncError("ENABLE_KASPI_WORKBOOK_MAP_SYNC=1 is required for --apply")

    inserted = 0
    updated = 0
    unchanged = 0
    skipped = 0
    missing_sku_key = 0
    missing_sku_id = 0
    created_sku_size = 0
    candidate_count = 0
    per_store_rows: dict[str, int] = {}

    report_json: Path | None = None
    report_md: Path | None = None
    backup_path: Path | None = None
    if as_of and output_root:
        report_json, report_md = _build_report_paths(output_root=output_root, as_of=as_of)

    with get_db(db_path) as conn:
        if not _table_exists(conn, "dim_kaspi_article_map"):
            raise RuntimeError("dim_kaspi_article_map not found. Run scripts/migrate_020_kaspi_article_map.py first.")

        if apply_changes:
            backup_path = _backup_db(db_path, backup_root)

        for _, row in df.iterrows():
            row_store_name = _clean_str(row.get(store_col)) if store_col else None
            kaspi_article = _clean_str(row.get(article_col)) if article_col else None
            if not kaspi_article and article_v2_col:
                kaspi_article = _clean_str(row.get(article_v2_col))
            sku_key = _clean_str(row.get(sku_key_col)) if sku_key_col else None
            if not kaspi_article or not sku_key:
                skipped += 1
                continue

            raw_sku_id = _clean_str(row.get(sku_id_col)) if sku_id_col else None
            raw_size = _clean_str(row.get(size_col)) if size_col else None
            norm_size = normalize_size(raw_size) if raw_size else None
            sku_id = raw_sku_id if raw_sku_id and _value_exists(conn, "dim_sku_size", "sku_id", raw_sku_id) else None

            kaspi_offer_name = _clean_str(row.get(offer_col)) if offer_col else None
            kaspi_name_core = _clean_str(row.get(name_core_col)) if name_core_col else None
            model = _clean_str(row.get(model_col)) if model_col else None
            brand = _clean_str(row.get(brand_col)) if brand_col else None

            if sku_key and not _value_exists(conn, "dim_sku", "sku_key", sku_key):
                missing_sku_key += 1
                sku_key = None

            if not sku_id and sku_key and norm_size:
                candidate_sku_id = f"{sku_key}_{norm_size}"
                if _value_exists(conn, "dim_sku_size", "sku_id", candidate_sku_id):
                    sku_id = candidate_sku_id
                elif apply_changes:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO dim_sku_size (sku_id, sku_key, my_size)
                        VALUES (?, ?, ?)
                        """,
                        (candidate_sku_id, sku_key, norm_size),
                    )
                    if _value_exists(conn, "dim_sku_size", "sku_id", candidate_sku_id):
                        created_sku_size += 1
                        sku_id = candidate_sku_id

            if sku_key and not sku_id:
                missing_sku_id += 1

            if not sku_key:
                skipped += 1
                continue

            target_stores = _target_stores(
                store_catalog=store_catalog,
                row_store_name=row_store_name,
                store_filter=store_filter,
            )
            for store_code in target_stores:
                candidate_count += 1
                per_store_rows[store_code] = per_store_rows.get(store_code, 0) + 1
                merchant_id = _clean_str(store_catalog.get(store_code, {}).get("merchant_id")) if store_catalog else None
                existing = conn.execute(
                    "SELECT id, kaspi_offer_name, kaspi_name_core, sku_key, sku_id, model, brand FROM dim_kaspi_article_map WHERE store_code = ? AND kaspi_article = ?",
                    (store_code, kaspi_article),
                ).fetchone()

                if existing:
                    existing_values = {
                        "kaspi_offer_name": _clean_str(existing[1]),
                        "kaspi_name_core": _clean_str(existing[2]),
                        "sku_key": _clean_str(existing[3]),
                        "sku_id": _clean_str(existing[4]),
                        "model": _clean_str(existing[5]),
                        "brand": _clean_str(existing[6]),
                    }
                    next_values = {
                        "kaspi_offer_name": kaspi_offer_name,
                        "kaspi_name_core": kaspi_name_core,
                        "sku_key": sku_key,
                        "sku_id": sku_id,
                        "model": model,
                        "brand": brand,
                    }
                    if existing_values == next_values:
                        unchanged += 1
                        continue
                    if apply_changes:
                        conn.execute(
                            """
                            UPDATE dim_kaspi_article_map
                            SET merchant_id = ?,
                                kaspi_offer_name = ?,
                                kaspi_name_core = ?,
                                sku_key = ?,
                                sku_id = ?,
                                model = ?,
                                brand = ?,
                                source = ?,
                                updated_at = datetime('now')
                            WHERE id = ?
                            """,
                            (
                                merchant_id,
                                kaspi_offer_name,
                                kaspi_name_core,
                                sku_key,
                                sku_id,
                                model,
                                brand,
                                f"CRM:{sheet}",
                                existing[0],
                            ),
                        )
                    updated += 1
                    continue

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

    report = {
        "workbook": str(workbook),
        "sheet": sheet,
        "store_filter": normalize_store_code(store_filter) if store_filter else None,
        "candidate_count": candidate_count,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "missing_sku_key": missing_sku_key,
        "missing_sku_id": missing_sku_id,
        "created_sku_size": created_sku_size,
        "stores_seeded": sorted(per_store_rows),
        "rows_per_store": per_store_rows,
        "status": "APPLIED" if apply_changes else "DRY_RUN",
        "backup_path": str(backup_path) if backup_path else "",
        "report_json": str(report_json) if report_json else "",
        "report_md": str(report_md) if report_md else "",
    }

    if report_json:
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report_md:
        lines = [
            "# Workbook Catalog Offer Map Sync",
            "",
            f"- workbook: `{workbook}`",
            f"- sheet: `{sheet}`",
            f"- status: `{report['status']}`",
            f"- candidate_count: `{candidate_count}`",
            f"- inserted: `{inserted}`",
            f"- updated: `{updated}`",
            f"- unchanged: `{unchanged}`",
            f"- skipped: `{skipped}`",
            f"- missing_sku_key: `{missing_sku_key}`",
            f"- missing_sku_id: `{missing_sku_id}`",
            f"- created_sku_size: `{created_sku_size}`",
            f"- stores_seeded: `{', '.join(report['stores_seeded'])}`",
        ]
        if backup_path:
            lines.append(f"- backup_path: `{backup_path}`")
        report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Kaspi article mapping from CRM workbook catalog")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to sqlite DB")
    parser.add_argument("--workbook", default=str(_resolve_default_workbook()), help="Path to CRM workbook")
    parser.add_argument("--sheet", default=DEFAULT_SHEET, help="Sheet name to import")
    parser.add_argument("--store", default=None, help="Optional store code filter (default seeds all stores)")
    parser.add_argument("--as-of", default=None, help="Optional as-of date for artifact output")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Artifact output root")
    parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT), help="Backup output root")
    parser.add_argument("--apply", action="store_true", help="Apply changes to DB (default is dry-run)")
    args = parser.parse_args()

    report = import_map(
        db_path=Path(args.db),
        workbook=Path(args.workbook),
        sheet=args.sheet,
        store_filter=args.store,
        apply_changes=args.apply,
        as_of=date.fromisoformat(args.as_of) if args.as_of else None,
        output_root=Path(args.output_root),
        backup_root=Path(args.backup_root),
    )
    print("Kaspi article map import")
    print(f"  Workbook: {report['workbook']}")
    print(f"  Sheet: {report['sheet']}")
    if report["store_filter"]:
        print(f"  Store filter: {report['store_filter']}")
    print(f"  Candidate count: {report['candidate_count']}")
    print(f"  Inserted: {report['inserted']}")
    print(f"  Updated: {report['updated']}")
    print(f"  Unchanged: {report['unchanged']}")
    print(f"  Skipped: {report['skipped']}")
    print(f"  Missing sku_key: {report['missing_sku_key']}")
    print(f"  Missing sku_id: {report['missing_sku_id']}")
    print(f"  Created sku_size rows: {report['created_sku_size']}")
    print(f"  Status: {report['status']}")
    if report["backup_path"]:
        print(f"  Backup: {report['backup_path']}")
    if report["report_json"]:
        print(f"  Report JSON: {report['report_json']}")
    if report["report_md"]:
        print(f"  Report MD: {report['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
