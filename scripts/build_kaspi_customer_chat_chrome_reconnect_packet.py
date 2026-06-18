#!/usr/bin/env python3
"""Build an approval-gated Chrome reconnect packet for the Kaspi no-send canary.

This preflight never opens Chrome and never touches Kaspi. It only records
whether the Chrome extension repair path is ready for owner approval.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CHROME_PLUGIN_BASE = Path.home() / ".codex" / "plugins" / "cache" / "openai-bundled" / "chrome"
CHROME_PLUGIN_ROOT_ENV = "CODEX_CHROME_PLUGIN_ROOT"
DEFAULT_CANARY_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_live_canary_packet_2026-06-16_20260616_125511_final"
)
ACCEPTED_NO_SEND_GATE = "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"
APPROVAL_REQUIRED_GATE = "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION"


def _plugin_version_key(path: Path) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in path.name.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(-1)
    return tuple(parts)


def _resolve_chrome_plugin_root(base: Path = CHROME_PLUGIN_BASE) -> Path:
    override = os.environ.get(CHROME_PLUGIN_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    latest = base / "latest"
    if latest.exists():
        return latest.resolve()
    candidates = [
        path
        for path in base.iterdir()
        if path.is_dir() and (path / "scripts" / "chrome-is-running.js").exists()
    ] if base.exists() else []
    if candidates:
        return max(candidates, key=_plugin_version_key)
    return base / "latest"


CHROME_PLUGIN_ROOT = _resolve_chrome_plugin_root()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_chrome_reconnect_{stamp}"


def _run_node_json(script_name: str, args: list[str]) -> dict[str, Any]:
    script = CHROME_PLUGIN_ROOT / "scripts" / script_name
    result = subprocess.run(
        ["node", str(script), *args],
        cwd=CHROME_PLUGIN_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        parsed = {"raw_stdout": result.stdout.strip()}
    return {
        "script": script_name,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "stdout_json": parsed,
        "stderr_present": bool((result.stderr or "").strip()),
    }


def _collect_diagnostics() -> dict[str, Any]:
    return {
        "chrome_is_running": _run_node_json("chrome-is-running.js", ["--json"]),
        "installed_browsers": _run_node_json("installed-browsers.js", ["--json"]),
        "extension_installed": _run_node_json("check-extension-installed.js", ["--json"]),
        "native_host_manifest": _run_node_json("check-native-host-manifest.js", ["--json"]),
        "open_chrome_window_dry_run": _run_node_json("open-chrome-window.js", ["--dry-run", "--json"]),
    }


def _chrome_installed(installed: dict[str, Any]) -> bool:
    browsers = installed.get("stdout_json", {}).get("installed_browsers") or []
    return any(str(row.get("name") or "") == "Google Chrome" for row in browsers)


def _dry_run_command(dry_run: dict[str, Any]) -> str:
    payload = dry_run.get("stdout_json") or {}
    command = str(payload.get("command") or "").strip()
    args = [str(item) for item in payload.get("args") or []]
    return " ".join([command, *args]).strip()


def _summarize_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    chrome_running = bool(
        diagnostics.get("chrome_is_running", {}).get("stdout_json", {}).get("running")
    )
    extension_payload = diagnostics.get("extension_installed", {}).get("stdout_json") or {}
    native_payload = diagnostics.get("native_host_manifest", {}).get("stdout_json") or {}
    dry_run_payload = diagnostics.get("open_chrome_window_dry_run", {}).get("stdout_json") or {}
    selected_profile = extension_payload.get("selectedProfileDirectory")
    return {
        "chrome_running": chrome_running,
        "google_chrome_installed": _chrome_installed(diagnostics.get("installed_browsers", {})),
        "selected_profile_directory": selected_profile,
        "extension_installed_in_selected_profile": bool(extension_payload.get("installed")),
        "extension_enabled_in_selected_profile": bool(extension_payload.get("enabled")),
        "native_host_manifest_correct": bool(native_payload.get("correct")),
        "dry_run_available": bool(dry_run_payload.get("dryRun") is True),
        "dry_run_command": _dry_run_command(diagnostics.get("open_chrome_window_dry_run", {})),
        "dry_run_profile_directory": dry_run_payload.get("profileDirectory"),
    }


def _approval_phrase(summary: dict[str, Any]) -> str:
    profile = summary.get("selected_profile_directory") or "<unknown profile>"
    return (
        "I approve opening a new Google Chrome window for selected "
        f"{profile} solely to reconnect the Codex Chrome Extension and retry the Kaspi live UI "
        "no-send canary. No customer message typing/sending, Kaspi writes, cookie/localStorage/"
        "session inspection, Google Board writes, DB writes, Telegram/WhatsApp sends, scheduler "
        "changes, or external writes are approved."
    )


def _build_closeout(manifest: dict[str, Any]) -> str:
    summary = manifest["diagnostic_summary"]
    lines = [
        "# Kaspi Customer Chat Chrome Reconnect Preflight",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        f"- Canary packet: {manifest['canary_packet_dir']}",
        f"- Current live UI validation gate: {manifest.get('current_live_ui_validation_gate')}",
        "- No Chrome window was opened by this preflight.",
        "- No Kaspi page action, order search, chat open, message typing, or send happened.",
        "",
        "## Diagnostic Summary",
        "",
        f"- Chrome running: {str(summary.get('chrome_running')).lower()}",
        f"- Google Chrome installed: {str(summary.get('google_chrome_installed')).lower()}",
        f"- Selected profile: `{summary.get('selected_profile_directory')}`",
        f"- Extension installed in selected profile: {str(summary.get('extension_installed_in_selected_profile')).lower()}",
        f"- Extension enabled in selected profile: {str(summary.get('extension_enabled_in_selected_profile')).lower()}",
        f"- Native host manifest correct: {str(summary.get('native_host_manifest_correct')).lower()}",
        f"- Dry-run repair command: `{summary.get('dry_run_command')}`",
        "",
        "## Required Approval Phrase",
        "",
        "```text",
        manifest.get("approval_phrase") or "",
        "```",
        "",
        "## Safety Notes",
        "",
        "- This packet is a preflight only.",
        "- The next live action remains owner-approval gated.",
        "- If the reconnect works, the next browser step is still no-send visual proof only.",
        "",
    ]
    blockers = manifest.get("blockers") or []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_CANARY_PACKET_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--diagnostics-json",
        type=Path,
        help="Optional fixture containing pre-collected Chrome diagnostics.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_dir = args.packet_dir.resolve()
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    validation = _read_json(validation_path) if validation_path.exists() else {}
    diagnostics = _read_json(args.diagnostics_json) if args.diagnostics_json else _collect_diagnostics()
    summary = _summarize_diagnostics(diagnostics)
    ready_for_approval = all(
        [
            summary["chrome_running"],
            summary["google_chrome_installed"],
            summary["extension_installed_in_selected_profile"],
            summary["extension_enabled_in_selected_profile"],
            summary["native_host_manifest_correct"],
            summary["dry_run_available"],
            summary["dry_run_command"],
        ]
    )

    blockers: list[str] = []
    if validation.get("gate") == ACCEPTED_NO_SEND_GATE:
        gate = "GREEN_LIVE_UI_NO_SEND_ALREADY_ACCEPTED_NO_RECONNECT_NEEDED"
    elif ready_for_approval:
        gate = APPROVAL_REQUIRED_GATE
    else:
        gate = "YELLOW_CHROME_RECONNECT_PREFLIGHT_NOT_READY_NO_UI_ACTION"
        for key, value in summary.items():
            if key.endswith("command") or key.endswith("directory"):
                continue
            if value is not True:
                blockers.append(f"{key}_not_true")

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "canary_packet_dir": str(packet_dir),
        "current_live_ui_validation_gate": validation.get("gate"),
        "diagnostic_summary": summary,
        "approval_phrase": _approval_phrase(summary) if gate == APPROVAL_REQUIRED_GATE else "",
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chrome_window_opened": False,
        "cookie_localstorage_session_inspection_allowed": False,
        "external_write_allowed": False,
        "blockers": blockers,
    }

    _write_json(output_dir / "chrome_reconnect_diagnostics_redacted.json", diagnostics)
    _write_json(output_dir / "chrome_reconnect_preflight_manifest.json", manifest)
    (output_dir / "chrome_reconnect_preflight_closeout.md").write_text(
        _build_closeout(manifest),
        encoding="utf-8",
    )
    if manifest["approval_phrase"]:
        (output_dir / "REQUIRED_EXACT_CHROME_RECONNECT_APPROVAL_PHRASE.txt").write_text(
            manifest["approval_phrase"] + "\n",
            encoding="utf-8",
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate != "YELLOW_CHROME_RECONNECT_PREFLIGHT_NOT_READY_NO_UI_ACTION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
