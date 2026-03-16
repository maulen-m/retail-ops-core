#!/usr/bin/env python3
"""Build a deterministic WebUI order status ledger from normalized source packs."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    DEFAULT_WEBUI_PACKS_ROOT,
    build_status_ledger,
    resolve_latest_dir,
)


class WebuiLedgerBuildError(RuntimeError):
    """Raised when the status ledger cannot be built."""


def _default_run_id(pack_roots: list[Path]) -> str:
    names = "_".join(path.name for path in pack_roots)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", names).strip("_")
    return f"webui_status_ledger_{safe or 'run'}"


def build_webui_status_ledger_cli(
    *,
    pack_roots: list[Path] | None,
    run_id: str | None,
    output_root: Path,
    strict: bool,
) -> dict[str, object]:
    resolved_packs = [path.expanduser().resolve() for path in (pack_roots or [])]
    if not resolved_packs:
        resolved_packs = [resolve_latest_dir(DEFAULT_WEBUI_PACKS_ROOT)]
    final_run_id = str(run_id or _default_run_id(resolved_packs)).strip()
    report = build_status_ledger(
        pack_roots=resolved_packs,
        run_id=final_run_id,
        output_root=output_root,
    )
    if strict and int(report["manifest"].get("ledger_row_count", 0)) == 0:
        raise WebuiLedgerBuildError("status ledger contains 0 rows")
    return {
        "status": "PASS",
        "run_root": str(report["run_root"]),
        "ledger_manifest_json": str(report["ledger_manifest_path"]),
        "webui_status_ledger_csv": str(report["ledger_csv"]),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build WebUI order status ledger")
    parser.add_argument("--pack-root", type=Path, action="append", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LEDGER_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = build_webui_status_ledger_cli(
            pack_roots=args.pack_root,
            run_id=args.run_id,
            output_root=args.output_root,
            strict=bool(args.strict),
        )
    except WebuiLedgerBuildError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_LEDGER_BUILD_FAIL")
        print(f"message={exc}")
        return 1

    print(f"ledger_root={report['run_root']}")
    print(f"ledger_manifest_json={report['ledger_manifest_json']}")
    print(f"webui_status_ledger_csv={report['webui_status_ledger_csv']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
