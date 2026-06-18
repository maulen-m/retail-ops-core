#!/usr/bin/env python3
"""Append a non-PII OD-030 ops incident telemetry row."""

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
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "ops_incident_telemetry.json"

SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b(token|secret|password|bearer)\b"),
    re.compile(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"),
    re.compile(r"(?<!\d)\+?7\d{10}(?!\d)"),
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _now_almaty() -> datetime:
    return datetime.now(ALMATY_TZ).replace(microsecond=0)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug[:40] or "incident"


def _contains_sensitive_text(value: str) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _read_existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {str(row.get("incident_id") or "").strip() for row in csv.DictReader(handle)}


def build_incident_row(
    *,
    config: dict[str, Any],
    incident_id: str | None,
    occurred_at: datetime,
    incident_class: str,
    source_surface: str,
    severity: str,
    resolution_status: str,
    minutes_spent: float,
    evidence_ref: str,
    operator_notes: str,
) -> dict[str, str]:
    rate = float(config.get("placeholder_rate_kzt_per_hour") or 0)
    cost = round(minutes_spent / 60.0 * rate, 2)
    resolved_id = incident_id or f"INC-{occurred_at.strftime('%Y%m%d-%H%M%S')}-{_slug(incident_class)}"
    return {
        "incident_id": resolved_id,
        "occurred_at": occurred_at.isoformat(),
        "incident_class": incident_class.strip(),
        "source_surface": source_surface.strip(),
        "severity": severity.strip(),
        "resolution_status": resolution_status.strip(),
        "minutes_spent": _format_number(minutes_spent),
        "cost_rate_kzt_per_hour": _format_number(rate),
        "cost_basis_mark": str(config.get("cost_basis_mark") or "ASSUMED"),
        "cost_kzt": f"{cost:.2f}",
        "owner_decision_id": str(config.get("owner_decision_id") or "OD-030"),
        "gate_id": str(config.get("gate_id") or "G-OPS-01"),
        "evidence_ref": evidence_ref.strip(),
        "operator_notes": operator_notes.strip(),
    }


def validate_row(row: dict[str, str], *, required_columns: list[str], log_path: Path) -> list[str]:
    errors: list[str] = []
    for col in required_columns:
        if not str(row.get(col) or "").strip():
            errors.append(f"{col} is required")
    minutes = float(row.get("minutes_spent") or 0)
    if minutes <= 0:
        errors.append("minutes_spent must be positive")
    if row["severity"] not in {"low", "medium", "high", "blocker"}:
        errors.append("severity must be low, medium, high, or blocker")
    if _contains_sensitive_text(row.get("evidence_ref", "")) or _contains_sensitive_text(row.get("operator_notes", "")):
        errors.append("evidence_ref/operator_notes contain forbidden sensitive text")
    if row["incident_id"] in _read_existing_ids(log_path):
        errors.append(f"incident_id already exists: {row['incident_id']}")
    return errors


def append_row(path: Path, row: dict[str, str], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one OD-030 ops incident telemetry row.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--incident-id")
    parser.add_argument("--occurred-at")
    parser.add_argument("--incident-class", required=True)
    parser.add_argument("--source-surface", required=True)
    parser.add_argument("--severity", default="medium")
    parser.add_argument("--resolution-status", default="observed")
    parser.add_argument("--minutes-spent", type=float, required=True)
    parser.add_argument("--evidence-ref", default="not_recorded")
    parser.add_argument("--operator-notes", default="non_pii_summary_not_recorded")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    config = _load_json(args.config)
    occurred_at = datetime.fromisoformat(args.occurred_at) if args.occurred_at else _now_almaty()
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=ALMATY_TZ)
    log_path = _resolve_project_path(args.log_path or config.get("log_path") or ".claude/ops_incident_telemetry.csv")
    required_columns = [str(col) for col in config.get("required_columns") or []]
    row = build_incident_row(
        config=config,
        incident_id=args.incident_id,
        occurred_at=occurred_at,
        incident_class=args.incident_class,
        source_surface=args.source_surface,
        severity=args.severity,
        resolution_status=args.resolution_status,
        minutes_spent=args.minutes_spent,
        evidence_ref=args.evidence_ref,
        operator_notes=args.operator_notes,
    )
    errors = validate_row(row, required_columns=required_columns, log_path=log_path)
    result = {
        "ok": not errors,
        "write_applied": bool(args.apply and not errors),
        "log_path": str(log_path),
        "row": row,
        "errors": errors,
    }
    if not errors and args.apply:
        append_row(log_path, row, required_columns)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
