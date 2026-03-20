from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_sales_truth_drift_report import build_sales_truth_drift_report


def _write_parity(parity_root: Path, as_of: str, rows: list[dict]) -> None:
    target = parity_root / as_of
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": as_of,
        "status": "PASS",
        "daily_rows": rows,
    }
    (target / "parity_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_sales_truth_drift_report_passes_when_no_mismatch(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    _write_parity(
        parity_root,
        "2026-02-26",
        [
            {
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "ref_units": 10,
                "db_units": 10,
                "ref_rev_kzt": 1000,
                "db_rev_kzt": 1000,
                "match": True,
            }
        ],
    )

    report = build_sales_truth_drift_report(
        as_of="2026-02-26",
        output_root=tmp_path / "daily",
        parity_root=parity_root,
        lookback_days=14,
        strict=True,
        ocean_drop_path=None,
        crm_archive_lookup=None,
    )

    assert report["status"] == "PASS"
    assert Path(report["json_path"]).exists()


def test_build_sales_truth_drift_report_fails_closed_on_mismatch(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    _write_parity(
        parity_root,
        "2026-02-26",
        [
            {
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "ref_units": 10,
                "db_units": 9,
                "ref_rev_kzt": 1000,
                "db_rev_kzt": 900,
                "match": False,
            }
        ],
    )

    with pytest.raises(RuntimeError, match="drift detected"):
        build_sales_truth_drift_report(
            as_of="2026-02-26",
            output_root=tmp_path / "daily",
            parity_root=parity_root,
            lookback_days=14,
            strict=True,
            ocean_drop_path=None,
            crm_archive_lookup=None,
        )


def test_build_sales_truth_drift_report_ignores_volatile_mismatch_in_strict_mode(
    tmp_path: Path,
) -> None:
    parity_root = tmp_path / "parity"
    _write_parity(
        parity_root,
        "2026-02-26",
        [
            {
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "ref_units": 10,
                "db_units": 9,
                "ref_rev_kzt": 1000,
                "db_rev_kzt": 900,
                "is_volatile": True,
                "match": False,
            }
        ],
    )

    report = build_sales_truth_drift_report(
        as_of="2026-02-26",
        output_root=tmp_path / "daily",
        parity_root=parity_root,
        lookback_days=14,
        strict=True,
        ocean_drop_path=None,
        crm_archive_lookup=None,
    )

    assert report["status"] == "PASS"
