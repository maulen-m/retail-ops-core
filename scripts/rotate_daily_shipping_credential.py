#!/usr/bin/env python3
"""Rotate one allowlisted daily-shipping Telegram credential after closeout.

The tool is deliberately post-closeout only.  Readiness/dry-run mode inspects
metadata and key names without reading credential values.  Apply mode requires
both ``--apply`` and ``ENABLE_DAILY_SHIPPING_CREDENTIAL_ROTATION=1``, a same-day
successful apply closeout, and a fresh token supplied through an owner-only file
outside the repository.  The fresh token is verified with Telegram ``getMe``
before an atomic environment-file rewrite.  Reports never contain credentials.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_RECEIPT_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Autonomous_business"
    / "credential_rotation"
)
ROTATION_APPLY_ENV = "ENABLE_DAILY_SHIPPING_CREDENTIAL_ROTATION"
ALLOWED_KEYS = frozenset({"TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_WAYBILL"})
ALMATY_TZ = ZoneInfo("Asia/Almaty")
TOKEN_PATTERN = re.compile(r"^[1-9][0-9]{4,14}:[A-Za-z0-9_-]{20,}$")
Verifier = Callable[[str], Mapping[str, Any]]


class CredentialRotationError(RuntimeError):
    """A fail-closed credential-rotation contract violation."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _aware(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _iso_utc(value: datetime) -> str:
    return _aware(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_allowlisted_key(key: str) -> None:
    if key not in ALLOWED_KEYS:
        raise CredentialRotationError(f"credential key is not allowlisted: {key}")


def _require_regular_owner_file(path: Path, *, label: str) -> Path:
    expanded = path.expanduser()
    try:
        metadata = expanded.lstat()
    except FileNotFoundError as exc:
        raise CredentialRotationError(f"{label} does not exist: {expanded}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise CredentialRotationError(f"{label} must not be a symlink: {expanded}")
    if not stat.S_ISREG(metadata.st_mode):
        raise CredentialRotationError(f"{label} must be a regular file: {expanded}")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode != 0o600:
        raise CredentialRotationError(
            f"{label} must have exact 0600 permissions, found {mode:04o}: {expanded}"
        )
    return expanded.resolve()


def _require_outside_repo(path: Path, *, project_root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    root = project_root.expanduser().resolve()
    if resolved == root or _is_relative_to(resolved, root):
        raise CredentialRotationError(f"{label} must be outside the repo: {resolved}")
    return resolved


def _dotenv_key_counts(path: Path) -> dict[str, int]:
    """Return key counts while deliberately discarding all dotenv values."""

    counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.lstrip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                counts[key] = counts.get(key, 0) + 1
    return counts


def inspect_rotation_readiness(
    *,
    env_path: Path = DEFAULT_ENV_PATH,
    key: str,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Inspect only file metadata and dotenv key names; never return values."""

    _require_allowlisted_key(key)
    env_file = _require_regular_owner_file(Path(env_path), label="environment file")
    counts = _dotenv_key_counts(env_file)
    if counts.get(key, 0) > 1:
        raise CredentialRotationError(f"environment file has duplicate target key: {key}")
    return {
        "schema_version": 1,
        "ok": True,
        "gate": "READY_AFTER_CLOSEOUT",
        "project_root": str(Path(project_root).expanduser().resolve()),
        "env_path": str(env_file),
        "key": key,
        "key_present": counts.get(key, 0) == 1,
        "credential_values_read": False,
        "credential_values_exposed": False,
        "external_writes_performed": 0,
    }


def _load_successful_closeout(path: Path, *, target_date: str) -> dict[str, Any]:
    report_path = Path(path).expanduser()
    try:
        metadata = report_path.lstat()
    except FileNotFoundError as exc:
        raise CredentialRotationError(
            f"same-day closeout report does not exist: {report_path}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CredentialRotationError("same-day closeout report must be a regular file")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialRotationError("same-day closeout report is invalid JSON") from exc
    if (
        not isinstance(report, dict)
        or report.get("ok") is not True
        or str(report.get("mode") or "") != "apply"
    ):
        raise CredentialRotationError(
            "credential rotation requires a successful apply closeout"
        )
    if str(report.get("target_date") or "") != target_date:
        raise CredentialRotationError(
            f"closeout target date must equal current Almaty date {target_date}"
        )
    if not str(report.get("run_id") or "").strip():
        raise CredentialRotationError("closeout report is missing run_id")
    return report


def _read_fresh_token(path: Path, *, project_root: Path) -> str:
    token_path = _require_regular_owner_file(Path(path), label="fresh token file")
    _require_outside_repo(token_path, project_root=project_root, label="fresh token file")
    raw = token_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if len(lines) != 1 or raw.strip() != lines[0] or not TOKEN_PATTERN.fullmatch(lines[0]):
        raise CredentialRotationError("fresh Telegram token format is invalid")
    return lines[0]


def _verify_telegram_get_me(token: str) -> Mapping[str, Any]:
    """Perform one read-only identity check without surfacing URL or response body."""

    try:
        import requests

        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=(5, 20),
        )
    except Exception:  # requests exceptions vary by installed version
        raise CredentialRotationError(
            "fresh Telegram token verification failed: transport error"
        ) from None
    if response.status_code != 200:
        return {"ok": False, "error": "telegram_get_me_rejected"}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": "telegram_get_me_invalid_json"}
    result = payload.get("result") if isinstance(payload, dict) else None
    return {
        "ok": bool(
            isinstance(payload, dict)
            and payload.get("ok") is True
            and isinstance(result, dict)
            and result.get("id") is not None
        )
    }


def _replace_dotenv_value(payload: str, *, key: str, token: str) -> str:
    lines = payload.splitlines(keepends=True)
    matches: list[int] = []
    pattern = re.compile(rf"^(\s*(?:export\s+)?{re.escape(key)}\s*=).*$")
    for index, raw_line in enumerate(lines):
        if pattern.match(raw_line.rstrip("\r\n")):
            matches.append(index)
    if len(matches) > 1:
        raise CredentialRotationError(f"environment file has duplicate target key: {key}")
    if matches:
        index = matches[0]
        raw_line = lines[index]
        newline = "\r\n" if raw_line.endswith("\r\n") else "\n" if raw_line.endswith("\n") else ""
        prefix = pattern.match(raw_line.rstrip("\r\n"))
        assert prefix is not None
        lines[index] = f"{prefix.group(1)}{token}{newline}"
    else:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(f"{key}={token}\n")
    return "".join(lines)


def _atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            mode,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    _atomic_write_bytes(path, serialized, mode=0o600)


class _RotationLock(AbstractContextManager["_RotationLock"]):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "_RotationLock":
        self.handle = self.path.open("a+")
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise CredentialRotationError(
                    "another daily-shipping credential rotation is active"
                ) from exc
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def rotate_credential(
    *,
    env_path: Path = DEFAULT_ENV_PATH,
    key: str,
    token_file: Path,
    closeout_report_path: Path,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    project_root: Path = PROJECT_ROOT,
    apply: bool = False,
    environment: MutableMapping[str, str] | Mapping[str, str] | None = None,
    now: datetime | None = None,
    verifier: Verifier = _verify_telegram_get_me,
) -> dict[str, Any]:
    """Inspect or rotate one token; apply can occur only after today's closeout."""

    readiness = inspect_rotation_readiness(
        env_path=Path(env_path), key=key, project_root=Path(project_root)
    )
    if not apply:
        return {
            **readiness,
            "gate": "DRY_RUN",
            "would_require_same_day_successful_closeout": True,
            "would_verify_with_telegram_get_me": True,
        }

    active_environment = os.environ if environment is None else environment
    if active_environment.get(ROTATION_APPLY_ENV) != "1":
        raise CredentialRotationError(
            f"{ROTATION_APPLY_ENV}=1 is required together with --apply"
        )

    current = _aware(now)
    target_date = current.astimezone(ALMATY_TZ).date().isoformat()
    closeout_input = Path(closeout_report_path).expanduser()
    closeout = _load_successful_closeout(closeout_input, target_date=target_date)
    closeout_path = closeout_input.resolve()
    root = Path(project_root).expanduser().resolve()
    env_file = Path(readiness["env_path"])
    env_before = env_file.read_bytes()
    env_before_sha = _sha256_bytes(env_before)
    token = _read_fresh_token(Path(token_file), project_root=root)
    verification = verifier(token)
    if not isinstance(verification, Mapping) or verification.get("ok") is not True:
        raise CredentialRotationError(
            "fresh Telegram token verification failed: Telegram identity rejected"
        )

    receipts = _require_outside_repo(
        Path(receipt_root), project_root=root, label="credential receipt root"
    )
    receipts.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(receipts, 0o700)
    with _RotationLock(receipts / ".rotation.lock"):
        if _sha256(env_file) != env_before_sha:
            raise CredentialRotationError(
                "environment file changed during credential verification; retry"
            )
        updated_text = _replace_dotenv_value(
            env_before.decode("utf-8"), key=key, token=token
        )
        env_after = updated_text.encode("utf-8")
        stamp = current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = receipts / f"{stamp}_{os.getpid()}_{key.lower()}"
        run_dir.mkdir(mode=0o700)
        os.chmod(run_dir, 0o700)
        backup_path = run_dir / "before.env"
        receipt_path = run_dir / "rotation_receipt.json"
        _atomic_write_bytes(backup_path, env_before, mode=0o600)
        report: dict[str, Any] = {
            "schema_version": 1,
            "ok": True,
            "gate": "GREEN",
            "mode": "apply",
            "rotated_at_utc": _iso_utc(current),
            "target_date": target_date,
            "key": key,
            "env_path": str(env_file),
            "env_before_sha256": env_before_sha,
            "env_after_sha256": _sha256_bytes(env_after),
            "backup_path": str(backup_path),
            "backup_sha256": _sha256(backup_path),
            "receipt_path": str(receipt_path),
            "closeout_report_path": str(closeout_path),
            "closeout_report_sha256": _sha256(closeout_path),
            "closeout_run_id": str(closeout["run_id"]),
            "telegram_identity_verified": True,
            "credential_values_read": True,
            "credential_values_exposed": False,
            "external_writes_performed": 0,
        }
        env_replaced = False
        try:
            _atomic_write_bytes(env_file, env_after, mode=0o600)
            env_replaced = True
            _atomic_write_json(receipt_path, report)
        except Exception:
            if env_replaced:
                _atomic_write_bytes(env_file, env_before, mode=0o600)
            receipt_path.unlink(missing_ok=True)
            raise
        return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or rotate one daily-shipping Telegram credential."
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--key", choices=sorted(ALLOWED_KEYS), required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--closeout-report", type=Path)
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.apply and (args.token_file is None or args.closeout_report is None):
        raise SystemExit("--apply requires --token-file and --closeout-report")
    try:
        report = rotate_credential(
            env_path=args.env_file,
            key=args.key,
            token_file=args.token_file or Path("unused-in-dry-run"),
            closeout_report_path=args.closeout_report or Path("unused-in-dry-run"),
            receipt_root=args.receipt_root,
            apply=args.apply,
        )
    except CredentialRotationError as exc:
        if args.json:
            print(json.dumps({"ok": False, "gate": "RED", "error": str(exc)}))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Gate: {report['gate']} | key={report['key']} | "
            f"credential_values_exposed={str(report['credential_values_exposed']).lower()}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
