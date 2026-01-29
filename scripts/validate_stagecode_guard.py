#!/usr/bin/env python3
"""Fail if raw Kaspi state/status tokens appear in StageCode-governed pipelines."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).parent.parent

FORBIDDEN_TOKENS = {
    "KASPI_DELIVERY",
    "ACCEPTED_BY_MERCHANT",
    "APPROVED_BY_BANK",
    "SIGN_REQUIRED",
    "KASPI_DELIVERY_RETURN_REQUESTED",
}

DEFAULT_TARGETS = [
    "core/alerts/order_alerts.py",
    "core/sync/order_sync_engine.py",
    "scripts/build_daily_waybills.py",
    "scripts/download_waybills_api.py",
    "scripts/report_waybill_status.py",
    "scripts/translate_orders_to_cashflow_events.py",
    "scripts/validate_pending_orders.py",
]


def _iter_targets(paths: Iterable[str]) -> list[Path]:
    targets = []
    for rel in paths:
        candidate = PROJECT_ROOT / rel
        if candidate.is_file():
            targets.append(candidate)
    return targets


def _scan_file(path: Path) -> list[str]:
    hits: list[str] = []
    text = path.read_text(encoding="utf-8")
    for idx, line in enumerate(text.splitlines(), start=1):
        for token in FORBIDDEN_TOKENS:
            if token in line:
                if "StageCode." in line:
                    continue
                hits.append(f"{path}:{idx}:{token}")
    return hits


def run_guard(paths: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for target in _iter_targets(paths):
        hits.extend(_scan_file(target))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="StageCode guard (no raw Kaspi tokens in pipelines)")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=DEFAULT_TARGETS,
        help="Target files to scan (relative to repo root)",
    )
    args = parser.parse_args()
    hits = run_guard(args.paths)
    if hits:
        print("StageCode guard failed. Raw tokens found:")
        for hit in hits:
            print(f"  {hit}")
        return 1
    print("StageCode guard OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
