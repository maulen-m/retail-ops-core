#!/usr/bin/env python3
"""Refresh Kaspi UI archive pack from deterministic seed files and optional anchor update."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_kaspi_archive_ui_history import DEFAULT_STORES, export_kaspi_archive_ui_history
from scripts.validate_kaspi_archive_pack_integrity import validate_kaspi_archive_pack_integrity

DEFAULT_ANCHOR_PATH = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_ui_pack.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports"
DEFAULT_VALIDATION_ROOT = PROJECT_ROOT / "exports" / "validation" / "archive_ui_pack_refresh"


class UiPackRefreshError(RuntimeError):
    """Raised when UI pack refresh fails."""


def _collect_seed_files(*, seed_root: Path | None, anchor_path: Path) -> list[Path]:
    files: list[Path] = []
    if seed_root is not None:
        root = seed_root.expanduser().resolve()
        if not root.exists():
            raise UiPackRefreshError(f"seed root not found: {root}")
        files.extend(sorted(root.glob("*.xlsx")))

    if not files and anchor_path.exists():
        payload = json.loads(anchor_path.read_text(encoding="utf-8"))
        pack_root = str(payload.get("pack_root") or "").strip()
        if pack_root:
            root = Path(pack_root).expanduser().resolve()
            for store in DEFAULT_STORES:
                files.extend(sorted((root / f"store_{store}" / "raw").glob("*.xlsx")))

    # last fallback via env for unattended runs
    if not files:
        env_root = str(os.environ.get("AB_KASPI_UI_SEED_DIR") or "").strip()
        if env_root:
            files.extend(sorted(Path(env_root).expanduser().resolve().glob("*.xlsx")))

    uniq: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved not in seen and resolved.exists():
            uniq.append(resolved)
            seen.add(resolved)
    return uniq


def refresh_kaspi_archive_ui_pack(
    *,
    as_of: date,
    since: date,
    output_root: Path,
    validation_root: Path,
    anchor_path: Path,
    seed_root: Path | None,
    strict: bool,
    apply: bool,
) -> dict[str, Any]:
    if since > as_of:
        raise UiPackRefreshError("since must be <= as_of")

    if apply and os.environ.get("ENABLE_ANCHOR_APPLY") != "1":
        raise UiPackRefreshError("ENABLE_ANCHOR_APPLY=1 is required with --apply")

    seeds = _collect_seed_files(seed_root=seed_root, anchor_path=anchor_path)
    if not seeds:
        raise UiPackRefreshError(
            "no UI seed files found. Provide --seed-root or set AB_KASPI_UI_SEED_DIR or ensure anchor pack has store_*/raw/*.xlsx"
        )

    export_report = export_kaspi_archive_ui_history(
        since=since,
        until=as_of,
        output_root=output_root.resolve(),
        strict=bool(strict),
        stores=list(DEFAULT_STORES),
        seed_xlsx_files=seeds,
        resume_manifest=None,
    )

    pack_root = Path(export_report["output_dir"]).resolve()
    integrity = validate_kaspi_archive_pack_integrity(
        source="ui",
        export_root=pack_root,
        as_of=as_of.isoformat(),
        since=since.isoformat(),
        until=as_of.isoformat(),
        strict=bool(strict),
        output_root=PROJECT_ROOT / "exports" / "validation" / "archive_pack_integrity",
    )

    anchor_updated = False
    if apply:
        anchor_payload = {
            "version": 1,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "pack_root": str(pack_root),
            "source": "ui_seed_files",
            "notes": f"Refreshed by refresh_kaspi_archive_ui_pack.py for as_of {as_of.isoformat()}.",
        }
        anchor_path.parent.mkdir(parents=True, exist_ok=True)
        anchor_path.write_text(json.dumps(anchor_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        anchor_updated = True

    out_dir = validation_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "report.json"
    report_md = out_dir / "report.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "since": since.isoformat(),
        "status": "PASS",
        "ok": True,
        "apply": bool(apply),
        "anchor_updated": anchor_updated,
        "anchor_path": str(anchor_path),
        "pack_root": str(pack_root),
        "seed_files": [str(p) for p in seeds],
        "integrity_status": integrity.get("status"),
        "integrity_error_code": integrity.get("error_code"),
        "integrity_report_json": str(
            (PROJECT_ROOT / "exports" / "validation" / "archive_pack_integrity" / "ui" / as_of.isoformat() / "integrity_report.json").resolve()
        ),
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# Archive UI Pack Refresh",
                "",
                f"- as_of: `{as_of.isoformat()}`",
                f"- since: `{since.isoformat()}`",
                f"- status: `{payload['status']}`",
                f"- pack_root: `{pack_root}`",
                f"- apply: `{str(bool(apply)).lower()}`",
                f"- anchor_updated: `{str(anchor_updated).lower()}`",
                f"- integrity_status: `{payload['integrity_status']}`",
                "",
                "## Seed Files",
                "",
            ]
            + [f"- `{p}`" for p in payload["seed_files"]]
        )
        + "\n",
        encoding="utf-8",
    )
    payload["json_path"] = str(report_json)
    payload["md_path"] = str(report_md)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh kaspi archive UI pack from seeded xlsx exports")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--since", default="2025-06-06")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--anchor-path", type=Path, default=DEFAULT_ANCHOR_PATH)
    parser.add_argument("--seed-root", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = refresh_kaspi_archive_ui_pack(
            as_of=date.fromisoformat(str(args.as_of)),
            since=date.fromisoformat(str(args.since)),
            output_root=args.output_root,
            validation_root=args.validation_root,
            anchor_path=args.anchor_path,
            seed_root=args.seed_root,
            strict=bool(args.strict),
            apply=bool(args.apply),
        )
    except UiPackRefreshError as exc:
        print("status=FAIL")
        print("error_code=UI_PACK_REFRESH_FAIL")
        print(f"message={exc}")
        return 1

    print(f"archive_ui_pack_refresh_json={report['json_path']}")
    print(f"archive_ui_pack_refresh_md={report['md_path']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
