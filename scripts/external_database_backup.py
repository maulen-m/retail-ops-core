#!/usr/bin/env python3
"""
Create timestamped snapshots of External_database to Google Drive backup root.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_SOURCE_ROOT = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database"
)
DEFAULT_BACKUP_ROOT = Path(
    "~/Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business/repo_backups_G/External_database"
)


@dataclass(frozen=True)
class SnapshotPaths:
    snapshots_dir: Path
    snapshot_dir: Path
    snapshot_data_dir: Path
    manifest_path: Path
    latest_pointer_path: Path


def build_snapshot_paths(backup_root: Path, timestamp: str) -> SnapshotPaths:
    snapshots_dir = backup_root / "snapshots"
    snapshot_dir = snapshots_dir / timestamp
    return SnapshotPaths(
        snapshots_dir=snapshots_dir,
        snapshot_dir=snapshot_dir,
        snapshot_data_dir=snapshot_dir / "External_database",
        manifest_path=snapshot_dir / "backup_manifest.json",
        latest_pointer_path=backup_root / "latest_snapshot.txt",
    )


def dir_stats(path: Path) -> tuple[int, int]:
    files = 0
    bytes_total = 0
    if not path.exists():
        return files, bytes_total
    for file_path in path.rglob("*"):
        if file_path.is_file():
            files += 1
            bytes_total += file_path.stat().st_size
    return files, bytes_total


def list_snapshot_dirs(backup_root: Path) -> list[Path]:
    snapshots_dir = backup_root / "snapshots"
    if not snapshots_dir.exists():
        return []
    return sorted([p for p in snapshots_dir.iterdir() if p.is_dir()])


def parse_snapshot_name(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, "%Y%m%d_%H%M%S").replace(tzinfo=ALMATY_TZ)
    except ValueError:
        return None


def cleanup_old_snapshots(backup_root: Path, keep_days: int) -> list[str]:
    cutoff = datetime.now(ALMATY_TZ) - timedelta(days=keep_days)
    deleted: list[str] = []
    for snapshot_dir in list_snapshot_dirs(backup_root):
        dt = parse_snapshot_name(snapshot_dir.name)
        if dt is None:
            continue
        if dt < cutoff:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            deleted.append(snapshot_dir.name)
    return deleted


def create_snapshot(
    source_root: Path,
    backup_root: Path,
    keep_days: int = 30,
    critical_subdirs: list[str] | None = None,
) -> dict[str, Any]:
    if not source_root.exists():
        raise FileNotFoundError(f"Source root does not exist: {source_root}")

    critical_subdirs = critical_subdirs or ["Kaspi_marketing"]
    started_at = datetime.now(ALMATY_TZ)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    paths = build_snapshot_paths(backup_root, timestamp)

    paths.snapshots_dir.mkdir(parents=True, exist_ok=True)
    if paths.snapshot_dir.exists():
        raise RuntimeError(f"Snapshot already exists: {paths.snapshot_dir}")

    shutil.copytree(source_root, paths.snapshot_data_dir, copy_function=shutil.copy2)
    file_count, bytes_total = dir_stats(paths.snapshot_data_dir)

    critical_missing: list[str] = []
    for subdir in critical_subdirs:
        if not (paths.snapshot_data_dir / subdir).exists():
            critical_missing.append(subdir)

    finished_at = datetime.now(ALMATY_TZ)
    duration_seconds = round((finished_at - started_at).total_seconds(), 2)
    status = "ok" if file_count > 0 and not critical_missing else "invalid"

    manifest: dict[str, Any] = {
        "snapshot_id": timestamp,
        "status": status,
        "source_root": str(source_root),
        "backup_root": str(backup_root),
        "snapshot_data_dir": str(paths.snapshot_data_dir),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "files": file_count,
        "bytes_total": bytes_total,
        "keep_days": keep_days,
        "critical_subdirs": critical_subdirs,
        "critical_missing": critical_missing,
    }

    paths.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths.latest_pointer_path.write_text(timestamp + "\n", encoding="utf-8")

    deleted = cleanup_old_snapshots(backup_root, keep_days=keep_days)
    manifest["deleted_snapshots"] = deleted
    paths.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup External_database to Google Drive snapshots")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument(
        "--critical-subdir",
        action="append",
        dest="critical_subdirs",
        help="Critical subdir that must exist in snapshot (repeatable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = create_snapshot(
        source_root=args.source_root,
        backup_root=args.backup_root,
        keep_days=args.keep_days,
        critical_subdirs=args.critical_subdirs,
    )
    print(
        json.dumps(
            {
                "snapshot_id": manifest["snapshot_id"],
                "status": manifest["status"],
                "files": manifest["files"],
                "bytes_total": manifest["bytes_total"],
                "deleted_snapshots": manifest.get("deleted_snapshots", []),
            },
            ensure_ascii=False,
        )
    )
    return 0 if manifest["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
