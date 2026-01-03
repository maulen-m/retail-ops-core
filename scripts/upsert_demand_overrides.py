#!/usr/bin/env python3
"""
Upsert demand overrides into dim_demand_overrides (idempotent).

Examples:
  python3 scripts/upsert_demand_overrides.py --seed-defaults
  python3 scripts/upsert_demand_overrides.py \\
    --sku-key CL_OC_MEN_LINE52_BLACK --d-override 50 \\
    --start-date 2026-01-01 --end-date 2026-03-01 \\
    --reason "Jan-Feb seasonal spike"
"""

import argparse
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.business_params import set_demand_override

DB_PATH = PROJECT_ROOT / "db" / "app.db"

DEFAULT_OVERRIDES = [
    {
        "sku_key": "CL_OC_MEN_LINE52_BLACK",
        "d_override": 50.0,
        "start_date": "2026-01-01",
        "end_date": "2026-03-01",
        "reason": "Jan-Feb seasonal spike",
        "source": "MANUAL",
        "active_flag": 1,
    },
    {
        "sku_key": "CL_OC_MEN_LINE51_WHITE",
        "d_override": 12.0,
        "start_date": "2026-01-01",
        "end_date": "2026-03-01",
        "reason": "Marketing uplift + new Kaspi images",
        "source": "MANUAL",
        "active_flag": 1,
    },
]


def upsert_overrides(overrides: list[dict], db_path: Path) -> int:
    """Upsert overrides (idempotent). Returns number of overrides applied."""
    applied = 0
    for override in overrides:
        set_demand_override(
            sku_key=override["sku_key"],
            d_override=float(override["d_override"]),
            start_date=override.get("start_date"),
            end_date=override.get("end_date"),
            reason=override.get("reason", ""),
            source=override.get("source", "MANUAL"),
            active_flag=int(override.get("active_flag", 1)),
            db_path=db_path,
        )
        applied += 1
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Upsert demand overrides")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Database path")
    parser.add_argument("--seed-defaults", action="store_true", help="Seed default overrides")
    parser.add_argument("--sku-key", type=str, help="SKU key to override")
    parser.add_argument("--d-override", type=float, help="Override daily demand value")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--reason", type=str, default="", help="Override reason")
    parser.add_argument("--source", type=str, default="MANUAL", help="Override source")
    parser.add_argument("--active-flag", type=int, default=1, help="1=active, 0=inactive")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    overrides = []
    if args.seed_defaults or not args.sku_key:
        overrides = DEFAULT_OVERRIDES
    else:
        if args.d_override is None:
            print("ERROR: --d-override is required when using --sku-key")
            return 1

        start_date = args.start_date or date.today().isoformat()
        end_date = args.end_date or "9999-12-31"
        overrides = [
            {
                "sku_key": args.sku_key,
                "d_override": args.d_override,
                "start_date": start_date,
                "end_date": end_date,
                "reason": args.reason,
                "source": args.source,
                "active_flag": args.active_flag,
            }
        ]

    applied = upsert_overrides(overrides, db_path)
    print(f"Upserted {applied} demand overrides into {db_path}")
    for override in overrides:
        print(
            f"  - {override['sku_key']}: D={override['d_override']} "
            f"[{override.get('start_date')} → {override.get('end_date')}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
