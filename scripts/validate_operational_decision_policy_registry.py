#!/usr/bin/env python3
"""Validate active C3 DB policy against operational_decision_policy.yaml."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_registry_c3 import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_POLICY_PATH,
    validate_operational_decision_policy_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate C3 policy registry drift")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors = validate_operational_decision_policy_registry(args.db, args.policy, strict=args.strict)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("C3 POLICY REGISTRY DRIFT FAILURES:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("OK: active C3 policy registry matches YAML")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
