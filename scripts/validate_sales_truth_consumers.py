#!/usr/bin/env python3
"""Static validator: production scripts must not read raw sales tables directly."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = PROJECT_ROOT / "config" / "sales_truth_consumer_contract.yaml"


def load_consumer_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = ("disallowed_tables", "production_scripts", "allow_raw_read_scripts")
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required contract key: {key}")
        if not isinstance(data[key], list):
            raise ValueError(f"Contract key must be a list: {key}")

    return {
        "disallowed_tables": [str(x) for x in data["disallowed_tables"]],
        "production_scripts": [str(x) for x in data["production_scripts"]],
        "allow_raw_read_scripts": [str(x) for x in data["allow_raw_read_scripts"]],
    }


def _compile_patterns(disallowed_tables: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for table in disallowed_tables:
        escaped = re.escape(table)
        pattern = re.compile(rf"\b(from|join|update|into|delete\s+from)\s+{escaped}\b", re.IGNORECASE)
        patterns.append((table, pattern))
    return patterns


def validate_sales_truth_consumers(
    *,
    project_root: Path = PROJECT_ROOT,
    contract_path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = load_consumer_contract(contract_path)
    patterns = _compile_patterns(contract["disallowed_tables"])

    errors: list[str] = []
    checked_scripts: list[str] = []

    for rel_path in contract["production_scripts"]:
        script_path = project_root / rel_path
        checked_scripts.append(rel_path)
        if not script_path.exists():
            errors.append(f"missing production script: {rel_path}")
            continue

        text = script_path.read_text(encoding="utf-8")
        for table, pattern in patterns:
            if pattern.search(text):
                errors.append(
                    f"{rel_path}: disallowed raw sales table reference detected ({table})"
                )

    return {
        "ok": not errors,
        "errors": errors,
        "checked_scripts": checked_scripts,
        "contract_path": str(contract_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production scripts use published sales truth views")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()

    report = validate_sales_truth_consumers(
        project_root=args.project_root,
        contract_path=args.contract,
    )
    print(
        "sales_truth_consumers: "
        f"checked={len(report['checked_scripts'])} ok={report['ok']} contract={report['contract_path']}"
    )
    for error in report["errors"]:
        print(f"ERROR: {error}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
