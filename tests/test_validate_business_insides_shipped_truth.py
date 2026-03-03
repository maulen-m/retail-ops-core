from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_business_insides_shipped_truth import validate_business_insides_shipped_truth


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_validate_business_insides_shipped_truth_passes_when_totals_match(tmp_path: Path) -> None:
    shipped_summary = tmp_path / "shipped" / "summary.json"
    business_dir = tmp_path / "business"

    _write_json(
        shipped_summary,
        {
            "rows": [
                {"day": "2026-02-20", "store": "Universal", "api_primary": 5, "provisional": False},
                {"day": "2026-02-20", "store": "STORE-B", "api_primary": 7, "provisional": False},
            ]
        },
    )
    _write_json(
        business_dir / "BUSINESS_INSIDES_2026-02-20.json",
        {"waybill_snapshot": {"totals": {"orders": 12}}},
    )

    report = validate_business_insides_shipped_truth(
        since="2026-02-20",
        until="2026-02-20",
        business_dir=business_dir,
        shipped_summary=shipped_summary,
        output_root=tmp_path / "out",
        strict=True,
    )

    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_validate_business_insides_shipped_truth_fails_on_mismatch(tmp_path: Path) -> None:
    shipped_summary = tmp_path / "shipped" / "summary.json"
    business_dir = tmp_path / "business"

    _write_json(
        shipped_summary,
        {"rows": [{"day": "2026-02-21", "store": "Universal", "api_primary": 9, "provisional": False}]},
    )
    _write_json(
        business_dir / "BUSINESS_INSIDES_2026-02-21.json",
        {"waybill_snapshot": {"totals": {"orders": 8}}},
    )

    with pytest.raises(RuntimeError, match="business insides shipped truth validation failed"):
        validate_business_insides_shipped_truth(
            since="2026-02-21",
            until="2026-02-21",
            business_dir=business_dir,
            shipped_summary=shipped_summary,
            output_root=tmp_path / "out",
            strict=True,
        )


def test_validate_business_insides_shipped_truth_fails_when_snapshot_missing(tmp_path: Path) -> None:
    shipped_summary = tmp_path / "shipped" / "summary.json"

    _write_json(
        shipped_summary,
        {"rows": [{"day": "2026-02-22", "store": "AcmeWear", "api_primary": 3, "provisional": False}]},
    )

    with pytest.raises(RuntimeError, match="business insides shipped truth validation failed"):
        validate_business_insides_shipped_truth(
            since="2026-02-22",
            until="2026-02-22",
            business_dir=tmp_path / "business",
            shipped_summary=shipped_summary,
            output_root=tmp_path / "out",
            strict=True,
        )


def test_validate_business_insides_shipped_truth_ignores_provisional_rows(tmp_path: Path) -> None:
    shipped_summary = tmp_path / "shipped" / "summary.json"
    business_dir = tmp_path / "business"

    _write_json(
        shipped_summary,
        {"rows": [{"day": "2026-02-23", "store": "AcmeWear", "api_primary": 4, "provisional": True}]},
    )

    report = validate_business_insides_shipped_truth(
        since="2026-02-23",
        until="2026-02-23",
        business_dir=business_dir,
        shipped_summary=shipped_summary,
        output_root=tmp_path / "out",
        strict=True,
    )

    assert report["ok"] is True
    assert report["rows"] == []
