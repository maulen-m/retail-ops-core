#!/usr/bin/env python3
"""Validate C3 manual decision approvals fail closed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, validate_manual_decision_approvals  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate C3 manual decision approvals")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors = validate_manual_decision_approvals(args.db, strict=args.strict)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("C3 MANUAL APPROVAL FAILURES:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("OK: C3 manual approvals are fail-closed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
