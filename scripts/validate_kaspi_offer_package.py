#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.kaspi_offer_manifest import validate_offer_package_layout


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Kaspi offer ZIP/XLSM package structure before upload.")
    parser.add_argument("--package-dir", required=True, help="Path to built package directory")
    parser.add_argument("--zip", dest="zip_path", help="Optional explicit ZIP path inside the package")
    parser.add_argument("--report-json", help="Optional path to write validation report JSON")
    args = parser.parse_args()

    package_dir = Path(args.package_dir).expanduser().resolve()
    zip_path = Path(args.zip_path).expanduser().resolve() if args.zip_path else None
    report = validate_offer_package_layout(package_dir=package_dir, zip_path=zip_path)

    if args.report_json:
        report_path = Path(args.report_json).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report_json: {report_path}")

    print(f"ok: {report['ok']}")
    print(f"package_dir: {report['package_dir']}")
    if report.get("zip_path"):
        print(f"zip_path: {report['zip_path']}")
    if report.get("image_codes"):
        print("image_codes:")
        for code in report["image_codes"]:
            print(f"  - {code}")
    if report["warnings"]:
        print("warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    if report["errors"]:
        print("errors:")
        for error in report["errors"]:
            print(f"  - {error}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
