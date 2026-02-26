#!/usr/bin/env python3
"""Deterministic as-of date resolver for strict daily artifact workflows."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
import re
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DAILY_ROOT = PROJECT_ROOT / "exports" / "daily"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class AsOfResolution:
    as_of: str
    source: str
    daily_report_path: str | None = None


def _validate_iso_day(day: str) -> None:
    if not _DATE_RE.match(day):
        raise ValueError(f"invalid as-of date format: {day}")
    # raises ValueError for impossible dates
    date.fromisoformat(day)


def _is_complete_daily_report(path: Path, *, day_iso: str) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False

    if not isinstance(payload, dict):
        return False
    if str(payload.get("as_of") or "") != day_iso:
        return False
    status = str(payload.get("status") or "").upper()
    if status not in {"GREEN", "RED"}:
        return False
    if not isinstance(payload.get("ok"), bool):
        return False
    return True


def _candidate_complete_days(daily_root: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    if not daily_root.exists():
        return candidates
    for child in sorted(daily_root.iterdir()):
        if not child.is_dir():
            continue
        day_iso = child.name
        if not _DATE_RE.match(day_iso):
            continue
        report_path = child / "daily_ops_report.json"
        if _is_complete_daily_report(report_path, day_iso=day_iso):
            candidates.append((day_iso, report_path))
    candidates.sort(key=lambda row: row[0])
    return candidates


def resolve_as_of_date(
    *,
    project_root: Path,
    explicit_as_of: str | None,
    strict: bool,
    daily_root: Path | None = None,
) -> AsOfResolution:
    root = Path(project_root).resolve()
    report_root = Path(daily_root).resolve() if daily_root else (root / "exports" / "daily")

    if explicit_as_of:
        _validate_iso_day(explicit_as_of)
        report_path = report_root / explicit_as_of / "daily_ops_report.json"
        return AsOfResolution(
            as_of=explicit_as_of,
            source="explicit",
            daily_report_path=str(report_path) if report_path.exists() else None,
        )

    candidates = _candidate_complete_days(report_root)
    if candidates:
        day_iso, report_path = candidates[-1]
        return AsOfResolution(as_of=day_iso, source="latest_complete_day", daily_report_path=str(report_path))

    if strict:
        raise RuntimeError(
            f"no complete as-of date found under strict mode in {report_root} (expected exports/daily/<YYYY-MM-DD>/daily_ops_report.json with valid schema)"
        )

    fallback = date.today().isoformat()
    return AsOfResolution(as_of=fallback, source="today_fallback", daily_report_path=None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve authoritative as-of date")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--daily-root", type=Path, default=DEFAULT_DAILY_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = resolve_as_of_date(
        project_root=args.project_root,
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=args.daily_root,
    )
    payload: dict[str, Any] = asdict(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"as_of={payload['as_of']}")
        print(f"source={payload['source']}")
        if payload.get("daily_report_path"):
            print(f"daily_report_path={payload['daily_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
