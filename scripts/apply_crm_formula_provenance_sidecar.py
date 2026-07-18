#!/usr/bin/env python3
"""Promote a validated CRM formula sidecar on a copied DB only.

This is a thin, CRM-validator-bound entrypoint over the shared copied-DB
writer. The canonical production ``db/app.db`` remains hard-refused. Apply
requires both ``--apply`` and
``AB_ALLOW_COPIED_DB_SALES_FORMULA_REPAIR=1``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.apply_sales_formula_provenance_sidecar import (  # noqa: E402
    SidecarApplyError,
    promote_sidecar,
)
from scripts.build_crm_formula_provenance_sidecar import (  # noqa: E402
    ProvenanceError,
    _json_bytes,
    _write_atomic,
    validate_manifest,
)


def promote_crm_sidecar(**kwargs: Any) -> dict[str, Any]:
    report = promote_sidecar(**kwargs, manifest_validator=validate_manifest)
    return {
        **report,
        "schema": "sales_formula_provenance_crm_copied_db_promotion_v1",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-db-sha256", required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = promote_crm_sidecar(
            manifest_path=args.manifest,
            db_path=args.db,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_db_sha256=args.expected_db_sha256,
            apply=args.apply,
            backup_dir=args.backup_dir,
        )
    except (OSError, ValueError, sqlite3.Error, ProvenanceError, SidecarApplyError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    if args.report:
        _write_atomic(args.report, _json_bytes(report, pretty=True))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
