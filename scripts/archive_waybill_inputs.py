#!/usr/bin/env python3
"""
Archive waybill workflow inputs with selection-aware PDF scope.

This script archives:
1) CRM workbook snapshot
2) Only waybill PDFs that belong to the current selected order IDs
3) Optional waybill ZIP artifacts

It also applies retention for:
- Active waybill cache PDFs
- Local archive input folders

Old cache PDFs can be migrated into External_database before deletion.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


LOGGER = logging.getLogger(__name__)
DEFAULT_EXTERNAL_DB_ROOT = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database"
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_order_id_from_filename(path: Path) -> str:
    stem = path.stem
    if stem.isdigit():
        return stem
    name = path.name
    if name.startswith("KASPI_SHOP-") and name.lower().endswith(".pdf"):
        maybe = name[len("KASPI_SHOP-") : -4]
        if maybe.isdigit():
            return maybe
    return ""


def _load_selection_order_ids(selection_cache: Path) -> set[str]:
    if not selection_cache.exists():
        LOGGER.warning(f"Selection cache not found: {selection_cache}")
        return set()
    try:
        payload = json.loads(selection_cache.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning(f"Failed to read selection cache {selection_cache}: {exc}")
        return set()
    stores = payload.get("stores") or {}
    order_ids: set[str] = set()
    for ids in stores.values():
        if not ids:
            continue
        for oid in ids:
            text = str(oid).strip()
            if text and text.isdigit():
                order_ids.add(text)
    return order_ids


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _remove_old_dirs(base_dir: Path, prefix: str, days: int) -> int:
    if not base_dir.exists() or days < 0:
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for child in base_dir.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith(prefix):
            continue
        try:
            mtime = datetime.fromtimestamp(child.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


def _is_gdrive_like_path(path: Path) -> bool:
    as_posix = str(path).replace("\\", "/")
    return (
        "/Library/CloudStorage/GoogleDrive-" in as_posix
        or "/repo_backups_G/External_database" in as_posix
    )


def _resolve_external_db_root(candidate: Path | None) -> Path | None:
    if candidate is None:
        return None
    if _is_gdrive_like_path(candidate):
        LOGGER.warning(
            "External DB root points to Google Drive snapshot path; "
            f"forcing local External_database root: {DEFAULT_EXTERNAL_DB_ROOT}"
        )
        return DEFAULT_EXTERNAL_DB_ROOT
    return candidate


@dataclass
class ArchiveResult:
    timestamp: str
    selected_orders: int = 0
    copied_waybills: int = 0
    missing_waybills: int = 0
    skipped_unselected: int = 0
    copied_zip_count: int = 0
    copied_workbook_local: bool = False
    copied_workbook_gdrive: bool = False
    copied_workbook_external_db: bool = False
    migrated_old_cache: int = 0
    deduped_old_cache: int = 0
    removed_old_cache: int = 0
    removed_old_archives: int = 0
    archive_dir: Path | None = None
    external_db_repo_dir: Path | None = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive waybill workflow inputs using selected order IDs only."
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--selection-cache", type=Path, required=True)
    parser.add_argument("--crm-file", type=Path, required=True)
    parser.add_argument("--waybill-dir", type=Path, required=True)
    parser.add_argument("--active-orders-dir", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--gdrive-archive-root", type=Path, required=False)
    parser.add_argument("--external-db-root", type=Path, required=False)
    parser.add_argument("--repo-label", default="Autonomous_business")
    parser.add_argument(
        "--cache-retention-days",
        type=int,
        default=_env_int("KASPI_WAYBILL_CACHE_RETENTION_DAYS", 30),
    )
    parser.add_argument(
        "--archive-retention-days",
        type=int,
        default=_env_int("KASPI_ARCHIVE_RETENTION_DAYS", 14),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    result = ArchiveResult(timestamp=ts)

    selected_order_ids = _load_selection_order_ids(args.selection_cache)
    result.selected_orders = len(selected_order_ids)
    if not selected_order_ids:
        LOGGER.warning("Selection set is empty; archiving workbook/metadata only.")

    archive_dir = args.archive_root / f"input_{ts}"
    waybills_archive_dir = archive_dir / "waybills"
    archive_dir.mkdir(parents=True, exist_ok=True)
    waybills_archive_dir.mkdir(parents=True, exist_ok=True)
    result.archive_dir = archive_dir

    # Always copy workbook to local archive.
    result.copied_workbook_local = _copy_if_exists(
        args.crm_file, archive_dir / args.crm_file.name
    )

    # Google Drive backup remains workbook-only.
    if args.gdrive_archive_root:
        gdrive_dir = args.gdrive_archive_root / f"input_{ts}"
        gdrive_dir.mkdir(parents=True, exist_ok=True)
        result.copied_workbook_gdrive = _copy_if_exists(
            args.crm_file, gdrive_dir / args.crm_file.name
        )

    # Selection-aware waybill archive.
    selected_remaining = set(selected_order_ids)
    if args.waybill_dir.exists() and selected_order_ids:
        for pdf in sorted(args.waybill_dir.glob("*.pdf")):
            oid = _parse_order_id_from_filename(pdf)
            if not oid:
                continue
            if oid not in selected_order_ids:
                result.skipped_unselected += 1
                continue
            if _copy_if_exists(pdf, waybills_archive_dir / f"{oid}.pdf"):
                result.copied_waybills += 1
                selected_remaining.discard(oid)
    result.missing_waybills = len(selected_remaining)

    # Keep ZIP input artifacts in local archive (small footprint vs PDFs).
    if args.active_orders_dir.exists():
        for zf in sorted(args.active_orders_dir.glob("waybill*.zip")):
            if _copy_if_exists(zf, archive_dir / zf.name):
                result.copied_zip_count += 1

    # Migrate old cache PDFs to External_database before pruning local cache.
    external_db_root = _resolve_external_db_root(args.external_db_root)
    if external_db_root:
        repo_dir = external_db_root / args.repo_label / "kaspi_waybills"
        by_order_dir = repo_dir / "by_order"
        manifests_dir = repo_dir / "manifests" / datetime.now().strftime("%Y-%m-%d")
        workbooks_dir = repo_dir / "workbooks"
        by_order_dir.mkdir(parents=True, exist_ok=True)
        manifests_dir.mkdir(parents=True, exist_ok=True)
        workbooks_dir.mkdir(parents=True, exist_ok=True)
        result.external_db_repo_dir = repo_dir

        # Workbook snapshot to external DB as well.
        workbook_name = f"{args.crm_file.stem}_{ts}{args.crm_file.suffix}"
        result.copied_workbook_external_db = _copy_if_exists(
            args.crm_file, workbooks_dir / workbook_name
        )

        # Prepare list of old cache files.
        cutoff = datetime.now() - timedelta(days=args.cache_retention_days)
        old_cache_files: list[Path] = []
        if args.waybill_dir.exists():
            for pdf in args.waybill_dir.glob("*.pdf"):
                try:
                    mtime = datetime.fromtimestamp(pdf.stat().st_mtime)
                except OSError:
                    continue
                if mtime < cutoff:
                    old_cache_files.append(pdf)

        for pdf in old_cache_files:
            oid = _parse_order_id_from_filename(pdf)
            if not oid:
                continue
            dst = by_order_dir / f"{oid}.pdf"
            if dst.exists():
                result.deduped_old_cache += 1
            else:
                if _copy_if_exists(pdf, dst):
                    result.migrated_old_cache += 1

        # Manifest for this archive run.
        manifest = {
            "timestamp": ts,
            "selection_cache": str(args.selection_cache),
            "selected_orders": sorted(selected_order_ids),
            "selected_count": result.selected_orders,
            "copied_waybills": result.copied_waybills,
            "missing_waybills": result.missing_waybills,
            "skipped_unselected": result.skipped_unselected,
            "copied_zip_count": result.copied_zip_count,
            "migrated_old_cache": result.migrated_old_cache,
            "deduped_old_cache": result.deduped_old_cache,
            "cache_retention_days": args.cache_retention_days,
            "archive_retention_days": args.archive_retention_days,
            "archive_dir": str(archive_dir),
            "external_db_repo_dir": str(repo_dir),
        }
        manifest_path = manifests_dir / f"input_{ts}_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Always write local manifest.
    local_manifest = {
        "timestamp": ts,
        "selected_count": result.selected_orders,
        "copied_waybills": result.copied_waybills,
        "missing_waybills": result.missing_waybills,
        "skipped_unselected": result.skipped_unselected,
        "copied_zip_count": result.copied_zip_count,
        "copied_workbook_local": result.copied_workbook_local,
        "copied_workbook_gdrive": result.copied_workbook_gdrive,
        "copied_workbook_external_db": result.copied_workbook_external_db,
    }
    (archive_dir / "archive_manifest.json").write_text(
        json.dumps(local_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (archive_dir / "archive_manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["key", "value"])
        for key, value in local_manifest.items():
            writer.writerow([key, value])

    # Remove old cache PDFs from local active folder.
    if args.cache_retention_days >= 0 and args.waybill_dir.exists():
        cutoff = datetime.now() - timedelta(days=args.cache_retention_days)
        for pdf in args.waybill_dir.glob("*.pdf"):
            try:
                mtime = datetime.fromtimestamp(pdf.stat().st_mtime)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    pdf.unlink()
                    result.removed_old_cache += 1
                except OSError:
                    continue

    # Remove old local archive folders.
    result.removed_old_archives = _remove_old_dirs(
        args.archive_root, "input_", args.archive_retention_days
    )

    # Human-readable summary.
    print(f"Archive dir: {archive_dir}")
    print(f"Selected orders: {result.selected_orders}")
    print(f"Waybills copied (selected only): {result.copied_waybills}")
    print(f"Waybills missing from cache: {result.missing_waybills}")
    print(f"Waybills skipped (unselected): {result.skipped_unselected}")
    print(f"Workbook copied (local): {int(result.copied_workbook_local)}")
    print(f"Workbook copied (gdrive): {int(result.copied_workbook_gdrive)}")
    print(f"Workbook copied (external_db): {int(result.copied_workbook_external_db)}")
    print(f"Old cache migrated (external_db): {result.migrated_old_cache}")
    print(f"Old cache deduped (external_db): {result.deduped_old_cache}")
    print(f"Old cache removed (local): {result.removed_old_cache}")
    print(f"Old archive folders removed: {result.removed_old_archives}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
