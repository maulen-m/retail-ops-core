#!/usr/bin/env python3
"""Helpers for consuming effective WebUI-vs-DB gate status downstream."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.webui_archive_truth_utils import coerce_iso_date_string


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ledger_identity(path_value: str) -> tuple[str, ...]:
    candidate = Path(str(path_value or "")).expanduser()
    parts = list(candidate.parts)
    if "exports" in parts:
        exports_idx = parts.index("exports")
        relative = tuple(parts[exports_idx + 1 :])
        if len(relative) >= 2 and relative[0] == "order_status_ledger":
            return relative[:2]
    return tuple(part for part in parts[-2:] if part)


def _iter_webui_db_report_paths(output_dir: Path) -> list[Path]:
    candidates: list[Path] = [output_dir / "webui_vs_db_report.json"]
    candidates.extend(sorted(output_dir.glob("*/webui_vs_db_report.json"), reverse=True))
    validation_root = PROJECT_ROOT / "exports" / "validation"
    for folder_name in [
        "webui_archive_single_truth",
        "webui_shipped_authority_recon",
        "workbook_catalog_offer_map_sync",
    ]:
        folder = validation_root / folder_name
        if not folder.exists():
            continue
        for child in sorted(folder.iterdir(), reverse=True):
            candidate = child / "webui_vs_db_report.json"
            if candidate.exists():
                candidates.append(candidate)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def resolve_effective_missing_in_db_orders(
    *,
    output_dir: Path,
    ledger_root: Path,
    start: str,
    end: str,
    projection_meta: dict[str, Any] | None,
) -> tuple[int, dict[str, Any] | None]:
    raw_missing = int((projection_meta or {}).get("missing_in_db_orders", 0) or 0)
    expected_ledger_root = str(ledger_root.resolve())
    expected_ledger_identity = _ledger_identity(expected_ledger_root)
    expected_start = coerce_iso_date_string(start)
    expected_end = coerce_iso_date_string(end)
    for candidate in _iter_webui_db_report_paths(output_dir.resolve()):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        period = payload.get("period") or {}
        actual_start = str(period.get("start") or "")
        actual_end = str(period.get("end") or "")
        try:
            actual_start = coerce_iso_date_string(actual_start)
            actual_end = coerce_iso_date_string(actual_end)
        except Exception:
            continue
        if actual_start != expected_start:
            continue
        if actual_end != expected_end:
            continue
        actual_ledger_root = str(payload.get("ledger_root") or "")
        if actual_ledger_root != expected_ledger_root and _ledger_identity(actual_ledger_root) != expected_ledger_identity:
            continue
        return int(payload.get("missing_in_db_orders", raw_missing) or 0), {
            "path": str(candidate),
            "payload": payload,
        }
    return raw_missing, None
