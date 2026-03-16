from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.identity_stabilization_common import StatusError
from scripts.validate_reference_freshness import validate_reference_freshness


def _write_reference_csv(path: Path, delivered_date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "transaction_date": delivered_date,
                "status_internal": "DELIVERED",
                "return_flag": "0",
                "store_code": "UNIVERSAL",
            },
            {
                "transaction_date": delivered_date,
                "status_internal": "DELIVERED",
                "return_flag": "0",
                "store_code": "STOREB",
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def test_validate_reference_freshness_pass(tmp_path: Path) -> None:
    reference_root = tmp_path / "mapped"
    csv_path = (
        reference_root
        / "2025-06-06_to_2026-03-02"
        / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    )
    _write_reference_csv(csv_path, "2026-03-02")

    report = validate_reference_freshness(
        as_of=date(2026, 3, 4),
        reference_root=reference_root,
        output_root=tmp_path / "out",
        max_delivery_lag_days=2,
        enforce_per_store=False,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["max_delivered_date"] == "2026-03-02"


def test_validate_reference_freshness_fails_when_stale(tmp_path: Path) -> None:
    reference_root = tmp_path / "mapped"
    csv_path = (
        reference_root
        / "2025-06-06_to_2026-02-25"
        / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    )
    _write_reference_csv(csv_path, "2026-02-25")

    with pytest.raises(StatusError, match="REFERENCE_STALE"):
        validate_reference_freshness(
            as_of=date(2026, 3, 4),
            reference_root=reference_root,
            output_root=tmp_path / "out",
            max_delivery_lag_days=2,
            enforce_per_store=False,
            strict=True,
        )


def test_validate_reference_freshness_per_store_check_optional(tmp_path: Path) -> None:
    reference_root = tmp_path / "mapped"
    csv_path = (
        reference_root
        / "2025-06-06_to_2026-03-04"
        / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"transaction_date": "2026-03-04", "status_internal": "DELIVERED", "return_flag": "0", "store_code": "UNIVERSAL"},
            {"transaction_date": "2026-02-20", "status_internal": "DELIVERED", "return_flag": "0", "store_code": "STOREB"},
        ]
    ).to_csv(csv_path, index=False, encoding="utf-8")

    report = validate_reference_freshness(
        as_of=date(2026, 3, 4),
        reference_root=reference_root,
        output_root=tmp_path / "out",
        max_delivery_lag_days=2,
        enforce_per_store=False,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["max_delivered_date"] == "2026-03-04"
    assert "STOREB" in report["stale_stores"]

    with pytest.raises(StatusError, match="REFERENCE_STALE"):
        validate_reference_freshness(
            as_of=date(2026, 3, 4),
            reference_root=reference_root,
            output_root=tmp_path / "out",
            max_delivery_lag_days=2,
            enforce_per_store=True,
            strict=True,
        )


def test_validate_reference_freshness_honors_statusdate_cutover(tmp_path: Path) -> None:
    reference_root = tmp_path / "mapped"
    csv_path = (
        reference_root
        / "2025-06-06_to_2026-03-07"
        / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    )
    _write_reference_csv(csv_path, "2026-02-27")

    report = validate_reference_freshness(
        as_of=date(2026, 3, 7),
        reference_root=reference_root,
        output_root=tmp_path / "out",
        max_delivery_lag_days=7,
        enforce_per_store=False,
        strict=True,
        statusdate_cutover=date(2026, 2, 27),
    )

    assert report["status"] == "PASS"
    assert report["max_delivered_date"] == "2026-02-27"
    assert report["effective_as_of"] == "2026-02-27"


def test_validate_reference_freshness_still_fails_before_cutover(tmp_path: Path) -> None:
    reference_root = tmp_path / "mapped"
    csv_path = (
        reference_root
        / "2025-06-06_to_2026-03-07"
        / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    )
    _write_reference_csv(csv_path, "2026-02-18")

    with pytest.raises(StatusError, match="REFERENCE_STALE"):
        validate_reference_freshness(
            as_of=date(2026, 3, 7),
            reference_root=reference_root,
            output_root=tmp_path / "out",
            max_delivery_lag_days=7,
            enforce_per_store=False,
            strict=True,
            statusdate_cutover=date(2026, 2, 27),
        )
