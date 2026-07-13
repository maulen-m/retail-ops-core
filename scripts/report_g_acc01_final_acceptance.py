#!/usr/bin/env python3
"""Publish the G-ACC-01 final acceptance scored matrix."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, time
import json
from math import isfinite
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


def _parse_source_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
        for fmt in ("%Y%m%d_%H%M%S", "%Y%m%d_%H%M", "%Y%m%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _positive_finite_hours(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) and parsed > 0 else None


def _source_freshness(raw: Any, *, as_of_dt: datetime, max_age_hours: float | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "raw": str(raw or ""),
        "observed_at": None,
        "age_hours": None,
        "max_age_hours": max_age_hours,
        "ok": False,
        "error": "",
    }
    if max_age_hours is None:
        result["error"] = "freshness limit is missing or invalid"
        return result
    observed = _parse_source_timestamp(raw)
    if observed is None:
        result["error"] = "timestamp is missing or invalid"
        return result
    result["observed_at"] = observed.replace(microsecond=0).isoformat()
    age_seconds = (as_of_dt - observed).total_seconds()
    result["age_hours"] = round(age_seconds / 3600.0, 6)
    if age_seconds < 0:
        result["error"] = "timestamp is in the future"
        return result
    if age_seconds > max_age_hours * 3600.0:
        result["error"] = "timestamp is stale"
        return result
    result["ok"] = True
    return result


def _freshness_sla_limit(raw: Any) -> tuple[str, float | None, str]:
    text = str(raw or "").strip().lower()
    if text == "n/a":
        return "NOT_APPLICABLE", None, ""
    duration_match = re.match(r"^(\d+(?:\.\d+)?)d(?:\b|\s)", text)
    if duration_match:
        return "DURATION", float(duration_match.group(1)) * 24.0, ""
    if text.startswith("continuous"):
        return "DURATION", 24.0, ""
    if not text:
        return "UNSUPPORTED", None, "freshness_sla is missing"
    return "UNSUPPORTED", None, "freshness_sla is not time-evaluable"


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


def _load_scoreboard(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    if not path.exists():
        return {}, {
            "error": f"missing scoreboard: {path}",
            "row_count": 0,
            "last_row_number": None,
            "last_dated": "",
            "dated_values": [],
        }
    rows: dict[str, dict[str, str]] = {}
    physical_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            dated = str(row.get("dated") or "").strip()
            physical_rows.append({"row_number": row_number, "gate_id": gate_id, "dated": dated})
            if not gate_id:
                continue
            state = str(row.get("status") or row.get("state") or "").strip().upper()
            rows[gate_id] = {
                "state": state,
                "evidence": str(row.get("evidence") or "").strip(),
                "dated": dated,
            }
    last_row = physical_rows[-1] if physical_rows else {}
    return rows, {
        "row_count": len(physical_rows),
        "last_row_number": last_row.get("row_number"),
        "last_dated": last_row.get("dated", ""),
        "dated_values": [row["dated"] for row in physical_rows],
    }


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
        f"Evaluated at: {report['evaluated_at']}",
        f"Dashboard updated: {report['dashboard_meta'].get('updated', '')}",
        "",
        "## Summary",
        "",
        f"- total_gates: {report['total_gates']}",
        f"- hard_green: {report['hard_green']}/{report['hard_total']}",
        f"- advisory_green_or_waived: {report['advisory_green_or_waived']}/{report['advisory_total']}",
        f"- owner_signoff_present: {report['owner_signoff_present']}",
        f"- deferred_queue_rows: {report['deferred_queue']['row_count']}",
        f"- source_freshness_ok: {report['source_freshness_ok']}",
        f"- inputs_reconciled: {report['inputs_reconciled']}",
        f"- evaluation_mode: {report['evaluation_mode']}",
        (
            "- operational_as_of_age_hours: "
            f"{report['operational_as_of']['age_hours']} "
            f"(max {report['operational_as_of']['max_age_hours']})"
        ),
        f"- status_counts_current: {report['status_counts_current']}",
        f"- status_counts_label: {report['status_counts_label']}",
        (
            "- dashboard_source_age_hours: "
            f"{report['source_freshness']['dashboard']['age_hours']} "
            f"(max {report['source_freshness']['dashboard']['max_age_hours']})"
        ),
        (
            "- scoreboard_source_age_hours: "
            f"{report['source_freshness']['scoreboard']['age_hours']} "
            f"(max {report['source_freshness']['scoreboard']['max_age_hours']})"
        ),
        f"- scoreboard_missing_gate_ids: {len(report['provenance']['scoreboard_missing_gate_ids'])}",
        f"- dashboard_scoreboard_disagreements: {len(report['provenance']['dashboard_scoreboard_disagreements'])}",
        f"- green_gates_missing_evidence: {len(report['provenance']['green_gates_missing_evidence'])}",
        f"- green_gate_freshness_failures: {len(report['provenance']['green_gate_freshness_failures'])}",
        f"- invalid_dashboard_states: {len(report['provenance']['invalid_dashboard_states'])}",
        f"- invalid_scoreboard_states: {len(report['provenance']['invalid_scoreboard_states'])}",
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
    evaluation_time: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    acceptance_blockers: list[str] = []
    as_of_dt = _parse_as_of(as_of)
    evaluation_dt = (
        _parse_as_of(evaluation_time)
        if evaluation_time
        else datetime.now(ALMATY_TZ)
    )

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
    allowed_advisory = {
        str(value).upper()
        for value in config.get("allowed_advisory_statuses") or ["GREEN", "WAIVED"]
    }
    allowed_dashboard_statuses = {
        str(value).strip().upper()
        for value in config.get("allowed_dashboard_statuses") or []
        if str(value).strip()
    }

    gate_matrix = _load_gate_matrix(matrix_path)
    dashboard_states, dashboard_meta = _load_dashboard(dashboard_path)
    scoreboard_rows, scoreboard_meta = _load_scoreboard(scoreboard_path)
    checks.append(_check(bool(gate_matrix), "gate_matrix_loaded", str(matrix_path), gate_count=len(gate_matrix)))
    checks.append(_check(bool(dashboard_states), "dashboard_loaded", str(dashboard_path), gate_count=len(dashboard_states)))
    checks.append(_check(bool(scoreboard_rows), "scoreboard_loaded", str(scoreboard_path), gate_count=len(scoreboard_rows)))

    matrix_ids = {str(row.get("gate_id") or "").strip() for row in gate_matrix}
    matrix_ids.discard("")
    dashboard_ids = set(dashboard_states)
    scoreboard_ids = set(scoreboard_rows)
    dashboard_missing_gate_ids = sorted(matrix_ids - dashboard_ids)
    dashboard_extra_gate_ids = sorted(dashboard_ids - matrix_ids)
    scoreboard_missing_gate_ids = sorted(matrix_ids - scoreboard_ids)
    scoreboard_extra_gate_ids = sorted(scoreboard_ids - matrix_ids)
    gate_by_id = {
        str(row.get("gate_id") or "").strip(): row
        for row in gate_matrix
        if str(row.get("gate_id") or "").strip()
    }
    checks.append(
        _check(
            len(gate_matrix) == len(dashboard_states),
            "matrix_dashboard_gate_count_match",
            f"matrix={len(gate_matrix)} dashboard={len(dashboard_states)}",
        )
    )
    checks.append(
        _check(
            not dashboard_missing_gate_ids and not dashboard_extra_gate_ids,
            "matrix_dashboard_gate_identity_match",
            f"missing={dashboard_missing_gate_ids} extra={dashboard_extra_gate_ids}",
        )
    )

    provenance_flags = {
        "require_scoreboard_matrix_coverage": config.get("require_scoreboard_matrix_coverage") is True,
        "require_dashboard_scoreboard_agreement": config.get("require_dashboard_scoreboard_agreement") is True,
        "require_green_gate_evidence": config.get("require_green_gate_evidence") is True,
    }
    provenance_policy_ok = (
        config.get("dashboard_is_authority") is True
        and bool(allowed_dashboard_statuses)
        and all(provenance_flags.values())
    )
    checks.append(
        _check(
            provenance_policy_ok,
            "provenance_policy_valid",
            (
                f"dashboard_is_authority={config.get('dashboard_is_authority')} "
                f"allowed_dashboard_statuses={sorted(allowed_dashboard_statuses)} "
                f"flags={provenance_flags}"
            ),
        )
    )
    checks.append(
        _check(
            not scoreboard_missing_gate_ids,
            "scoreboard_matrix_coverage",
            f"missing={scoreboard_missing_gate_ids} extra={scoreboard_extra_gate_ids}",
        )
    )

    invalid_dashboard_states = [
        {"gate_id": gate_id, "raw_state": str(dashboard_states.get(gate_id) or "").strip().upper()}
        for gate_id in sorted(matrix_ids & dashboard_ids)
        if str(dashboard_states.get(gate_id) or "").strip().upper() not in VALID_GATE_STATUSES
        or str(dashboard_states.get(gate_id) or "").strip().upper() == "MISSING"
    ]
    invalid_scoreboard_states = [
        {"gate_id": gate_id, "raw_state": str(scoreboard_rows[gate_id].get("state") or "").strip().upper()}
        for gate_id in sorted(matrix_ids & scoreboard_ids)
        if str(scoreboard_rows[gate_id].get("state") or "").strip().upper() not in VALID_GATE_STATUSES
        or str(scoreboard_rows[gate_id].get("state") or "").strip().upper() == "MISSING"
    ]
    checks.append(
        _check(
            not invalid_dashboard_states and not invalid_scoreboard_states,
            "source_gate_states_valid",
            f"dashboard={invalid_dashboard_states} scoreboard={invalid_scoreboard_states}",
        )
    )

    dashboard_scoreboard_disagreements: list[dict[str, str]] = []
    for gate_id in sorted(matrix_ids & dashboard_ids & scoreboard_ids):
        dashboard_state = _normal_status(dashboard_states.get(gate_id))
        scoreboard_state = _normal_status(scoreboard_rows[gate_id].get("state"))
        if dashboard_state != scoreboard_state:
            dashboard_scoreboard_disagreements.append(
                {
                    "gate_id": gate_id,
                    "dashboard": dashboard_state,
                    "scoreboard": scoreboard_state,
                }
            )
    checks.append(
        _check(
            not dashboard_scoreboard_disagreements,
            "dashboard_scoreboard_agreement",
            f"disagreement_count={len(dashboard_scoreboard_disagreements)}",
        )
    )

    accepted_gate_ids: set[str] = set()
    for gate_id in sorted(matrix_ids - {"G-ACC-01"}):
        state = _normal_status(dashboard_states.get(gate_id))
        blocking = str(gate_by_id.get(gate_id, {}).get("blocking") or "").strip().upper()
        if (blocking == "HARD" and state == "GREEN") or (
            blocking == "ADVISORY" and state in allowed_advisory
        ):
            accepted_gate_ids.add(gate_id)

    green_gates_missing_evidence: list[str] = []
    for gate_id in sorted(accepted_gate_ids):
        row = scoreboard_rows.get(gate_id, {})
        if not str(row.get("evidence") or "").strip() or _parse_source_timestamp(row.get("dated")) is None:
            green_gates_missing_evidence.append(gate_id)
    checks.append(
        _check(
            not green_gates_missing_evidence,
            "green_gate_evidence_complete",
            f"missing_or_invalid={green_gates_missing_evidence}",
        )
    )

    green_gate_freshness_failures: list[dict[str, Any]] = []
    for gate_id in sorted(accepted_gate_ids):
        scoreboard_row = scoreboard_rows.get(gate_id, {})
        observed = _parse_source_timestamp(scoreboard_row.get("dated"))
        if observed is None:
            continue
        freshness_sla = str(gate_by_id.get(gate_id, {}).get("freshness_sla") or "").strip()
        policy, max_age_hours, policy_error = _freshness_sla_limit(freshness_sla)
        age_hours = round((as_of_dt - observed).total_seconds() / 3600.0, 6)
        if age_hours < 0:
            error = "evidence timestamp is in the future"
        elif policy == "NOT_APPLICABLE":
            continue
        elif policy == "DURATION":
            if max_age_hours is not None and age_hours > max_age_hours:
                error = "evidence exceeds freshness_sla"
            else:
                error = ""
        else:
            error = policy_error
        if error:
            green_gate_freshness_failures.append(
                {
                    "gate_id": gate_id,
                    "freshness_sla": freshness_sla,
                    "dated": str(scoreboard_row.get("dated") or ""),
                    "age_hours": age_hours,
                    "max_age_hours": max_age_hours,
                    "error": error,
                }
            )
    checks.append(
        _check(
            not green_gate_freshness_failures,
            "green_gate_freshness_sla",
            f"failure_count={len(green_gate_freshness_failures)}",
        )
    )

    dashboard_status = str(dashboard_meta.get("status") or "").strip().upper()
    checks.append(
        _check(
            dashboard_status in allowed_dashboard_statuses,
            "dashboard_terminal_status",
            f"status={dashboard_status or 'MISSING'} allowed={sorted(allowed_dashboard_statuses)}",
        )
    )

    max_dashboard_age_hours = _positive_finite_hours(config.get("max_dashboard_age_hours"))
    max_scoreboard_age_hours = _positive_finite_hours(config.get("max_scoreboard_age_hours"))
    max_operational_as_of_age_hours = _positive_finite_hours(
        config.get("max_operational_as_of_age_hours")
    )
    freshness_policy_ok = all(
        limit is not None
        for limit in (
            max_dashboard_age_hours,
            max_scoreboard_age_hours,
            max_operational_as_of_age_hours,
        )
    )
    checks.append(
        _check(
            freshness_policy_ok,
            "freshness_policy_valid",
            (
                f"max_dashboard_age_hours={config.get('max_dashboard_age_hours')} "
                f"max_scoreboard_age_hours={config.get('max_scoreboard_age_hours')} "
                "max_operational_as_of_age_hours="
                f"{config.get('max_operational_as_of_age_hours')}"
            ),
        )
    )
    dashboard_freshness = _source_freshness(
        dashboard_meta.get("updated"),
        as_of_dt=as_of_dt,
        max_age_hours=max_dashboard_age_hours,
    )
    scoreboard_freshness = _source_freshness(
        scoreboard_meta.get("last_dated"),
        as_of_dt=as_of_dt,
        max_age_hours=max_scoreboard_age_hours,
    )
    scoreboard_freshness.update(
        {
            "row_number": scoreboard_meta.get("last_row_number"),
            "unparseable_dated_count": sum(
                1
                for value in scoreboard_meta.get("dated_values", [])
                if _parse_source_timestamp(value) is None
            ),
        }
    )
    source_freshness = {
        "dashboard": dashboard_freshness,
        "scoreboard": scoreboard_freshness,
    }
    source_freshness_ok = freshness_policy_ok and all(
        bool(row["ok"]) for row in source_freshness.values()
    )
    checks.append(
        _check(
            dashboard_freshness["ok"],
            "dashboard_source_freshness",
            (
                f"raw={dashboard_freshness['raw']} age_hours={dashboard_freshness['age_hours']} "
                f"max_age_hours={dashboard_freshness['max_age_hours']} "
                f"error={dashboard_freshness['error'] or 'none'}"
            ),
        )
    )
    checks.append(
        _check(
            scoreboard_freshness["ok"],
            "scoreboard_source_freshness",
            (
                f"raw={scoreboard_freshness['raw']} age_hours={scoreboard_freshness['age_hours']} "
                f"max_age_hours={scoreboard_freshness['max_age_hours']} "
                f"row_number={scoreboard_freshness['row_number']} "
                f"error={scoreboard_freshness['error'] or 'none'}"
            ),
        )
    )
    operational_as_of = _source_freshness(
        as_of_dt.isoformat(),
        as_of_dt=evaluation_dt,
        max_age_hours=max_operational_as_of_age_hours,
    )
    checks.append(
        _check(
            operational_as_of["ok"],
            "operational_as_of_window",
            (
                f"as_of={operational_as_of['raw']} "
                f"evaluated_at={evaluation_dt.replace(microsecond=0).isoformat()} "
                f"age_hours={operational_as_of['age_hours']} "
                f"max_age_hours={operational_as_of['max_age_hours']} "
                f"error={operational_as_of['error'] or 'none'}"
            ),
        )
    )

    provenance_ok = (
        provenance_policy_ok
        and not dashboard_missing_gate_ids
        and not dashboard_extra_gate_ids
        and not scoreboard_missing_gate_ids
        and not dashboard_scoreboard_disagreements
        and not green_gates_missing_evidence
        and not invalid_dashboard_states
        and not invalid_scoreboard_states
        and not green_gate_freshness_failures
        and dashboard_status in allowed_dashboard_statuses
    )
    provenance = {
        "ok": provenance_ok,
        "dashboard_missing_gate_ids": dashboard_missing_gate_ids,
        "dashboard_extra_gate_ids": dashboard_extra_gate_ids,
        "scoreboard_missing_gate_ids": scoreboard_missing_gate_ids,
        "scoreboard_extra_gate_ids": scoreboard_extra_gate_ids,
        "dashboard_scoreboard_disagreements": dashboard_scoreboard_disagreements,
        "green_gates_missing_evidence": green_gates_missing_evidence,
        "green_gate_freshness_failures": green_gate_freshness_failures,
        "invalid_dashboard_states": invalid_dashboard_states,
        "invalid_scoreboard_states": invalid_scoreboard_states,
        "dashboard_status": dashboard_status,
        "allowed_dashboard_statuses": sorted(allowed_dashboard_statuses),
    }
    inputs_reconciled = source_freshness_ok and provenance_ok
    status_counts_current = inputs_reconciled and operational_as_of["ok"]
    if status_counts_current:
        status_counts_label = "CURRENT_RECONCILED_INPUTS"
    elif inputs_reconciled and not operational_as_of["ok"]:
        status_counts_label = "HISTORICAL_REPLAY_RECONCILED_INPUTS"
    else:
        status_counts_label = "STALE_OR_UNRECONCILED_INPUT_REPLAY"
    evaluation_mode = "OPERATIONAL" if operational_as_of["ok"] else "HISTORICAL_REPLAY"

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
        "evaluated_at": evaluation_dt.replace(microsecond=0).isoformat(),
        "evaluation_mode": evaluation_mode,
        "operational_as_of": operational_as_of,
        "config_path": str(config_path),
        "gate_matrix_path": str(matrix_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "dashboard_meta": dashboard_meta,
        "scoreboard_meta": {
            "row_count": scoreboard_meta.get("row_count"),
            "last_row_number": scoreboard_meta.get("last_row_number"),
            "last_dated": scoreboard_meta.get("last_dated"),
        },
        "source_freshness": source_freshness,
        "source_freshness_ok": source_freshness_ok,
        "provenance": provenance,
        "inputs_reconciled": inputs_reconciled,
        "status_counts_current": status_counts_current,
        "status_counts_label": status_counts_label,
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
