#!/usr/bin/env python3
"""Profile normalized WebUI pack status-change coverage."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import load_pack_manifest, load_pack_rows

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-06"
)
PROFILE_COLUMNS = [
    "scope",
    "source_pack_id",
    "store_code",
    "delivered_rows",
    "status_change_nonblank_count",
    "status_change_blank_count",
    "status_change_nonblank_ratio",
    "generated_at",
]


class NormalizedStatusChangeProfileError(RuntimeError):
    """Raised when normalized WebUI status-change profiling cannot complete."""


def profile_webui_normalized_status_change(
    *,
    pack_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    pack_root = pack_root.expanduser().resolve()
    manifest = load_pack_manifest(pack_root)
    rows = load_pack_rows(pack_root)
    delivered = rows[rows.get("status_internal", pd.Series(dtype=object)).eq("DELIVERED")].copy()
    if delivered.empty:
        summary = pd.DataFrame(
            [
                {
                    "scope": "PACK_TOTAL",
                    "source_pack_id": str(manifest.get("pack_id") or ""),
                    "store_code": "__ALL__",
                    "delivered_rows": 0,
                    "status_change_nonblank_count": 0,
                    "status_change_blank_count": 0,
                    "status_change_nonblank_ratio": 0.0,
                    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
            ],
            columns=PROFILE_COLUMNS,
        )
    else:
        delivered["status_change_present"] = (
            delivered.get("status_change_at", pd.Series(dtype=object)).astype(str).str.strip().ne("")
        )
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        by_store = (
            delivered.groupby(["pack_id", "store_code"], dropna=False)
            .agg(
                delivered_rows=("order_id", "size"),
                status_change_nonblank_count=("status_change_present", lambda s: int(s.sum())),
            )
            .reset_index()
            .rename(columns={"pack_id": "source_pack_id"})
        )
        by_store["status_change_blank_count"] = (
            by_store["delivered_rows"] - by_store["status_change_nonblank_count"]
        )
        by_store["status_change_nonblank_ratio"] = by_store["status_change_nonblank_count"] / by_store["delivered_rows"].replace(0, 1)
        by_store["scope"] = "STORE"
        by_store["generated_at"] = generated_at

        total = pd.DataFrame(
            [
                {
                    "scope": "PACK_TOTAL",
                    "source_pack_id": str(manifest.get("pack_id") or ""),
                    "store_code": "__ALL__",
                    "delivered_rows": int(len(delivered)),
                    "status_change_nonblank_count": int(delivered["status_change_present"].sum()),
                    "status_change_blank_count": int((~delivered["status_change_present"]).sum()),
                    "status_change_nonblank_ratio": float(delivered["status_change_present"].mean()),
                    "generated_at": generated_at,
                }
            ]
        )
        summary = pd.concat([total[PROFILE_COLUMNS], by_store[PROFILE_COLUMNS]], ignore_index=True)

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_csv = output_dir / "normalized_status_change_profile.csv"
    summary.to_csv(profile_csv, index=False, encoding="utf-8")

    return {
        "status": "PASS",
        "profile_csv": str(profile_csv),
        "pack_root": str(pack_root),
        "source_pack_id": str(manifest.get("pack_id") or ""),
        "delivered_rows": int(summary.loc[summary["scope"] == "PACK_TOTAL", "delivered_rows"].iloc[0]),
        "status_change_nonblank_count": int(
            summary.loc[summary["scope"] == "PACK_TOTAL", "status_change_nonblank_count"].iloc[0]
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile normalized WebUI pack status-change coverage")
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = profile_webui_normalized_status_change(
            pack_root=args.pack_root,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError, NormalizedStatusChangeProfileError) as exc:
        print("status=FAIL")
        print("error_code=NORMALIZED_STATUS_CHANGE_PROFILE_FAIL")
        print(f"message={exc}")
        return 1

    print(f"normalized_status_change_profile_csv={report['profile_csv']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
