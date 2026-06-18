#!/usr/bin/env python3
"""Publish the G-LIQ-03 liquidation release-velocity and ladder discipline report."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "liquidation_release_velocity.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"

TRANCHE_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "tier",
    "release_date",
    "initial_units",
    "released_units",
    "sold_units",
    "current_units",
    "floor_version",
    "stock_confidence",
    "rollback_price",
    "owner_decision_id",
    "stop_rule_status",
    "escalation_decision",
    "status",
    "notes",
]

LEAD_MAP_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "lead_store",
    "allowed_follower_stores",
    "effective_from",
    "source_artifact",
    "status",
    "owner_decision_id",
    "notes",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(raw: str | None) -> datetime:
    text = str(raw or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _parse_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _upper(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [{str(k or ""): str(v or "") for k, v in row.items()} for row in reader]
    return rows, columns


def _load_scoreboard(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            status = str(row.get("status") or row.get("state") or "").strip().upper()
            if gate_id and status:
                states[gate_id] = status
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
        status = str(row.get("status") or "").strip().upper()
        if gate_id and status:
            states[gate_id] = status
    return states


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _lead_keys(rows: list[dict[str, str]]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for row in rows:
        if _upper(row.get("status")) != "ACTIVE":
            continue
        keys.add(
            (
                str(row.get("tranche_id") or "").strip(),
                str(row.get("sku_key") or "").strip(),
                str(row.get("size") or "").strip() or "ALL",
            )
        )
    return keys


def _is_active_tranche(row: dict[str, str]) -> bool:
    status = _upper(row.get("status"))
    return status in {"ACTIVE", "OPEN", "LIVE"}


def _row_review(
    row: dict[str, str],
    *,
    as_of_date: date,
    required_fields: list[str],
    dwell_days: dict[str, int],
    min_sell_through: float,
    parked_tiers: set[str],
    lead_keys: set[tuple[str, str, str]],
) -> dict[str, Any]:
    tranche_id = str(row.get("tranche_id") or "").strip()
    sku_key = str(row.get("sku_key") or "").strip()
    size = str(row.get("size") or "").strip() or "ALL"
    tier = _upper(row.get("tier"))
    release_date = _parse_date(row.get("release_date"))
    released_units = _as_int(row.get("released_units"))
    sold_units = _as_int(row.get("sold_units"))
    sell_through = round((sold_units / released_units) * 100.0, 2) if released_units > 0 else 0.0
    days_since_release = (as_of_date - release_date).days if release_date else None
    dwell = int(dwell_days.get(tier, 0))
    escalation = _upper(row.get("escalation_decision"))
    stop_status = _upper(row.get("stop_rule_status"))
    violations: list[str] = []
    missing = [field for field in required_fields if not str(row.get(field) or "").strip()]
    if missing:
        violations.append("missing_required_fields:" + ",".join(missing))
    if tier in parked_tiers:
        violations.append("parked_tier_active")
    if released_units <= 0:
        violations.append("released_units_not_positive")
    if sold_units < 0 or sold_units > released_units:
        violations.append("sold_units_out_of_bounds")
    if release_date is None:
        violations.append("release_date_invalid")
    if (tranche_id, sku_key, size) not in lead_keys and (tranche_id, sku_key, "ALL") not in lead_keys:
        violations.append("missing_active_lead_store_map_row")
    if days_since_release is not None and dwell > 0 and days_since_release >= dwell:
        if sell_through < min_sell_through and (
            "ADVANCE" in escalation or "ESCALATE" in escalation or stop_status in {"OPEN", ""}
        ):
            violations.append("under_min_sellthrough_escalated")
    return {
        "tranche_id": tranche_id,
        "sku_key": sku_key,
        "size": size,
        "tier": tier,
        "release_date": release_date.isoformat() if release_date else "",
        "released_units": released_units,
        "sold_units": sold_units,
        "current_units": _as_int(row.get("current_units")),
        "sell_through_pct": sell_through,
        "days_since_release": "" if days_since_release is None else days_since_release,
        "dwell_days": dwell,
        "stop_rule_status": stop_status,
        "escalation_decision": escalation,
        "status": "VIOLATION" if violations else "OK",
        "violation_reasons": ";".join(violations),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-LIQ-03 Release Velocity Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Liquidation execution gate: {report['liquidation_gate']}={report['liquidation_gate_status']}",
        "",
        "## Summary",
        "",
        f"- active_tranche_rows: {report['active_tranche_rows']}",
        f"- active_lead_store_rows: {report['active_lead_store_rows']}",
        f"- weighted_sell_through_pct: {report['weighted_sell_through_pct']}",
        f"- rule_violation_count: {report['rule_violation_count']}",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Violations", ""])
    if report["rule_violations"]:
        for row in report["rule_violations"]:
            lines.append(f"- {row['tranche_id']} {row['sku_key']} {row['size']}: {row['violation_reasons']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_release_velocity_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    generated_at = _now_almaty()
    run_label = generated_at[:19].replace("-", "").replace(":", "").replace("T", "_")
    out_dir = output_root / f"g_liq02_release_velocity_{run_label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()

    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    register_summary_path = _resolve_path(config.get("liquidation_register_summary", ""))
    segment_map_path = _resolve_path(config.get("liquidation_segment_map_csv", ""))
    tranche_path = _resolve_path(config["tranche_ledger_path"])
    lead_map_path = _resolve_path(config["lead_store_map_csv"])
    liquidation_gate = str(config.get("liquidation_execution_gate", "G-LIQ-02"))
    required_fields = [str(value) for value in config.get("required_row_fields", [])]
    dwell_days = {str(key).upper(): int(value) for key, value in config.get("tier_dwell_days", {}).items()}
    min_sell_through = _as_float(config.get("min_sell_through_pct_for_escalation", 3.0))
    parked_tiers = {_upper(value) for value in config.get("parked_tiers", [])}

    gate_states = _load_dashboard_gate_states(dashboard_path)
    gate_states.update(_load_scoreboard(scoreboard_path))
    liquidation_status = gate_states.get(liquidation_gate, "MISSING")

    tranche_rows, tranche_columns = _load_csv(tranche_path)
    lead_rows, lead_columns = _load_csv(lead_map_path)
    active_tranche_rows = [row for row in tranche_rows if _is_active_tranche(row)]
    active_lead_rows = [row for row in lead_rows if _upper(row.get("status")) == "ACTIVE"]
    leads = _lead_keys(lead_rows)

    blockers: list[str] = []
    fatal_errors: list[str] = []
    missing_tranche_columns = [column for column in TRANCHE_COLUMNS if column not in tranche_columns]
    missing_lead_columns = [column for column in LEAD_MAP_COLUMNS if column not in lead_columns]
    if missing_tranche_columns:
        fatal_errors.append("missing_tranche_columns:" + ",".join(missing_tranche_columns))
    if missing_lead_columns:
        fatal_errors.append("missing_lead_map_columns:" + ",".join(missing_lead_columns))
    if not register_summary_path.exists():
        blockers.append(f"liquidation_register_summary_missing:{register_summary_path}")
    if not segment_map_path.exists():
        blockers.append(f"liquidation_segment_map_missing:{segment_map_path}")
    if liquidation_status != "GREEN":
        blockers.append(f"liquidation_gate_not_green:{liquidation_gate}={liquidation_status}")
    if not active_tranche_rows:
        blockers.append("active_tranche_rows=0")

    review_rows = [
        _row_review(
            row,
            as_of_date=as_of_date,
            required_fields=required_fields,
            dwell_days=dwell_days,
            min_sell_through=min_sell_through,
            parked_tiers=parked_tiers,
            lead_keys=leads,
        )
        for row in active_tranche_rows
    ]
    violations = [row for row in review_rows if row["status"] == "VIOLATION"]
    total_released = sum(int(row["released_units"]) for row in review_rows)
    total_sold = sum(int(row["sold_units"]) for row in review_rows)
    weighted_sell_through = round((total_sold / total_released) * 100.0, 2) if total_released > 0 else 0.0

    if fatal_errors or violations:
        gate = "RED"
    elif blockers:
        gate = "ARMED"
    else:
        gate = "GREEN"

    rows_csv = out_dir / "release_velocity_rows.csv"
    _write_csv(
        rows_csv,
        review_rows,
        [
            "tranche_id",
            "sku_key",
            "size",
            "tier",
            "release_date",
            "released_units",
            "sold_units",
            "current_units",
            "sell_through_pct",
            "days_since_release",
            "dwell_days",
            "stop_rule_status",
            "escalation_decision",
            "status",
            "violation_reasons",
        ],
    )

    report: dict[str, Any] = {
        "contract_id": config.get("contract_id"),
        "gate_id": config.get("gate_id", "G-LIQ-03"),
        "gate": gate,
        "generated_at": generated_at,
        "as_of": as_of_dt.isoformat(),
        "config_path": str(config_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "liquidation_register_summary": str(register_summary_path),
        "liquidation_segment_map_csv": str(segment_map_path),
        "tranche_ledger_path": str(tranche_path),
        "lead_store_map_csv": str(lead_map_path),
        "liquidation_gate": liquidation_gate,
        "liquidation_gate_status": liquidation_status,
        "active_tranche_rows": len(active_tranche_rows),
        "active_lead_store_rows": len(active_lead_rows),
        "total_released_units": total_released,
        "total_sold_units": total_sold,
        "weighted_sell_through_pct": weighted_sell_through,
        "rule_violation_count": len(violations),
        "rule_violations": violations,
        "blockers": blockers,
        "fatal_errors": fatal_errors,
        "release_velocity_rows_csv": str(rows_csv),
        "external_writes_performed": False,
    }
    json_path = out_dir / "release_velocity_report.json"
    md_path = out_dir / "release_velocity_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = build_release_velocity_report(
        config_path=args.config,
        output_root=args.output_root,
        as_of=args.as_of or None,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
