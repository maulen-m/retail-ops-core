#!/usr/bin/env python3
"""
Validate that no multiple raw sku_id values normalize to the same canonical sku_id.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import normalize_sku_id

EXPORT_DIR = PROJECT_ROOT / "exports"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical sku_id uniqueness")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--table", default="dim_sku_size", help="Table to scan (default: dim_sku_size)")
    args = parser.parse_args()

    with get_db(args.db) as conn:
        rows = conn.execute(
            f"SELECT sku_key, sku_id, my_size FROM {args.table}"
        ).fetchall()

    normalized_map: dict[str, set[str]] = {}
    for row in rows:
        norm = normalize_sku_id(row["sku_id"], row["sku_key"])
        if not norm:
            continue
        normalized_map.setdefault(norm, set()).add(str(row["sku_id"]))

    conflicts = {k: v for k, v in normalized_map.items() if len(v) > 1}

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EXPORT_DIR / "validate_sku_id_canonical_report.csv"
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["canonical_sku_id", "raw_variants"])
        for canonical, variants in sorted(conflicts.items()):
            writer.writerow([canonical, "; ".join(sorted(variants))])

    if conflicts:
        print(f"Conflicts found: {len(conflicts)} (report: {report_path})")
        return 1

    print(f"OK: no conflicts (report: {report_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
