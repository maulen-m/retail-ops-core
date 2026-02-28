#!/usr/bin/env python3
"""Sync dim_kaspi_article_map from Ocean Drop mapped CSV (dry-run default)."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import json
import os
from pathlib import Path
import sqlite3
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.ocean_drop_anchor import (
    DEFAULT_REGISTRY as DEFAULT_ANCHOR_REGISTRY,
    OceanDropAnchorError,
    resolve_ocean_drop_path,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_coverage"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"

STORE_MAP = {
    "30000001_PP1": "UNIVERSAL",
    "30137883_PP1": "ACMEWEAR",
    "30000002_PP1": "STOREB",
    "30290083_PP1": "11KZ",
    "30362323_PP1": "MELVIS",
}


class IdentitySyncError(RuntimeError):
    pass


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_identity_map_sync_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _normalize_article(text: str) -> str:
    value = str(text or "").strip().upper()
    return value


def _build_candidates(df: pd.DataFrame, strict: bool) -> list[dict[str, str]]:
    required = {"Склад передачи КД", "Артикул", "mapped_sku_key"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise IdentitySyncError(f"missing required columns: {', '.join(missing)}")

    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for _, row in df.iterrows():
        warehouse = str(row.get("Склад передачи КД") or "").strip().upper()
        store = STORE_MAP.get(warehouse, "UNKNOWN")
        if strict and store == "UNKNOWN":
            raise IdentitySyncError(f"unknown warehouse: {warehouse}")
        if store == "UNKNOWN":
            continue
        article = _normalize_article(str(row.get("Артикул") or ""))
        if not article:
            continue
        sku_key = str(row.get("mapped_sku_key") or "").strip().upper()
        if not sku_key:
            continue
        grouped[(store, article)][sku_key] += 1

    candidates: list[dict[str, str]] = []
    for (store, article), counter in sorted(grouped.items()):
        sku_key = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        candidates.append(
            {
                "store_code": store,
                "kaspi_article": article,
                "sku_key": sku_key,
                "sku_id": sku_key,
                "source": "OCEAN_DROP",
            }
        )
    return candidates


def sync_dim_kaspi_article_map_from_ocean_drop(
    *,
    db_path: Path,
    ocean_drop_path: Path,
    as_of: date,
    output_root: Path,
    strict: bool,
    apply: bool,
    backup_root: Path,
) -> dict[str, str]:
    df = pd.read_csv(ocean_drop_path, dtype=str)
    candidates = _build_candidates(df, strict)

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_json = out_dir / "identity_map_sync_plan.json"
    plan_md = out_dir / "identity_map_sync_plan.md"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone()
        if not has_table:
            raise IdentitySyncError("dim_kaspi_article_map missing")

        existing_rows = conn.execute(
            """
            SELECT id, UPPER(COALESCE(store_code,'')) AS store_code, UPPER(COALESCE(kaspi_article,'')) AS kaspi_article,
                   UPPER(COALESCE(sku_key,'')) AS sku_key, UPPER(COALESCE(sku_id,'')) AS sku_id
            FROM dim_kaspi_article_map
            """
        ).fetchall()
        existing = {(r["store_code"], r["kaspi_article"]): r for r in existing_rows}

        inserts: list[dict[str, str]] = []
        updates: list[dict[str, str]] = []
        unchanged = 0
        for row in candidates:
            key = (row["store_code"], row["kaspi_article"])
            current = existing.get(key)
            if current is None:
                inserts.append(row)
                continue
            if str(current["sku_key"] or "") != row["sku_key"] or str(current["sku_id"] or "") != row["sku_id"]:
                patch = dict(row)
                patch["id"] = int(current["id"])
                updates.append(patch)
            else:
                unchanged += 1

        plan = {
            "as_of": as_of.isoformat(),
            "source_path": str(ocean_drop_path),
            "candidate_count": len(candidates),
            "insert_count": len(inserts),
            "update_count": len(updates),
            "unchanged_count": unchanged,
            "rows_insert": inserts,
            "rows_update": updates,
        }
        plan_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan_md.write_text(
            "\n".join(
                [
                    "# Ocean Drop Identity Map Sync Plan",
                    "",
                    f"- as_of: `{as_of.isoformat()}`",
                    f"- candidate_count: `{len(candidates)}`",
                    f"- insert_count: `{len(inserts)}`",
                    f"- update_count: `{len(updates)}`",
                    f"- unchanged_count: `{unchanged}`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        apply_status = "DRY_RUN"
        backup_path = None
        if apply:
            if str(os.environ.get("ENABLE_OCEAN_DROP_IDENTITY_APPLY") or "").strip() != "1":
                raise IdentitySyncError("ENABLE_OCEAN_DROP_IDENTITY_APPLY=1 is required for --apply")
            backup_path = _backup_db(db_path, backup_root)
            for row in inserts:
                conn.execute(
                    """
                    INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["store_code"], row["kaspi_article"], row["sku_key"], row["sku_id"], row["source"]),
                )
            for row in updates:
                conn.execute(
                    """
                    UPDATE dim_kaspi_article_map
                    SET sku_key=?, sku_id=?, source=?
                    WHERE id=?
                    """,
                    (row["sku_key"], row["sku_id"], row["source"], row["id"]),
                )
            conn.commit()
            apply_status = "APPLIED"
    finally:
        conn.close()

    return {
        "plan_json": str(plan_json),
        "plan_md": str(plan_md),
        "status": apply_status,
        "backup_path": str(backup_path) if backup_path else "",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync dim_kaspi_article_map from Ocean Drop")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--ocean-drop", type=Path, default=None)
    parser.add_argument("--anchor-registry", type=Path, default=DEFAULT_ANCHOR_REGISTRY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        ocean_drop_path = resolve_ocean_drop_path(explicit_path=args.ocean_drop, registry_path=args.anchor_registry)
    except OceanDropAnchorError as exc:
        raise IdentitySyncError(str(exc)) from exc

    report = sync_dim_kaspi_article_map_from_ocean_drop(
        db_path=args.db,
        ocean_drop_path=ocean_drop_path,
        as_of=date.fromisoformat(str(args.as_of)),
        output_root=args.output_root,
        strict=bool(args.strict),
        apply=bool(args.apply),
        backup_root=args.backup_root,
    )
    print(f"identity_map_sync_plan_json={report['plan_json']}")
    print(f"identity_map_sync_plan_md={report['plan_md']}")
    print(f"status={report['status']}")
    if report["backup_path"]:
        print(f"db_backup_path={report['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
