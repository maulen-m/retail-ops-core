#!/usr/bin/env python3
"""Ingest Web_automation ACMEWEAR child-bundle mappings into AB article-map truth."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAPPING_CSV = Path(
    "~/Docs/Web_automation/Docs/agent_handoffs/"
    "AUTONOMOUS_BUSINESS_ACMEWEAR_CHILD_BUNDLE_INGEST_20260503/"
    "acmewear_child_bundle_ab_mapping.csv"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "acmewear_child_bundle_ab_mapping"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"
APPLY_ENV = "ENABLE_ACMEWEAR_CHILD_BUNDLE_AB_MAPPING_APPLY"
SOURCE = "WEB_AUTOMATION_ACMEWEAR_CHILD_BUNDLE_2026-05-03"
BRAND = "ACMEWEAR"

REQUIRED_COLUMNS = {
    "store",
    "store_code",
    "card_group",
    "bundle_code",
    "parent_family",
    "parent_sku_key",
    "ab_sku_key_proposed",
    "merchant_article",
    "internal_size",
    "kaspi_name_core_required",
    "generic_fallback_to_avoid",
}

SIZE_ORDER = {
    "S": 1,
    "M": 2,
    "L": 3,
    "XL": 4,
    "2XL": 5,
    "3XL": 6,
    "4XL": 7,
}
FAMILY_COLOR = {
    "LINE61": "BLACK",
    "LINE51": "BLACK_WHITE",
}


class IngestError(RuntimeError):
    """Raised when the child-bundle mapping cannot be ingested safely."""


@dataclass(frozen=True)
class MappingRow:
    store_code: str
    merchant_id: str
    card_group: str
    bundle_code: str
    parent_family: str
    parent_sku_key: str
    ab_sku_key_proposed: str
    kaspi_article: str
    my_size: str
    kaspi_name_core: str
    generic_fallback_to_avoid: str
    sale_state: str
    color: str

    @property
    def sku_key(self) -> str:
        return self.bundle_code

    @property
    def sku_id(self) -> str:
        return f"{self.sku_key}_{self.my_size}"

    @property
    def technical_core(self) -> str:
        parts = self.kaspi_article.split("-")
        return "-".join(parts[:4]) if len(parts) >= 4 else self.kaspi_article

    @property
    def is_archived_sale_row(self) -> bool:
        return "archive" in self.sale_state.lower() or "no-stock" in self.sale_state.lower()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _load_mapping_rows(mapping_csv: Path, *, expected_rows: int | None = None) -> list[MappingRow]:
    if not mapping_csv.exists():
        raise FileNotFoundError(f"mapping CSV not found: {mapping_csv}")

    with mapping_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise IngestError(f"mapping CSV missing required columns: {missing}")
        raw_rows = list(reader)

    if expected_rows is not None and len(raw_rows) != expected_rows:
        raise IngestError(f"expected {expected_rows} mapping rows, found {len(raw_rows)}")

    rows: list[MappingRow] = []
    seen_articles: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_rows, start=2):
        store_code = _clean(raw.get("store")).upper()
        merchant_id = _clean(raw.get("store_code"))
        card_group = _clean(raw.get("card_group"))
        bundle_code = _clean(raw.get("bundle_code")).upper()
        parent_family = _clean(raw.get("parent_family")).upper()
        parent_sku_key = _clean(raw.get("parent_sku_key"))
        proposed = _clean(raw.get("ab_sku_key_proposed"))
        article = _clean(raw.get("merchant_article")).upper()
        my_size = _clean(raw.get("internal_size")).upper()
        core = _clean(raw.get("kaspi_name_core_required"))
        generic = _clean(raw.get("generic_fallback_to_avoid"))
        sale_state = _clean(raw.get("current_sale_state_after_20260503_stock_update"))

        if not all([store_code, merchant_id, card_group, bundle_code, parent_family, article, my_size, core]):
            raise IngestError(f"mapping CSV row {index} has blank required identity fields")
        if my_size not in SIZE_ORDER:
            raise IngestError(f"mapping CSV row {index} has unsupported internal_size={my_size!r}")
        if core == generic or core == "Спортивный_костюм_ACMEWEAR":
            raise IngestError(f"mapping CSV row {index} keeps generic fallback as required core")

        key = (store_code, article)
        if key in seen_articles:
            raise IngestError(f"duplicate mapping row for {store_code}/{article}")
        seen_articles.add(key)

        rows.append(
            MappingRow(
                store_code=store_code,
                merchant_id=merchant_id,
                card_group=card_group,
                bundle_code=bundle_code,
                parent_family=parent_family,
                parent_sku_key=parent_sku_key,
                ab_sku_key_proposed=proposed,
                kaspi_article=article,
                my_size=my_size,
                kaspi_name_core=core,
                generic_fallback_to_avoid=generic,
                sale_state=sale_state,
                color=FAMILY_COLOR.get(parent_family, ""),
            )
        )
    return rows


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _require_schema(conn: sqlite3.Connection) -> None:
    required = {"dim_store", "dim_sku", "dim_sku_size", "dim_kaspi_article_map"}
    missing = sorted(table for table in required if not _table_exists(conn, table))
    if missing:
        raise IngestError(f"missing required tables: {', '.join(missing)}")


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_acmewear_child_bundle_ab_mapping_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _existing_row(conn: sqlite3.Connection, row: MappingRow) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, kaspi_name_core, sku_key, sku_id, source
        FROM dim_kaspi_article_map
        WHERE store_code = ? AND kaspi_article = ?
        """,
        (row.store_code, row.kaspi_article),
    ).fetchone()


