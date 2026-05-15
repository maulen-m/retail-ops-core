#!/usr/bin/env python3
"""Validate C3 policy/source registry schema objects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, validate_policy_registry_schema  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate C3 policy registry schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors = validate_policy_registry_schema(args.db)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("C3 POLICY REGISTRY SCHEMA FAILURES:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("OK: C3 policy registry schema valid")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
