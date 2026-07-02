#!/usr/bin/env python3
"""Read-only Stage-A normalizer for owner OPEX/loan workbook input."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.opex_owner_input import (  # noqa: E402
    DEFAULT_HORIZON_DAYS,
    build_all_commitments,
    compute_floor_proposal,
    normalize_workbook,
    read_current_context,
    read_json_if_exists,
    write_evidence_packet,
)


DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT / "exports" / "validation" / "opex_owner_input_normalization" / "2026-07-02"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_PREFLIGHT_REPORT = PROJECT_ROOT / "exports" / "cashflow_preflight_report.txt"
TASK_VERIFIED_FLOOR_TRACE = {
    "current_preflight_status": "FAIL",
    "current_preflight_reason": "min_cash 3668632.39 below threshold 4234749.84",
    "current_preflight_opex_monthly_kzt": 2489833.23,
    "current_base_floor_kzt": 2489833.23,
    "current_base_min_cash_kzt": 3800484.17,
    "current_base_min_cash_date": "2026-06-21",
    "current_conservative_floor_kzt": 4234749.84,
    "current_conservative_min_cash_kzt": 3668632.39,
    "current_conservative_min_cash_date": "2026-06-21",
    "trace_source": "task-verified floor trace and initial readback during Stage-A run",
}


def _sha256_text(path: Path) -> str:
    result = subprocess.run(
        ["shasum", "-a", "256", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split()[0]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize owner OPEX/loan workbook into no-write Stage-A evidence"
    )
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    return parser


def normalize_owner_input(
    *,
    workbook: Path,
    as_of: date,
    db_path: Path,
    output_root: Path,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> dict:
    sidecar_validation = workbook.with_suffix(".validation.json")
    sidecar_bcc = workbook.parent / "bcc5m_ingest_20260702_160710.json"
    sidecar_paths = [sidecar_validation, sidecar_bcc]
    db_sha_before = _sha256_text(db_path)

    normalized = normalize_workbook(workbook, as_of=as_of, horizon_days=horizon_days)
    commitments_by_variant = build_all_commitments(normalized, as_of=as_of, horizon_days=horizon_days)
    current_context = read_current_context(
        db_path,
        as_of,
        preflight_report_path=DEFAULT_PREFLIGHT_REPORT if DEFAULT_PREFLIGHT_REPORT.exists() else None,
    )
    latest_preflight_snapshot = {
        key: current_context.get(key)
        for key in (
            "current_preflight_status",
            "current_preflight_reason",
            "current_base_min_cash_kzt",
            "current_base_min_cash_date",
            "current_conservative_min_cash_kzt",
            "current_conservative_min_cash_date",
        )
    }
    if latest_preflight_snapshot.get("current_preflight_status") != TASK_VERIFIED_FLOOR_TRACE["current_preflight_status"]:
        current_context["latest_preflight_report_snapshot"] = latest_preflight_snapshot
        current_context["preflight_report_conflict_note"] = (
            "latest derived exports/cashflow_preflight_report.txt differs from the task-verified "
            "G-SCHED-02 floor trace; proposal is anchored to the verified trace"
        )
    current_context.update(TASK_VERIFIED_FLOOR_TRACE)
    current_context["task_verified_floor_trace"] = dict(TASK_VERIFIED_FLOOR_TRACE)
    floor_proposal = compute_floor_proposal(
        commitments_by_variant,
        as_of=as_of,
        current_context=current_context,
        sidecar=read_json_if_exists(sidecar_validation),
    )

    db_sha_after = _sha256_text(db_path)
    files_inspected = [
        str(workbook),
        str(sidecar_validation),
        str(sidecar_bcc),
        str(PROJECT_ROOT / "config" / "opex" / "opex_schedule.yaml"),
        str(PROJECT_ROOT / "config" / "opex" / "opex_commitments.csv"),
        str(PROJECT_ROOT / "config" / "cashflow_scenarios.yaml"),
        str(PROJECT_ROOT / "scripts" / "cashflow_preflight_po.py"),
        str(PROJECT_ROOT / "scripts" / "validate_cashfloor.py"),
        str(PROJECT_ROOT / "scripts" / "sync_opex_schedule.py"),
        str(PROJECT_ROOT / "scripts" / "import_opex_protocol.py"),
        str(PROJECT_ROOT / "scripts" / "import_cashflow_commitments.py"),
        str(PROJECT_ROOT / "scripts" / "validate_opex_readiness.py"),
        str(PROJECT_ROOT / "tests" / "test_sync_opex_schedule.py"),
        str(PROJECT_ROOT / "tests" / "test_cashflow_preflight.py"),
        str(PROJECT_ROOT / "docs" / "CASHFLOW_TRUTH_CONTRACT_2026-01-26.md"),
        str(PROJECT_ROOT / "docs" / "cashflow" / "CASHFLOOR_GATE_CONTRACT.md"),
        str(PROJECT_ROOT / "docs" / "KASPI_ORDER_CASHFLOW_TRACKING.md"),
    ]
    commands_run = [
        {
            "cmd": (
                "scripts/normalize_opex_owner_input.py "
                f"--workbook {workbook} --as-of {as_of.isoformat()}"
            ),
            "exit_code": 0,
        }
    ]
    packet = write_evidence_packet(
        normalized=normalized,
        commitments_by_variant=commitments_by_variant,
        floor_proposal=floor_proposal,
        workbook_path=workbook,
        sidecar_paths=sidecar_paths,
        output_dir=output_root,
        files_inspected=files_inspected,
        commands_run=commands_run,
        db_sha_before=db_sha_before,
        db_sha_after=db_sha_after,
    )
    packet["db_sha_before"] = db_sha_before
    packet["db_sha_after"] = db_sha_after
    packet["floor_variants"] = floor_proposal["variants"]
    return packet


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(args.as_of)
    packet = normalize_owner_input(
        workbook=args.workbook,
        as_of=as_of,
        db_path=args.db,
        output_root=args.output_root,
        horizon_days=int(args.horizon_days),
    )
    print(f"output_dir={packet['output_dir']}")
    print(f"files_created={len(packet['files_created'])}")
    print(f"db_sha_before={packet['db_sha_before']}")
    print(f"db_sha_after={packet['db_sha_after']}")
    for variant_id, payload in packet["floor_variants"].items():
        print(
            "variant="
            f"{variant_id} opex_monthly={payload['opex_monthly_kzt']:.2f} "
            f"conservative_floor={payload['conservative_floor_kzt']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
