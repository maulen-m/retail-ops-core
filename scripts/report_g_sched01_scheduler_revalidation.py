#!/usr/bin/env python3
"""Build a no-write G-SCHED-01 scheduler revalidation report."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_sched01_scheduler_revalidation"

DAILY_OPS_SCOPE_LABELS = {
    "com.example.kaspi-import-v2",
    "com.example.google-ops-board-publish",
    "com.example.google-ops-board-prewindow-health",
    "com.example.google-ops-board-size-writeback",
    "com.example.google-ops-board-closeout-watch",
    "com.example.google-ops-board-closeout-caffeinate",
    "com.example.kaspi-waybill-deadline",
    "com.example.waybill-telegram-control",
    "com.example.kaspi-shipped-truth-sync",
    "com.example.kaspi-daily-ops-report",
}

BENIGN_NONZERO_WHILE_PAUSED = {
    "com.example.single-truth-preflight",
    "com.example.table-delta-backup",
    "com.example.external-database-backup",
    "com.autonomous-business.end-of-day",
    "com.example.crm-db-sync",
    "com.example.exchange-import",
    "com.example.operational-stock-daily-truth",
    "com.example.kaspi-marketing-ads",
    "com.example.gmail-pubsub",
    "com.example.gmail-watch-refresh",
}


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_zero_exit(value: Any) -> bool:
    text = str(value or "").strip()
    return text in {"", "0", "0: 0"}


def _contract_checks_clean(heartbeat: dict[str, Any]) -> bool:
    checks = heartbeat.get("checks") or []
    contract_rows = [
        row
        for row in checks
        if any(
            token in str(row.get("check") or "")
            for token in ("plist_schedule_contract", "plist_has_no_second_component", "program_arguments_contract", "schedule_tokens")
        )
    ]
    return bool(contract_rows) and all(bool(row.get("ok")) for row in contract_rows)


def build_report(
    *,
    status_report: Path,
    heartbeat_report: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    status = _load_json(status_report)
    heartbeat = _load_json(heartbeat_report)

    labels = list(status.get("labels") or [])
    missing_plists = [row for row in labels if not row.get("plist_exists")]
    daily_ops_not_loaded = [
        row for row in labels if str(row.get("label")) in DAILY_OPS_SCOPE_LABELS and not row.get("loaded")
    ]
    loaded_nonzero = [
        row
        for row in labels
        if row.get("loaded") and not _is_zero_exit(row.get("last_exit_code"))
    ]
    loaded_nonzero_requiring_decision = [
        row for row in loaded_nonzero if str(row.get("label")) not in BENIGN_NONZERO_WHILE_PAUSED
    ]

    contract_ok = _contract_checks_clean(heartbeat)
    heartbeat_errors = [str(item) for item in heartbeat.get("errors") or []]
    blockers: list[str] = []
    if missing_plists:
        blockers.append(f"missing_plists:{len(missing_plists)}")
    if not contract_ok:
        blockers.append("scheduler_contract_or_docs_drift")
    if daily_ops_not_loaded:
        blockers.append(f"daily_ops_intentionally_paused:{len(daily_ops_not_loaded)}")
    if loaded_nonzero:
        blockers.append(f"loaded_nonzero_last_exit:{len(loaded_nonzero)}")
    if heartbeat_errors:
        blockers.append(f"heartbeat_errors:{len(heartbeat_errors)}")

    promotable_green = not blockers
    gate = "GREEN" if promotable_green else "ARMED"
    g_sched01_state = "GREEN" if promotable_green else "PARTIAL_RETAINED"
    generated_at = _now_almaty()
    out_dir = output_root / generated_at.replace(":", "").replace("-", "").split("+", 1)[0]
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "gate_id": "G-SCHED-01",
        "gate": gate,
        "g_sched01_state": g_sched01_state,
        "generated_at": generated_at,
        "as_of": as_of or heartbeat.get("as_of") or "",
        "status_report": str(status_report),
        "heartbeat_report": str(heartbeat_report),
        "scheduler_contract_clean": contract_ok,
        "daily_ops_scope_loaded_count": len(DAILY_OPS_SCOPE_LABELS) - len(daily_ops_not_loaded),
        "daily_ops_scope_not_loaded_count": len(daily_ops_not_loaded),
        "loaded_nonzero_count": len(loaded_nonzero),
        "loaded_nonzero_requiring_decision_count": len(loaded_nonzero_requiring_decision),
        "missing_plist_count": len(missing_plists),
        "heartbeat_status": heartbeat.get("status", ""),
        "heartbeat_errors": heartbeat_errors,
        "blockers": blockers,
        "daily_ops_not_loaded_labels": [str(row.get("label")) for row in daily_ops_not_loaded],
        "loaded_nonzero_labels": [
            {
                "label": str(row.get("label")),
                "last_exit_code": str(row.get("last_exit_code") or ""),
                "state": str(row.get("state") or ""),
                "purpose": str(row.get("purpose") or ""),
            }
            for row in loaded_nonzero
        ],
        "do_not_do_yet": [
            "Do not mark G-SCHED-01 GREEN while daily-ops labels are deliberately not loaded.",
            "Do not kickstart write-capable scheduler jobs just to manufacture a clean last-exit code.",
            "Do not treat heartbeat failures as regressions when they are caused by the approved paused implementation window.",
            "Do not mutate LaunchAgents from this report.",
        ],
        "no_write_surfaces": {
            "production_db_written": False,
            "workbook_written": False,
            "google_sheet_written": False,
            "telegram_sent": False,
            "launchagent_changed": False,
            "external_write": False,
        },
    }
    json_path = out_dir / "g_sched01_scheduler_revalidation_report.json"
    md_path = out_dir / "g_sched01_scheduler_revalidation_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-SCHED-01 Scheduler Revalidation",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"G-SCHED-01 state: `{report['g_sched01_state']}`",
        "",
        "## Summary",
        "",
        f"- scheduler_contract_clean: `{report['scheduler_contract_clean']}`",
        f"- daily_ops_scope_loaded_count: `{report['daily_ops_scope_loaded_count']}`",
        f"- daily_ops_scope_not_loaded_count: `{report['daily_ops_scope_not_loaded_count']}`",
        f"- loaded_nonzero_count: `{report['loaded_nonzero_count']}`",
        f"- heartbeat_status: `{report['heartbeat_status']}`",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- `{item}`" for item in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Loaded Nonzero Labels", ""])
    if report["loaded_nonzero_labels"]:
        for row in report["loaded_nonzero_labels"]:
            lines.append(
                f"- `{row['label']}` last_exit=`{row['last_exit_code']}` state=`{row['state']}` purpose={row['purpose']}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Daily-Ops Labels Not Loaded", ""])
    if report["daily_ops_not_loaded_labels"]:
        lines.extend(f"- `{label}`" for label in report["daily_ops_not_loaded_labels"])
    else:
        lines.append("- none")
    lines.extend(["", "## Do Not Do Yet", ""])
    lines.extend(f"- {item}" for item in report["do_not_do_yet"])
    lines.extend(["", "No DB, workbook, Google Sheet, Telegram, LaunchAgent, marketplace, cash, PO, stock, or external write was performed."])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a no-write G-SCHED-01 scheduler revalidation report")
    parser.add_argument("--status-report", type=Path, required=True)
    parser.add_argument("--heartbeat-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_report(
        status_report=args.status_report,
        heartbeat_report=args.heartbeat_report,
        output_root=args.output_root,
        as_of=args.as_of,
    )
    print(f"Gate: {report['gate']}")
    print(f"Report: {report['json_path']}")
    if args.strict and report["gate"] != "GREEN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
