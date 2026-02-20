#!/usr/bin/env python3
"""Generate Kaspi XML pricelist (price/stock/preorder) with safety gates."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from core.integrations.kaspi_pricelist.generator import generate_pricelist


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Kaspi pricelist XML")
    parser.add_argument("--store", required=True, help="Store code (e.g., UNIVERSAL)")
    parser.add_argument("--db", default="db/app.db", help="Path to sqlite DB")
    parser.add_argument(
        "--config",
        default="config/kaspi_pricelist.yaml",
        help="Pricelist config YAML",
    )
    parser.add_argument(
        "--output-dir",
        default="exports/kaspi_pricelist",
        help="Output directory for generated XML",
    )
    parser.add_argument("--dry-run", action="store_true", help="Generate only (default)")
    parser.add_argument("--publish", action="store_true", help="Publish XML to publish path")
    parser.add_argument(
        "--publish-path",
        default=None,
        help="Publish target file path (required with --publish)",
    )
    parser.add_argument(
        "--allowlist",
        default=None,
        help="Path to SKU allowlist (one SKU per line). Required with --publish.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    dry_run = args.dry_run or not args.publish
    publish_path = Path(args.publish_path) if args.publish_path else None
    allowlist_path = Path(args.allowlist) if args.allowlist else None

    if args.publish:
        if os.environ.get("ENABLE_KASPI_PRICELIST_PUBLISH") != "1":
            raise RuntimeError("ENABLE_KASPI_PRICELIST_PUBLISH=1 is required to publish")
        if publish_path is None:
            raise RuntimeError("--publish-path is required when --publish is set")
        if allowlist_path is None:
            raise RuntimeError("--allowlist is required when --publish is set")

    result = generate_pricelist(
        db_path=Path(args.db),
        store_code=args.store,
        config_path=Path(args.config),
        output_dir=Path(args.output_dir),
        dry_run=dry_run,
        publish_path=publish_path,
        allowlist_path=allowlist_path,
    )

    print(f"Generated XML: {result.catalog_path}")
    print(f"Diff report: {result.diff_report_path}")
    print(f"Offers: {result.offer_count}")
    if args.publish:
        print(f"Published to: {publish_path}")
    else:
        print("Dry-run only (no publish)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
