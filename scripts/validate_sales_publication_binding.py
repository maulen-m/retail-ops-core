#!/usr/bin/env python3
"""Validate an applied sales publication binding and all pinned evidence."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.apply_sales_publication_binding_manifest import (  # noqa: E402
    PublicationBindingApplyError,
    _exact_applied_state,
    _load_manifest,
    _validate_external_evidence,
)
from scripts.build_sales_publication_binding_manifest import sha256_file  # noqa: E402


def validate(*, db_path: Path, manifest_path: Path) -> dict[str, object]:
    db_path = db_path.resolve()
    manifest_path = manifest_path.resolve()
    manifest = _load_manifest(manifest_path)
    _validate_external_evidence(manifest)
    state = _exact_applied_state(
        db_path=db_path,
        manifest=manifest,
        manifest_path=manifest_path,
    )
    if state is None:
        raise PublicationBindingApplyError("reviewed publication binding is not applied")
    conn = sqlite3.connect(str(db_path))
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()
    if integrity.lower() != "ok":
        raise PublicationBindingApplyError(f"integrity_check failed: {integrity}")
    return {
        "status": "PASS",
        "db_path": str(db_path),
        "db_sha256": sha256_file(db_path),
        "manifest_path": str(manifest_path),
        "manifest_internal_sha256": manifest["manifest_sha256"],
        "binding_id": manifest["binding_id"],
        "integrity_check": integrity,
        **state,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(db_path=args.db, manifest_path=args.manifest)
    except PublicationBindingApplyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "binding_id": report["binding_id"], "db_sha256": report["db_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