def _plan_changes(conn: sqlite3.Connection, rows: list[MappingRow]) -> dict[str, Any]:
    to_insert = 0
    to_update = 0
    unchanged = 0
    conflicts: list[dict[str, str]] = []

    for row in rows:
        existing = _existing_row(conn, row)
        if not existing:
            to_insert += 1
            continue

        existing_core = _clean(existing["kaspi_name_core"])
        existing_sku_key = _clean(existing["sku_key"]).upper()
        existing_sku_id = _clean(existing["sku_id"]).upper()
        allowed_old_cores = {
            "",
            row.kaspi_name_core,
            row.technical_core,
            row.generic_fallback_to_avoid,
            "Спортивный_костюм_ACMEWEAR",
        }
        if existing_sku_key and existing_sku_key != row.sku_key:
            conflicts.append(
                {
                    "article": row.kaspi_article,
                    "field": "sku_key",
                    "existing": existing_sku_key,
                    "expected": row.sku_key,
                }
            )
            continue
        if existing_sku_id and existing_sku_id != row.sku_id:
            conflicts.append(
                {
                    "article": row.kaspi_article,
                    "field": "sku_id",
                    "existing": existing_sku_id,
                    "expected": row.sku_id,
                }
            )
            continue
        if existing_core not in allowed_old_cores:
            conflicts.append(
                {
                    "article": row.kaspi_article,
                    "field": "kaspi_name_core",
                    "existing": existing_core,
                    "expected": row.kaspi_name_core,
                }
            )
            continue

        if existing_core == row.kaspi_name_core and existing_sku_key == row.sku_key and existing_sku_id == row.sku_id:
            unchanged += 1
        else:
            to_update += 1

    return {
        "to_insert": to_insert,
        "to_update": to_update,
        "unchanged": unchanged,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
    }


