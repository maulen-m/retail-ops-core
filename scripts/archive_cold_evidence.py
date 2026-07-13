#!/usr/bin/env python3
"""Losslessly archive cold orchestration evidence before retiring its expanded copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLY_ENV = "ENABLE_COLD_EVIDENCE_ARCHIVE"
DEFAULT_MIN_AGE_DAYS = 14


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _scope_run(run: Path, project_root: Path) -> Path:
    run = run.expanduser().resolve()
    expected_parent = (
        project_root.expanduser().resolve() / ".claude" / "orchestrator_runs"
    )
    if run.parent != expected_parent:
        raise ValueError(f"run must be an immediate child of {expected_parent}")
    return run


def _scope_target(target: Path, project_root: Path) -> tuple[Path, str]:
    target = target.expanduser().resolve()
    root = project_root.expanduser().resolve()
    validation_parent = root / "exports" / "validation"
    orchestration_parent = root / ".claude" / "orchestrator_runs"
    if target.parent == validation_parent:
        return target, "validation_packet"
    if target.name == "evidence" and target.parent.parent == orchestration_parent:
        return target, "orchestration_evidence"
    raise ValueError(
        "target must be one immediate exports/validation packet or one "
        ".claude/orchestrator_runs/*/evidence directory"
    )


def _tree_stats(evidence: Path) -> dict[str, Any]:
    entries = list(evidence.rglob("*"))
    files = [path for path in entries if path.is_file() or path.is_symlink()]
    logical_bytes = sum(path.lstat().st_size for path in files)
    mtimes = [evidence.lstat().st_mtime, *(path.lstat().st_mtime for path in entries)]
    return {
        "file_count": len(files),
        "directory_count": sum(
            path.is_dir() and not path.is_symlink() for path in entries
        ),
        "logical_bytes": logical_bytes,
        "latest_mtime_utc": datetime.fromtimestamp(max(mtimes), timezone.utc),
    }


def inspect_cold_tree(
    *,
    target: Path,
    project_root: Path = PROJECT_ROOT,
    min_age_days: int = DEFAULT_MIN_AGE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    target, scope = _scope_target(target, project_root)
    if not target.is_dir():
        raise FileNotFoundError(f"expanded cold tree is missing: {target}")
    if min_age_days < 1:
        raise ValueError("min_age_days must be at least 1")
    stats = _tree_stats(target)
    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_seconds = (
        current.astimezone(timezone.utc) - stats["latest_mtime_utc"]
    ).total_seconds()
    age_days = age_seconds / 86400
    if age_days < min_age_days:
        raise ValueError(
            f"evidence is not cold enough: age={age_days:.3f}d minimum={min_age_days}d"
        )
    archive = target.with_name(f"{target.name}.tar.zst")
    manifest = target.with_name(f"{target.name}.archive_manifest.json")
    return {
        "schema_version": 1,
        "gate": "DRY_RUN",
        "scope": scope,
        "target": str(target),
        "source_tree": target.name,
        "file_count": stats["file_count"],
        "directory_count": stats["directory_count"],
        "logical_bytes": stats["logical_bytes"],
        "latest_mtime_utc": stats["latest_mtime_utc"]
        .isoformat()
        .replace("+00:00", "Z"),
        "age_days": round(age_days, 3),
        "minimum_age_days": min_age_days,
        "archive": str(archive),
        "manifest": str(manifest),
        "expanded_tree_retired": False,
    }


def inspect_evidence(
    *,
    run: Path,
    project_root: Path = PROJECT_ROOT,
    min_age_days: int = DEFAULT_MIN_AGE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    run = _scope_run(run, project_root)
    evidence = run / "evidence"
    payload = inspect_cold_tree(
        target=evidence,
        project_root=project_root,
        min_age_days=min_age_days,
        now=now,
    )
    return {**payload, "run": str(run)}


def _run_archive_pipeline(
    *,
    parent: Path,
    source_name: str,
    output: Path,
    popen: Callable[..., Any] = subprocess.Popen,
) -> None:
    zstd = shutil.which("zstd") or "/opt/homebrew/bin/zstd"
    tar_process = popen(
        ["tar", "-cf", "-", "-C", str(parent), source_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert tar_process.stdout is not None
    zstd_process = popen(
        [zstd, "-T0", "-8", "-q", "-o", str(output)],
        stdin=tar_process.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tar_process.stdout.close()
    _, zstd_stderr = zstd_process.communicate()
    tar_stderr = tar_process.stderr.read() if tar_process.stderr else b""
    tar_returncode = tar_process.wait()
    if tar_returncode != 0 or zstd_process.returncode != 0:
        raise RuntimeError(
            "cold evidence archive pipeline failed "
            f"(tar_rc={tar_returncode}, zstd_rc={zstd_process.returncode}, "
            f"tar_error={bool(tar_stderr)}, zstd_error={bool(zstd_stderr)})"
        )


def verify_archive(
    archive: Path,
    *,
    expected_file_count: int,
    expected_root: str = "evidence",
    runner: Callable[..., Any] = subprocess.run,
    popen: Callable[..., Any] = subprocess.Popen,
) -> dict[str, Any]:
    zstd = shutil.which("zstd") or "/opt/homebrew/bin/zstd"
    integrity = runner([zstd, "-q", "-t", str(archive)], capture_output=True)
    if integrity.returncode != 0:
        raise RuntimeError("cold evidence archive failed zstd integrity verification")

    decompressor = popen([zstd, "-q", "-dc", str(archive)], stdout=subprocess.PIPE)
    assert decompressor.stdout is not None
    listing = runner(
        ["tar", "-tf", "-"],
        stdin=decompressor.stdout,
        capture_output=True,
        text=True,
    )
    decompressor.stdout.close()
    decompress_returncode = decompressor.wait()
    if listing.returncode != 0 or decompress_returncode != 0:
        raise RuntimeError("cold evidence archive failed tar listing verification")
    names = [line for line in listing.stdout.splitlines() if line]
    if not names or names[0].rstrip("/") != expected_root:
        raise RuntimeError("cold evidence archive has an unexpected root")
    file_count = sum(not name.endswith("/") for name in names)
    if file_count != expected_file_count:
        raise RuntimeError(
            f"cold evidence archive file count mismatch: {file_count} != {expected_file_count}"
        )
    return {
        "gate": "GREEN",
        "archive": str(archive),
        "archive_sha256": _sha256(archive),
        "archive_size_bytes": archive.stat().st_size,
        "file_count": file_count,
        "entry_count": len(names),
    }


def archive_cold_tree(
    *,
    target: Path,
    project_root: Path = PROJECT_ROOT,
    min_age_days: int = DEFAULT_MIN_AGE_DAYS,
    apply: bool = False,
) -> dict[str, Any]:
    if apply and os.environ.get(APPLY_ENV) != "1":
        raise PermissionError(f"{APPLY_ENV}=1 is required with --apply")
    inspection = inspect_cold_tree(
        target=target,
        project_root=project_root,
        min_age_days=min_age_days,
    )
    if not apply:
        return inspection

    target = Path(inspection["target"])
    parent = target.parent
    archive = Path(inspection["archive"])
    manifest_path = Path(inspection["manifest"])
    if archive.exists() or manifest_path.exists():
        raise FileExistsError("cold evidence archive or manifest already exists")
    temporary = parent / f".{target.name}.tar.zst.tmp.{os.getpid()}"
    retirement = parent / f".{target.name}.retiring.{os.getpid()}"
    try:
        _run_archive_pipeline(parent=parent, source_name=target.name, output=temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        verified = verify_archive(
            temporary,
            expected_file_count=int(inspection["file_count"]),
            expected_root=target.name,
        )
        os.replace(temporary, archive)
        archive_sha = _sha256(archive)
        if archive_sha != verified["archive_sha256"]:
            raise RuntimeError("cold evidence archive hash changed during finalization")
        manifest = {
            **inspection,
            "gate": "GREEN",
            "created_at_utc": _utc_now().isoformat().replace("+00:00", "Z"),
            "archive": str(archive),
            "archive_sha256": archive_sha,
            "archive_size_bytes": archive.stat().st_size,
            "verification": {
                "zstd_integrity": "ok",
                "tar_listing": "ok",
                "file_count": verified["file_count"],
                "entry_count": verified["entry_count"],
            },
            "expanded_tree_retired": False,
            "restore_command": f"zstd -dc '{archive}' | tar -xf - -C '{parent}'",
        }
        _atomic_write_json(manifest_path, manifest)
        os.replace(target, retirement)
        shutil.rmtree(retirement)
        manifest["expanded_tree_retired"] = True
        _atomic_write_json(manifest_path, manifest)
        return manifest
    finally:
        temporary.unlink(missing_ok=True)


def archive_evidence(
    *,
    run: Path,
    project_root: Path = PROJECT_ROOT,
    min_age_days: int = DEFAULT_MIN_AGE_DAYS,
    apply: bool = False,
) -> dict[str, Any]:
    run = _scope_run(run, project_root)
    payload = archive_cold_tree(
        target=run / "evidence",
        project_root=project_root,
        min_age_days=min_age_days,
        apply=apply,
    )
    return {**payload, "run": str(run)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--run", type=Path)
    target.add_argument("--target", type=Path)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--min-age-days", type=int, default=DEFAULT_MIN_AGE_DAYS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.run:
        payload = archive_evidence(
            run=args.run,
            project_root=args.project_root,
            min_age_days=args.min_age_days,
            apply=args.apply,
        )
    else:
        payload = archive_cold_tree(
            target=args.target,
            project_root=args.project_root,
            min_age_days=args.min_age_days,
            apply=args.apply,
        )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Gate: {payload['gate']}")
        print(f"Target: {payload['target']}")
        print(f"Archive: {payload['archive']}")
    return 0 if payload["gate"] in {"GREEN", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
