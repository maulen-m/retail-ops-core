#!/usr/bin/env python3
"""Publish the G-ACC-01 final acceptance scored matrix."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, time
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "final_acceptance_gate.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_acc01_final_acceptance"

MATRIX_COLUMNS = [
    "gate_id",
    "domain",
    "phase",
    "workstream",
    "blocking",
    "owner_waivable",
    "initial_state",
    "measured_value",
    "scored_state",
    "status_source",
    "evidence",
    "dated",
    "criterion",
]

VALID_GATE_STATUSES = {"GREEN", "ARMED", "PARTIAL", "RED", "PENDING", "WAIVED", "OFF", "MISSING"}


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(value: str | None) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _resolve_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, check_id: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": check_id, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _load_gate_matrix(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_dashboard(path: Path) -> tuple[dict[str, str], dict[str, Any]]:
    if not path.exists():
        return {}, {"error": f"missing dashboard: {path}"}
    text = path.read_text(encoding="utf-8")
    match = re.search(r"window\.GP\s*=\s*(\{.*\});\s*$", text, re.S)
    if not match:
        return {}, {"error": "dashboard payload not found"}
    payload = json.loads(match.group(1))
    states: dict[str, str] = {}
    for row in payload.get("gates", []):
        gate_id = str(row.get("id") or "").strip()
        status = str(row.get("status") or "").strip().upper()
        if gate_id:
            states[gate_id] = status
    meta = {
        "updated": payload.get("updated", ""),
        "status": payload.get("status", ""),
        "current_phase": payload.get("current_phase", ""),
        "current_take": payload.get("current_take", ""),
        "gate_count": len(states),
    }
    return states, meta


def _load_scoreboard(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            if not gate_id:
                continue
            state = str(row.get("status") or row.get("state") or "").strip().upper()
            rows[gate_id] = {
                "state": state,
                "evidence": str(row.get("evidence") or "").strip(),
                "dated": str(row.get("dated") or "").strip(),
            }
    return rows


def _normal_status(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    return text if text in VALID_GATE_STATUSES else "MISSING"


def _initial_state(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.split(" ", 1)[0].strip().upper()


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _score_row_status(blocking: str, measured: str, allowed_advisory: set[str]) -> str:
    if blocking == "HARD":
        return "PASS" if measured == "GREEN" else "BLOCKED"
    if blocking == "ADVISORY":
        return "PASS" if measured in allowed_advisory else "WAIVER_REQUIRED"
    return "BLOCKED"


def _build_matrix_rows(
    *,
    gate_matrix: list[dict[str, str]],
    dashboard_states: dict[str, str],
    scoreboard_rows: dict[str, dict[str, str]],
    acceptance_status: str,
    allowed_advisory: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate in gate_matrix:
        gate_id = str(gate.get("gate_id") or "").strip()
        blocking = str(gate.get("blocking") or "").strip().upper()
        scoreboard_row = scoreboard_rows.get(gate_id, {})
        if gate_id == "G-ACC-01":
            measured = acceptance_status
            status_source = "derived_acceptance"
        elif gate_id in dashboard_states:
            measured = _normal_status(dashboard_states[gate_id])
            status_source = "dashboard"
        elif scoreboard_row.get("state"):
            measured = _normal_status(scoreboard_row.get("state"))
            status_source = "scoreboard"
        else:
            measured = "MISSING"
            status_source = "missing"

        rows.append(
            {
                "gate_id": gate_id,
                "domain": gate.get("domain", ""),
                "phase": gate.get("phase", ""),
                "workstream": gate.get("workstream", ""),
                "blocking": blocking,
                "owner_waivable": gate.get("owner_waivable", ""),
                "initial_state": _initial_state(gate.get("current_state", "")),
                "measured_value": measured,
                "scored_state": _score_row_status(blocking, measured, allowed_advisory),
                "status_source": status_source,
                "evidence": scoreboard_row.get("evidence", ""),
                "dated": scoreboard_row.get("dated", ""),
                "criterion": gate.get("criterion", ""),
            }
        )
    return rows


def _post_eod_ok(as_of_dt: datetime, cutoff_text: str) -> tuple[bool, str]:
    hour_text, minute_text = str(cutoff_text or "21:10").split(":", 1)
    cutoff = time(hour=int(hour_text), minute=int(minute_text), tzinfo=ALMATY_TZ)
    current = as_of_dt.timetz().replace(microsecond=0)
    ok = current >= cutoff
    return ok, f"as_of_time={current.isoformat()} cutoff={cutoff.isoformat()}"


def _parse_deferred_queue(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "row_count": 0,
            "fallback_complete": False,
            "acceptance_review_count": 0,
            "rows": [],
        }
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0].lower() == "item" or len(cells) < 6:
            continue
        rows.append(
            {
                "item": cells[0],
                "lane": cells[1],
                "kzt_exposure": cells[2],
                "age_days": cells[3],
                "fallback_applied": cells[4],
                "resurfaces_at": cells[5],
            }
        )
    fallback_complete = all(row["fallback_applied"] and row["resurfaces_at"] for row in rows)
    acceptance_review = [
        row
        for row in rows
        if "acceptance" in row["resurfaces_at"].lower() or "acceptance" in row["fallback_applied"].lower()
    ]
    return {
        "path": str(path),
        "exists": True,
        "row_count": len(rows),
        "fallback_complete": fallback_complete,
        "acceptance_review_count": len(acceptance_review),
        "rows": rows,
    }


def _owner_signoff_present(path: Path, marker: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing owner signoff artifact: {path}"
    text = path.read_text(encoding="utf-8")
    if marker and marker not in text:
        return False, f"owner signoff marker missing: {marker}"
    return True, str(path)


def _count_statuses(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("measured_value") or "MISSING")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-ACC-01 Final Acceptance Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Dashboard updated: {report['dashboard_meta'].get('updated', '')}",
        "",
        "## Summary",
        "",
        f"- total_gates: {report['total_gates']}",
        f"- hard_green: {report['hard_green']}/{report['hard_total']}",
        f"- advisory_green_or_waived: {report['advisory_green_or_waived']}/{report['advisory_total']}",
        f"- owner_signoff_present: {report['owner_signoff_present']}",
        f"- deferred_queue_rows: {report['deferred_queue']['row_count']}",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## Acceptance Blockers", ""])
    if report["acceptance_blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["acceptance_blockers"])
    else:
        lines.append("- none")

    lines.extend(["", "## Hard Gate Blockers", ""])
    if report["hard_gate_blockers"]:
        for blocker in report["hard_gate_blockers"][:40]:
            lines.append(f"- {blocker}")
        if len(report["hard_gate_blockers"]) > 40:
            lines.append(f"- ... {len(report['hard_gate_blockers']) - 40} more")
    else:
        lines.append("- none")

    lines.extend(["", "## Advisory Decisions Required", ""])
    if report["advisory_decisions_required"]:
        lines.extend(f"- {blocker}" for blocker in report["advisory_decisions_required"])
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- scored_matrix_csv: `{report['artifacts']['scored_matrix_csv']}`",
            f"- owner_approval_required_csv: `{report['artifacts']['owner_approval_required_csv']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_final_acceptance_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    acceptance_blockers: list[str] = []

    config_path = config_path.expanduser().resolve()
    config = _load_json(config_path) if config_path.exists() else {}
    checks.append(_check(bool(config), "config_present", str(config_path)))
    checks.append(
        _check(
            config.get("contract_id") == "FINAL_ACCEPTANCE_GATE_V1" and config.get("gate_id") == "G-ACC-01",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )

    matrix_path = _resolve_path(config.get("gate_matrix_path"))
    dashboard_path = _resolve_path(config.get("dashboard_path"))
    scoreboard_path = _resolve_path(config.get("scoreboard_path"))
    deferred_path = _resolve_path(config.get("deferred_queue_path"))
    signoff_path = _resolve_path(config.get("owner_signoff_path"))
    allowed_advisory = {str(value).upper() for value in config.get("allowed_advisory_statuses") or ["GREEN", "WAIVED"]}

    gate_matrix = _load_gate_matrix(matrix_path)
    dashboard_states, dashboard_meta = _load_dashboard(dashboard_path)
    scoreboard_rows = _load_scoreboard(scoreboard_path)
    checks.append(_check(bool(gate_matrix), "gate_matrix_loaded", str(matrix_path), gate_count=len(gate_matrix)))
    checks.append(_check(bool(dashboard_states), "dashboard_loaded", str(dashboard_path), gate_count=len(dashboard_states)))
    checks.append(_check(bool(scoreboard_rows), "scoreboard_loaded", str(scoreboard_path), gate_count=len(scoreboard_rows)))
    checks.append(
        _check(
            len(gate_matrix) == len(dashboard_states),
            "matrix_dashboard_gate_count_match",
            f"matrix={len(gate_matrix)} dashboard={len(dashboard_states)}",
        )
    )

    as_of_dt = _parse_as_of(as_of)
    post_eod_ok, post_eod_details = _post_eod_ok(as_of_dt, str(config.get("post_eod_cutoff_local_time") or "21:10"))
    checks.append(_check(post_eod_ok, "post_eod_acceptance_window", post_eod_details))
    if not post_eod_ok:
        acceptance_blockers.append(f"post_eod_acceptance_window: {post_eod_details}")

    deferred_queue = _parse_deferred_queue(deferred_path)
    checks.append(
        _check(
            deferred_queue["exists"] and deferred_queue["fallback_complete"],
            "deferred_queue_policy",
            f"rows={deferred_queue['row_count']} fallback_complete={deferred_queue['fallback_complete']}",
        )
    )
    if not deferred_queue["exists"] or not deferred_queue["fallback_complete"]:
        acceptance_blockers.append("deferred queue is missing or lacks fallback/unblock policy rows")

    signoff_ok, signoff_details = _owner_signoff_present(
        signoff_path, str(config.get("owner_signoff_marker") or "")
    )
    checks.append(_check(signoff_ok, "owner_signoff_present", signoff_details))
    if not signoff_ok:
        acceptance_blockers.append(signoff_details)

    for row in checks:
        if not row["ok"] and row["check"] not in {"post_eod_acceptance_window", "deferred_queue_policy", "owner_signoff_present"}:
            acceptance_blockers.append(f"{row['check']}: {row['details']}")

    provisional_rows = _build_matrix_rows(
        gate_matrix=gate_matrix,
        dashboard_states=dashboard_states,
        scoreboard_rows=scoreboard_rows,
        acceptance_status="PENDING",
        allowed_advisory=allowed_advisory,
    )
    hard_gate_blockers = [
        f"{row['gate_id']}={row['measured_value']} ({row['domain']})"
        for row in provisional_rows
        if row["gate_id"] != "G-ACC-01" and row["blocking"] == "HARD" and row["measured_value"] != "GREEN"
    ]
    advisory_decisions_required = [
        f"{row['gate_id']}={row['measured_value']} ({row['domain']})"
        for row in provisional_rows
        if row["blocking"] == "ADVISORY" and row["measured_value"] not in allowed_advisory
    ]

    gate = "GREEN" if not hard_gate_blockers and not advisory_decisions_required and not acceptance_blockers else "RED"
    scored_rows = _build_matrix_rows(
        gate_matrix=gate_matrix,
        dashboard_states=dashboard_states,
        scoreboard_rows=scoreboard_rows,
        acceptance_status=gate,
        allowed_advisory=allowed_advisory,
    )

    output_root = output_root.expanduser().resolve()
    run_id = _now_almaty().replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix_csv = out_dir / "final_gate_matrix.csv"
    owner_csv = out_dir / "owner_approval_required.csv"
    _write_csv(matrix_csv, scored_rows, MATRIX_COLUMNS)
    owner_rows = [
        {"item": item, "kind": "hard_gate_blocker"} for item in hard_gate_blockers
    ] + [
        {"item": item, "kind": "advisory_decision_required"} for item in advisory_decisions_required
    ] + [
        {"item": item, "kind": "acceptance_blocker"} for item in acceptance_blockers
    ]
    _write_csv(owner_csv, owner_rows, ["kind", "item"])

    hard_rows = [row for row in scored_rows if row["blocking"] == "HARD"]
    advisory_rows = [row for row in scored_rows if row["blocking"] == "ADVISORY"]
    report: dict[str, Any] = {
        "gate_id": "G-ACC-01",
        "gate": gate,
        "ok": gate == "GREEN",
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.replace(microsecond=0).isoformat(),
        "config_path": str(config_path),
        "gate_matrix_path": str(matrix_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "dashboard_meta": dashboard_meta,
        "total_gates": len(scored_rows),
        "status_counts": _count_statuses(scored_rows),
        "hard_total": len(hard_rows),
        "hard_green": sum(1 for row in hard_rows if row["measured_value"] == "GREEN"),
        "advisory_total": len(advisory_rows),
        "advisory_green_or_waived": sum(1 for row in advisory_rows if row["measured_value"] in allowed_advisory),
        "hard_gate_blockers": hard_gate_blockers,
        "advisory_decisions_required": advisory_decisions_required,
        "acceptance_blockers": acceptance_blockers,
        "deferred_queue": deferred_queue,
        "owner_signoff_present": signoff_ok,
        "checks": checks,
        "artifacts": {
            "scored_matrix_csv": str(matrix_csv),
            "owner_approval_required_csv": str(owner_csv),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = out_dir / "final_acceptance_report.json"
    md_path = out_dir / "final_acceptance_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_final_acceptance_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
        if report["acceptance_blockers"]:
            print("Acceptance blockers:")
            for blocker in report["acceptance_blockers"]:
                print(f"  - {blocker}")
        if report["hard_gate_blockers"]:
            print("Hard gate blockers:")
            for blocker in report["hard_gate_blockers"]:
                print(f"  - {blocker}")
        if report["advisory_decisions_required"]:
            print("Advisory decisions required:")
            for blocker in report["advisory_decisions_required"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
