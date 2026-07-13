#!/usr/bin/env python3
"""Losslessly compact old runtime DB backups and retain exact restore proof.

The default is a read-only inventory. Apply mode requires both ``--apply`` and
``ENABLE_RUNTIME_BACKUP_COMPACTION=1``. A source backup is removed only after
zstd integrity testing, decompressed SHA-256 equality, an atomic archive move,
and an adjacent restore manifest. The global JSONL ledger is supplementary;
the adjacent manifest is sufficient to verify and restore one archive.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "runtime" / "backups"
APPLY_ENV = "ENABLE_RUNTIME_BACKUP_COMPACTION"
RESTORE_ENV = "ENABLE_RUNTIME_BACKUP_RESTORE"
ELIGIBLE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
MANIFEST_NAME = "compaction_manifest.jsonl"
LOCK_NAME = ".backup_compaction.lock"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_decompressed_zstd(path: Path, zstd_bin: str) -> str:
    digest = hashlib.sha256()
    process = subprocess.Popen(
        [zstd_bin, "-q", "-dc", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    stderr = process.stderr.read() if process.stderr is not None else b""
    return_code = process.wait()
    if return_code != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"zstd decompression verification failed rc={return_code}: {message}")
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def discover_candidates(
    root: Path,
    *,
    older_than_days: int,
    now: float | None = None,
) -> list[Path]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"backup root does not exist: {root}")
    if older_than_days < 1:
        raise ValueError("older_than_days must be at least 1")

    cutoff = (time.time() if now is None else now) - (older_than_days * 24 * 60 * 60)
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in ELIGIBLE_SUFFIXES:
            continue
        if path.stat().st_mtime < cutoff:
            candidates.append(path)
    return sorted(candidates, key=lambda item: (item.stat().st_mtime_ns, item.as_posix()))


class CompactionLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "CompactionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise RuntimeError(f"backup compaction is already running: {self.path}") from exc
            raise
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"{os.getpid()}\n")
        self.handle.flush()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is None:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None


def _free_percent(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return (usage.free / usage.total) * 100 if usage.total else 0.0


def _require_binary(binary: str) -> str:
    resolved = shutil.which(binary) if "/" not in binary else binary
    if not resolved or not Path(resolved).is_file():
        raise FileNotFoundError(f"required zstd binary not found: {binary}")
    return str(Path(resolved).resolve())


def _compress_one(source: Path, root: Path, zstd_bin: str) -> dict[str, Any]:
    archive = Path(f"{source}.zst")
    sidecar = Path(f"{archive}.manifest.json")
    relative_source = _relative(source, root)
    if archive.exists() or sidecar.exists():
        return {
            "source": relative_source,
            "status": "SKIPPED_DESTINATION_EXISTS",
            "archive": archive.name,
        }

    source_stat = source.stat()
    original_sha256 = sha256_file(source)
    temp = archive.with_name(f".{archive.name}.tmp.{os.getpid()}")
    try:
        result = subprocess.run(
            [zstd_bin, "-q", "-6", "-f", "-o", str(temp), str(source)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip()
            raise RuntimeError(f"zstd compression failed rc={result.returncode}: {detail}")

        result = subprocess.run(
            [zstd_bin, "-q", "-t", str(temp)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip()
            raise RuntimeError(f"zstd archive test failed rc={result.returncode}: {detail}")

        decompressed_sha256 = sha256_decompressed_zstd(temp, zstd_bin)
        if decompressed_sha256 != original_sha256:
            raise RuntimeError("decompressed SHA-256 does not match source")

        compressed_sha256 = sha256_file(temp)
        compressed_size = temp.stat().st_size
        os.replace(temp, archive)
        os.utime(archive, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
        _fsync_directory(archive.parent)

        record = {
            "schema_version": 1,
            "completed_at_utc": utc_now(),
            "original_relative_path": relative_source,
            "archive_relative_path": _relative(archive, root),
            "original_size_bytes": source_stat.st_size,
            "compressed_size_bytes": compressed_size,
            "original_mtime_ns": source_stat.st_mtime_ns,
            "original_sha256": original_sha256,
            "compressed_sha256": compressed_sha256,
            "verification": "zstd_test_and_decompressed_sha256_match",
            "restore_command": (
                "ENABLE_RUNTIME_BACKUP_RESTORE=1 "
                "python scripts/compact_runtime_backups.py restore "
                f"--archive {archive} --output {source} --apply"
            ),
        }
        _atomic_write_json(sidecar, record)
        source.unlink()
        _fsync_directory(source.parent)
        _append_jsonl(root / MANIFEST_NAME, record)
        return {
            "source": relative_source,
            "archive": record["archive_relative_path"],
            "status": "COMPACTED_VERIFIED",
            "original_size_bytes": source_stat.st_size,
            "compressed_size_bytes": compressed_size,
            "logical_bytes_reduced": source_stat.st_size - compressed_size,
            "original_sha256": original_sha256,
        }
    finally:
        temp.unlink(missing_ok=True)


def compact_backups(
    *,
    root: Path,
    older_than_days: int = 30,
    apply: bool = False,
    max_files: int | None = None,
    target_free_percent: float | None = None,
    zstd_bin: str = "zstd",
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if max_files is not None and max_files < 1:
        raise ValueError("max_files must be at least 1")
    if target_free_percent is not None and not 0 < target_free_percent <= 100:
        raise ValueError("target_free_percent must be within (0, 100]")
    if apply and os.environ.get(APPLY_ENV) != "1":
        raise PermissionError(f"apply requires {APPLY_ENV}=1")

    candidates = discover_candidates(root, older_than_days=older_than_days)
    selected = candidates[:max_files] if max_files is not None else candidates
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "root": str(root),
        "mode": "APPLY" if apply else "DRY_RUN",
        "older_than_days": older_than_days,
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "compacted_count": 0,
        "logical_bytes_reduced": 0,
        "free_percent_before": round(_free_percent(root), 3),
        "free_percent_after": None,
        "items": [],
        "gate": "DRY_RUN" if not apply else "GREEN",
    }
    if not apply:
        report["items"] = [
            {
                "source": _relative(path, root),
                "size_bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "status": "WOULD_COMPACT",
            }
            for path in selected
        ]
        report["free_percent_after"] = report["free_percent_before"]
        return report

    zstd_bin = _require_binary(zstd_bin)
    with CompactionLock(root / LOCK_NAME):
        for source in selected:
            if target_free_percent is not None and _free_percent(root) >= target_free_percent:
                report["items"].append(
                    {"status": "TARGET_FREE_PERCENT_REACHED", "target": target_free_percent}
                )
                break
            try:
                item = _compress_one(source, root, zstd_bin)
            except Exception as exc:
                item = {
                    "source": _relative(source, root),
                    "status": "FAILED_SOURCE_PRESERVED",
                    "error": str(exc),
                }
            report["items"].append(item)
            if item["status"] == "COMPACTED_VERIFIED":
                report["compacted_count"] += 1
                report["logical_bytes_reduced"] += item["logical_bytes_reduced"]
            elif item["status"] not in {"TARGET_FREE_PERCENT_REACHED"}:
                report["gate"] = "YELLOW"

    report["free_percent_after"] = round(_free_percent(root), 3)
    return report


def restore_backup(
    *,
    archive: Path,
    output: Path,
    apply: bool = False,
    force: bool = False,
    zstd_bin: str = "zstd",
) -> dict[str, Any]:
    archive = archive.expanduser().resolve()
    output = output.expanduser().resolve()
    sidecar = Path(f"{archive}.manifest.json")
    if not archive.is_file() or not sidecar.is_file():
        raise FileNotFoundError("archive and adjacent manifest are both required")
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "mode": "APPLY" if apply else "DRY_RUN",
        "archive": str(archive),
        "output": str(output),
        "expected_sha256": record["original_sha256"],
        "gate": "DRY_RUN" if not apply else "GREEN",
    }
    if not apply:
        return report
    if os.environ.get(RESTORE_ENV) != "1":
        raise PermissionError(f"apply requires {RESTORE_ENV}=1")
    if output.exists() and not force:
        raise FileExistsError(f"restore output already exists: {output}")

    zstd_bin = _require_binary(zstd_bin)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.restore.tmp.{os.getpid()}")
    try:
        with temp.open("wb") as handle:
            result = subprocess.run(
                [zstd_bin, "-q", "-dc", str(archive)],
                check=False,
                stdout=handle,
                stderr=subprocess.PIPE,
            )
            handle.flush()
            os.fsync(handle.fileno())
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"zstd restore failed rc={result.returncode}: {detail}")
        restored_sha256 = sha256_file(temp)
        if restored_sha256 != record["original_sha256"]:
            raise RuntimeError("restored SHA-256 does not match adjacent manifest")
        os.replace(temp, output)
        mtime_ns = int(record["original_mtime_ns"])
        os.utime(output, ns=(mtime_ns, mtime_ns))
        _fsync_directory(output.parent)
        report["restored_sha256"] = restored_sha256
        report["restored_size_bytes"] = output.stat().st_size
        return report
    finally:
        temp.unlink(missing_ok=True)


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(
        f"gate={payload['gate']} mode={payload['mode']} "
        f"compacted={payload.get('compacted_count', 0)} "
        f"candidates={payload.get('candidate_count', 0)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compact = subparsers.add_parser("compact", help="inventory or compact old DB backups")
    compact.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    compact.add_argument("--older-than-days", type=int, default=30)
    compact.add_argument("--max-files", type=int)
    compact.add_argument("--target-free-percent", type=float)
    compact.add_argument("--zstd-bin", default="zstd")
    compact.add_argument("--apply", action="store_true")
    compact.add_argument("--json", action="store_true")

    restore = subparsers.add_parser("restore", help="restore one verified archive")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True)
    restore.add_argument("--zstd-bin", default="zstd")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--force", action="store_true")
    restore.add_argument("--json", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compact":
        payload = compact_backups(
            root=args.root,
            older_than_days=args.older_than_days,
            apply=args.apply,
            max_files=args.max_files,
            target_free_percent=args.target_free_percent,
            zstd_bin=args.zstd_bin,
        )
    else:
        payload = restore_backup(
            archive=args.archive,
            output=args.output,
            apply=args.apply,
            force=args.force,
            zstd_bin=args.zstd_bin,
        )
    _emit(payload, json_output=args.json)
    return 0 if payload["gate"] in {"GREEN", "DRY_RUN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
