from __future__ import annotations

from pathlib import Path

from scripts.validate_product_truth_canonicalization import (
    DEFAULT_CONFIG,
    parse_po1a_addback,
    parse_line31_sales,
    parse_line31_stock_anchor,
    validate_config,
)


def test_product_truth_canonicalization_contract_passes() -> None:
    result = validate_config(DEFAULT_CONFIG, strict=True)

    assert result.ok, result.errors
    assert result.metrics["rush31_owner_total"] == 290
    assert result.metrics["line31_sales_qty"] == 50
    assert result.metrics["line31_sell_price_distribution"] == {16990: 50}
    assert result.metrics["line31_gross_revenue_kzt"] == 849500
    assert result.metrics["line31_anchor_total_sets"] == 139
    assert result.metrics["line31_po1a_mapped_sets"] == 279
    assert result.metrics["line31_po1a_physical_not_for_sale_reserve_sets"] == 59
    assert result.metrics["line31_po1a_quarantined_sets"] == 0
    assert result.metrics["rombik_kid30_physical_stock_pool_units"] == 93
    assert result.metrics["rombik_kid30_route_split_total_per_store"] == 93
    assert result.metrics["rombik_kid30_authorized_product_codes"] == ["128541983", "135222379"]


def test_line31_sales_parser_preserves_16990_price() -> None:
    source = Path(
        "~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__LINE31_sales.md"
    )

    rows = parse_line31_sales(source)

    assert len(rows) == 50
    assert {row["sell_price_kzt"] for row in rows} == {16990}
    assert sum(row["total_price_kzt"] for row in rows) == 849500


def test_line31_stock_anchor_and_po1a_quarantine_are_separate() -> None:
    anchor = Path(
        "~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__STOCK_13.4.26.md"
    )
    po1a = Path(
        "~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/"
        "LINE31_PO1A_NON_OLIVE_ASTANA_SALES_ACTIVATION__2026-05-24/"
        "line31_po1a_non_olive_arrived_quantities.csv"
    )
    mapping = {
        "Starry Black 3-piece Set": "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK",
        "Ivory / White / Starry Black Mixed Set": (
            "CL_OF_ARC_WM_LINE31_B-C-011_IVORY_J-C-026_WHITE_L-C-023_STARRY-BLACK"
        ),
        "Misty Blue 3-piece Set": "CL_OF_ARC_WM_LINE31_C-014_MISTY-BLUE",
        "Ivory 3-piece Set": "CL_OF_ARC_WM_LINE31_C-011_IVORY",
    }
    reserve = {
        "Bean Paste Pink 3-piece Set",
        "Pomelo Pink 3-piece Set",
        "Eggplant Purple 3-piece Set",
        "Whale Blue 3-piece Set",
    }

    anchor_rows = parse_line31_stock_anchor(anchor)
    po1a_rows = parse_po1a_addback(po1a, mapping, set(), reserve)

    assert sum(row["anchor_qty"] for row in anchor_rows) == 139
    assert sum(row["po1a_addback_qty"] for row in po1a_rows) == 338
    assert (
        sum(row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"] == "MAPPED_PO1A_ADD_BACK")
        == 279
    )
    assert (
        sum(row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"] == "PHYSICAL_NOT_FOR_SALE_RESERVE")
        == 59
    )
    assert not [
        row for row in po1a_rows if row["mapping_status"].startswith("QUARANTINED")
    ]


def test_pricelist_stock_is_non_authoritative_inventory_evidence() -> None:
    result = validate_config(DEFAULT_CONFIG, strict=True)

    assert result.ok, result.errors
    config = DEFAULT_CONFIG.read_text(encoding="utf-8")
    assert '"pp_columns_inventory_authority": false' in config
    assert "PHYSICAL_INVENTORY_TRUTH_ECONOMIC_STOCK_TRUTH_REORDER_QTY" in config
    assert "NON_LIVE_INCORRECT_UNATTACHED_SINGLE_SIZE_OFFER" in config
