#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.kaspi_offer_manifest import (
    apply_workbook_ingest_payload,
    build_offer_packages,
    build_workbook_ingest_payload,
    load_offer_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Kaspi offer packages from an offer manifest.")
    parser.add_argument("--manifest", required=True, help="Path to offer_manifest.yaml")
    parser.add_argument("--timestamp", help="Optional fixed timestamp (YYYYMMDD_HHMMSS)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write package folders/XLSM/ZIP files. Default is dry-run planning only.",
    )
    parser.add_argument(
        "--apply-workbook",
        action="store_true",
        help="After package build, append workbook ingest payload via xlwings.",
    )
    parser.add_argument(
        "--report-json",
        help="Optional explicit path for the build report JSON. Defaults into sources/reports/",
    )
    parser.add_argument(
        "--payload-json",
        help="Optional explicit path for the workbook payload JSON. Defaults into sources/reports/",
    )
    args = parser.parse_args()

    manifest = load_offer_manifest(Path(args.manifest))
    build_report = build_offer_packages(manifest, timestamp=args.timestamp, apply=args.apply)
    payload = build_workbook_ingest_payload(manifest, build_report)

    sources_reports = manifest["product_root"] / "sources" / "reports"
    build_report_path = Path(args.report_json).expanduser() if args.report_json else (
        sources_reports / f"{manifest['product']['base_model']}_offer_build_{build_report['timestamp']}.json"
    )
    payload_path = Path(args.payload_json).expanduser() if args.payload_json else (
        sources_reports / f"{manifest['product']['base_model']}_workbook_payload_{build_report['timestamp']}.json"
    )

    build_report_path.parent.mkdir(parents=True, exist_ok=True)
    build_report_path.write_text(__import__("json").dumps(build_report, ensure_ascii=False, indent=2), encoding="utf-8")
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"manifest: {manifest['manifest_path']}")
    print(f"product_root: {manifest['product_root']}")
    print(f"timestamp: {build_report['timestamp']}")
    print(f"build_report: {build_report_path}")
    print(f"workbook_payload: {payload_path}")
    print(f"packages: {len(build_report['packages'])}")

    if args.apply_workbook:
        workbook_path_value = payload.get("workbook_path") or manifest.get("workbook", {}).get("workbook_path")
        if not workbook_path_value:
            raise SystemExit("Workbook path missing in manifest.workbook.workbook_path")
        apply_report = apply_workbook_ingest_payload(Path(workbook_path_value), payload)
        print("workbook_apply:")
        for key, value in apply_report.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
