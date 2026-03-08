#!/usr/bin/env python3
"""Validate WebUI archive download run manifests and copied files."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import DEFAULT_STORES_CONFIG, compute_sha256, load_enabled_stores

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "webui_archive_download_runs"


class PlaywrightArchiveDownloadValidationError(RuntimeError):
    """Raised when strict download validation fails."""


def _resolve_run_root(run_id: str, output_root: Path) -> Path:
    candidate = Path(run_id).expanduser()
    if candidate.exists():
        return candidate.resolve()
    alt = output_root.resolve() / run_id
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(f"download run not found: {run_id}")


def validate_playwright_archive_downloads(
    *,
    run_id: str,
    output_root: Path,
    stores_config: Path,
    strict: bool,
) -> dict[str, Any]:
    run_root = _resolve_run_root(run_id, output_root)
    manifest_path = run_root / "run_manifest.json"
    if not manifest_path.exists():
        raise PlaywrightArchiveDownloadValidationError(f"missing run_manifest.json in {run_root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enabled_stores = load_enabled_stores(stores_config)
    target_stores = [
        str(store).strip().upper()
        for store in (manifest.get("target_stores") or enabled_stores)
        if str(store).strip()
    ]

    errors: list[str] = []
    store_results = manifest.get("store_results") or []
    seen_stores = {str(row.get("store_code") or "").upper() for row in store_results}
    missing_stores = [store for store in target_stores if store not in seen_stores]
    if missing_stores:
        errors.append(f"missing stores in run manifest: {', '.join(missing_stores)}")

    validated_files = 0
    for row in store_results:
        if str(row.get("status") or "").upper() != "PASS":
            errors.append(f"store run failed: {row.get('store_code')}")
            continue
        copied_file = Path(str(row.get("copied_file") or ""))
        expected_sha = str(row.get("sha256") or "")
        if not copied_file.exists():
            errors.append(f"copied file missing: {copied_file}")
            continue
        validated_files += 1
        if expected_sha and compute_sha256(copied_file) != expected_sha:
            errors.append(f"copied file hash mismatch: {copied_file}")

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_root": str(run_root),
        "run_id": manifest.get("run_id") or run_root.name,
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "strict": bool(strict),
        "mode": manifest.get("mode"),
        "enabled_stores": enabled_stores,
        "target_stores": target_stores,
        "validated_files": validated_files,
        "errors": errors,
    }
    report_path = run_root / "download_validation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["download_validation_json"] = str(report_path)
    if strict and not report["ok"]:
        raise PlaywrightArchiveDownloadValidationError("; ".join(errors))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate WebUI archive download runs")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_playwright_archive_downloads(
            run_id=str(args.run_id),
            output_root=args.output_root,
            stores_config=args.stores_config,
            strict=bool(args.strict),
        )
    except PlaywrightArchiveDownloadValidationError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_ARCHIVE_DOWNLOAD_VALIDATION_FAIL")
        print(f"message={exc}")
        return 1

    print(f"download_validation_json={report['download_validation_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
