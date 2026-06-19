#!/usr/bin/env python3
"""Publish a deterministic no-write map of remaining green-path blockers."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "green_path_remaining_blockers"

HARD_BLOCKER_RE = re.compile(r"^(?P<gate>G-[A-Z]+-\d{2})=(?P<status>[A-Z]+)\s+\((?P<group>[^)]+)\)")
CASH_LINE_RE = re.compile(r"^(?P<key>[a-z_]+_kzt):\s+(?P<value>-?\d+(?:\.\d+)?)$")

CATEGORY_BY_GATE = {
    "G-SCHED-01": "daily_ops_paused_or_scheduler_evidence",
    "G-SCHED-02": "cash_floor_policy",
    "G-ALERT-02": "elapsed_evidence",
    "G-CASH-04": "cash_floor_or_redeployment_policy",
    "G-RET-02": "real_owner_fact_required",
    "G-RET-03": "real_owner_fact_required",
    "G-PRICE-03": "owner_strategy_decision",
    "G-WA-01": "owner_strategy_decision",
    "G-WA-02": "owner_strategy_decision",
    "G-DARK-01": "owner_strategy_decision",
    "G-DARK-02": "elapsed_or_strategy_dependent",
    "G-LIQ-02": "owner_strategy_decision",
    "G-LIQ-03": "elapsed_or_strategy_dependent",
    "G-PO-02": "real_owner_fact_required",
    "G-PO-03": "real_owner_fact_required",
    "G-MET-01": "real_owner_fact_required",
    "G-MET-02": "elapsed_or_measurement_history",
    "G-MET-03": "real_owner_fact_required",
    "G-MET-04": "real_owner_fact_required",
    "G-OPS-01": "elapsed_or_measurement_history",
}

DO_NOT_DO_YET = [
    "Do not mark any HARD gate GREEN from intention, stale evidence, or strategic preference alone.",
    "Do not perform live price, relist, Repricer, Kaspi merchant, Google Sheet, Telegram, workbook, cash, PO, stock, or LaunchAgent writes from this report.",
    "Do not invent return QC, handling-cost, return-loss, stage-ledger, forecast, or comeback facts.",
    "Do not use daily-ops heartbeat failures as a surprise regression while daily ops are intentionally paused for green-path implementation.",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _resolve(raw: str | Path | None) -> Path | None:
    if raw in (None, ""):
        return None
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _latest(pattern: str) -> Path | None:
    paths = sorted(PROJECT_ROOT.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return paths[-1] if paths else None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_blocker(raw: str) -> dict[str, Any]:
    match = HARD_BLOCKER_RE.match(str(raw))
    if not match:
        gate_id = str(raw).split("=", 1)[0].strip()
        status = ""
        group = ""
    else:
        gate_id = match.group("gate")
        status = match.group("status")
        group = match.group("group")
    return {
        "gate_id": gate_id,
        "status": status,
        "group": group,
        "category": CATEGORY_BY_GATE.get(gate_id, "unclassified"),
        "source": raw,
    }


def _cash_preflight_summary(text: str) -> dict[str, Any]:
    values: dict[str, float] = {}
    status = ""
    reason = ""
    for line in text.splitlines():
        stripped = line.strip()
        match = CASH_LINE_RE.match(stripped)
        if match:
            values[match.group("key")] = float(match.group("value"))
        elif stripped.startswith("status:"):
            status = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("reason:"):
            reason = stripped.split(":", 1)[1].strip()
    return {
        "status": status,
        "reason": reason,
        "base_min_cash_kzt": values.get("base_min_cash_kzt"),
        "base_floor_kzt": values.get("base_floor_kzt"),
        "conservative_min_cash_kzt": values.get("conservative_min_cash_kzt"),
        "conservative_floor_kzt": values.get("conservative_floor_kzt"),
    }


def _category_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or "unclassified")
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _recommended_next_steps(*, queue: dict[str, Any], acceptance: dict[str, Any], daily_ops: dict[str, Any]) -> list[str]:
    steps = [
        "After 21:10 Asia/Almaty and after scheduled alert logs exist, rerun final acceptance and alert elapsed-window validation read-only.",
        "Keep returned goods quarantined until real staff QC facts are provided; then use the existing return-QC writer with backup/env/readback gates.",
        "Keep G-PRICE-03 and G-DARK-01 no-write unless owner gives a new exact strategy decision or external-write approval for the listed scope.",
        "Resolve G-SCHED-02 only by a governed cash-floor policy decision, real cash change, or a validated source correction; do not bypass the floor silently.",
    ]
    if int(queue.get("dispatch_ready_count") or 0) > 0:
        steps.insert(0, "Dispatch the owner-action queue items that are currently APPROVED and still pass fresh preflight.")
    if str(daily_ops.get("scope") or "") == "daily-ops":
        steps.append("Daily ops are intentionally paused for implementation; resume them only for the daily shipping window or explicit validation.")
    if acceptance.get("owner_signoff_present") is False:
        steps.append("Do not create final owner signoff until hard gates and advisory/waiver requirements are actually satisfied.")
    return steps


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Green-Path Remaining Blockers",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Status: {report['status']}",
        "",
        "## Counts",
        "",
    ]
    for key, value in report["status_counts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Categories", ""])
    for key, value in report["category_counts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Current Acceptance Blockers", ""])
    if report["acceptance_blockers"]:
        lines.extend(f"- {item}" for item in report["acceptance_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Hard Blockers", ""])
    for row in report["hard_blockers"]:
        lines.append(f"- `{row['gate_id']}` {row['status']} ({row['category']}): {row['source']}")
    lines.extend(["", "## Recommended Next Steps", ""])
    lines.extend(f"- {item}" for item in report["recommended_next_steps"])
    lines.extend(["", "## Do Not Do Yet", ""])
    lines.extend(f"- {item}" for item in report["do_not_do_yet"])
    return "\n".join(lines) + "\n"


def build_remaining_blockers_report(
    *,
    acceptance_report: Path | None = None,
    owner_queue_report: Path | None = None,
    eod_transcript: Path | None = None,
    daily_ops_verify: Path | None = None,
    scheduler_heartbeat_report: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    acceptance_path = acceptance_report or _latest("exports/validation/g_acc01_final_acceptance/*/*/final_acceptance_report.json")
    queue_path = owner_queue_report or _latest("exports/validation/owner_action_queue/*/owner_action_queue_report.json")
    eod_path = eod_transcript or _latest("exports/validation/g_sched02_eod_after_g_met04_*/run_end_of_day_dryrun.txt")
    daily_ops_path = daily_ops_verify or _latest("exports/automation_control/*/*_verify_daily-ops/verify_report.json")
    heartbeat_path = scheduler_heartbeat_report or _latest("exports/validation/g_sched03_heartbeat_*/*/scheduler_heartbeat.json")

    acceptance = _load_json(acceptance_path)
    queue = _load_json(queue_path)
    daily_ops = _load_json(daily_ops_path)
    heartbeat = _load_json(heartbeat_path)
    eod_text = _read_text(eod_path)

    hard_blockers = [_parse_blocker(item) for item in acceptance.get("hard_gate_blockers") or []]
    advisory_blockers = [_parse_blocker(item) for item in acceptance.get("advisory_decisions_required") or []]
    all_blockers = hard_blockers + advisory_blockers
    category_counts = _category_counts(all_blockers)

    waiting_actions = [str(item) for item in queue.get("waiting_actions") or []]
    dispatch_ready = int(queue.get("dispatch_ready_count") or 0)
    cash_summary = _cash_preflight_summary(eod_text)
    daily_ops_labels = (daily_ops.get("status") or {}).get("loaded_count", daily_ops.get("loaded_count"))
    heartbeat_errors = [str(item) for item in heartbeat.get("errors") or []]

    no_local_dispatch = dispatch_ready == 0
    waiting_external = bool(waiting_actions or acceptance.get("acceptance_blockers") or hard_blockers)
    gate = "ARMED" if waiting_external and no_local_dispatch else "GREEN"
    status = "BLOCKED_WAITING_OWNER_FACTS_TIME_OR_POLICY" if gate == "ARMED" else "READY"

    report: dict[str, Any] = {
        "gate_id": "GREEN-PATH-REMAINING-BLOCKERS",
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "status": status,
        "generated_at": _now_almaty(),
        "source_paths": {
            "acceptance_report": str(acceptance_path) if acceptance_path else "",
            "owner_queue_report": str(queue_path) if queue_path else "",
            "eod_transcript": str(eod_path) if eod_path else "",
            "daily_ops_verify": str(daily_ops_path) if daily_ops_path else "",
            "scheduler_heartbeat_report": str(heartbeat_path) if heartbeat_path else "",
        },
        "status_counts": acceptance.get("status_counts") or {},
        "hard_green": acceptance.get("hard_green"),
        "hard_total": acceptance.get("hard_total"),
        "advisory_green_or_waived": acceptance.get("advisory_green_or_waived"),
        "advisory_total": acceptance.get("advisory_total"),
        "acceptance_blockers": acceptance.get("acceptance_blockers") or [],
        "hard_blockers": hard_blockers,
        "advisory_blockers": advisory_blockers,
        "category_counts": category_counts,
        "owner_queue": {
            "dispatch_ready_count": dispatch_ready,
            "waiting_actions": waiting_actions,
            "dispatch_state": queue.get("dispatch_state", ""),
        },
        "cashflow_po_preflight": cash_summary,
        "daily_ops": {
            "verify_ok": daily_ops.get("ok"),
            "scope": daily_ops.get("scope", ""),
            "loaded_count": daily_ops_labels,
        },
        "scheduler_heartbeat": {
            "status": heartbeat.get("status", ""),
            "errors": heartbeat_errors,
            "note": "heartbeat failures are contextual while daily ops are intentionally paused",
        },
        "recommended_next_steps": _recommended_next_steps(queue=queue, acceptance=acceptance, daily_ops=daily_ops),
        "do_not_do_yet": DO_NOT_DO_YET,
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "remaining_blockers_report.json"
    md_path = output_root / "remaining_blockers_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-report", type=Path)
    parser.add_argument("--owner-queue-report", type=Path)
    parser.add_argument("--eod-transcript", type=Path)
    parser.add_argument("--daily-ops-verify", type=Path)
    parser.add_argument("--scheduler-heartbeat-report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = build_remaining_blockers_report(
        acceptance_report=_resolve(args.acceptance_report),
        owner_queue_report=_resolve(args.owner_queue_report),
        eod_transcript=_resolve(args.eod_transcript),
        daily_ops_verify=_resolve(args.daily_ops_verify),
        scheduler_heartbeat_report=_resolve(args.scheduler_heartbeat_report),
        output_root=args.output_dir,
    )
    print(f"Gate: {report['gate']}")
    print(f"Report: {report['json_path']}")
    print(f"Status: {report['status']}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