def validate_mapping_coverage(
    *,
    db_path: Path,
    mapping_csv: Path,
    expected_rows: int | None = None,
) -> dict[str, Any]:
    rows = _load_mapping_rows(mapping_csv, expected_rows=expected_rows)
    conn = _connect(db_path)
    try:
        _require_schema(conn)
        missing: list[str] = []
        mismatched_core: list[str] = []
        mismatched_identity: list[str] = []
        generic_fallback: list[str] = []
        technical_core: list[str] = []

        for row in rows:
            existing = _existing_row(conn, row)
            if not existing:
                missing.append(row.kaspi_article)
                continue
            core = _clean(existing["kaspi_name_core"])
            sku_key = _clean(existing["sku_key"]).upper()
            sku_id = _clean(existing["sku_id"]).upper()
            if core in {row.generic_fallback_to_avoid, "Спортивный_костюм_ACMEWEAR"}:
                generic_fallback.append(row.kaspi_article)
            if core == row.technical_core:
                technical_core.append(row.kaspi_article)
            if core != row.kaspi_name_core:
                mismatched_core.append(row.kaspi_article)
            if sku_key != row.sku_key or sku_id != row.sku_id:
                mismatched_identity.append(row.kaspi_article)

        resolved_rows = len(rows) - len(missing) - len(mismatched_core) - len(mismatched_identity)
        return {
            "ok": not missing and not mismatched_core and not mismatched_identity and not generic_fallback,
            "expected_rows": len(rows),
            "resolved_rows": resolved_rows,
            "missing_rows": len(missing),
            "mismatched_core_rows": len(mismatched_core),
            "mismatched_identity_rows": len(mismatched_identity),
            "generic_fallback_rows": len(generic_fallback),
            "technical_core_rows": len(technical_core),
            "archived_identity_rows": sum(1 for row in rows if row.is_archived_sale_row),
            "missing_sample": missing[:10],
            "mismatched_core_sample": mismatched_core[:10],
            "mismatched_identity_sample": mismatched_identity[:10],
            "generic_fallback_sample": generic_fallback[:10],
            "technical_core_sample": technical_core[:10],
        }
    finally:
        conn.close()


def _upsert_dim_sku(conn: sqlite3.Connection, rows: list[MappingRow]) -> int:
    unique: dict[str, MappingRow] = {row.sku_key: row for row in rows}
    for row in unique.values():
        conn.execute(
            """
            INSERT INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg,
                category, gender, active_flag
            )
            VALUES (?, ?, ?, 'CL', 0.0, 0.0, 'BUNDLE', 'MEN', 1)
            ON CONFLICT(sku_key) DO UPDATE SET
                model=excluded.model,
                color=excluded.color,
                product_type=excluded.product_type,
                category=excluded.category,
                gender=excluded.gender,
                active_flag=1,
                updated_at=datetime('now')
            """,
            (row.sku_key, row.bundle_code, row.color),
        )
    return len(unique)


def _upsert_dim_sku_size(conn: sqlite3.Connection, rows: list[MappingRow]) -> int:
    unique: dict[str, MappingRow] = {row.sku_id: row for row in rows}
    for row in unique.values():
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
            (row.sku_id, row.sku_key, row.my_size, SIZE_ORDER[row.my_size]),
        )
    return len(unique)


def _upsert_article_map(conn: sqlite3.Connection, rows: list[MappingRow]) -> int:
    for row in rows:
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, merchant_id, kaspi_article, kaspi_offer_name,
                kaspi_name_core, sku_key, sku_id, model, brand, source,
                active_flag
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(store_code, kaspi_article) DO UPDATE SET
                merchant_id=excluded.merchant_id,
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
                row.store_code,
                row.merchant_id,
                row.kaspi_article,
                row.kaspi_article,
                row.kaspi_name_core,
                row.sku_key,
                row.sku_id,
                row.bundle_code,
                BRAND,
                SOURCE,
            ),
        )
    return len(rows)


