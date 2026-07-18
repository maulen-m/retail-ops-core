#!/usr/bin/env python3
"""Dry-run or apply one approved manual physical-count reconciliation."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402
from core.ops.manual_stock_count_reconcile import (  # noqa: E402
    ALMATY,
    DEFAULT_OUTPUT_ROOT,
    file_sha256,
    reconcile_manual_stock_count,
    required_owner_approval_phrase,
)
from core.ops.manual_stock_count_manifest import load_approved_manual_stock_manifest  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-pre-sha256", default="")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--owner-instrument", type=Path)
    parser.add_argument("--owner-instrument-sha256", default="")
    parser.add_argument(
        "--print-required-owner-approval-phrase",
        action="store_true",
        help=(
            "print the exact current Asia/Almaty production approval phrase; "
            "requires --expected-pre-sha256 and performs no write"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.print_required_owner_approval_phrase:
        if not args.expected_pre_sha256:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error": (
                            "--print-required-owner-approval-phrase requires "
                            "--expected-pre-sha256"
                        ),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        manifest_path = args.manifest.expanduser().resolve()
        manifest = load_approved_manual_stock_manifest(manifest_path)
        print(
            required_owner_approval_phrase(
                apply_date_almaty=datetime.now(ALMATY).date().isoformat(),
                batch_id=str(manifest["batch_id"]),
                manifest_sha256=file_sha256(manifest_path),
                expected_pre_db_sha256=args.expected_pre_sha256,
            )
        )
        return 0
    try:
        summary = reconcile_manual_stock_count(
            db_path=args.db.expanduser(),
            manifest_path=args.manifest.expanduser(),
            output_root=args.output_root.expanduser(),
            apply=args.apply,
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir.expanduser() if args.backup_dir else None,
            owner_instrument=(
                args.owner_instrument.expanduser() if args.owner_instrument else None
            ),
            owner_instrument_sha256=args.owner_instrument_sha256,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
