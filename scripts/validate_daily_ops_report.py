#!/usr/bin/env python3
"""Validate daily ops report schema and consistency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "generated_at",
    "as_of",
    "status",
    "ok",
    "exit_code",
    "profile",
    "steps_total",
    "steps_failed",
    "failed_step_names",
    "stores_total",
    "stores_red",
    "stores_green",
    "red_store_codes",
    "store_results",
    "shipping_backlog",
    "summary_json",
]


def validate_daily_ops_report(path: Path, *, strict: bool = False) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    status = payload.get("status")
    if status not in {"GREEN", "RED"}:
        errors.append("status must be GREEN or RED")

    store_results = payload.get("store_results")
    if not isinstance(store_results, dict):
        errors.append("store_results must be an object")
    else:
        for store, meta in store_results.items():
            if not isinstance(meta, dict):
                errors.append(f"store_results[{store}] must be an object")
                continue
            if "ok" not in meta:
                errors.append(f"store_results[{store}] missing ok")
            if "rc" not in meta:
                errors.append(f"store_results[{store}] missing rc")

    shipping_backlog = payload.get("shipping_backlog")
    if not isinstance(shipping_backlog, dict):
        errors.append("shipping_backlog must be an object")
    else:
        if "present" not in shipping_backlog:
            errors.append("shipping_backlog missing present")

    failed_step_names = payload.get("failed_step_names")
    if not isinstance(failed_step_names, list):
        errors.append("failed_step_names must be a list")

    red_store_codes = payload.get("red_store_codes")
    if not isinstance(red_store_codes, list):
        errors.append("red_store_codes must be a list")

    summary_json = payload.get("summary_json")
    if not isinstance(summary_json, str) or not summary_json:
        errors.append("summary_json must be a non-empty string")
    elif not Path(summary_json).exists():
        errors.append("summary_json path does not exist")

    stores_total = int(payload.get("stores_total", -1)) if str(payload.get("stores_total", "")).isdigit() else payload.get("stores_total")
    stores_red = int(payload.get("stores_red", -1)) if str(payload.get("stores_red", "")).isdigit() else payload.get("stores_red")
    stores_green = int(payload.get("stores_green", -1)) if str(payload.get("stores_green", "")).isdigit() else payload.get("stores_green")

    if isinstance(store_results, dict):
        if stores_total != len(store_results):
            errors.append("stores_total mismatch vs store_results")
        computed_red = sum(1 for meta in store_results.values() if not bool(meta.get("ok", False)))
        if stores_red != computed_red:
            errors.append("stores_red mismatch vs store_results")
        if stores_green != (len(store_results) - computed_red):
            errors.append("stores_green mismatch vs store_results")
        if isinstance(red_store_codes, list):
            computed_red_codes = sorted(store for store, meta in store_results.items() if not bool(meta.get("ok", False)))
            if sorted(str(item) for item in red_store_codes) != computed_red_codes:
                errors.append("red_store_codes mismatch vs store_results")

    ok = not errors
    report = {
        "path": str(path),
        "ok": ok,
        "errors": errors,
    }
    if strict and not ok:
        raise RuntimeError("; ".join(errors))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate daily_ops_report.json")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_daily_ops_report(args.path, strict=bool(args.strict))
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("daily_ops_report: OK" if report["ok"] else "daily_ops_report: FAIL")
    for err in report["errors"]:
        print(f"- {err}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
