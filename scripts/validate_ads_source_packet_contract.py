#!/usr/bin/env python3
"""Validate a Web_automation ads capture packet before AB proof use."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ads.source_packet_contract import validate_ads_source_packet_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate an immutable Web_automation ads source packet manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--require-existing-files",
        action="store_true",
        help="Require packet_root and referenced manifest files to exist on disk.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Return nonzero on validation failure.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    validation = validate_ads_source_packet_file(
        args.manifest,
        require_existing_files=bool(args.require_existing_files),
        strict=False,
    )
    payload = validation.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ok={str(validation.ok).lower()}")
        print(f"manifest_path={validation.manifest_path}")
        if validation.errors:
            print("errors:")
            for error in validation.errors:
                print(f"- {error}")
        if validation.warnings:
            print("warnings:")
            for warning in validation.warnings:
                print(f"- {warning}")
    if args.strict and not validation.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
