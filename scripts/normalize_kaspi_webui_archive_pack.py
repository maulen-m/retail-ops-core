#!/usr/bin/env python3
"""Normalize Kaspi WebUI archive exports into an immutable source pack."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import DEFAULT_STORES_CONFIG, DEFAULT_WEBUI_PACKS_ROOT, write_pack

DEFAULT_UI_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_ui_pack.json"


class WebuiPackNormalizeError(RuntimeError):
    """Raised when normalization cannot produce a usable WebUI source pack."""


def _resolve_source_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env_value = str(os.environ.get("AB_WEBUI_ARCHIVE_SOURCE_ROOT") or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    if DEFAULT_UI_ANCHOR.exists():
        payload = json.loads(DEFAULT_UI_ANCHOR.read_text(encoding="utf-8"))
        root = str(payload.get("pack_root") or "").strip()
        if root:
            return Path(root).expanduser().resolve()
    raise WebuiPackNormalizeError("source root is not configured; pass --source-root")


def _default_pack_id(source_root: Path) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", source_root.name).strip("_")
    return f"webui_archive_pack_{safe or 'source'}"


def normalize_kaspi_webui_archive_pack(
    *,
    source_root: Path | None,
    pack_id: str | None,
    output_root: Path,
    stores_config: Path,
    strict: bool,
) -> dict[str, object]:
    resolved_source_root = _resolve_source_root(source_root)
    if not resolved_source_root.exists():
        raise WebuiPackNormalizeError(f"source root not found: {resolved_source_root}")
    final_pack_id = str(pack_id or _default_pack_id(resolved_source_root)).strip()
    if not final_pack_id:
        raise WebuiPackNormalizeError("pack_id resolved to empty value")

    report = write_pack(
        source_root=resolved_source_root,
        pack_id=final_pack_id,
        output_root=output_root,
        stores_config=stores_config,
    )
    manifest = report["manifest"]
    if strict:
        if int(manifest.get("source_file_count", 0)) == 0:
            raise WebuiPackNormalizeError("no WebUI archive source files found")
        if int(manifest.get("delivered_missing_status_change_date", 0)) > 0:
            raise WebuiPackNormalizeError(
                "delivered rows missing status-change date in normalized pack"
            )
    return {
        "status": "PASS",
        "pack_root": str(report["pack_root"]),
        "source_manifest_path": str(report["source_manifest_path"]),
        "normalized_rows_csv": str(report["normalized_rows_csv"]),
        "pack_id": final_pack_id,
        "source_root": str(resolved_source_root),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize Kaspi WebUI archive source pack")
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--pack-id", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_WEBUI_PACKS_ROOT)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = normalize_kaspi_webui_archive_pack(
            source_root=args.source_root,
            pack_id=args.pack_id,
            output_root=args.output_root,
            stores_config=args.stores_config,
            strict=bool(args.strict),
        )
    except WebuiPackNormalizeError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_PACK_NORMALIZE_FAIL")
        print(f"message={exc}")
        return 1

    print(f"pack_root={report['pack_root']}")
    print(f"source_manifest_json={report['source_manifest_path']}")
    print(f"normalized_rows_csv={report['normalized_rows_csv']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
