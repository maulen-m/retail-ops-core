#!/usr/bin/env python3
"""Publish the G-MET-02 owner dashboard cadence bundle."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time
import glob
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "owner_dashboard_cadence.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_met02_owner_dashboard_cadence"

ITEM_COLUMNS = [
    "cadence",
    "item_id",
    "label",
    "state",
    "source_status",
    "evidence_path",
    "evidence_date",
    "age_days",
    "details",
]


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


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=ALMATY_TZ)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _resolve_project_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _resolve_project_glob(raw: str | Path | None) -> str:
    text = str(raw or "")
    path = Path(text)
    if path.is_absolute():
        return text
    return str(PROJECT_ROOT / text)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _get_nested(payload: dict[str, Any], dotted: str) -> Any:
    cur: Any = payload
    for part in str(dotted).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _latest_match(pattern: str) -> Path | None:
    matches = [Path(path) for path in glob.glob(pattern)]
    matches = [path for path in matches if path.is_file()]
    if not matches:
        return None
    return sorted(matches, key=lambda path: (path.stat().st_mtime, str(path)))[-1]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _load_scoreboard(path: Path) -> tuple[dict[str, str], str]:
    if not path.exists() or not path.is_file():
        return {}, f"missing scoreboard: {path}"
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or "").strip()
            state = str(row.get("state") or "").strip()
            if gate_id:
                states[gate_id] = state
    return states, str(path)


def _source_status_from_payload(payload: dict[str, Any], item: dict[str, Any]) -> str:
    for key in ("gate", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if bool(item.get("pass_when_ok_true")):
        ok = payload.get("ok")
        if ok is True:
            return "OK"
        if ok is False:
            return "RED"
    summary = payload.get("summary")
    if isinstance(summary, dict):
        if summary.get("all_campaigns_dispositioned") is True and int(summary.get("external_actions_required_count") or 0) == 0:
            return "OK"
    return "UNKNOWN"


def _extract_summary(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in fields:
        out[field] = _get_nested(payload, field)
    return out


def _source_date_from_payload(payload: dict[str, Any], fields: list[str]) -> datetime | None:
    for field in fields:
        value = _get_nested(payload, field)
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _evaluate_json_item(item: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    pattern = _resolve_project_glob(item.get("path_glob"))
    latest = _latest_match(pattern)
    base = {
        "cadence": item.get("cadence", ""),
        "item_id": item.get("item_id", ""),
        "label": item.get("label", item.get("item_id", "")),
        "evidence_path": str(latest or ""),
        "evidence_date": "",
        "age_days": "",
        "source_status": "",
        "summary": {},
    }
    if latest is None:
        return {
            **base,
            "state": "PENDING",
            "details": f"missing evidence for glob {item.get('path_glob')}",
        }

    try:
        payload = _load_json(latest)
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "state": "RED", "source_status": "INVALID_JSON", "details": str(exc)}

    source_status = _source_status_from_payload(payload, item)
    source_date = _source_date_from_payload(payload, [str(v) for v in item.get("source_date_fields") or []])
    age_days: int | None = None
    if source_date is not None:
        age_days = (as_of_date - source_date.date()).days
    max_age = item.get("max_age_days")
    age_ok = True
    if max_age is not None:
        age_ok = age_days is not None and 0 <= age_days <= int(max_age)
    allowed = {str(value) for value in item.get("allowed_statuses") or []}
    status_ok = source_status in allowed
    greenish_statuses = {"GREEN", "OK", "PASS"}
    if status_ok and age_ok and source_status in greenish_statuses:
        state = "GREEN"
    elif source_status == "RED":
        state = "RED"
    else:
        state = "ARMED"
    detail_bits = [f"status={source_status}"]
    if max_age is not None:
        detail_bits.append(f"age_days={age_days} max_days={max_age}")
    if not status_ok:
        detail_bits.append("status_not_allowed")
    if not age_ok:
        detail_bits.append("stale_or_missing_date")
    return {
        **base,
        "state": state,
        "source_status": source_status,
        "evidence_date": source_date.date().isoformat() if source_date else "",
        "age_days": age_days if age_days is not None else "",
        "details": "; ".join(detail_bits),
        "summary": _extract_summary(payload, [str(v) for v in item.get("summary_fields") or []]),
    }


def _evaluate_scoreboard_item(item: dict[str, Any], states: dict[str, str], scoreboard_path: Path) -> dict[str, Any]:
    gate_ids = [str(value) for value in item.get("gate_ids") or []]
    allowed = {str(value) for value in item.get("allowed_statuses") or []}
    found = {gate_id: states.get(gate_id, "") for gate_id in gate_ids}
    missing = [gate_id for gate_id, state in found.items() if not state]
    disallowed = [f"{gate_id}={state}" for gate_id, state in found.items() if state and state not in allowed]
    state = "GREEN" if not missing and not disallowed and bool(gate_ids) else "ARMED"
    details = "gates=" + ",".join(f"{gate_id}:{status or 'MISSING'}" for gate_id, status in found.items())
    if missing:
        details += "; missing=" + ",".join(missing)
    if disallowed:
        details += "; not_allowed=" + ",".join(disallowed)
    return {
        "cadence": item.get("cadence", ""),
        "item_id": item.get("item_id", ""),
        "label": item.get("label", item.get("item_id", "")),
        "state": state,
        "source_status": "GREEN" if state == "GREEN" else "ARMED",
        "evidence_path": str(scoreboard_path),
        "evidence_date": "",
        "age_days": "",
        "details": details,
        "summary": found,
    }


def _evaluate_items(config: dict[str, Any], as_of_date: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    item_rows: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    scoreboard_path = _resolve_project_path(config.get("scoreboard_path", ""))
    scoreboard_states, scoreboard_details = _load_scoreboard(scoreboard_path)
    checks.append(_check(bool(scoreboard_states), "scoreboard_loaded", scoreboard_details, gate_count=len(scoreboard_states)))

    for item in config.get("items") or []:
        source_type = str(item.get("source_type") or "").strip()
        if source_type == "latest_json":
            row = _evaluate_json_item(item, as_of_date)
        elif source_type == "scoreboard_gate":
            row = _evaluate_scoreboard_item(item, scoreboard_states, scoreboard_path)
        else:
            row = {
                "cadence": item.get("cadence", ""),
                "item_id": item.get("item_id", ""),
                "label": item.get("label", item.get("item_id", "")),
                "state": "RED",
                "source_status": "UNKNOWN_SOURCE_TYPE",
                "evidence_path": "",
                "evidence_date": "",
                "age_days": "",
                "details": f"unknown source_type={source_type}",
                "summary": {},
            }
        item_rows.append(row)
    return item_rows, checks


def _history_dates(pattern: str, current_as_of: date) -> set[str]:
    dates = {current_as_of.isoformat()}
    for raw in glob.glob(_resolve_project_glob(pattern)):
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("as_of_date", "as_of", "generated_at"):
            parsed = _parse_datetime(payload.get(key))
            if parsed is not None:
                dates.add(parsed.date().isoformat())
                break
    return dates


def _cadence_summary(rows: list[dict[str, Any]], cadences: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for cadence in cadences:
        cadence_rows = [row for row in rows if row.get("cadence") == cadence]
        out[cadence] = {
            "total": len(cadence_rows),
            "green": sum(1 for row in cadence_rows if row.get("state") == "GREEN"),
            "armed": sum(1 for row in cadence_rows if row.get("state") == "ARMED"),
            "pending": sum(1 for row in cadence_rows if row.get("state") == "PENDING"),
            "red": sum(1 for row in cadence_rows if row.get("state") == "RED"),
        }
    return out


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-MET-02 Owner Dashboard Cadence",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Cadence history days: `{report['cadence_history_day_count']}`",
        "",
        "## Cadences",
        "",
        "| cadence | total | green | armed | pending | red |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cadence, summary in report["cadence_summary"].items():
        lines.append(
            f"| `{cadence}` | {summary['total']} | {summary['green']} | {summary['armed']} | "
            f"{summary['pending']} | {summary['red']} |"
        )
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Cadence Blockers", ""])
    if report["cadence_blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["cadence_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Measurement Blockers", ""])
    if report["measurement_blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["measurement_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Items", "", "| cadence | item | state | evidence | details |", "|---|---|---:|---|---|"])
    for row in report["items"]:
        evidence = row.get("evidence_path") or ""
        lines.append(
            f"| `{row['cadence']}` | `{row['item_id']}` | `{row['state']}` | `{evidence}` | {row['details']} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_owner_dashboard_cadence_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    cadence_blockers: list[str] = []
    measurement_blockers: list[str] = []

    config_path = config_path.expanduser().resolve()
    if config_path.exists():
        config = _load_json(config_path)
        checks.append(_check(True, "config_present", str(config_path)))
    else:
        config = {}
        checks.append(_check(False, "config_present", f"missing: {config_path}"))
    checks.append(
        _check(
            config.get("contract_id") == "OWNER_DASHBOARD_CADENCE_V1" and config.get("gate_id") == "G-MET-02",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )
    cadences = [str(value) for value in config.get("cadences") or []]
    checks.append(_check(set(cadences) == {"daily", "weekly", "monthly"}, "cadence_set", ",".join(cadences)))
    checks.append(_check(bool(config.get("items")), "items_configured", f"items={len(config.get('items') or [])}"))

    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    item_rows, item_checks = _evaluate_items(config, as_of_date)
    checks.extend(item_checks)
    summary = _cadence_summary(item_rows, cadences)

    for row in item_rows:
        if row.get("state") != "GREEN":
            cadence_blockers.append(f"{row.get('cadence')}.{row.get('item_id')}: {row.get('details')}")

    history_pattern = str(config.get("history_glob") or "")
    history_dates = _history_dates(history_pattern, as_of_date) if history_pattern else {as_of_date.isoformat()}
    required_history_days = int(config.get("required_history_days_for_green") or 7)
    if len(history_dates) < required_history_days:
        measurement_blockers.append(
            f"cadence_history_days={len(history_dates)} required={required_history_days}"
        )

    for cadence in cadences:
        if summary.get(cadence, {}).get("total", 0) <= 0:
            blockers.append(f"cadence {cadence} has no configured items")

    for row in checks:
        if not row["ok"]:
            blockers.append(f"{row['check']}: {row['details']}")

    if blockers:
        gate = "RED"
    elif cadence_blockers or measurement_blockers:
        gate = "ARMED"
    else:
        gate = "GREEN"

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    items_csv = output_root / "owner_dashboard_cadence_items.csv"
    _write_csv(items_csv, item_rows, ITEM_COLUMNS)

    report: dict[str, Any] = {
        "gate_id": "G-MET-02",
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.replace(microsecond=0).isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "config_path": str(config_path),
        "cadences": cadences,
        "cadence_summary": summary,
        "cadence_history_day_count": len(history_dates),
        "cadence_history_dates": sorted(history_dates),
        "required_history_days_for_green": required_history_days,
        "items": item_rows,
        "checks": checks,
        "blockers": blockers,
        "cadence_blockers": cadence_blockers,
        "measurement_blockers": measurement_blockers,
        "artifacts": {
            "items_csv": str(items_csv),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "owner_dashboard_cadence_report.json"
    md_path = output_root / "owner_dashboard_cadence_report.md"
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

    report = build_owner_dashboard_cadence_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
        if report["cadence_blockers"]:
            print("Cadence blockers:")
            for blocker in report["cadence_blockers"]:
                print(f"  - {blocker}")
        if report["measurement_blockers"]:
            print("Measurement blockers:")
            for blocker in report["measurement_blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
