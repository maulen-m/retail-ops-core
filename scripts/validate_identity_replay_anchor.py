#!/usr/bin/env python3
"""Validate replay-mode identity inputs against the latest proven stabilization anchor."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import StatusError, parse_iso_date, write_json

DEFAULT_IDENTITY_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_replay_anchor"

REQUIRED_FILES = (
    "offer_identity_reference.csv",
    "unresolved_rows.csv",
    "source_manifest.json",
    "import_report.json",
    "validate_external_snapshot_parity.json",
    "validate_recent_identity_coverage.json",
    "validate_order_entries_freshness.json",
)
STATUS_FILES = (
    "import_report.json",
    "validate_external_snapshot_parity.json",
    "validate_recent_identity_coverage.json",
    "validate_order_entries_freshness.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive failure path
        raise StatusError(
            "IDENTITY_REPLAY_ANCHOR_MISSING",
            f"invalid JSON in replay identity anchor file: {path}",
        ) from exc
    if not isinstance(payload, dict):
        raise StatusError(
            "IDENTITY_REPLAY_ANCHOR_MISSING",
            f"identity replay anchor payload must be an object: {path}",
        )
    return payload


def _resolve_anchor_candidates(identity_root: Path, as_of: date) -> list[tuple[str, Path]]:
    candidates: list[tuple[date, Path]] = []
    if identity_root.exists():
        for child in sorted(identity_root.iterdir()):
            if not child.is_dir():
                continue
            try:
                anchor_date = date.fromisoformat(child.name)
            except ValueError:
                continue
            if anchor_date <= as_of:
                candidates.append((anchor_date, child.resolve()))
    if not candidates:
        raise StatusError(
            "IDENTITY_REPLAY_ANCHOR_MISSING",
            f"no identity stabilization anchor found on or before {as_of.isoformat()} under {identity_root}",
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(anchor_date.isoformat(), anchor_path) for anchor_date, anchor_path in candidates]


def _failure_payload(*, as_of: date, identity_root: Path, code: str, message: str) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "identity_root": str(identity_root),
        "status": code,
        "error_code": code,
        "message": message,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Identity Replay Anchor",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- identity_root: `{payload['identity_root']}`",
    ]
    if payload.get("anchor_date"):
        lines.append(f"- anchor_date: `{payload['anchor_date']}`")
    if payload.get("anchor_dir"):
        lines.append(f"- anchor_dir: `{payload['anchor_dir']}`")
    if payload.get("latest_snapshot_date"):
        lines.append(f"- latest_snapshot_date: `{payload['latest_snapshot_date']}`")
    if payload.get("snapshot_lag_days") is not None:
        lines.append(f"- snapshot_lag_days: `{payload['snapshot_lag_days']}`")
    if payload.get("message"):
        lines.append(f"- message: `{payload['message']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_identity_replay_anchor(
    *,
    as_of: str | date,
    identity_root: Path,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    del strict  # explicit in CLI surface; function is always fail-closed
    as_of_date = parse_iso_date(as_of, field="as_of") if isinstance(as_of, str) else as_of
    resolved_identity_root = identity_root.resolve()
    candidates = _resolve_anchor_candidates(resolved_identity_root, as_of_date)
    selected_error: StatusError | None = None
    skipped_candidates: list[dict[str, str]] = []

    payload: dict[str, Any] | None = None
    for anchor_date, anchor_dir in candidates:
        try:
            missing = [name for name in REQUIRED_FILES if not (anchor_dir / name).exists()]
            if missing:
                raise StatusError(
                    "IDENTITY_REPLAY_ANCHOR_MISSING",
                    f"identity replay anchor {anchor_date} missing required files: {', '.join(missing)}",
                )

            manifest = _load_json(anchor_dir / "source_manifest.json")
            latest_snapshot_raw = str(manifest.get("latest_snapshot_date") or "").strip()
            if not latest_snapshot_raw:
                raise StatusError(
                    "IDENTITY_REPLAY_ANCHOR_MISSING",
                    f"identity replay anchor {anchor_date} missing latest_snapshot_date in source_manifest.json",
                )
            latest_snapshot_date = parse_iso_date(latest_snapshot_raw, field="latest_snapshot_date")

            checked_reports: dict[str, dict[str, str]] = {}
            for name in STATUS_FILES:
                report_payload = _load_json(anchor_dir / name)
                status = str(report_payload.get("status") or "").strip()
                error_code = str(report_payload.get("error_code") or "").strip()
                checked_reports[name] = {
                    "status": status,
                    "error_code": error_code,
                }
                if status != "PASS":
                    raise StatusError(
                        "IDENTITY_REPLAY_ANCHOR_FAIL",
                        f"identity replay anchor {anchor_date} is not proven clean: {name} -> {status or error_code or 'UNKNOWN'}",
                    )

            payload = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "as_of": as_of_date.isoformat(),
                "identity_root": str(resolved_identity_root),
                "anchor_date": anchor_date,
                "anchor_dir": str(anchor_dir),
                "latest_snapshot_date": latest_snapshot_date.isoformat(),
                "snapshot_lag_days": int((as_of_date - latest_snapshot_date).days),
                "status": "PASS",
                "error_code": "",
                "checked_reports": checked_reports,
                "skipped_candidates": skipped_candidates,
            }
            break
        except StatusError as exc:
            if selected_error is None:
                selected_error = exc
            skipped_candidates.append(
                {
                    "anchor_date": anchor_date,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )

    if payload is None:
        assert selected_error is not None
        raise selected_error

    out_dir = output_root.resolve() / as_of_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "validate_identity_replay_anchor.json", payload)
    _write_markdown(out_dir / "validate_identity_replay_anchor.md", payload)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate replay identity against the latest proven stabilization anchor")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--identity-root", type=Path, default=DEFAULT_IDENTITY_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    as_of_date = parse_iso_date(args.as_of, field="as_of")
    output_dir = args.output_root.resolve() / as_of_date.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = validate_identity_replay_anchor(
            as_of=as_of_date,
            identity_root=args.identity_root,
            output_root=args.output_root,
            strict=bool(args.strict),
        )
    except StatusError as exc:
        payload = _failure_payload(
            as_of=as_of_date,
            identity_root=args.identity_root.resolve(),
            code=exc.code,
            message=exc.message,
        )
        write_json(output_dir / "validate_identity_replay_anchor.json", payload)
        _write_markdown(output_dir / "validate_identity_replay_anchor.md", payload)
        print(f"status={exc.code}")
        print(f"error_code={exc.code}")
        print(f"message={exc.message}")
        return 1 if args.strict else 0

    print(f"status={payload['status']}")
    print(f"anchor_date={payload['anchor_date']}")
    print(f"latest_snapshot_date={payload['latest_snapshot_date']}")
    print(f"snapshot_lag_days={payload['snapshot_lag_days']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
