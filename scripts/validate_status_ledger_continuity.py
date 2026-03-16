#!/usr/bin/env python3
"""Validate WebUI status ledger continuity and store-window coverage."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    DEFAULT_STORES_CONFIG,
    compute_continuity_gaps,
    load_enabled_stores,
    load_status_ledger,
    resolve_latest_dir,
)


class StatusLedgerContinuityError(RuntimeError):
    """Raised when strict continuity validation fails."""


def _resolve_run_root(run_root: Path | None) -> Path:
    if run_root is None:
        return resolve_latest_dir(DEFAULT_LEDGER_ROOT)
    candidate = run_root.expanduser()
    if candidate.exists():
        return candidate.resolve()
    alt = DEFAULT_LEDGER_ROOT / candidate
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(f"ledger root not found: {run_root}")


def validate_status_ledger_continuity(
    *,
    ledger_root: Path | None,
    start: str,
    end: str,
    stores_config: Path,
    strict: bool,
) -> dict[str, Any]:
    run_root = _resolve_run_root(ledger_root)
    ledger, manifest = load_status_ledger(run_root)
    enabled_stores = load_enabled_stores(stores_config)
    gaps = compute_continuity_gaps(
        pack_windows=manifest.get("pack_windows") or [],
        enabled_stores=enabled_stores,
        start=start,
        end=end,
    )
    continuity_gaps_csv = run_root / "continuity_gaps.csv"
    continuity_report_json = run_root / "continuity_report.json"
    gaps.to_csv(continuity_gaps_csv, index=False, encoding="utf-8")

    stores_with_rows = sorted({str(value).upper() for value in ledger.get("store_code", pd.Series(dtype=object)).tolist() if str(value).strip()})
    status = "PASS" if gaps.empty and not ledger.empty else "FAIL"
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ledger_root": str(run_root),
        "run_id": manifest.get("run_id"),
        "status": status,
        "ok": status == "PASS",
        "strict": bool(strict),
        "period": {"start": start, "end": end},
        "ledger_rows": int(len(ledger)),
        "enabled_stores": enabled_stores,
        "stores_with_rows": stores_with_rows,
        "gap_count": int(len(gaps)),
        "ledger_sha256": manifest.get("ledger_sha256"),
        "outputs": {
            "continuity_report_json": str(continuity_report_json),
            "continuity_gaps_csv": str(continuity_gaps_csv),
        },
    }
    continuity_report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if strict and not report["ok"]:
        raise StatusLedgerContinuityError(
            f"status ledger continuity failed: gap_count={report['gap_count']} ledger_rows={report['ledger_rows']}"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate WebUI status ledger continuity")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_status_ledger_continuity(
            ledger_root=args.ledger_root,
            start=str(args.start),
            end=str(args.end),
            stores_config=args.stores_config,
            strict=bool(args.strict),
        )
    except StatusLedgerContinuityError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_LEDGER_CONTINUITY_FAIL")
        print(f"message={exc}")
        return 1

    print(f"continuity_report_json={report['outputs']['continuity_report_json']}")
    print(f"continuity_gaps_csv={report['outputs']['continuity_gaps_csv']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
