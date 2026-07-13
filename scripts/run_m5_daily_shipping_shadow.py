#!/usr/bin/env python3
"""Run the receiver-side M5 daily-shipping shadow gate.

This tool can validate and dry-run a restored minimal shipping snapshot. It
cannot load schedulers or invoke an apply-capable closeout. Subprocess output is
never copied into the summary, and inherited write gates and secret-like
environment variables are removed before execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zipfile import BadZipFile, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "daily_shipping_runtime.json"
DEFAULT_RUNTIME_ROOT = Path("~/Docs/Autonomous_business")
DEFAULT_RELEASE_TAG = "release/daily-shipping-20260713-v2.2"
SECRET_ENV_FRAGMENTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "COOKIE",
    "AUTHORIZATION",
    "PRIVATE_KEY",
)
ALLOWED_ENV_KEYS = {
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "PATH",
    "TMPDIR",
    "USER",
}
FORBIDDEN_COMMAND_ARGS = {
    "--apply",
    "--live",
    "--send",
    "--send-alert",
    "bootstrap",
    "bootout",
    "kickstart",
}
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PRESERVED_REPLAY_ARTIFACTS = {
    "workflow/replay/closeout_report.json",
    "workflow/replay/run_control_snapshot.json",
    "workflow/replay/salesraw_snapshot.json",
}


class ShadowGateError(RuntimeError):
    """The receiver shadow preconditions are not proven."""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowGateError(f"{label} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ShadowGateError(f"{label} must be a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_relative(value: str) -> Path:
    relative = Path(str(value))
    if (
        not value
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ShadowGateError(f"unsafe snapshot artifact path: {value}")
    return relative


def _receiver_artifact_path(
    relative: Path, *, project_root: Path, business_date: str
) -> Path | None:
    value = relative.as_posix()
    if value == "data/app.db.sqlite":
        return project_root / "db" / "app.db"
    if value.startswith("excel_ui/") or value.startswith("runtime/state/"):
        return project_root / relative
    if value == "workflow/closeout_checkpoint.json":
        return (
            project_root
            / "exports"
            / "google_ops_board"
            / "workflow_runs"
            / business_date
            / "closeout_checkpoint.json"
        )
    if value in PRESERVED_REPLAY_ARTIFACTS:
        return None
    raise ShadowGateError(f"unsupported snapshot artifact: {value}")


def verify_snapshot_transfer(
    snapshot_manifest_path: Path, *, project_root: Path
) -> dict[str, Any]:
    """Verify the source snapshot and its receiver-side copies."""

    project_root = project_root.expanduser().resolve()
    manifest_path = snapshot_manifest_path.expanduser().resolve()
    if manifest_path == project_root or _is_relative_to(manifest_path, project_root):
        raise ShadowGateError("snapshot manifest must remain outside the receiver repo")
    payload = _load_json(manifest_path, label="snapshot manifest")
    if int(payload.get("schema_version") or 0) != 1:
        raise ShadowGateError("unsupported snapshot manifest schema")
    business_date = str(payload.get("business_date") or "")
    try:
        _ = __import__("datetime").date.fromisoformat(business_date)
    except ValueError as exc:
        raise ShadowGateError("snapshot business_date is invalid") from exc
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ShadowGateError("snapshot artifacts are missing")
    required = {
        "data/app.db.sqlite",
        "excel_ui/SALES_KSP_CRM_V3.xlsx",
        *PRESERVED_REPLAY_ARTIFACTS,
    }
    missing = sorted(required.difference(artifacts))
    if missing:
        raise ShadowGateError(
            "required snapshot artifact missing: " + ", ".join(missing)
        )

    snapshot_root = manifest_path.parent.resolve()
    for raw_relative, raw_expected in sorted(artifacts.items()):
        relative = _safe_relative(str(raw_relative))
        expected = raw_expected if isinstance(raw_expected, dict) else {}
        expected_size = int(expected.get("size_bytes") or -1)
        expected_sha = str(expected.get("sha256") or "")
        if expected_size < 0 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ShadowGateError(f"invalid snapshot artifact metadata: {relative}")
        source = (snapshot_root / relative).resolve()
        if not _is_relative_to(source, snapshot_root) or not source.is_file():
            raise ShadowGateError(f"snapshot artifact missing: {relative}")
        if source.stat().st_size != expected_size:
            raise ShadowGateError(f"snapshot artifact size mismatch: {relative}")
        if _sha256(source) != expected_sha:
            raise ShadowGateError(f"snapshot artifact SHA-256 mismatch: {relative}")
        receiver = _receiver_artifact_path(
            relative, project_root=project_root, business_date=business_date
        )
        if receiver is None:
            continue
        if not receiver.is_file():
            raise ShadowGateError(f"receiver artifact missing: {relative}")
        if receiver.stat().st_size != expected_size:
            raise ShadowGateError(f"receiver size mismatch: {relative}")
        if _sha256(receiver) != expected_sha:
            raise ShadowGateError(f"receiver SHA-256 mismatch: {relative}")

    database = project_root / "db" / "app.db"
    try:
        with sqlite3.connect(
            f"{database.resolve().as_uri()}?mode=ro", uri=True, timeout=30
        ) as connection:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    except sqlite3.Error as exc:
        raise ShadowGateError("receiver database quick check could not run") from exc
    if quick_check != "ok":
        raise ShadowGateError(f"receiver database quick check failed: {quick_check}")

    workbook = project_root / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    try:
        with ZipFile(workbook) as archive:
            bad_member = archive.testzip()
    except BadZipFile as exc:
        raise ShadowGateError("receiver workbook is not a valid XLSX ZIP") from exc
    if bad_member:
        raise ShadowGateError("receiver workbook ZIP integrity failed")
    return {
        "artifact_count": len(artifacts),
        "business_date": business_date,
        "source_hostname": str(payload.get("hostname") or ""),
        "database_quick_check": quick_check,
        "workbook_zip_ok": True,
        "snapshot_manifest_sha256": _sha256(manifest_path),
    }


def sanitize_shadow_environment(
    source: Mapping[str, str], *, python_bin: str
) -> dict[str, str]:
    """Build a minimal environment with no inherited write gates or secrets."""

    result: dict[str, str] = {}
    for key in ALLOWED_ENV_KEYS:
        value = source.get(key)
        upper = key.upper()
        if value and not upper.startswith("ENABLE_") and not any(
            fragment in upper for fragment in SECRET_ENV_FRAGMENTS
        ):
            result[key] = str(value)
    result.setdefault("HOME", str(Path.home()))
    result.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    result["PYTHON_BIN"] = str(python_bin)
    result["PYTHONUNBUFFERED"] = "1"
    return result


def _expand_path(value: str, *, project_root: Path, runtime_home: Path) -> Path:
    expanded = str(value).replace("${PROJECT_ROOT}", str(project_root)).replace(
        "${HOME}", str(runtime_home)
    )
    return Path(expanded).expanduser().resolve()


def _credential_receipts(
    manifest: dict[str, Any], *, project_root: Path
) -> list[dict[str, Any]]:
    runtime_home = Path(str(manifest.get("runtime_home") or Path.home())).resolve()
    receipts: list[dict[str, Any]] = []
    for index, item in enumerate(manifest.get("credential_files") or [], start=1):
        path = _expand_path(
            str(item.get("path") or ""),
            project_root=project_root,
            runtime_home=runtime_home,
        )
        required = bool(item.get("required", True))
        if not path.is_file():
            if required:
                raise ShadowGateError(f"required credential file missing: credential_{index}")
            receipts.append(
                {"role": f"credential_{index}", "present": False, "required": False}
            )
            continue
        actual_mode = stat.S_IMODE(path.stat().st_mode)
        maximum_mode = int(str(item.get("max_mode") or "0600"), 8)
        if actual_mode & ~maximum_mode:
            raise ShadowGateError(f"credential mode exceeds limit: credential_{index}")
        receipts.append(
            {
                "role": f"credential_{index}",
                "basename": path.name,
                "present": True,
                "mode": f"{actual_mode:04o}",
            }
        )
    if not receipts:
        raise ShadowGateError("manifest declares no credential files")
    return receipts


def _run(
    runner: Callable[..., Any],
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: int,
) -> Any:
    try:
        return runner(
            list(command),
            cwd=str(cwd),
            env=dict(environment),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return type("TimedOut", (), {"returncode": 124, "stdout": "", "stderr": ""})()


def _git_release_receipt(
    *,
    project_root: Path,
    expected_commit: str,
    expected_tag: str,
    runner: Callable[..., Any],
    environment: Mapping[str, str],
) -> dict[str, str]:
    if not COMMIT_RE.fullmatch(expected_commit):
        raise ShadowGateError("expected commit must be a full lowercase SHA-1")
    status = _run(
        runner,
        ["git", "status", "--porcelain"],
        cwd=project_root,
        environment=environment,
        timeout=30,
    )
    if status.returncode != 0:
        raise ShadowGateError("git status failed")
    if str(status.stdout or "").strip():
        raise ShadowGateError("receiver checkout is dirty")
    head = _run(
        runner,
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        environment=environment,
        timeout=30,
    )
    observed_commit = str(head.stdout or "").strip()
    if head.returncode != 0 or observed_commit != expected_commit:
        raise ShadowGateError("receiver checkout commit mismatch")
    tag = _run(
        runner,
        ["git", "rev-parse", f"{expected_tag}^{{}}"],
        cwd=project_root,
        environment=environment,
        timeout=30,
    )
    tag_commit = str(tag.stdout or "").strip()
    if tag.returncode != 0 or not COMMIT_RE.fullmatch(tag_commit):
        raise ShadowGateError("release tag cannot be resolved")
    ancestor = _run(
        runner,
        ["git", "merge-base", "--is-ancestor", tag_commit, observed_commit],
        cwd=project_root,
        environment=environment,
        timeout=30,
    )
    if ancestor.returncode != 0:
        raise ShadowGateError("release tag is not an ancestor of receiver checkout")
    return {
        "expected_commit": expected_commit,
        "observed_commit": observed_commit,
        "release_tag": expected_tag,
        "release_tag_commit": tag_commit,
    }


def _loaded_shipping_labels(
    labels: set[str], *, launchctl_output: str | None
) -> list[str]:
    if launchctl_output is None:
        raise ShadowGateError("launchctl evidence is missing")
    observed: set[str] = set()
    for line in str(launchctl_output).splitlines():
        fields = line.split()
        if fields:
            observed.add(fields[-1])
    return sorted(labels.intersection(observed))


def _service_account_path(
    manifest: dict[str, Any], *, project_root: Path
) -> Path:
    runtime_home = Path(str(manifest.get("runtime_home") or Path.home())).resolve()
    candidates = []
    for item in manifest.get("credential_files") or []:
        path = _expand_path(
            str(item.get("path") or ""),
            project_root=project_root,
            runtime_home=runtime_home,
        )
        if path.suffix.lower() == ".json":
            candidates.append(path)
    if len(candidates) != 1:
        raise ShadowGateError("expected exactly one service-account credential file")
    return candidates[0]


def _spreadsheet_id(manifest: dict[str, Any]) -> str:
    values = {
        str((item.get("environment_variables") or {}).get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID"))
        for item in manifest.get("schedulers") or []
        if (item.get("environment_variables") or {}).get(
            "AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID"
        )
    }
    if len(values) != 1:
        raise ShadowGateError("canonical spreadsheet identity is missing or divergent")
    return values.pop()


def build_shadow_commands(
    *,
    project_root: Path,
    manifest_path: Path,
    snapshot_manifest_path: Path,
    output_root: Path,
    python_bin: Path,
) -> list[dict[str, Any]]:
    manifest = _load_json(manifest_path, label="runtime manifest")
    snapshot = _load_json(snapshot_manifest_path, label="snapshot manifest")
    business_date = str(snapshot.get("business_date") or "")
    service_account = _service_account_path(manifest, project_root=project_root)
    spreadsheet_id = _spreadsheet_id(manifest)
    commands: list[dict[str, Any]] = [
        {
            "name": "release_gate",
            "argv": [
                "/bin/bash",
                str(project_root / "scripts" / "run_daily_shipping_release_gate.sh"),
            ],
            "timeout": 1800,
        },
        {
            "name": "runtime_credentials",
            "argv": [
                str(python_bin),
                str(project_root / "scripts" / "validate_daily_shipping_runtime.py"),
                "--manifest",
                str(manifest_path),
                "--project-root",
                str(project_root),
                "--check-credentials",
                "--json",
            ],
            "timeout": 180,
        },
        {
            "name": "shipment_preflight",
            "argv": [
                str(python_bin),
                str(project_root / "scripts" / "preflight_shipment.py"),
                "--project-root",
                str(project_root),
                "--json",
                "--output",
                str(output_root / "shipment_preflight.json"),
            ],
            "timeout": 600,
            "report_path": str(output_root / "shipment_preflight.json"),
        },
        {
            "name": "preserved_day_replay",
            "argv": [
                str(python_bin),
                str(project_root / "scripts" / "run_google_ops_board_closeout.py"),
                "--db-path",
                str(project_root / "db" / "app.db"),
                "--service-account-json",
                str(service_account),
                "--spreadsheet-id",
                spreadsheet_id,
                "--target-date",
                business_date,
                "--shadow-board-run-dir",
                str(snapshot_manifest_path.parent / "workflow" / "replay"),
                "--run-root",
                str(output_root / "replay"),
                "--json-out",
                str(output_root / "replay_closeout.json"),
            ],
            "timeout": 1800,
            "report_path": str(output_root / "replay_closeout.json"),
        },
    ]
    for stage in commands:
        forbidden = FORBIDDEN_COMMAND_ARGS.intersection(stage["argv"])
        if forbidden or any(Path(value).name == "launchctl" for value in stage["argv"]):
            raise ShadowGateError(
                f"shadow command contains forbidden mutation surface: {stage['name']}"
            )
    return commands


def _validate_stage_evidence(stage: dict[str, Any], completed: Any) -> bool:
    name = str(stage["name"])
    if name == "runtime_credentials":
        try:
            payload = json.loads(str(completed.stdout or ""))
        except json.JSONDecodeError:
            return False
        return bool(payload.get("ok")) and payload.get("credential_values_read") is False
    report_path = stage.get("report_path")
    if not report_path:
        return True
    payload = _load_json(Path(str(report_path)), label=f"{name} report")
    if name == "preserved_day_replay":
        return (
            bool(payload.get("ok"))
            and str(payload.get("mode")) == "dry_run"
            and str(payload.get("board_source_mode")) == "preserved_snapshot"
        )
    return bool(payload.get("ok"))


def _prepare_output_root(output_root: Path, *, project_root: Path) -> Path:
    resolved = output_root.expanduser().resolve()
    if resolved == project_root or _is_relative_to(resolved, project_root):
        raise ShadowGateError("output root must be outside the receiver repo")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise ShadowGateError("output root must be absent or empty")
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    return resolved


def run_shadow(
    *,
    project_root: Path,
    manifest_path: Path,
    snapshot_manifest_path: Path,
    output_root: Path,
    expected_commit: str,
    receiver_hostname: str | None = None,
    expected_tag: str = DEFAULT_RELEASE_TAG,
    required_runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    python_bin: Path | None = None,
    launchctl_output: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Validate and execute one no-send receiver shadow run."""

    project_root = project_root.expanduser().resolve()
    required_runtime_root = required_runtime_root.expanduser().resolve()
    if project_root != required_runtime_root:
        raise ShadowGateError(
            f"receiver runtime path mismatch: expected {required_runtime_root}"
        )
    manifest_path = manifest_path.expanduser().resolve()
    manifest = _load_json(manifest_path, label="runtime manifest")
    declared_root = Path(str(manifest.get("project_root") or "")).expanduser().resolve()
    if declared_root != project_root:
        raise ShadowGateError("runtime manifest project_root does not match receiver")
    output_root = _prepare_output_root(output_root, project_root=project_root)
    executable = (python_bin or project_root / ".venv" / "bin" / "python").resolve()
    if not executable.is_file():
        raise ShadowGateError("receiver virtual-environment Python is missing")
    environment = sanitize_shadow_environment(os.environ, python_bin=str(executable))
    environment["HOME"] = str(Path(str(manifest.get("runtime_home") or Path.home())))

    snapshot = verify_snapshot_transfer(
        snapshot_manifest_path, project_root=project_root
    )
    receiver = receiver_hostname or socket.gethostname()

    def normalize_host(value: Any) -> str:
        return str(value or "").lower().removesuffix(".local")

    if normalize_host(receiver) == normalize_host(snapshot["source_hostname"]):
        raise ShadowGateError("receiver is the snapshot source host, not the M5 shadow host")
    git_receipt = _git_release_receipt(
        project_root=project_root,
        expected_commit=expected_commit,
        expected_tag=expected_tag,
        runner=runner,
        environment=environment,
    )
    labels = {
        str(item.get("label") or "")
        for item in manifest.get("schedulers") or []
        if item.get("label")
    }
    if launchctl_output is None:
        launchctl = _run(
            runner,
            ["launchctl", "list"],
            cwd=project_root,
            environment=environment,
            timeout=30,
        )
        if launchctl.returncode != 0:
            raise ShadowGateError("launchctl list failed on receiver")
        launchctl_output = str(launchctl.stdout or "")
    loaded = _loaded_shipping_labels(labels, launchctl_output=launchctl_output)
    if loaded:
        raise ShadowGateError(
            "shipping labels already loaded on receiver: " + ", ".join(loaded)
        )
    credentials = _credential_receipts(manifest, project_root=project_root)
    commands = build_shadow_commands(
        project_root=project_root,
        manifest_path=manifest_path,
        snapshot_manifest_path=snapshot_manifest_path,
        output_root=output_root,
        python_bin=executable,
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "gate": "RED",
        "receiver_hostname": receiver,
        "source_hostname": snapshot["source_hostname"],
        "business_date": snapshot["business_date"],
        "snapshot_manifest_sha256": snapshot["snapshot_manifest_sha256"],
        "snapshot_artifact_count": snapshot["artifact_count"],
        "database_quick_check": snapshot["database_quick_check"],
        **git_receipt,
        "shipping_scheduler_count": len(labels),
        "loaded_shipping_labels": [],
        "credentials": credentials,
        "stages": [],
        "external_writes_performed": 0,
        "credential_values_read": False,
        "credential_values_read_by_wrapper": False,
        "credential_values_exposed": False,
        "cutover_authorized": False,
        "errors": [],
    }
    report_path = output_root / "shadow_report.json"
    for stage in commands:
        if stage["name"] == "preserved_day_replay":
            report["credential_values_read"] = True
            report["runtime_credential_use"] = "read_only_kaspi_api_probe"
        started = time.monotonic()
        completed = _run(
            runner,
            stage["argv"],
            cwd=project_root,
            environment=environment,
            timeout=int(stage["timeout"]),
        )
        elapsed_ms = int(round((time.monotonic() - started) * 1000))
        stage_receipt = {
            "name": stage["name"],
            "returncode": int(completed.returncode),
            "elapsed_ms": elapsed_ms,
            "ok": False,
        }
        report["stages"].append(stage_receipt)
        if completed.returncode != 0:
            report["errors"].append(
                f"{stage['name']} failed with returncode {int(completed.returncode)}"
            )
            _atomic_write_json(report_path, report)
            return report
        try:
            evidence_ok = _validate_stage_evidence(stage, completed)
        except ShadowGateError:
            evidence_ok = False
        if not evidence_ok:
            report["errors"].append(f"{stage['name']} evidence is missing or invalid")
            _atomic_write_json(report_path, report)
            return report
        stage_receipt["ok"] = True
    report["gate"] = "GREEN"
    _atomic_write_json(report_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG)
    parser.add_argument("--receiver-hostname")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_shadow(
            project_root=args.project_root,
            manifest_path=args.manifest,
            snapshot_manifest_path=args.snapshot_manifest,
            output_root=args.output_root,
            expected_commit=str(args.expected_commit),
            expected_tag=str(args.release_tag),
            receiver_hostname=args.receiver_hostname,
        )
    except ShadowGateError as exc:
        report = {
            "schema_version": 1,
            "gate": "RED",
            "errors": [str(exc)],
            "external_writes_performed": 0,
            "credential_values_read": False,
            "credential_values_read_by_wrapper": False,
            "credential_values_exposed": False,
            "cutover_authorized": False,
        }
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        print(text)
    else:
        print(text, file=sys.stderr)
    return 0 if report.get("gate") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
