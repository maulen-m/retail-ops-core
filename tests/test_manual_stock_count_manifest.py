from __future__ import annotations

from pathlib import Path

import pytest

from core.ops.manual_stock_count_manifest import (
    ManualStockCountManifestError,
    aggregate_manual_stock_counts,
    latest_manual_stock_overrides_by_sku_id,
    load_approved_manual_stock_manifest,
    manual_stock_overrides_by_sku_id,
    validate_manual_stock_manifest,
)


NEW_PRE_SHIPMENTS_MANIFEST = (
    "config/anchors/manual_stock_counts/"
    "astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved.json"
)


def test_astana_manual_count_manifest_is_owner_approved_and_sums_duplicates() -> None:
    data = load_approved_manual_stock_manifest()
    aggregates = aggregate_manual_stock_counts(data)

    assert len(data["rows"]) == 43
    assert len(aggregates) == 39
    assert sum(row.quantity for row in aggregates) == 1833

    suit_2xl = next(row for row in aggregates if row.sku_id == "CL_NEW-CLO2_MEN_SUIT-61_BLACK_2XL")
    assert suit_2xl.quantity == 61
    assert suit_2xl.source_row_count == 2
    assert suit_2xl.source_images == ("IMG_4820.jpeg", "IMG_4821.jpeg")

    rombik_3xl = next(row for row in aggregates if row.sku_id == "CL_NEW-CLO_MEN_ROMBIK_BLACK_3XL")
    assert rombik_3xl.quantity == 21


def test_astana_manual_count_manifest_keeps_return_and_cancellation_units_out() -> None:
    data = load_approved_manual_stock_manifest()
    assert data["count_scope"]["quarantine_returns_included"] is False
    assert data["count_scope"]["cancellation_units_included"] is False
    assert data["count_scope"]["quarantine_returns_status"] == "not_counted_pending_employee_count"
    assert data["count_scope"]["cancellation_units_status"] == "not_counted_pending_employee_count"


def test_astana_manual_count_shared_rombik_s_pool_expands_alias_without_double_counting() -> None:
    data = load_approved_manual_stock_manifest()
    overrides = manual_stock_overrides_by_sku_id(data)

    men_s = overrides["CL_NEW-CLO_MEN_ROMBIK_BLACK_S"]
    kid_s = overrides["CL_NEW-CLO_KID_ROMBIK_BLACK_S"]

    assert men_s is kid_s
    assert men_s.quantity == 74
    assert men_s.stock_pool_id == "SHARED_ROMBIK_BLACK_S_MEN_KIDS"
    assert men_s.counting_policy == "shared_pool_override_do_not_double_count_aliases"

    kid30 = overrides["CL_NEW-CLO_KID_ROMBIK_BLACK_30"]
    assert kid30 is not kid_s
    assert kid30.quantity == 93
    assert kid30.stock_pool_id == "CL_NEW-CLO_KID_ROMBIK_BLACK_30"


def test_astana_manual_count_manifest_fails_if_quarantine_is_marked_included() -> None:
    data = load_approved_manual_stock_manifest()
    data["count_scope"] = dict(data["count_scope"], quarantine_returns_included=True)

    with pytest.raises(ManualStockCountManifestError, match="quarantine_returns_included"):
        validate_manual_stock_manifest(data)


def test_astana_20260604_pre_shipments_manifest_preserves_stopline_scope() -> None:
    data = load_approved_manual_stock_manifest(Path(NEW_PRE_SHIPMENTS_MANIFEST))
    aggregates = aggregate_manual_stock_counts(data)

    assert data["batch_id"] == "ASTANA_WAREHOUSE_MANUAL_COUNT_2026_06_04_PRE_SHIPMENTS"
    assert len(data["rows"]) == 66
    assert len(aggregates) == 66
    assert sum(row.quantity for row in aggregates) == 3989

    assert "CL_OC_MEN_LINE51_WHITE_S" not in {row.sku_id for row in aggregates}
    assert data["quarantine"]["mapping_pending_units"] == 273
    assert all(row["status"] == "QUARANTINED_NOT_MATERIALIZED" for row in data["quarantine"]["mapping_pending_rows"])

    rombik_s = next(row for row in aggregates if row.stock_pool_id == "SHARED_ROMBIK_BLACK_S_MEN_KIDS")
    assert rombik_s.quantity == 75
    assert rombik_s.applies_to_sku_ids == ("CL_NEW-CLO_MEN_ROMBIK_BLACK_S", "CL_NEW-CLO_KID_ROMBIK_BLACK_S")


def test_latest_manual_stock_overrides_use_20260604_rows_without_inventing_line51_s() -> None:
    old_data = load_approved_manual_stock_manifest()
    new_data = load_approved_manual_stock_manifest(Path(NEW_PRE_SHIPMENTS_MANIFEST))
    overrides = latest_manual_stock_overrides_by_sku_id([old_data, new_data])

    assert overrides["CL_OC_MEN_LINE52_BLACK_3XL"].quantity == 83
    assert overrides["CL_NEW-CLO_MEN_ROMBIK_BLACK_S"].quantity == 75
    assert overrides["CL_NEW-CLO_KID_ROMBIK_BLACK_S"] is overrides["CL_NEW-CLO_MEN_ROMBIK_BLACK_S"]
    assert "CL_OC_MEN_LINE51_WHITE_S" not in overrides
