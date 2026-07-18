#!/usr/bin/env python3
"""Validate and independently reconstruct a CRM formula sidecar."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.build_crm_formula_provenance_sidecar import validate_manifest
from scripts.build_sales_formula_provenance_sidecar import ProvenanceError, _json_bytes, _write_atomic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_manifest(args.manifest)
    except (OSError, ValueError, sqlite3.Error, ProvenanceError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    if args.report:
        _write_atomic(args.report, _json_bytes(report, pretty=True))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
