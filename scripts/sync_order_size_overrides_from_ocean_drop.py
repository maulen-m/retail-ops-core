#!/usr/bin/env python3
"""Sync order size overrides from Ocean Drop mapped data (dry-run default)."""

from __future__ import annotations

import argparse
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


class SizeOverrideError(RuntimeError):
    pass


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_size_override_sync_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def sync_order_size_overrides_from_ocean_drop(
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
    required = {"№ заказа", "mapped_size"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SizeOverrideError(f"missing required columns: {', '.join(missing)}")

    candidates = {}
    for _, row in df.iterrows():
        order_id = str(row.get("№ заказа") or "").strip()
        size = str(row.get("mapped_size") or "").strip().upper()
        if not order_id or not size:
            continue
        candidates[order_id] = size

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_json = out_dir / "order_size_override_sync_plan.json"
    plan_md = out_dir / "order_size_override_sync_plan.md"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not has_table:
            raise SizeOverrideError("fact_orders_kaspi missing")

        cols = {row[1] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()}
        for col in ("assigned_size", "size_source", "size_confidence"):
            if col not in cols:
                raise SizeOverrideError(f"fact_orders_kaspi missing {col}")

        updates = []
        missing_orders = []
        for order_id, size in sorted(candidates.items()):
            rows = conn.execute(
                """
                SELECT id, COALESCE(assigned_size,''), COALESCE(size_source,''), COALESCE(size_confidence,'')
                FROM fact_orders_kaspi
                WHERE order_id=?
                """,
                (order_id,),
            ).fetchall()
            if not rows:
                missing_orders.append(order_id)
                continue
            for row in rows:
                if str(row[1]).strip().upper() == size and str(row[2]).strip().upper() == "OCEAN_DROP":
                    continue
                updates.append(
                    {
                        "id": int(row[0]),
                        "order_id": order_id,
                        "assigned_size": size,
                        "size_source": "OCEAN_DROP",
                        "size_confidence": "HIGH",
                    }
                )

        if strict and missing_orders:
            raise SizeOverrideError(f"missing orders in fact_orders_kaspi: {', '.join(missing_orders[:20])}")

        plan = {
            "as_of": as_of.isoformat(),
            "source_path": str(ocean_drop_path),
            "candidate_orders": len(candidates),
            "update_count": len(updates),
            "missing_order_count": len(missing_orders),
            "missing_orders_sample": missing_orders[:100],
            "rows_update": updates,
        }
        plan_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan_md.write_text(
            "\n".join(
                [
                    "# Ocean Drop Order Size Override Sync Plan",
                    "",
                    f"- as_of: `{as_of.isoformat()}`",
                    f"- candidate_orders: `{len(candidates)}`",
                    f"- update_count: `{len(updates)}`",
                    f"- missing_order_count: `{len(missing_orders)}`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        status = "DRY_RUN"
        backup_path = None
        if apply:
            if str(os.environ.get("ENABLE_OCEAN_DROP_SIZE_APPLY") or "").strip() != "1":
                raise SizeOverrideError("ENABLE_OCEAN_DROP_SIZE_APPLY=1 is required for --apply")
            backup_path = _backup_db(db_path, backup_root)
            conn.executemany(
                """
                UPDATE fact_orders_kaspi
                SET assigned_size=:assigned_size,
                    size_source=:size_source,
                    size_confidence=:size_confidence,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
                """,
                updates,
            )
            conn.commit()
            status = "APPLIED"
    finally:
        conn.close()

    return {
        "plan_json": str(plan_json),
        "plan_md": str(plan_md),
        "status": status,
        "backup_path": str(backup_path) if backup_path else "",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync fact_orders_kaspi size overrides from Ocean Drop")
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
        raise SizeOverrideError(str(exc)) from exc

    report = sync_order_size_overrides_from_ocean_drop(
        db_path=args.db,
        ocean_drop_path=ocean_drop_path,
        as_of=date.fromisoformat(str(args.as_of)),
        output_root=args.output_root,
        strict=bool(args.strict),
        apply=bool(args.apply),
        backup_root=args.backup_root,
    )
    print(f"order_size_override_sync_plan_json={report['plan_json']}")
    print(f"order_size_override_sync_plan_md={report['plan_md']}")
    print(f"status={report['status']}")
    if report["backup_path"]:
        print(f"db_backup_path={report['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