def _write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "acmewear_child_bundle_ab_mapping_ingest_report.json"
    md_path = output_dir / "acmewear_child_bundle_ab_mapping_ingest_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# ACMEWEAR Child Bundle AB Mapping Ingest",
        "",
        f"- status: `{report['status']}`",
        f"- mapping_csv: `{report['mapping_csv']}`",
        f"- db_path: `{report['db_path']}`",
        f"- backup_path: `{report.get('backup_path') or ''}`",
        f"- rows: `{report['row_count']}`",
        f"- groups: `{', '.join(report['groups'])}`",
        f"- to_insert: `{report['changes']['to_insert']}`",
        f"- to_update: `{report['changes']['to_update']}`",
        f"- unchanged: `{report['changes']['unchanged']}`",
        f"- conflict_count: `{report['changes']['conflict_count']}`",
        f"- before_ok: `{report['before']['coverage']['ok']}`",
        f"- after_ok: `{report['after']['coverage']['ok']}`",
        f"- after_resolved_rows: `{report['after']['coverage']['resolved_rows']}`",
        f"- after_generic_fallback_rows: `{report['after']['coverage']['generic_fallback_rows']}`",
        f"- after_technical_core_rows: `{report['after']['coverage']['technical_core_rows']}`",
        "",
        "Rollback:",
        f"- restore DB backup if needed: `cp {report.get('backup_path') or '<backup_path>'} {report['db_path']}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["report_json"] = str(json_path)
    report["report_md"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def run_ingest(
    *,
    db_path: Path,
    mapping_csv: Path,
    backup_root: Path,
    output_root: Path,
    apply: bool,
    expected_rows: int | None = 80,
) -> dict[str, Any]:
    if apply and _clean(os.environ.get(APPLY_ENV)) != "1":
        raise IngestError(f"{APPLY_ENV}=1 is required with --apply")

    rows = _load_mapping_rows(mapping_csv, expected_rows=expected_rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / stamp
    backup_path: Path | None = None

    conn = _connect(db_path)
    try:
        _require_schema(conn)
        changes = _plan_changes(conn, rows)
        if changes["conflict_count"]:
            raise IngestError(f"conflicting existing child-bundle mappings: {changes['conflicts'][:5]}")
        before = {
            "coverage": validate_mapping_coverage(
                db_path=db_path,
                mapping_csv=mapping_csv,
                expected_rows=expected_rows,
            )
        }

        upserts = {
            "dim_sku": len({row.sku_key for row in rows}),
            "dim_sku_size": len({row.sku_id for row in rows}),
            "dim_kaspi_article_map": len(rows),
        }
        status = "DRY_RUN"
        if apply:
            backup_path = _backup_db(db_path, backup_root)
            upserts = {
                "dim_sku": _upsert_dim_sku(conn, rows),
                "dim_sku_size": _upsert_dim_sku_size(conn, rows),
                "dim_kaspi_article_map": _upsert_article_map(conn, rows),
            }
            conn.commit()
            status = "APPLIED"
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    after = {
        "coverage": validate_mapping_coverage(
            db_path=db_path,
            mapping_csv=mapping_csv,
            expected_rows=expected_rows,
        )
    }
    report = {
        "status": status,
        "source": SOURCE,
        "db_path": str(db_path),
        "mapping_csv": str(mapping_csv),
        "backup_path": str(backup_path) if backup_path else "",
        "row_count": len(rows),
        "groups": sorted({row.card_group for row in rows}),
        "archived_identity_rows": sum(1 for row in rows if row.is_archived_sale_row),
        "proposed_ab_sku_keys": sorted({row.ab_sku_key_proposed for row in rows if row.ab_sku_key_proposed}),
        "changes": changes,
        "upserts": upserts,
        "before": before,
        "after": after,
        "report_dir": str(output_dir),
    }
    return _write_report(report, output_dir)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--mapping-csv", type=Path, default=DEFAULT_MAPPING_CSV)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-rows", type=int, default=80)
    parser.add_argument("--apply", action="store_true", help="Apply DB upserts. Default is dry-run.")
    parser.add_argument("--validate-only", action="store_true", help="Only validate existing DB coverage.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.validate_only:
        coverage = validate_mapping_coverage(
            db_path=args.db,
            mapping_csv=args.mapping_csv,
            expected_rows=args.expected_rows,
        )
        print(json.dumps(coverage, ensure_ascii=False, indent=2))
        return 0 if coverage["ok"] else 1

    report = run_ingest(
        db_path=args.db,
        mapping_csv=args.mapping_csv,
        backup_root=args.backup_root,
        output_root=args.output_root,
        apply=args.apply,
        expected_rows=args.expected_rows,
    )
    print(
        "acmewear_child_bundle_ab_mapping_ingest: "
        f"status={report['status']} rows={report['row_count']} "
        f"backup={report.get('backup_path') or 'NONE'} report={report['report_json']}"
    )
    print("changes: " + json.dumps(report["changes"], ensure_ascii=False, sort_keys=True))
    print("after_coverage: " + json.dumps(report["after"]["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
