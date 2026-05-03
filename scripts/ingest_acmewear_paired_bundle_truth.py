#!/usr/bin/env python3
"""Ingest ACMEWEAR paired bundle compact identity truth into SQLite."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "acmewear_bundle_stage2"
APPLY_ENV = "ENABLE_ACMEWEAR_BUNDLE_TRUTH_APPLY"
SOURCE = "ACMEWEAR_PAIRED_BUNDLE_STAGE2_2026-04-25"
STORE_CODE = "ACMEWEAR"
BRAND = "ACMEWEAR"


@dataclass(frozen=True)
class BundleFamily:
    sku_key: str
    model: str
    color: str
    product_type: str = "CL"
    category: str = "BUNDLE"
    gender: str = "MEN"


SIZE_ROWS = [
    ("S", "42", 1),
    ("M", "44", 2),
    ("L", "46", 3),
    ("XL", "48", 4),
    ("XL", "50", 4),
    ("2XL", "52", 5),
    ("3XL", "54", 6),
    ("4XL", "56", 7),
    ("4XL", "58", 7),
    ("4XL", "60", 7),
]

NORMALIZED_SIZES = [
    ("S", 1),
    ("M", 2),
    ("L", 3),
    ("XL", 4),
    ("2XL", 5),
    ("3XL", 6),
    ("4XL", 7),
]

FAMILIES = [
    BundleFamily("SUIT-21-LS", "SUIT-21-LS", "BLACK"),
    BundleFamily("SUIT-21-TS", "SUIT-21-TS", "BLACK"),
    BundleFamily("SUIT-31-LS", "SUIT-31-LS", "BLACK"),
    BundleFamily("SUIT-31-TS", "SUIT-31-TS", "BLACK"),
    BundleFamily("SUIT-21-TK", "SUIT-21-TK", "BLACK"),
    BundleFamily("SUIT-31-TK", "SUIT-31-TK", "BLACK"),
    BundleFamily("LINE-21-LS", "LINE-21-LS", "BLACK_WHITE"),
    BundleFamily("LINE-21-TS", "LINE-21-TS", "BLACK_WHITE"),
    BundleFamily("LINE-31-LS", "LINE-31-LS", "BLACK_WHITE"),
    BundleFamily("LINE-31-TS", "LINE-31-TS", "BLACK_WHITE"),
]


class IngestError(RuntimeError):
    pass


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_acmewear_bundle_stage2_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _require_schema(conn: sqlite3.Connection) -> None:
    required = {"dim_store", "dim_sku", "dim_sku_size", "dim_kaspi_article_map"}
    missing = sorted(table for table in required if not _table_exists(conn, table))
    if missing:
        raise IngestError(f"missing required tables: {', '.join(missing)}")
    store = conn.execute(
        "SELECT 1 FROM dim_store WHERE UPPER(TRIM(store_code)) = ?",
        (STORE_CODE,),
    ).fetchone()
    if not store:
        raise IngestError(f"missing dim_store row: {STORE_CODE}")


def _article_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for family in FAMILIES:
        for category_token in ("ST", "TRM"):
            for my_size, size_rus, _ in SIZE_ROWS:
                token = f"{family.sku_key}-{category_token}-{my_size}-{size_rus}"
                rows.append(
                    {
                        "store_code": STORE_CODE,
                        "kaspi_article": token,
                        "kaspi_offer_name": token,
                        "kaspi_name_core": f"{family.sku_key}-{category_token}",
                        "sku_key": family.sku_key,
                        "sku_id": f"{family.sku_key}_{my_size}",
                        "model": family.model,
                        "brand": BRAND,
                        "source": SOURCE,
                    }
                )
    return rows


def _snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    sku_keys = tuple(family.sku_key for family in FAMILIES)
    placeholders = ",".join("?" for _ in sku_keys)
    article_rows = _article_rows()
    article_tokens = tuple(row["kaspi_article"] for row in article_rows)
    article_placeholders = ",".join("?" for _ in article_tokens)

    dim_sku_count = conn.execute(
        f"SELECT COUNT(*) AS c FROM dim_sku WHERE sku_key IN ({placeholders})",
        sku_keys,
    ).fetchone()["c"]
    dim_sku_size_count = conn.execute(
        f"SELECT COUNT(*) AS c FROM dim_sku_size WHERE sku_key IN ({placeholders})",
        sku_keys,
    ).fetchone()["c"]
    article_count = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM dim_kaspi_article_map
        WHERE UPPER(TRIM(store_code)) = ?
          AND kaspi_article IN ({article_placeholders})
        """,
        (STORE_CODE, *article_tokens),
    ).fetchone()["c"]
    wrong_article_count = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM dim_kaspi_article_map
        WHERE UPPER(TRIM(store_code)) = ?
          AND kaspi_article IN ({article_placeholders})
          AND (
              sku_key IS NULL
              OR sku_id IS NULL
              OR sku_key || '_' || substr(sku_id, length(sku_key) + 2) != sku_id
          )
        """,
        (STORE_CODE, *article_tokens),
    ).fetchone()["c"]
    return {
        "dim_sku_count": int(dim_sku_count),
        "dim_sku_size_count": int(dim_sku_size_count),
        "dim_kaspi_article_map_count": int(article_count),
        "dim_kaspi_article_map_wrong_shape_count": int(wrong_article_count),
    }


def _execute_upserts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {
        "dim_sku_upserts": 0,
        "dim_sku_size_upserts": 0,
        "dim_kaspi_article_map_upserts": 0,
    }

    for family in FAMILIES:
        conn.execute(
            """
            INSERT INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg,
                category, gender, active_flag
            )
            VALUES (?, ?, ?, ?, 0.0, 0.0, ?, ?, 1)
            ON CONFLICT(sku_key) DO UPDATE SET
                model=excluded.model,
                color=excluded.color,
                product_type=excluded.product_type,
                category=excluded.category,
                gender=excluded.gender,
                active_flag=1,
                updated_at=datetime('now')
            """,
            (
                family.sku_key,
                family.model,
                family.color,
                family.product_type,
                family.category,
                family.gender,
            ),
        )
        counts["dim_sku_upserts"] += 1

    for family in FAMILIES:
        for my_size, size_order in NORMALIZED_SIZES:
            conn.execute(
                """
                INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order, active_flag)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(sku_id) DO UPDATE SET
                    sku_key=excluded.sku_key,
                    my_size=excluded.my_size,
                    size_order=excluded.size_order,
                    active_flag=1
                """,
                (f"{family.sku_key}_{my_size}", family.sku_key, my_size, size_order),
            )
            counts["dim_sku_size_upserts"] += 1

    for row in _article_rows():
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, kaspi_name_core,
                sku_key, sku_id, model, brand, source, active_flag
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(store_code, kaspi_article) DO UPDATE SET
                kaspi_offer_name=excluded.kaspi_offer_name,
                kaspi_name_core=excluded.kaspi_name_core,
                sku_key=excluded.sku_key,
                sku_id=excluded.sku_id,
                model=excluded.model,
                brand=excluded.brand,
                source=excluded.source,
                active_flag=1,
                updated_at=datetime('now')
            """,
            (
                row["store_code"],
                row["kaspi_article"],
                row["kaspi_offer_name"],
                row["kaspi_name_core"],
                row["sku_key"],
                row["sku_id"],
                row["model"],
                row["brand"],
                row["source"],
            ),
        )
        counts["dim_kaspi_article_map_upserts"] += 1

    return counts


