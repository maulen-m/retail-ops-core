#!/usr/bin/env python3
"""Rotate canonical daily-shipping launchd logs into verified owner-only gzip archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "config" / "daily_shipping_runtime.json"
APPLY_ENV = "ENABLE_DAILY_SHIPPING_LOG_MAINTENANCE"


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


def _expand_path(value: str, *, project_root: Path) -> Path:
    expanded = value.replace("${PROJECT_ROOT}", str(project_root)).replace(
        "${HOME}", str(Path.home())
    )
    return Path(expanded).expanduser().resolve()


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_log_paths(*, manifest_path: Path, project_root: Path) -> list[Path]:
    manifest = _load_manifest(manifest_path)
    expected_parent = project_root.expanduser().resolve() / "runtime_logs"
    raw_paths: list[str] = []
    for scheduler in manifest.get("schedulers") or []:
        raw_paths.extend(
            [str(scheduler.get("stdout") or ""), str(scheduler.get("stderr") or "")]
        )
    maintenance = manifest.get("observability", {}).get("log_maintenance") or {}
    raw_paths.extend(str(value) for value in maintenance.get("extra_paths") or [])
    paths: set[Path] = set()
    for value in raw_paths:
        if not value:
            continue
        path = _expand_path(value, project_root=project_root)
        if path.parent != expected_parent:
            raise ValueError(f"canonical shipping log is outside runtime_logs: {path}")
        paths.add(path)
    return sorted(paths, key=lambda path: path.name)


def _no_open_handles(path: Path) -> bool:
    completed = subprocess.run(
        ["/usr/sbin/lsof", "-t", "--", str(path)],
        capture_output=True,
        text=True,
    )
    return completed.returncode != 0 or not completed.stdout.strip()


def _wait_closed(
    path: Path,
    *,
    no_open_handles: Callable[[Path], bool],
    timeout_seconds: float = 60,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not no_open_handles(path):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"rotated log still has an open writer: {path}")
        sleeper(0.25)


def _rotate_one(
    *,
    source: Path,
    archive_root: Path,
    now: datetime,
    no_open_handles: Callable[[Path], bool],
) -> dict[str, Any]:
    source_mode = source.stat().st_mode & 0o777
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = source.with_name(f".{source.name}.rotating.{os.getpid()}")
    archive = archive_root / f"{source.name}.{stamp}.gz"
    temporary = archive.with_name(f".{archive.name}.tmp.{os.getpid()}")
    manifest_path = archive.with_suffix(f"{archive.suffix}.manifest.json")
    if raw.exists() or archive.exists() or manifest_path.exists():
        raise FileExistsError(
            f"log rotation target already exists for {source.name} at {stamp}"
        )
    os.replace(source, raw)
    source.touch(mode=source_mode, exist_ok=False)
    try:
        _wait_closed(raw, no_open_handles=no_open_handles)
        original_sha = _sha256(raw)
        with (
            raw.open("rb") as source_handle,
            gzip.open(temporary, "wb", compresslevel=6) as target,
        ):
            shutil.copyfileobj(source_handle, target, length=1024 * 1024)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        with gzip.open(temporary, "rb") as compressed:
            digest = hashlib.sha256()
            for chunk in iter(lambda: compressed.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != original_sha:
            raise RuntimeError(f"rotated log gzip verification failed: {source.name}")
        os.replace(temporary, archive)
        manifest = {
            "schema_version": 1,
            "source_name": source.name,
            "rotated_at_utc": now.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "original_size_bytes": raw.stat().st_size,
            "original_sha256": original_sha,
            "archive": str(archive),
            "archive_size_bytes": archive.stat().st_size,
            "archive_sha256": _sha256(archive),
            "gzip_roundtrip_sha256": original_sha,
        }
        _atomic_write_json(manifest_path, manifest)
        raw.unlink()
        return {
            **manifest,
            "manifest": str(manifest_path),
            "status": "ROTATED_VERIFIED",
        }
    finally:
        temporary.unlink(missing_ok=True)


def _enforce_archive_count(archive_root: Path, *, source_name: str, keep: int) -> int:
    archives = sorted(
        archive_root.glob(f"{source_name}.*.gz"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    removed = 0
    for archive in archives[keep:]:
        manifest = archive.with_suffix(f"{archive.suffix}.manifest.json")
        archive.unlink()
        manifest.unlink(missing_ok=True)
        removed += 1
    return removed


def rotate_daily_shipping_logs(
    *,
    manifest_path: Path = MANIFEST_PATH,
    project_root: Path = PROJECT_ROOT,
    apply: bool = False,
    now: datetime | None = None,
    no_open_handles: Callable[[Path], bool] = _no_open_handles,
) -> dict[str, Any]:
    if apply and os.environ.get(APPLY_ENV) != "1":
        raise PermissionError(f"{APPLY_ENV}=1 is required with --apply")
    manifest = _load_manifest(manifest_path)
    policy = manifest.get("observability", {}).get("log_maintenance") or {}
    max_bytes = int(policy["max_bytes"])
    keep = int(policy["keep_archives_per_log"])
    if max_bytes < 1 or keep < 1:
        raise ValueError("log max_bytes and keep_archives_per_log must be positive")
    archive_root = _expand_path(str(policy["archive_root"]), project_root=project_root)
    root = project_root.expanduser().resolve()
    try:
        archive_root.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("log archive root must be outside the repo")
    paths = discover_log_paths(manifest_path=manifest_path, project_root=project_root)
    candidates = [
        path for path in paths if path.is_file() and path.stat().st_size > max_bytes
    ]
    if not apply:
        return {
            "schema_version": 1,
            "gate": "DRY_RUN",
            "max_bytes": max_bytes,
            "keep_archives_per_log": keep,
            "discovered_count": len(paths),
            "oversize_count": len(candidates),
            "items": [
                {
                    "source": str(path),
                    "size_bytes": path.stat().st_size,
                    "status": "WOULD_ROTATE",
                }
                for path in candidates
            ],
        }

    archive_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(archive_root, 0o700)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    items: list[dict[str, Any]] = []
    removed_archives = 0
    for source in candidates:
        if not no_open_handles(source):
            items.append(
                {
                    "source": str(source),
                    "size_bytes": source.stat().st_size,
                    "status": "SKIPPED_OPEN",
                }
            )
            continue
        item = _rotate_one(
            source=source,
            archive_root=archive_root,
            now=current,
            no_open_handles=no_open_handles,
        )
        items.append(item)
        removed_archives += _enforce_archive_count(
            archive_root,
            source_name=source.name,
            keep=keep,
        )
    rotated = sum(item.get("status") == "ROTATED_VERIFIED" for item in items)
    skipped = sum(item.get("status") == "SKIPPED_OPEN" for item in items)
    return {
        "schema_version": 1,
        "gate": "GREEN" if skipped == 0 else "YELLOW",
        "max_bytes": max_bytes,
        "keep_archives_per_log": keep,
        "discovered_count": len(paths),
        "oversize_count": len(candidates),
        "rotated_count": rotated,
        "skipped_open_count": skipped,
        "expired_archives_removed": removed_archives,
        "items": items,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = rotate_daily_shipping_logs(
        manifest_path=args.manifest,
        project_root=args.project_root,
        apply=args.apply,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Gate: {payload['gate']}")
        print(f"Rotated: {payload.get('rotated_count', 0)}")
    return 0 if payload["gate"] in {"GREEN", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
