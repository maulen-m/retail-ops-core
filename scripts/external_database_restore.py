#!/usr/bin/env python3
"""
Restore missing External_database paths from latest snapshot backup.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_ROOT = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database"
)
DEFAULT_BACKUP_ROOT = Path(
    "~/Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business/repo_backups_G/External_database"
)


def list_snapshot_dirs(backup_root: Path) -> list[Path]:
    snapshots_dir = backup_root / "snapshots"
    if not snapshots_dir.exists():
        return []
    return sorted([p for p in snapshots_dir.iterdir() if p.is_dir()], reverse=True)


def load_manifest(snapshot_dir: Path) -> dict[str, Any] | None:
    manifest_path = snapshot_dir / "backup_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_latest_valid_snapshot(backup_root: Path) -> Path | None:
    for snapshot_dir in list_snapshot_dirs(backup_root):
        manifest = load_manifest(snapshot_dir)
        if not manifest:
            continue
        if manifest.get("status") != "ok":
            continue
        data_dir = snapshot_dir / "External_database"
        if data_dir.exists():
            return snapshot_dir
    return None


def _copy_missing_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    if not dest.exists():
        shutil.copytree(src, dest, copy_function=shutil.copy2)
        return
    for item in src.iterdir():
        src_item = item
        dst_item = dest / item.name
        if dst_item.exists():
            continue
        if src_item.is_dir():
            shutil.copytree(src_item, dst_item, copy_function=shutil.copy2)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_item, dst_item)


def restore_missing_paths(
    source_root: Path,
    backup_root: Path,
    required_subdirs: list[str] | None = None,
) -> dict[str, Any]:
    required_subdirs = required_subdirs or ["Kaspi_marketing"]
    actions: list[str] = []

    snapshot_dir = get_latest_valid_snapshot(backup_root)
    if snapshot_dir is None:
        return {
            "restored": False,
            "reason": "no_valid_snapshot",
            "snapshot": "",
            "actions": actions,
        }

    snapshot_data = snapshot_dir / "External_database"
    if not source_root.exists():
        source_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(snapshot_data, source_root, copy_function=shutil.copy2)
        actions.append(f"restored_full:{source_root}")
    else:
        for subdir in required_subdirs:
            src_subdir = snapshot_data / subdir
            dst_subdir = source_root / subdir
            if dst_subdir.exists():
                continue
            if not src_subdir.exists():
                actions.append(f"missing_in_snapshot:{subdir}")
                continue
            _copy_missing_tree(src_subdir, dst_subdir)
            actions.append(f"restored_subdir:{subdir}")

    return {
        "restored": bool(actions),
        "reason": "ok",
        "snapshot": str(snapshot_dir),
        "actions": actions,
    }


def ensure_external_database_available(
    source_root: Path,
    backup_root: Path,
    required_subdirs: list[str] | None = None,
) -> dict[str, Any]:
    source_ok = source_root.exists()
    required_subdirs = required_subdirs or ["Kaspi_marketing"]
    if source_ok and all((source_root / subdir).exists() for subdir in required_subdirs):
        return {
            "restored": False,
            "reason": "already_available",
            "snapshot": "",
            "actions": [],
        }
    return restore_missing_paths(
        source_root=source_root,
        backup_root=backup_root,
        required_subdirs=required_subdirs,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore missing External_database paths from latest backup")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument(
        "--required-subdir",
        action="append",
        dest="required_subdirs",
        help="Required subdir to restore when missing (repeatable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = ensure_external_database_available(
        source_root=args.source_root,
        backup_root=args.backup_root,
        required_subdirs=args.required_subdirs,
    )
    print(json.dumps(result, ensure_ascii=False))
    if result["reason"] == "no_valid_snapshot":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
