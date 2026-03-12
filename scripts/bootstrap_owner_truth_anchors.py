#!/usr/bin/env python3
"""Bootstrap or validate owner-truth anchor symlinks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AnchorBootstrapError(RuntimeError):
    """Raised when anchor bootstrap cannot be completed safely."""


def _anchor_specs(root: Path, *, release_as_of: str | None) -> dict[str, dict[str, Path]]:
    anchors_root = root / "config" / "anchors"
    specs: dict[str, dict[str, Path]] = {
        "crm_anchor": {"link": anchors_root / "SALES_KSP_CRM_LATEST.xlsx"},
        "inbound_anchor": {"link": anchors_root / "INBOUND_CALENDAR_LATEST.xlsx"},
        "stock_anchor": {"link": anchors_root / "STOCK_SNAPSHOT_LATEST.xlsx"},
        "env_anchor": {"link": root / ".env"},
        "waybill_selection_anchor": {
            "link": root / "excel_ui" / "ActiveOrders" / "waybills"
        },
    }
    if release_as_of:
        specs["release_validation_anchor"] = {
            "link": root / "exports" / "validation" / "ads_scope_closeout" / release_as_of,
        }
    return specs


def _validate_target(path: Path | None, *, name: str) -> Path:
    if path is None:
        raise AnchorBootstrapError(f"missing required anchor input: {name}")
    candidate = path.expanduser().resolve()
    if not candidate.exists():
        raise AnchorBootstrapError(f"missing required anchor input: {name} path={candidate}")
    return candidate


def bootstrap_owner_truth_anchors(
    *,
    project_root: Path,
    crm_workbook: Path | None,
    inbound_workbook: Path | None,
    stock_workbook: Path | None,
    env_file: Path | None,
    waybill_selection_cache: Path | None,
    release_as_of: str | None,
    release_validation_root: Path | None,
    validate_only: bool,
) -> dict[str, Any]:
    root = project_root.resolve()
    specs = _anchor_specs(root, release_as_of=release_as_of)
    specs["crm_anchor"]["target"] = crm_workbook
    specs["inbound_anchor"]["target"] = inbound_workbook
    specs["stock_anchor"]["target"] = stock_workbook
    specs["env_anchor"]["target"] = env_file
    specs["waybill_selection_anchor"]["target"] = waybill_selection_cache
    if "release_validation_anchor" in specs:
        specs["release_validation_anchor"]["target"] = release_validation_root
    anchors_root = root / "config" / "anchors"
    anchors_root.mkdir(parents=True, exist_ok=True)

    if not validate_only:
        for name, meta in specs.items():
            target = _validate_target(meta["target"], name=name)
            link_path = meta["link"]
            link_path.parent.mkdir(parents=True, exist_ok=True)
            if link_path.exists() or link_path.is_symlink():
                if link_path.is_symlink() or link_path.is_file():
                    link_path.unlink()
                elif link_path.is_dir():
                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()
            os.symlink(str(target), str(link_path))

    anchors_report: dict[str, dict[str, Any]] = {}
    for name, meta in specs.items():
        link_path = meta["link"]
        exists = link_path.exists() or link_path.is_symlink()
        target = None
        if exists and link_path.is_symlink():
            try:
                target = str(link_path.resolve(strict=True))
            except FileNotFoundError:
                target = None
        elif meta.get("target") is not None:
            target = str(Path(meta["target"]).expanduser().resolve())
        anchors_report[name] = {
            "link": str(link_path),
            "exists": exists,
            "is_symlink": link_path.is_symlink(),
            "target": target,
        }
        if validate_only and not exists:
            raise AnchorBootstrapError(f"missing required anchor symlink: {name} path={link_path}")

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project_root": str(root),
        "validate_only": bool(validate_only),
        "anchors": anchors_report,
        "status": "PASS",
        "ok": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap or validate owner-truth anchor symlinks")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--crm-workbook", type=Path, default=None)
    parser.add_argument("--inbound-workbook", type=Path, default=None)
    parser.add_argument("--stock-workbook", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--waybill-selection-cache", type=Path, default=None)
    parser.add_argument("--release-as-of", default=None)
    parser.add_argument("--release-validation-root", type=Path, default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output-json", type=Path, default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = bootstrap_owner_truth_anchors(
            project_root=args.project_root,
            crm_workbook=args.crm_workbook,
            inbound_workbook=args.inbound_workbook,
            stock_workbook=args.stock_workbook,
            env_file=args.env_file,
            waybill_selection_cache=args.waybill_selection_cache,
            release_as_of=str(args.release_as_of) if args.release_as_of else None,
            release_validation_root=args.release_validation_root,
            validate_only=bool(args.validate_only),
        )
    except AnchorBootstrapError as exc:
        print("status=FAIL")
        print("error_code=ANCHOR_BOOTSTRAP_FAIL")
        print(f"message={exc}")
        return 1

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"anchor_bootstrap_report={args.output_json}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
