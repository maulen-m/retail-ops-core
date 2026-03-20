#!/usr/bin/env python3
"""Validate Kaspi archive export pack under explicit API/UI source contracts."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_archive_export_integrity import validate_archive_export_integrity

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "archive_pack_integrity"
DEFAULT_UI_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_ui_pack.json"
DEFAULT_API_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_api_pack.json"


def _parse_date(value: str | None, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"missing required date field: {field}")
    date.fromisoformat(text)
    return text


def _parse_range_from_name(path: Path) -> tuple[str, str] | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})", path.name)
    if not match:
        return None
    return match.group(1), match.group(2)


def _load_anchor_path(anchor_path: Path) -> Path | None:
    if not anchor_path.exists():
        return None
    try:
        payload = json.loads(anchor_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    pack_root = str(payload.get("pack_root") or payload.get("export_root") or "").strip()
    return Path(pack_root).expanduser().resolve() if pack_root else None


def _resolve_export_root(source: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()

    env_key = "AB_KASPI_ARCHIVE_UI_PACK_ROOT" if source == "ui" else "AB_KASPI_ARCHIVE_API_PACK_ROOT"
    env_value = str(os.environ.get(env_key) or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    anchor = _load_anchor_path(DEFAULT_UI_ANCHOR if source == "ui" else DEFAULT_API_ANCHOR)
    if anchor is not None:
        return anchor

    raise RuntimeError(
        f"archive pack root is not configured for source={source}; provide --export-root or set {env_key}"
    )


def _resolve_since_until(
    *,
    export_root: Path,
    since: str | None,
    until: str | None,
) -> tuple[str, str]:
    if since and until:
        return _parse_date(since, field="since"), _parse_date(until, field="until")

    manifest_path = export_root / "manifest.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_since = str(payload.get("since") or "").strip()
        manifest_until = str(payload.get("until") or "").strip()
        if manifest_since and manifest_until:
            return _parse_date(manifest_since, field="manifest.since"), _parse_date(
                manifest_until, field="manifest.until"
            )

    parsed = _parse_range_from_name(export_root)
    if parsed:
        return parsed

    raise RuntimeError("unable to resolve since/until (use --since and --until)")


def validate_kaspi_archive_pack_integrity(
    *,
    source: str,
    export_root: Path | None,
    as_of: str | None,
    since: str | None,
    until: str | None,
    strict: bool,
    output_root: Path,
) -> dict[str, Any]:
    source_norm = str(source).strip().lower()
    if source_norm not in {"api", "ui"}:
        raise RuntimeError("source must be one of: api, ui")

    resolved_root = _resolve_export_root(source_norm, export_root)
    if not resolved_root.exists():
        raise RuntimeError(f"export root not found: {resolved_root}")

    since_iso, until_iso = _resolve_since_until(export_root=resolved_root, since=since, until=until)
    if as_of:
        as_of_iso = _parse_date(as_of, field="as_of")
        if until_iso < as_of_iso:
            raise RuntimeError(
                f"pack until date {until_iso} is older than requested as_of {as_of_iso}"
            )
    else:
        as_of_iso = until_iso

    report = validate_archive_export_integrity(
        export_root=resolved_root,
        since=since_iso,
        until=until_iso,
        strict=False,
        require_status_change_date_for_completed=(source_norm == "ui"),
        window_days=90 if source_norm == "ui" else 14,
        output_root=output_root.resolve() / source_norm / as_of_iso,
    )
    report["source"] = source_norm
    report["contract"] = (
        "KASPI_ARCHIVE_UI_PACK_CONTRACT" if source_norm == "ui" else "KASPI_ARCHIVE_API_PACK_CONTRACT"
    )
    status = str(report.get("status") or "FAIL").upper()
    report["status"] = status
    report["ok"] = status == "PASS"
    report["as_of"] = as_of_iso

    if strict and not report["ok"]:
        raise RuntimeError(
            f"archive pack integrity failed for source={source_norm}: {len(report.get('errors') or [])} error(s)"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate archive pack integrity under API/UI contract")
    parser.add_argument("--source", required=True, choices=["api", "ui"])
    parser.add_argument("--export-root", type=Path, default=None)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--until", type=str, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_kaspi_archive_pack_integrity(
        source=args.source,
        export_root=args.export_root,
        as_of=args.as_of,
        since=args.since,
        until=args.until,
        strict=bool(args.strict),
        output_root=args.output_root,
    )
    artifact_json = (
        Path(args.output_root).resolve()
        / str(args.source).lower()
        / str(report["as_of"])
        / "integrity_report.json"
    )
    artifact_md = artifact_json.with_name("integrity_report.md")
    print(f"archive_pack_integrity_json={artifact_json}")
    print(f"archive_pack_integrity_md={artifact_md}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
