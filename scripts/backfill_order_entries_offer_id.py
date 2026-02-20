#!/usr/bin/env python3
"""
Backfill offer_id in fact_order_entries_kaspi from raw_json attributes.offer.code.

Default: DRY RUN. Apply requires ENABLE_ORDER_WRITE=1 and --apply.
Writes a CSV change log to exports/.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH

EXPORT_DIR = PROJECT_ROOT / "exports"


def _extract_offer_code(payload: dict[str, Any]) -> str | None:
    attrs = payload.get("attributes", {}) if isinstance(payload, dict) else {}
    offer = attrs.get("offer", {}) if isinstance(attrs, dict) else {}
    for key in ("code", "offerId", "id"):
        value = offer.get(key)
        if value:
            return str(value).strip()
    direct = attrs.get("offerId")
    if direct:
        return str(direct).strip()
    return None


def backfill_offer_id(
    db_path: Path,
    apply: bool = False,
    exports_dir: Path | None = None,
) -> dict[str, int]:
    stats = {"candidates": 0, "updated": 0, "missing_code": 0, "parse_error": 0}
    export_dir = exports_dir or EXPORT_DIR
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / f"order_entry_offer_backfill_{datetime.now():%Y%m%d_%H%M%S}.csv"

    updates: list[dict[str, Any]] = []

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entry_id, order_id, offer_id, raw_json
            FROM fact_order_entries_kaspi
            WHERE offer_id IS NULL OR offer_id = ''
            """
        ).fetchall()
        for entry_id, order_id, offer_id, raw_json in rows:
            stats["candidates"] += 1
            if not raw_json:
                stats["missing_code"] += 1
                continue
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                stats["parse_error"] += 1
                continue
            code = _extract_offer_code(payload)
            if not code:
                stats["missing_code"] += 1
                continue
            updates.append(
                {
                    "entry_id": entry_id,
                    "order_id": order_id,
                    "offer_id_old": offer_id,
                    "offer_id_new": code,
                }
            )

        if apply and updates:
            for row in updates:
                conn.execute(
                    "UPDATE fact_order_entries_kaspi SET offer_id = ? WHERE entry_id = ?",
                    (row["offer_id_new"], row["entry_id"]),
                )
            stats["updated"] = len(updates)
        else:
            stats["updated"] = len(updates)

    if updates:
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(updates[0].keys()))
            writer.writeheader()
            writer.writerows(updates)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill offer_id in order entries from raw_json")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default: dry-run)")
    parser.add_argument("--db", default=None, help="DB path override")
    args = parser.parse_args()

    if args.apply and os.environ.get("ENABLE_ORDER_WRITE") != "1":
        print("ERROR: ENABLE_ORDER_WRITE=1 is required to apply changes.")
        return 1

    db_path = Path(args.db).expanduser() if args.db else DEFAULT_DB_PATH
    stats = backfill_offer_id(db_path=db_path, apply=args.apply)

    print("Order entries offer_id backfill summary")
    print(f"  Candidates: {stats['candidates']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Missing code: {stats['missing_code']}")
    print(f"  Parse error: {stats['parse_error']}")
    if not args.apply:
        print("  Dry-run only (no DB writes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
