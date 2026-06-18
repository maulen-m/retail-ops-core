#!/usr/bin/env python3
"""Optional Kaspi order enrichment (entries + cached lookups)."""
from __future__ import annotations

import argparse
import logging
import os
from datetime import timedelta
from pathlib import Path

from core.db.queries import get_cutoff_date_almaty
from core.sync.kaspi_order_enrichment import enrich_orders, _load_config
from core.integrations.kaspi_api_client import STORE_TOKEN_MAP
from core.stores.roster import load_sync_enabled_kaspi_store_codes

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_enrichment.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich Kaspi orders with entry-level data")
    parser.add_argument("--store", type=str, help="Store code (UNIVERSAL, ACMEWEAR, 11KZ, MELVIS, STOREB)")
    parser.add_argument("--all", action="store_true", help="Enrich all configured stores")
    parser.add_argument("--since", type=str, help="Since date (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, help="Until date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Write enriched rows to DB")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    cfg = _load_config(args.config)
    if not cfg.get("enabled"):
        print("Kaspi enrichment disabled (config).")
        return 0

    cutoff = get_cutoff_date_almaty()
    lookback_days = int(cfg.get("default_lookback_days") or 0) or 7
    since = args.since or (cutoff - timedelta(days=lookback_days - 1)).isoformat()
    until = args.until or cutoff.isoformat()

    if args.apply and os.environ.get("ENABLE_KASPI_ENRICHMENT") != "1":
        raise RuntimeError("ENABLE_KASPI_ENRICHMENT=1 is required to apply enrichment writes.")

    stores = []
    if args.all:
        stores = [store for store in load_sync_enabled_kaspi_store_codes() if store in STORE_TOKEN_MAP]
    elif args.store:
        stores = [args.store]
    else:
        raise SystemExit("Specify --store or --all.")

    for store in stores:
        result = enrich_orders(
            db_path=PROJECT_ROOT / "db" / "app.db",
            store_code=store,
            since=since,
            until=until,
            apply=args.apply,
            config_path=args.config,
        )
        print(
            f"{store}: enabled={result.get('enabled')} inserted={result.get('inserted')} "
            f"skipped={result.get('skipped')}"
        )

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
