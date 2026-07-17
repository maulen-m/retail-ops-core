#!/usr/bin/env python3
"""Create, back up, verify, and restore daily-shipping recovery snapshots.

The production database is copied with SQLite's online backup API. Remote
backup is encrypted by restic and is disabled unless both ``--apply`` and the
matching environment gate are present. Credential values are never read by
this module; restic obtains its password through a Keychain-backed command.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import AbstractContextManager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_daily_shipping_closeout import (  # noqa: E402
    CloseoutEvidenceError,
    verify_closeout_evidence,
)


DEFAULT_STATE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Autonomous_business"
    / "shipping_recovery"
)
DEFAULT_REPOSITORY = (
    "rclone:gdrive2:Autonomous_business_backups/restic_critical_shipping_m1"
)
DEFAULT_PASSWORD_COMMAND = (
    "/usr/bin/security find-generic-password -a adil "
    "-s Autonomous_business_restic_gdrive2 -w"
)
DEFAULT_TAG = "daily-shipping-critical"
BACKUP_APPLY_ENV = "ENABLE_SHIPPING_RECOVERY_BACKUP"
RETENTION_APPLY_ENV = "ENABLE_SHIPPING_RECOVERY_RETENTION"
RESTORE_APPLY_ENV = "ENABLE_SHIPPING_RECOVERY_RESTORE"
RTO_SECONDS = 30 * 60
ALMATY_TZ = ZoneInfo("Asia/Almaty")
RETENTION_POLICY = {
    "keep_within": "24h",
    "keep_daily": 14,
    "keep_weekly": 8,
    "keep_monthly": 12,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime:
    value = value or _utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso_utc(value: datetime) -> str:
    return _aware(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_outside_repo(path: Path, project_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    root = project_root.expanduser().resolve()
    if resolved == root or _is_relative_to(resolved, root):
        raise ValueError(
            f"recovery state and restore targets must be outside the repo: {resolved}"
        )
    return resolved


def _atomic_write_json(
    path: Path, payload: dict[str, Any], *, mode: int = 0o600
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class RecoveryLock(AbstractContextManager["RecoveryLock"]):
    """Nonblocking process lock for the recovery scheduler."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "RecoveryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self.handle = self.path.open("a+")
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise RuntimeError(
                    f"shipping recovery backup is already running: {self.path}"
                ) from exc
            raise
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()}\n")
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def _copy_sqlite(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    source_connection = sqlite3.connect(source_uri, uri=True, timeout=30)
    target_connection = sqlite3.connect(target, timeout=30)
    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    with sqlite3.connect(
        f"{target.resolve().as_uri()}?mode=ro", uri=True
    ) as connection:
        result = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    if result != "ok":
        raise RuntimeError(f"snapshot database quick check failed: {result}")
    return result


def _copy_workbook(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    try:
        with ZipFile(target) as archive:
            bad_member = archive.testzip()
    except BadZipFile as exc:
        raise RuntimeError(
            f"snapshot workbook is not a valid XLSX ZIP: {source}"
        ) from exc
    if bad_member:
        raise RuntimeError(
            f"snapshot workbook failed ZIP validation at {bad_member}: {source}"
        )


def _record_artifact(
    artifacts: dict[str, dict[str, Any]], snapshot: Path, path: Path
) -> None:
    relative = path.relative_to(snapshot).as_posix()
    artifacts[relative] = {
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _target_date(now: datetime) -> str:
    return _aware(now).astimezone(ALMATY_TZ).date().isoformat()


def _latest_successful_closeout_run(
    project_root: Path, *, business_date: str
) -> Path | None:
    day_root = (
        project_root
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / business_date
    )
    if not day_root.is_dir():
        return None
    for report_path in sorted(
        day_root.glob("*/closeout_report.json"),
        key=lambda path: path.parent.name,
        reverse=True,
    ):
        try:
            verify_closeout_evidence(
                closeout_report_path=report_path,
                expected_date=date.fromisoformat(business_date),
                project_root=project_root,
            )
            for filename in (
                "run_control_snapshot.json",
                "salesraw_snapshot.json",
            ):
                snapshot = json.loads(
                    (report_path.parent / filename).read_text(encoding="utf-8")
                )
                if (
                    not isinstance(snapshot, dict)
                    or str(snapshot.get("target_date") or "") != business_date
                    or not isinstance(snapshot.get("matrix"), list)
                ):
                    raise ValueError("invalid preserved board snapshot")
        except (
            CloseoutEvidenceError,
            OSError,
            json.JSONDecodeError,
            ValueError,
        ):
            continue
        return report_path.parent
    return None


def _closeout_evidence_receipt(report: dict[str, Any]) -> dict[str, Any]:
    hash_fields = {
        "delivery_report": "delivery_report_sha256",
        "expected_order_gate": "expected_order_gate_sha256",
        "expected_orders": "expected_orders_sha256",
        "ledger": "ledger_sha256",
        "manifest": "manifest_sha256",
        "shipping_report": "shipping_report_sha256",
        "shipped_truth_sync_report": "shipped_truth_sync_report_sha256",
        "zero_order_marker": "zero_order_marker_sha256",
    }
    terminal_hashes = {
        label: str(report[field])
        for label, field in hash_fields.items()
        if str(report.get(field) or "")
    }
    return {
        "schema_version": 1,
        "ok": True,
        "gate": "GREEN",
        "target_date": str(report["target_date"]),
        "run_id": str(report["run_id"]),
        "completion_kind": str(report["completion_kind"]),
        "expected_order_count": int(report.get("expected_order_count") or 0),
        "manifest_count": int(report["manifest_count"]),
        "confirmed_count": int(report["confirmed_count"]),
        "pending_count": int(report["pending_count"]),
        "required_stage_count": int(report.get("required_stage_count") or 0),
        "closeout_report_sha256": str(report["closeout_report_sha256"]),
        "terminal_artifact_sha256": terminal_hashes,
        "credential_values_exposed": False,
        "customer_data_exposed": False,
        "external_writes_performed": 0,
    }


def create_snapshot(
    *,
    project_root: Path = PROJECT_ROOT,
    state_root: Path = DEFAULT_STATE_ROOT,
    now: datetime | None = None,
    hostname: str | None = None,
) -> dict[str, Any]:
    """Create one owner-only, internally verified local recovery snapshot."""

    project_root = project_root.expanduser().resolve()
    state_root = _require_outside_repo(state_root, project_root)
    state_root.mkdir(parents=True, exist_ok=True)
    os.chmod(state_root, 0o700)
    staging_root = state_root / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    os.chmod(staging_root, 0o700)
    current = _aware(now)
    stamp = current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = staging_root / f"shipping_{stamp}_{os.getpid()}"
    snapshot.mkdir(mode=0o700)

    try:
        source_db = project_root / "db" / "app.db"
        if not source_db.is_file():
            raise FileNotFoundError(f"production database is missing: {source_db}")
        copied_db = snapshot / "data" / "app.db.sqlite"
        quick_check = _copy_sqlite(source_db, copied_db)
        artifacts: dict[str, dict[str, Any]] = {}
        _record_artifact(artifacts, snapshot, copied_db)

        workbook = project_root / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
        if workbook.is_file():
            copied_workbook = snapshot / "excel_ui" / workbook.name
            _copy_workbook(workbook, copied_workbook)
            _record_artifact(artifacts, snapshot, copied_workbook)

        optional_state = [
            project_root / "runtime" / "state" / "waybill_shipping_obligations.json",
            project_root / "runtime" / "state" / "google_ops_board_ready_watch.json",
            project_root / "runtime" / "state" / "waybill_prepacked_exclusion.json",
            project_root / "runtime" / "state" / "google_ops_board_closeout_halt_barrier.json",
        ]
        for source in optional_state:
            if not source.is_file():
                continue
            target = snapshot / "runtime" / "state" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            _record_artifact(artifacts, snapshot, target)

        checkpoint = (
            project_root
            / "exports"
            / "google_ops_board"
            / "workflow_runs"
            / _target_date(current)
            / "closeout_checkpoint.json"
        )
        if checkpoint.is_file():
            copied_checkpoint = snapshot / "workflow" / "closeout_checkpoint.json"
            copied_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkpoint, copied_checkpoint)
            _record_artifact(artifacts, snapshot, copied_checkpoint)

        replay_source = _latest_successful_closeout_run(
            project_root,
            business_date=_target_date(current),
        )
        if replay_source is not None:
            for filename in (
                "closeout_report.json",
                "run_control_snapshot.json",
                "salesraw_snapshot.json",
            ):
                replay_target = snapshot / "workflow" / "replay" / filename
                replay_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(replay_source / filename, replay_target)
                _record_artifact(artifacts, snapshot, replay_target)
            evidence = verify_closeout_evidence(
                closeout_report_path=replay_source / "closeout_report.json",
                expected_date=date.fromisoformat(_target_date(current)),
                project_root=project_root,
            )
            evidence_target = (
                snapshot / "workflow" / "replay" / "closeout_evidence.json"
            )
            _atomic_write_json(
                evidence_target,
                _closeout_evidence_receipt(evidence),
            )
            _record_artifact(artifacts, snapshot, evidence_target)

        manifest = {
            "schema_version": 1,
            "created_at_utc": _iso_utc(current),
            "hostname": hostname or socket.gethostname(),
            "business_date": _target_date(current),
            "database_quick_check": quick_check,
            "artifacts": artifacts,
        }
        manifest_path = snapshot / "snapshot_manifest.json"
        _atomic_write_json(manifest_path, manifest)
        return {
            "gate": "GREEN",
            "snapshot_dir": str(snapshot),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "database_sha256": artifacts["data/app.db.sqlite"]["sha256"],
            "database_quick_check": quick_check,
            "artifact_count": len(artifacts),
            "created_at_utc": manifest["created_at_utc"],
            "credential_values_read": False,
        }
    except Exception:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise


def _restic_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("RESTIC_REPOSITORY", DEFAULT_REPOSITORY)
    environment.setdefault("RESTIC_PASSWORD_COMMAND", DEFAULT_PASSWORD_COMMAND)
    return environment


def _summary_snapshot_id(stdout: str) -> str:
    snapshot_id = ""
    for raw_line in str(stdout or "").splitlines():
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if payload.get("message_type") == "summary":
            snapshot_id = str(payload.get("snapshot_id") or payload.get("id") or "")
    return snapshot_id


def run_backup(
    *,
    project_root: Path = PROJECT_ROOT,
    state_root: Path = DEFAULT_STATE_ROOT,
    apply: bool = False,
    runner: Callable[..., Any] = subprocess.run,
    now: datetime | None = None,
    hostname: str | None = None,
    restic_bin: str | None = None,
    tag: str = DEFAULT_TAG,
) -> dict[str, Any]:
    """Create a snapshot and, when gated, send it to the encrypted repository."""

    if apply and os.environ.get(BACKUP_APPLY_ENV) != "1":
        raise PermissionError(f"{BACKUP_APPLY_ENV}=1 is required with --apply")
    project_root = project_root.expanduser().resolve()
    state_root = _require_outside_repo(state_root, project_root)
    state_root.mkdir(parents=True, exist_ok=True)
    os.chmod(state_root, 0o700)
    executable = restic_bin or shutil.which("restic") or "/opt/homebrew/bin/restic"

    with RecoveryLock(state_root / ".backup.lock"):
        snapshot_report = create_snapshot(
            project_root=project_root,
            state_root=state_root,
            now=now,
            hostname=hostname,
        )
        snapshot_dir = Path(snapshot_report["snapshot_dir"])
        try:
            if not apply:
                return {
                    **snapshot_report,
                    "gate": "DRY_RUN",
                    "remote_attempted": False,
                }
            command = [
                executable,
                "backup",
                "--json",
                "--host",
                hostname or socket.gethostname(),
                "--tag",
                tag,
                str(snapshot_dir),
            ]
            completed = runner(
                command,
                capture_output=True,
                text=True,
                env=_restic_environment(),
                timeout=12 * 60,
            )
            snapshot_id = _summary_snapshot_id(completed.stdout)
            if completed.returncode != 0 or not snapshot_id:
                return {
                    "gate": "RED",
                    "remote_attempted": True,
                    "returncode": int(completed.returncode),
                    "error": "encrypted_remote_backup_failed",
                    "credential_values_read": False,
                }
            completed_at = _utc_now() if now is None else _aware(now)
            latest = {
                "schema_version": 1,
                "gate": "GREEN",
                "snapshot_id": snapshot_id,
                "tag": tag,
                "hostname": hostname or socket.gethostname(),
                "completed_at_utc": _iso_utc(completed_at),
                "manifest_sha256": snapshot_report["manifest_sha256"],
                "database_sha256": snapshot_report["database_sha256"],
                "database_quick_check": snapshot_report["database_quick_check"],
                "artifact_count": snapshot_report["artifact_count"],
                "credential_values_read": False,
            }
            _atomic_write_json(state_root / "latest_success.json", latest)
            return {**latest, "remote_attempted": True}
        finally:
            shutil.rmtree(snapshot_dir, ignore_errors=True)


def recovery_status(
    *,
    state_root: Path = DEFAULT_STATE_ROOT,
    now: datetime | None = None,
    max_age_minutes: int = 15,
) -> dict[str, Any]:
    latest_path = state_root.expanduser().resolve() / "latest_success.json"
    if not latest_path.is_file():
        return {
            "gate": "RED",
            "reason": "latest_success_missing",
            "latest_success_path": str(latest_path),
            "credential_values_read": False,
        }
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        completed = datetime.fromisoformat(
            str(latest["completed_at_utc"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        return {
            "gate": "RED",
            "reason": f"latest_success_invalid:{type(exc).__name__}",
            "latest_success_path": str(latest_path),
            "credential_values_read": False,
        }
    age_seconds = max(
        0.0,
        (
            _aware(now).astimezone(timezone.utc) - completed.astimezone(timezone.utc)
        ).total_seconds(),
    )
    gate = "GREEN" if age_seconds <= max_age_minutes * 60 else "RED"
    return {
        "gate": gate,
        "reason": "fresh" if gate == "GREEN" else "latest_success_stale",
        "snapshot_id": str(latest.get("snapshot_id") or ""),
        "completed_at_utc": _iso_utc(completed),
        "age_seconds": round(age_seconds, 3),
        "max_age_minutes": max_age_minutes,
        "latest_success_path": str(latest_path),
        "credential_values_read": False,
    }


def run_retention(
    *,
    state_root: Path = DEFAULT_STATE_ROOT,
    project_root: Path = PROJECT_ROOT,
    apply: bool = False,
    runner: Callable[..., Any] = subprocess.run,
    now: datetime | None = None,
    restic_bin: str | None = None,
    tag: str = DEFAULT_TAG,
) -> dict[str, Any]:
    """Apply the tag-scoped daily/weekly/monthly encrypted retention policy."""

    if apply and os.environ.get(RETENTION_APPLY_ENV) != "1":
        raise PermissionError(f"{RETENTION_APPLY_ENV}=1 is required with --apply")
    state_root = _require_outside_repo(state_root, project_root)
    policy = dict(RETENTION_POLICY)
    if not apply:
        return {
            "gate": "DRY_RUN",
            "remote_attempted": False,
            "tag": tag,
            "policy": policy,
            "credential_values_read": False,
        }

    state_root.mkdir(parents=True, exist_ok=True)
    os.chmod(state_root, 0o700)
    executable = restic_bin or shutil.which("restic") or "/opt/homebrew/bin/restic"
    command = [
        executable,
        "forget",
        "--json",
        "--tag",
        tag,
        "--keep-within",
        str(policy["keep_within"]),
        "--keep-daily",
        str(policy["keep_daily"]),
        "--keep-weekly",
        str(policy["keep_weekly"]),
        "--keep-monthly",
        str(policy["keep_monthly"]),
        "--prune",
    ]
    with RecoveryLock(state_root / ".retention.lock"):
        completed = runner(
            command,
            capture_output=True,
            text=True,
            env=_restic_environment(),
            timeout=30 * 60,
        )
    if completed.returncode != 0:
        return {
            "gate": "RED",
            "remote_attempted": True,
            "returncode": int(completed.returncode),
            "error": "encrypted_retention_failed",
            "credential_values_read": False,
        }

    completed_at = _aware(now)
    receipt = {
        "schema_version": 1,
        "gate": "GREEN",
        "tag": tag,
        "policy": policy,
        "completed_at_utc": _iso_utc(completed_at),
        "credential_values_read": False,
    }
    _atomic_write_json(state_root / "latest_retention.json", receipt)
    return {**receipt, "remote_attempted": True}


def _verify_restored_snapshot(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_root = manifest_path.parent
    for relative, expected in dict(manifest.get("artifacts") or {}).items():
        path = snapshot_root / relative
        if not path.is_file():
            raise RuntimeError(f"restored artifact missing: {relative}")
        if path.stat().st_size != int(expected["size_bytes"]):
            raise RuntimeError(f"restored artifact size mismatch: {relative}")
        if _sha256(path) != str(expected["sha256"]):
            raise RuntimeError(f"restored artifact SHA-256 mismatch: {relative}")
    database = snapshot_root / "data" / "app.db.sqlite"
    with sqlite3.connect(
        f"{database.resolve().as_uri()}?mode=ro", uri=True
    ) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    if quick_check != "ok":
        raise RuntimeError(f"restored database quick check failed: {quick_check}")
    return {
        "database_quick_check": quick_check,
        "artifact_count": len(manifest["artifacts"]),
    }


def restore_drill(
    *,
    state_root: Path = DEFAULT_STATE_ROOT,
    target: Path,
    project_root: Path = PROJECT_ROOT,
    apply: bool = False,
    runner: Callable[..., Any] = subprocess.run,
    restic_bin: str | None = None,
    elapsed_seconds: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Restore the latest encrypted snapshot and verify hashes plus SQLite."""

    if apply and os.environ.get(RESTORE_APPLY_ENV) != "1":
        raise PermissionError(f"{RESTORE_APPLY_ENV}=1 is required with --apply")
    target = _require_outside_repo(target, project_root)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"restore target must be absent or empty: {target}")
    latest_path = state_root.expanduser().resolve() / "latest_success.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    if not apply:
        return {
            "gate": "DRY_RUN",
            "snapshot_id": str(latest.get("snapshot_id") or ""),
            "target": str(target),
            "credential_values_read": False,
        }
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target, 0o700)
    executable = restic_bin or shutil.which("restic") or "/opt/homebrew/bin/restic"
    command = [
        executable,
        "restore",
        str(latest["snapshot_id"]),
        "--target",
        str(target),
    ]
    started = time.monotonic()
    completed = runner(
        command,
        capture_output=True,
        text=True,
        env=_restic_environment(),
        timeout=RTO_SECONDS,
    )
    elapsed = elapsed_seconds() if elapsed_seconds else time.monotonic() - started
    if completed.returncode != 0:
        return {
            "gate": "RED",
            "error": "encrypted_restore_failed",
            "returncode": int(completed.returncode),
            "elapsed_seconds": round(float(elapsed), 3),
            "credential_values_read": False,
        }
    manifests = list(target.rglob("snapshot_manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError(
            f"expected exactly one restored snapshot manifest, found {len(manifests)}"
        )
    manifest_path = manifests[0]
    manifest_sha = _sha256(manifest_path)
    if manifest_sha != str(latest["manifest_sha256"]):
        raise RuntimeError("restored snapshot manifest SHA-256 mismatch")
    verified = _verify_restored_snapshot(manifest_path)
    rto_met = float(elapsed) <= RTO_SECONDS
    return {
        "gate": "GREEN" if rto_met else "RED",
        "snapshot_id": str(latest["snapshot_id"]),
        "target": str(target),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "database_quick_check": verified["database_quick_check"],
        "artifact_count": verified["artifact_count"],
        "elapsed_seconds": round(float(elapsed), 3),
        "rto_seconds": RTO_SECONDS,
        "rto_met": rto_met,
        "credential_values_read": False,
    }


def _emit(payload: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        _atomic_write_json(output.expanduser().resolve(), payload)
    else:
        print(text, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
        subparser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
        subparser.add_argument("--json-out", type=Path)

    snapshot = subparsers.add_parser(
        "snapshot", help="Create one verified local snapshot"
    )
    common(snapshot)
    backup = subparsers.add_parser(
        "backup", help="Create and optionally send one encrypted snapshot"
    )
    common(backup)
    backup.add_argument("--apply", action="store_true")
    status = subparsers.add_parser("status", help="Check encrypted snapshot freshness")
    status.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    status.add_argument("--max-age-minutes", type=int, default=15)
    status.add_argument("--json-out", type=Path)
    retention = subparsers.add_parser(
        "retention", help="Apply encrypted backup retention"
    )
    common(retention)
    retention.add_argument("--apply", action="store_true")
    restore = subparsers.add_parser(
        "restore-drill", help="Restore and verify the latest encrypted snapshot"
    )
    common(restore)
    restore.add_argument("--target", type=Path, required=True)
    restore.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "snapshot":
        payload = create_snapshot(
            project_root=args.project_root, state_root=args.state_root
        )
    elif args.command == "backup":
        payload = run_backup(
            project_root=args.project_root,
            state_root=args.state_root,
            apply=args.apply,
        )
    elif args.command == "status":
        payload = recovery_status(
            state_root=args.state_root,
            max_age_minutes=args.max_age_minutes,
        )
    elif args.command == "retention":
        payload = run_retention(
            state_root=args.state_root,
            project_root=args.project_root,
            apply=args.apply,
        )
    else:
        payload = restore_drill(
            state_root=args.state_root,
            target=args.target,
            project_root=args.project_root,
            apply=args.apply,
        )
    _emit(payload, args.json_out)
    return 0 if payload.get("gate") in {"GREEN", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
