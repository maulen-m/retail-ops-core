#!/usr/bin/env python3
"""Create a copied-temp SQLite DB only after run-root runway checks pass."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

from check_validation_disk_runway import GIB, build_runway_report


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class CopiedTempDbError(RuntimeError):
    pass


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity(path: Path) -> str:
    uri = f"file:{path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    return str(row[0]) if row else "missing_integrity_result"


def _resolve_path(repo: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def _target_path(run_root: Path, db_name: str) -> Path:
    target = (run_root / db_name).resolve()
    try:
        target.relative_to(run_root.resolve())
    except ValueError as exc:
        raise CopiedTempDbError(f"target escapes run root: {db_name}") from exc
    if target.suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise CopiedTempDbError("target DB name must end with .db, .sqlite, or .sqlite3")
    return target


def build_copy_plan(
    *,
    repo: Path,
    source_db: Path,
    run_root: Path,
    db_name: str,
    min_free_gib: float,
    overwrite: bool,
) -> dict[str, Any]:
    target = _target_path(run_root, db_name)
    runway = build_runway_report(run_root, min_free_gib)
    source_size = source_db.stat().st_size if source_db.exists() and source_db.is_file() else 0
    min_free_bytes = int(min_free_gib * GIB)
    required_free_before_copy = min_free_bytes + source_size
    free_bytes = int(runway.get("free_bytes") or 0)
    errors: list[str] = []

    if not source_db.exists():
        errors.append("source_db_missing")
    elif not source_db.is_file():
        errors.append("source_db_not_file")
    if not bool(runway["ok"]):
        errors.append(str(runway["status"]))
    if free_bytes < required_free_before_copy:
        errors.append("insufficient_post_copy_runway")
    if target.exists() and not overwrite:
        errors.append("target_exists")
    if source_db.resolve() == target.resolve():
        errors.append("target_is_source")

    return {
        "ok": not errors,
        "status": "PASS" if not errors else "FAIL_PRECOPY_CHECK",
        "repo": str(repo),
        "source_db": str(source_db),
        "run_root": str(run_root),
        "target_db": str(target),
        "db_name": db_name,
        "source_size_bytes": source_size,
        "min_free_gib": min_free_gib,
        "min_free_bytes": min_free_bytes,
        "required_free_before_copy": required_free_before_copy,
        "free_bytes": free_bytes,
        "free_gib": round(free_bytes / GIB, 3),
        "runway": runway,
        "errors": errors,
    }


def create_copied_db(plan: dict[str, Any], manifest_out: Path | None) -> dict[str, Any]:
    if not plan["ok"]:
        raise CopiedTempDbError(";".join(plan["errors"]))

    source = Path(plan["source_db"])
    target = Path(plan["target_db"])
    target.parent.mkdir(parents=True, exist_ok=True)
    source_sha = _stream_sha256(source)
    shutil.copy2(source, target)
    target_sha = _stream_sha256(target)
    integrity = _sqlite_integrity(target)
    ok = source_sha == target_sha and integrity == "ok"
    result = {
        **plan,
        "mode": "COPY",
        "copied_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_sha256": source_sha,
        "target_sha256": target_sha,
        "sqlite_integrity_check": integrity,
        "ok": ok,
        "status": "COPIED_TEMP_DB_READY" if ok else "FAIL_COPY_VERIFY",
    }
    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result["manifest_out"] = str(manifest_out)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a copied-temp SQLite DB after fail-closed runway checks"
    )
    parser.add_argument("--repo", default=str(PROJECT_ROOT))
    parser.add_argument("--source-db", default="db/app.db")
    parser.add_argument("--run-root", required=True, help="Existing directory for copied-temp artifacts")
    parser.add_argument("--db-name", default="app_copied_temp.db")
    parser.add_argument("--min-free-gib", type=float, default=3.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--copy", action="store_true", help="Actually create the copied DB")
    parser.add_argument("--manifest-out", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    source_db = _resolve_path(repo, args.source_db)
    run_root = _resolve_path(repo, args.run_root)
    manifest_out = _resolve_path(repo, args.manifest_out) if args.manifest_out else None

    try:
        plan = build_copy_plan(
            repo=repo,
            source_db=source_db,
            run_root=run_root,
            db_name=args.db_name,
            min_free_gib=args.min_free_gib,
            overwrite=args.overwrite,
        )
        if args.copy:
            result = create_copied_db(plan, manifest_out)
        else:
            result = {**plan, "mode": "DRY_RUN"}
    except CopiedTempDbError as exc:
        print(f"COPIED_TEMP_DB_CREATE FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif result["ok"]:
        print(f"COPIED_TEMP_DB_CREATE {result['status']}")
        print(f"target_db={result['target_db']}")
    else:
        print(f"COPIED_TEMP_DB_CREATE {result['status']}")
        for error in result["errors"]:
            print(f"error={error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
