#!/usr/bin/env python3
"""Validate C3 source registry freshness results fail closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, validate_policy_source_freshness  # noqa: E402


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate C3 policy source freshness")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors = validate_policy_source_freshness(args.db, as_of=args.as_of, strict=args.strict)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "errors": errors,
                    "db_path": str(args.db),
                    "db_sha256": _sha256_file(args.db),
                    "requested_as_of": args.as_of,
                    "strict": bool(args.strict),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif errors:
        print("C3 SOURCE FRESHNESS FAILURES:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("OK: C3 required source freshness is green")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
