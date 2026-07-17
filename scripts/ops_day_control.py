#!/usr/bin/env python3
"""Thin, audited operator controls for one Google Ops Board day.

All commands are dry-run by default.  Mutating actions require both ``--apply``
and ``ENABLE_OPS_DAY_CONTROL=1``.  This module never calls Kaspi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.google_board_day_state import (  # noqa: E402
    checkpoint_path_for_date,
    effective_store_states,
    load_store_day_states,
    set_store_day_state,
)
from core.ops.waybill_shipping_obligations import (  # noqa: E402
    KNOWN_STORE_CODES,
    active_obligation_ids_by_store,
    load_shipping_obligation_ledger,
    normalize_store_code,
)
from core.paths import data_path  # noqa: E402
from scripts.google_ops_board_automation_common import (  # noqa: E402
    DEFAULT_CLOSEOUT_HALT_BARRIER_PATH,
    load_closeout_halt_barrier,
)
from scripts.send_waybills_telegram import (  # noqa: E402
    TELEGRAM_SEND_LEDGER_FILE,
    _set_entry_state,
    save_telegram_ledger,
)
from scripts.send_waybills_whatsapp import TODAY_FOLDER  # noqa: E402
from scripts.send_waybills_whatsapp import ALMATY_TZ  # noqa: E402


APPLY_ENV_GATE = "ENABLE_OPS_DAY_CONTROL"
DEFAULT_RUN_ROOT = data_path("exports", "google_ops_board", "workflow_runs")
DEFAULT_OBLIGATION_LEDGER_PATH = data_path(
    "runtime", "state", "waybill_shipping_obligations.json"
)
DEFAULT_AUDIT_ROOT = PROJECT_ROOT / "runs" / "ops_day_control"


def _parse_date(value: str) -> date:
    if value == "today":
        return datetime.now(ALMATY_TZ).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO date {value!r}; expected YYYY-MM-DD"
        ) from exc


def _parse_store(value: str) -> str:
    store = normalize_store_code(value)
    if store not in KNOWN_STORE_CODES:
        raise argparse.ArgumentTypeError(f"Unknown store code {value!r}")
    return store


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _append_audit_line(
    *,
    audit_root: Path,
    target_date: date,
    payload: dict[str, Any],
) -> Path:
    path = Path(audit_root) / f"{target_date.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _require_apply_gate(args: argparse.Namespace) -> None:
    if not args.apply:
        return
    if str(os.environ.get(APPLY_ENV_GATE) or "").strip() != "1":
        raise PermissionError(
            f"--apply requires {APPLY_ENV_GATE}=1"
        )


def _checkpoint_path(args: argparse.Namespace) -> Path:
    return checkpoint_path_for_date(
        args.target_date,
        workflow_run_root=Path(args.run_root),
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _obligation_summary(path: Path) -> dict[str, Any]:
    ledger = load_shipping_obligation_ledger(path)
    open_by_store = active_obligation_ids_by_store(ledger)
    by_store_status: dict[str, Counter[str]] = {}
    for raw_entry in dict(ledger.get("entries") or {}).values():
        entry = dict(raw_entry or {})
        store = normalize_store_code(entry.get("store_code"))
        status = str(entry.get("status") or "unknown")
        if store:
            by_store_status.setdefault(store, Counter())[status] += 1
    return {
        "path": str(path),
        "open_count": sum(len(order_ids) for order_ids in open_by_store.values()),
        "open_counts_by_store": {
            store: len(order_ids)
            for store, order_ids in sorted(open_by_store.items())
        },
        "counts_by_store_and_status": {
            store: dict(sorted(counts.items()))
            for store, counts in sorted(by_store_status.items())
        },
    }


def _status(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_path = _checkpoint_path(args)
    checkpoint = _read_json_object(checkpoint_path)
    stages = {
        name: {
            "status": str(dict(raw or {}).get("status") or ""),
            "updated_at": str(dict(raw or {}).get("updated_at") or ""),
            "run_id": str(dict(raw or {}).get("run_id") or ""),
        }
        for name, raw in dict(checkpoint.get("stages") or {}).items()
    }
    raw_day_states = load_store_day_states(
        args.target_date,
        checkpoint_path=checkpoint_path,
    )
    return {
        "ok": True,
        "command": "status",
        "target_date": args.target_date.isoformat(),
        "checkpoint": {
            "path": str(checkpoint_path),
            "exists": checkpoint_path.exists(),
            "last_stages": stages,
        },
        "store_day_states": {
            "section_present": bool(raw_day_states),
            "effective": effective_store_states(
                args.target_date,
                checkpoint_path=checkpoint_path,
            ),
        },
        "shipping_obligations": _obligation_summary(
            Path(args.obligation_ledger_path)
        ),
        "halt_barrier": load_closeout_halt_barrier(
            Path(args.halt_barrier_path)
        ),
        "dry_run": not args.apply,
    }


def _set_one_state(
    args: argparse.Namespace,
    *,
    state: str,
    postponed_to: str | date = "",
) -> dict[str, Any]:
    postponed_value = (
        postponed_to.isoformat()
        if isinstance(postponed_to, date)
        else str(postponed_to or "")
    )
    planned = {
        "store": args.store,
        "state": state,
        "reason": args.reason,
        "set_by": args.set_by,
        "postponed_to": postponed_value,
    }
    if args.apply:
        _require_apply_gate(args)
        planned["record"] = set_store_day_state(
            args.target_date,
            args.store,
            state,
            reason=args.reason,
            set_by=args.set_by,
            postponed_to=postponed_value,
            checkpoint_path=_checkpoint_path(args),
        )
    return {
        "ok": True,
        "command": args.command,
        "target_date": args.target_date.isoformat(),
        "applied": bool(args.apply),
        "planned": planned,
    }


def _terminate_day(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_path = _checkpoint_path(args)
    effective = effective_store_states(
        args.target_date,
        checkpoint_path=checkpoint_path,
    )
    stores = [
        store
        for store, record in sorted(effective.items())
        if str(record.get("state") or "") == "PENDING"
    ]
    postponed_to = (
        args.postponed_to.isoformat()
        if isinstance(args.postponed_to, date)
        else (args.target_date + timedelta(days=1)).isoformat()
    )
    if args.apply:
        _require_apply_gate(args)
        for store in stores:
            set_store_day_state(
                args.target_date,
                store,
                "POSTPONED",
                reason=args.reason,
                set_by=args.set_by,
                postponed_to=postponed_to,
                checkpoint_path=checkpoint_path,
            )
    return {
        "ok": True,
        "command": "terminate-day",
        "target_date": args.target_date.isoformat(),
        "applied": bool(args.apply),
        "stores_postponed": stores,
        "postponed_to": postponed_to,
        "reason": args.reason,
        "set_by": args.set_by,
    }


def _resolve_newest_send_manifest(
    *,
    today_folder: Path,
    target_date: date,
) -> Path:
    send_root = Path(today_folder).expanduser() / "MERGED" / "SEND"
    candidates: list[Path] = []
    for path in send_root.glob("*/send_batch_manifest.json"):
        try:
            payload = _read_json_object(path)
        except Exception:
            continue
        if str(payload.get("target_date") or "") == target_date.isoformat():
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError(
            f"no SEND manifest for {target_date.isoformat()} under {send_root}"
        )
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sender_python() -> Path:
    repo_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    return repo_python if repo_python.exists() else Path(sys.executable)


def _send_store_telegram(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _resolve_newest_send_manifest(
        today_folder=Path(args.today_folder),
        target_date=args.target_date,
    )
    manifest_sha256 = _file_sha256(manifest_path)
    command = [
        str(_sender_python()),
        str(PROJECT_ROOT / "scripts" / "send_waybills_telegram.py"),
        "--today-folder",
        str(Path(args.today_folder).expanduser()),
        "--bundle-source",
        "merged",
        "--expected-target-date",
        args.target_date.isoformat(),
        "--manifest-path",
        str(manifest_path),
        "--manifest-sha256",
        manifest_sha256,
    ]
    for store in args.store:
        command.extend(["--store", store])
    result: dict[str, Any] = {
        "ok": True,
        "command": "send-store-telegram",
        "target_date": args.target_date.isoformat(),
        "applied": bool(args.apply),
        "stores": list(args.store),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "sender_command": command,
    }
    if not args.apply:
        return result
    _require_apply_gate(args)
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    result["sender_returncode"] = int(completed.returncode)
    result["sender_stderr"] = completed.stderr
    try:
        result["sender_report"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result["sender_stdout"] = completed.stdout
    result["ok"] = completed.returncode == 0
    if completed.returncode != 0:
        return result
    for store in args.store:
        set_store_day_state(
            args.target_date,
            store,
            "AUTO_SENT",
            reason=args.reason,
            set_by=args.set_by,
            checkpoint_path=_checkpoint_path(args),
        )
    result["auto_sent_stores"] = list(args.store)
    return result


def _clear_stuck_send_entry(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _resolve_newest_send_manifest(
        today_folder=Path(args.today_folder),
        target_date=args.target_date,
    )
    ledger_path = manifest_path.parent / TELEGRAM_SEND_LEDGER_FILE
    ledger = _read_json_object(ledger_path)
    entries = ledger.get("entries")
    if not isinstance(entries, dict):
        raise ValueError(f"Telegram ledger entries are missing: {ledger_path}")
    if args.entry not in entries:
        raise KeyError(f"Telegram ledger entry not found: {args.entry}")
    current_state = str(dict(entries[args.entry] or {}).get("state") or "pending")
    if current_state == "confirmed":
        raise RuntimeError(f"confirmed Telegram ledger entry is immutable: {args.entry}")
    result = {
        "ok": True,
        "command": "clear-stuck-send-entry",
        "target_date": args.target_date.isoformat(),
        "applied": bool(args.apply),
        "manifest_path": str(manifest_path),
        "ledger_path": str(ledger_path),
        "entry": args.entry,
        "previous_state": current_state,
        "next_state": "pending",
    }
    if args.apply:
        _require_apply_gate(args)
        _set_entry_state(
            ledger,
            args.entry,
            "pending",
            note=f"ops_day_control reset by {args.set_by}: {args.reason}",
        )
        save_telegram_ledger(ledger_path, ledger)
    return result


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "status":
        return _status(args)
    if args.command == "mark-store-fulfilled":
        return _set_one_state(args, state="MANUAL_FULFILLED")
    if args.command == "postpone-store":
        return _set_one_state(
            args,
            state="POSTPONED",
            postponed_to=args.postponed_to,
        )
    if args.command == "send-store-telegram":
        return _send_store_telegram(args)
    if args.command == "terminate-day":
        return _terminate_day(args)
    if args.command == "clear-stuck-send-entry":
        return _clear_stuck_send_entry(args)
    raise ValueError(f"unsupported command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audited per-day shipping controls")
    parser.add_argument("--date", dest="target_date", type=_parse_date, default=_parse_date("today"))
    parser.add_argument("--apply", action="store_true", help="Apply the action; default is dry-run")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument(
        "--obligation-ledger-path",
        type=Path,
        default=DEFAULT_OBLIGATION_LEDGER_PATH,
    )
    parser.add_argument(
        "--halt-barrier-path",
        type=Path,
        default=DEFAULT_CLOSEOUT_HALT_BARRIER_PATH,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    fulfilled = subparsers.add_parser("mark-store-fulfilled")
    fulfilled.add_argument("--store", type=_parse_store, required=True)
    fulfilled.add_argument("--reason", required=True)
    fulfilled.add_argument("--set-by", default="ops_day_control")

    postpone = subparsers.add_parser("postpone-store")
    postpone.add_argument("--store", type=_parse_store, required=True)
    postpone.add_argument("--postponed-to", type=_parse_date, required=True)
    postpone.add_argument("--reason", required=True)
    postpone.add_argument("--set-by", default="ops_day_control")

    send_store = subparsers.add_parser("send-store-telegram")
    send_store.add_argument("--store", action="append", type=_parse_store, required=True)
    send_store.add_argument("--today-folder", type=Path, default=TODAY_FOLDER)
    send_store.add_argument(
        "--reason",
        default="store-specific Telegram delivery confirmed",
    )
    send_store.add_argument("--set-by", default="ops_day_control")

    terminate = subparsers.add_parser("terminate-day")
    terminate.add_argument("--postponed-to", type=_parse_date, default=None)
    terminate.add_argument("--reason", required=True)
    terminate.add_argument("--set-by", default="ops_day_control")

    clear_entry = subparsers.add_parser("clear-stuck-send-entry")
    clear_entry.add_argument("--entry", "--pdf-key", dest="entry", required=True)
    clear_entry.add_argument("--today-folder", type=Path, default=TODAY_FOLDER)
    clear_entry.add_argument("--reason", required=True)
    clear_entry.add_argument("--set-by", default="ops_day_control")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    started_at = datetime.now(ALMATY_TZ).isoformat()
    try:
        result = _dispatch(args)
        returncode = 0 if result.get("ok") else 1
    except Exception as exc:
        result = {
            "ok": False,
            "command": args.command,
            "target_date": args.target_date.isoformat(),
            "applied": bool(args.apply),
            "error": f"{type(exc).__name__}: {exc}",
        }
        returncode = 1
    audit_payload = {
        "schema_version": 1,
        "started_at": started_at,
        "completed_at": datetime.now(ALMATY_TZ).isoformat(),
        "target_date": args.target_date.isoformat(),
        "command": args.command,
        "apply_requested": bool(args.apply),
        "env_gate_enabled": str(os.environ.get(APPLY_ENV_GATE) or "").strip() == "1",
        "arguments": _json_safe(vars(args)),
        "result": _json_safe(result),
        "returncode": returncode,
    }
    try:
        audit_path = _append_audit_line(
            audit_root=DEFAULT_AUDIT_ROOT,
            target_date=args.target_date,
            payload=audit_payload,
        )
        result["audit_path"] = str(audit_path)
    except Exception as exc:
        result["audit_error"] = f"{type(exc).__name__}: {exc}"
        result["ok"] = False
        returncode = 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
