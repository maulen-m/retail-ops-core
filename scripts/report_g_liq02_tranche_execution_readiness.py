#!/usr/bin/env python3
"""Publish the G-LIQ-02 liquidation tranche-1 execution readiness report."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "liquidation_tranche1_execution.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_liq02_tranche_execution_readiness"

CANDIDATE_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "tier",
    "planned_units",
    "segment",
    "segment_reason",
    "goods_basis_kzt_known_cogs",
    "floor_version",
    "stock_confidence",
    "rollback_price",
    "owner_decision_id",
    "source_artifact",
    "status",
    "blockers",
    "notes",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [{str(k or ""): str(v or "") for k, v in row.items()} for row in reader]
        return rows, list(reader.fieldnames or [])


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{column: row.get(column, "") for column in columns} for row in rows])


def _as_int(raw: Any) -> int:
    try:
        return int(float(str(raw or "").strip() or "0"))
    except ValueError:
        return 0


def _as_float(raw: Any) -> float:
    try:
        return float(str(raw or "").strip() or "0")
    except ValueError:
        return 0.0


def _truthy(raw: Any) -> bool:
    return str(raw or "").strip().casefold() in {"1", "true", "yes", "y"}


def _status(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _load_scoreboard(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            state = str(row.get("status") or row.get("state") or "").strip().upper()
            if gate_id and state:
                states[gate_id] = state
    return states


def _load_dashboard_gate_states(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    match = re.search(r"window\.GP\s*=\s*(\{.*\});\s*$", text, re.S)
    if not match:
        return {}
    payload = json.loads(match.group(1))
    states: dict[str, str] = {}
    for row in payload.get("gates", []):
        gate_id = str(row.get("id") or "").strip()
        state = str(row.get("status") or "").strip().upper()
        if gate_id and state:
            states[gate_id] = state
    return states


def _check(ok: bool, check_id: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": check_id, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _missing_fields(row: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if not str(row.get(field) or "").strip()]


def _build_candidates(
    rows: list[dict[str, str]],
    *,
    segment_map_path: Path,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    candidate_segments = {str(value) for value in config.get("candidate_segments") or []}
    require_prior_canonical = bool(config.get("require_prior_canonical_tranche1", False))
    tranche_id = str(config.get("tranche_id") or "T1")
    owner_decision_id = str(config.get("owner_decision_id") or "OD-011")
    floor_version = str(config.get("floor_version") or "v7")
    default_tier = str(config.get("default_tier") or "T1")
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not _truthy(row.get("tranche_sizing_allowed")):
            continue
        segment = str(row.get("segment") or "").strip()
        if candidate_segments and segment not in candidate_segments:
            continue
        if require_prior_canonical and not _truthy(row.get("prior_canonical_tranche1")):
            continue
        stock_units = _as_int(row.get("stock_units"))
        if stock_units <= 0:
            continue
        goods_basis = _as_float(row.get("goods_basis_kzt_known_cogs"))
        blockers: list[str] = []
        if goods_basis <= 0:
            blockers.append("missing_known_goods_basis")
        blockers.append("not_executed")
        blockers.append("price_stopline_gate_required")
        candidates.append(
            {
                "tranche_id": tranche_id,
                "sku_key": str(row.get("sku_key") or "").strip(),
                "size": "ALL",
                "tier": default_tier,
                "planned_units": stock_units,
                "segment": segment,
                "segment_reason": str(row.get("segment_reason") or "").strip(),
                "goods_basis_kzt_known_cogs": f"{goods_basis:.2f}",
                "floor_version": floor_version,
                "stock_confidence": "GREEN",
                "rollback_price": "PENDING_EXECUTION_READBACK",
                "owner_decision_id": owner_decision_id,
                "source_artifact": str(segment_map_path),
                "status": "PLANNED_NOT_EXECUTED",
                "blockers": ";".join(blockers),
                "notes": "local readiness row only; no upload/apply/readback",
            }
        )
    return candidates


def _active_ledger_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if _status(row.get("status")) in {"ACTIVE", "OPEN", "LIVE"}]


def _applied_manifest_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if _status(row.get("status")) in {"APPLIED", "VERIFIED", "GREEN"}]


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-LIQ-02 Tranche Execution Readiness Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Passed checks: {report['passed_checks']}/{report['total_checks']}",
        "",
        "## Summary",
        "",
        f"- candidate_row_count: {report['candidate_row_count']}",
        f"- planned_units: {report['candidate_planned_units']}",
        f"- planned_goods_basis_kzt_known_cogs: {report['candidate_goods_basis_kzt_known_cogs']}",
        f"- executed_active_ledger_rows: {report['executed_active_ledger_rows']}",
        f"- applied_readback_rows: {report['applied_readback_rows']}",
        "",
        "## Checks",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_tranche_execution_readiness_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    config = _load_json(config_path)
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    summary_path = _resolve_path(config["register_summary_path"])
    segment_map_path = _resolve_path(config["segment_map_path"])
    ledger_path = _resolve_path(config["tranche_ledger_path"])
    manifest_path = _resolve_path(config["apply_readback_manifest_path"])
    generated_at = _now_almaty()
    run_id = generated_at.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fatal_errors: list[str] = []
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    gate_states = _load_dashboard_gate_states(dashboard_path)
    gate_states.update(_load_scoreboard(scoreboard_path))
    dependency_gates = [str(value) for value in config.get("dependency_gates") or []]
    price_stopline_gates = [str(value) for value in config.get("price_stopline_gates") or []]
    dependency_statuses = {gate_id: gate_states.get(gate_id, "MISSING") for gate_id in dependency_gates}
    stopline_statuses = {gate_id: gate_states.get(gate_id, "MISSING") for gate_id in price_stopline_gates}

    if not summary_path.exists():
        fatal_errors.append("missing_register_summary")
        summary: dict[str, Any] = {}
    else:
        summary = _load_json(summary_path)
    if not segment_map_path.exists():
        fatal_errors.append("missing_segment_map")
    segment_rows, segment_columns = _load_csv(segment_map_path)
    ledger_rows, ledger_columns = _load_csv(ledger_path)
    manifest_rows, _manifest_columns = _load_csv(manifest_path)

    candidates = _build_candidates(segment_rows, segment_map_path=segment_map_path, config=config) if segment_rows else []
    if segment_map_path.exists() and not candidates:
        fatal_errors.append("no_candidate_rows")
    candidate_path = out_dir / "tranche1_candidate_rows.csv"
    _write_csv(candidate_path, candidates, CANDIDATE_COLUMNS)

    active_ledger = _active_ledger_rows(ledger_rows)
    applied_manifest = _applied_manifest_rows(manifest_rows)
    required_candidate_fields = [str(value) for value in config.get("required_candidate_fields") or []]
    required_execution_fields = [str(value) for value in config.get("required_execution_fields") or []]
    candidate_missing = [
        {"row": idx, "missing": _missing_fields(row, required_candidate_fields)}
        for idx, row in enumerate(candidates, start=2)
        if _missing_fields(row, required_candidate_fields)
    ]
    ledger_missing = [
        {"row": idx, "missing": _missing_fields(row, required_execution_fields)}
        for idx, row in enumerate(active_ledger, start=2)
        if _missing_fields(row, required_execution_fields)
    ]

    dependency_missing = {gate: state for gate, state in dependency_statuses.items() if state != "GREEN"}
    checks.append(
        _check(
            not dependency_missing,
            "dependency_stack_green",
            "missing=" + ",".join(f"{gate}={state}" for gate, state in dependency_missing.items())
            if dependency_missing
            else "all dependencies GREEN",
            dependency_statuses=dependency_statuses,
        )
    )
    for gate, state in dependency_missing.items():
        blockers.append(f"dependency_gate_not_green:{gate}={state}")

    red_stoplines = {gate: state for gate, state in stopline_statuses.items() if state == "RED"}
    checks.append(
        _check(
            not red_stoplines,
            "price_stoplines_clear",
            "red=" + ",".join(f"{gate}={state}" for gate, state in red_stoplines.items())
            if red_stoplines
            else "none red",
            stopline_statuses=stopline_statuses,
        )
    )
    for gate, state in red_stoplines.items():
        blockers.append(f"price_stopline_red:{gate}={state}")

    register_ready = summary_path.exists() and segment_map_path.exists() and str(summary.get("gate") or "").upper() == "GREEN"
    checks.append(
        _check(
            register_ready,
            "register_artifacts_green",
            f"summary_exists={summary_path.exists()} segment_exists={segment_map_path.exists()} summary_gate={summary.get('gate')}",
        )
    )
    if not register_ready:
        blockers.append("liquidation_register_not_green_or_missing")

    candidates_ok = bool(candidates) and not candidate_missing
    checks.append(
        _check(
            candidates_ok,
            "candidate_rows_built",
            f"candidate_rows={len(candidates)} missing_required_rows={len(candidate_missing)}",
            candidate_csv=str(candidate_path),
        )
    )
    if not candidates_ok:
        blockers.append("candidate_rows_missing_or_incomplete")

    executed_ok = bool(active_ledger) and not ledger_missing
    checks.append(
        _check(
            executed_ok,
            "executed_ledger_rows_complete",
            f"active_ledger_rows={len(active_ledger)} missing_required_rows={len(ledger_missing)}",
            ledger_path=str(ledger_path),
        )
    )
    if not executed_ok:
        blockers.append("executed_tranche_ledger_missing_or_incomplete")

    apply_ok = bool(applied_manifest)
    checks.append(
        _check(
            apply_ok,
            "apply_readback_manifest_present",
            f"applied_readback_rows={len(applied_manifest)} manifest_path={manifest_path}",
        )
    )
    if not apply_ok:
        blockers.append("apply_readback_manifest_missing_applied_rows")

    if fatal_errors:
        gate = "RED"
    elif all(row["ok"] for row in checks):
        gate = "GREEN"
    else:
        gate = "ARMED"

    candidate_units = sum(_as_int(row.get("planned_units")) for row in candidates)
    candidate_goods_basis = round(sum(_as_float(row.get("goods_basis_kzt_known_cogs")) for row in candidates), 2)
    json_path = out_dir / "tranche_execution_readiness_report.json"
    md_path = out_dir / "tranche_execution_readiness_report.md"
    report: dict[str, Any] = {
        "contract_id": config.get("contract_id", "LIQUIDATION_TRANCHE1_EXECUTION_READINESS_V1"),
        "gate_id": config.get("gate_id", "G-LIQ-02"),
        "gate": gate,
        "generated_at": generated_at,
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "register_summary_path": str(summary_path),
        "segment_map_path": str(segment_map_path),
        "segment_map_columns": segment_columns,
        "tranche_ledger_path": str(ledger_path),
        "tranche_ledger_columns": ledger_columns,
        "apply_readback_manifest_path": str(manifest_path),
        "dependency_statuses": dependency_statuses,
        "price_stopline_statuses": stopline_statuses,
        "candidate_csv": str(candidate_path),
        "candidate_row_count": len(candidates),
        "candidate_planned_units": candidate_units,
        "candidate_goods_basis_kzt_known_cogs": candidate_goods_basis,
        "candidate_missing_required_rows": candidate_missing,
        "executed_active_ledger_rows": len(active_ledger),
        "executed_missing_required_rows": ledger_missing,
        "applied_readback_rows": len(applied_manifest),
        "fatal_errors": fatal_errors,
        "blockers": blockers,
        "checks": checks,
        "passed_checks": sum(1 for row in checks if row["ok"]),
        "total_checks": len(checks),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "external_writes_performed": False,
    }
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true", help="Return non-zero only when the gate is RED.")
    args = parser.parse_args(argv)

    report = build_tranche_execution_readiness_report(config_path=args.config, output_root=args.output_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
