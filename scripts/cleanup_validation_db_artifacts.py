#!/usr/bin/env python3
"""Dry-run/apply cleanup for non-production validation DB artifacts.

This helper is intentionally narrow: it only accepts manifest rows under
exports/validation and only deletes .db files classified as copied-temp or
copied-backup candidates.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DELETE_ENV_GATE = "ENABLE_VALIDATION_DB_CLEANUP_DELETE"
ALLOWED_CLASSES = {"CANDIDATE_COPIED_TEMP_DB", "CANDIDATE_COPIED_DB_BACKUP"}
FORBIDDEN_PATH_PARTS = {
    "db/app.db",
    "db_order_entry_owner_apply",
    "excel_ui/",
    "config/anchors/",
    "Docs/Oracle/Autonomous_business/",
    "owner_apply",
    "pre_apply",
    "prod_apply",
    "production_apply",
}


class CleanupPlanError(RuntimeError):
    pass


def _resolve_repo_path(repo: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (repo / path).resolve()
    try:
        resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise CleanupPlanError(f"path escapes repo: {raw_path}") from exc
    return resolved


def _as_repo_posix(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"path", "size_bytes", "class"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise CleanupPlanError(f"manifest missing columns: {', '.join(sorted(missing))}")
        return [dict(row) for row in reader]


def _classify_row(repo: Path, row: dict[str, str]) -> dict[str, Any]:
    raw_path = row["path"]
    resolved = _resolve_repo_path(repo, raw_path)
    rel = _as_repo_posix(repo, resolved)
    row_class = row.get("class", "")
    errors: list[str] = []

    if row_class not in ALLOWED_CLASSES:
        errors.append(f"class_not_allowed:{row_class}")
    if not rel.startswith("exports/validation/"):
        errors.append("outside_exports_validation")
    if resolved.suffix != ".db":
        errors.append("not_db_file")
    if any(part in rel for part in FORBIDDEN_PATH_PARTS):
        errors.append("forbidden_path_part")
    if not resolved.exists():
        errors.append("missing_file")
    elif not resolved.is_file():
        errors.append("not_file")

    actual_size = resolved.stat().st_size if resolved.exists() and resolved.is_file() else None
    declared_size = None
    try:
        declared_size = int(row.get("size_bytes") or "0")
    except ValueError:
        errors.append("invalid_size_bytes")
    if actual_size is not None and declared_size is not None and declared_size > 0:
        if actual_size != declared_size:
            errors.append(f"size_mismatch:declared={declared_size}:actual={actual_size}")

    return {
        "path": rel,
        "absolute_path": str(resolved),
        "class": row_class,
        "evidence_hint": row.get("evidence_hint", ""),
        "declared_size_bytes": declared_size,
        "actual_size_bytes": actual_size,
        "errors": errors,
        "eligible": not errors,
    }


def build_cleanup_plan(repo: Path, manifest: Path) -> dict[str, Any]:
    rows = _read_manifest(manifest)
    planned = [_classify_row(repo, row) for row in rows]
    eligible = [row for row in planned if row["eligible"]]
    blocked = [row for row in planned if not row["eligible"]]
    return {
        "manifest": str(manifest),
        "repo": str(repo),
        "row_count": len(planned),
        "eligible_count": len(eligible),
        "blocked_count": len(blocked),
        "eligible_bytes": sum(int(row["actual_size_bytes"] or 0) for row in eligible),
        "blocked": blocked,
        "eligible": eligible,
    }


def _default_deletion_manifest(repo: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo / "exports" / "validation" / "cleanup_manifests" / f"validation_db_cleanup_{stamp}.tsv"


def write_deletion_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "deleted_at",
        "path",
        "class",
        "size_bytes",
        "sha256_before_delete",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def apply_cleanup(repo: Path, plan: dict[str, Any], deletion_manifest: Path) -> dict[str, Any]:
    if os.environ.get(DELETE_ENV_GATE) != "1":
        raise CleanupPlanError(f"{DELETE_ENV_GATE}=1 is required with --apply")
    rows_for_manifest: list[dict[str, Any]] = []
    deleted_count = 0
    deleted_bytes = 0
    deleted_at = dt.datetime.now(dt.timezone.utc).isoformat()

    for row in plan["eligible"]:
        path = Path(row["absolute_path"])
        size = path.stat().st_size
        digest = _stream_sha256(path)
        rows_for_manifest.append(
            {
                "deleted_at": deleted_at,
                "path": row["path"],
                "class": row["class"],
                "size_bytes": size,
                "sha256_before_delete": digest,
                "status": "planned_delete",
            }
        )

    write_deletion_manifest(deletion_manifest, rows_for_manifest)

    for row in rows_for_manifest:
        path = repo / row["path"]
        size = path.stat().st_size
        path.unlink()
        row["status"] = "deleted"
        deleted_count += 1
        deleted_bytes += size

    write_deletion_manifest(deletion_manifest, rows_for_manifest)
    return {
        "mode": "APPLY",
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "deletion_manifest": str(deletion_manifest),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean non-production copied DB artifacts from exports/validation"
    )
    parser.add_argument("--repo", default=str(PROJECT_ROOT))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--apply", action="store_true", help="Delete eligible files")
    parser.add_argument("--deletion-manifest-out", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    manifest = _resolve_repo_path(repo, args.manifest)
    deletion_manifest = (
        _resolve_repo_path(repo, args.deletion_manifest_out)
        if args.deletion_manifest_out
        else _default_deletion_manifest(repo)
    )

    try:
        plan = build_cleanup_plan(repo, manifest)
        result: dict[str, Any] = {
            "mode": "DRY_RUN",
            "manifest": str(manifest),
            "eligible_count": plan["eligible_count"],
            "blocked_count": plan["blocked_count"],
            "eligible_bytes": plan["eligible_bytes"],
            "eligible_mib": round(plan["eligible_bytes"] / 1048576, 1),
            "blocked": plan["blocked"],
        }
        if args.apply:
            applied = apply_cleanup(repo, plan, deletion_manifest)
            result.update(applied)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"VALIDATION_DB_CLEANUP {result['mode']}")
            print(f"eligible_count={result['eligible_count']}")
            print(f"blocked_count={result['blocked_count']}")
            print(f"eligible_mib={result['eligible_mib']}")
            if args.apply:
                print(f"deleted_count={result['deleted_count']}")
                print(f"deletion_manifest={result['deletion_manifest']}")
        return 0
    except CleanupPlanError as exc:
        print(f"VALIDATION_DB_CLEANUP FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
