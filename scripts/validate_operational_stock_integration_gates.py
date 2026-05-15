#!/usr/bin/env python3
"""Validate Agent 7 operational stock integration gates.

The validator is read-only. It fails closed when order lifecycle, return QC,
PO inbound, ads coverage, or D1 cashflow evidence is missing or inconsistent.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.operational_stock_integration_gates import (  # noqa: E402
    evaluate_operational_stock_integration_gates,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate operational stock integration gates")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-findings", type=int, default=25)
    args = parser.parse_args()

    report = evaluate_operational_stock_integration_gates(args.db, as_of=args.as_of)
    if args.json:
        print(report.to_json())
    else:
        print(f"status={report.status}")
        print(f"finding_count={len(report.findings)}")
        counts = Counter(finding.code for finding in report.findings)
        for code, count in sorted(counts.items()):
            print(f"{code}={count}")
        for finding in report.findings[: max(0, args.max_findings)]:
            print(f"- {finding.code}: {finding.message} {finding.evidence}")
        if len(report.findings) > args.max_findings:
            print(f"... {len(report.findings) - args.max_findings} more findings")

    return 1 if report.status == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