def run_ingest(
    *,
    db_path: Path,
    backup_root: Path,
    output_root: Path,
    apply: bool,
) -> dict[str, Any]:
    if not db_path.exists():
        raise IngestError(f"db path does not exist: {db_path}")
    if apply and str(os.environ.get(APPLY_ENV) or "").strip() != "1":
        raise IngestError(f"{APPLY_ENV}=1 is required with --apply")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_path = None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _require_schema(conn)
        before = _snapshot(conn)
        upsert_counts = {
            "dim_sku_upserts": len(FAMILIES),
            "dim_sku_size_upserts": len(FAMILIES) * len(NORMALIZED_SIZES),
            "dim_kaspi_article_map_upserts": len(_article_rows()),
        }
        status = "DRY_RUN"
        if apply:
            backup_path = _backup_db(db_path, backup_root)
            upsert_counts = _execute_upserts(conn)
            conn.commit()
            status = "APPLIED"
        after = _snapshot(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    report = {
        "status": status,
        "db_path": str(db_path),
        "backup_path": str(backup_path) if backup_path else "",
        "source": SOURCE,
        "store_code": STORE_CODE,
        "target_counts": {
            "dim_sku": len(FAMILIES),
            "dim_sku_size": len(FAMILIES) * len(NORMALIZED_SIZES),
            "dim_kaspi_article_map": len(_article_rows()),
        },
        "upsert_counts": upsert_counts,
        "before": before,
        "after": after,
        "report_dir": str(output_dir),
    }
    report_path = output_dir / "acmewear_bundle_stage2_ingest_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true", help="Apply DB upserts. Default is dry run.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_ingest(
        db_path=args.db,
        backup_root=args.backup_root,
        output_root=args.output_root,
        apply=args.apply,
    )
    print(
        "acmewear_bundle_stage2_ingest: "
        f"status={report['status']} db={report['db_path']} "
        f"backup={report['backup_path'] or 'NONE'} report={report['report_path']}"
    )
    print("target_counts: " + json.dumps(report["target_counts"], sort_keys=True))
    print("upsert_counts: " + json.dumps(report["upsert_counts"], sort_keys=True))
    print("before: " + json.dumps(report["before"], sort_keys=True))
    print("after: " + json.dumps(report["after"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
