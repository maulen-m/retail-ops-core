from __future__ import annotations

from core.parsers.kaspi_export_parser import _extract_sku_parts
from core.parsers.kaspi_parser import extract_sku_from_article


def test_sales_parser_resolves_compact_suit_bundle_before_legacy_underscore_heuristic() -> None:
    parsed = extract_sku_from_article("SUIT-21-LS-ST-XL-48")

    assert parsed["sku_key"] == "SUIT-21-LS"
    assert parsed["my_size"] == "XL"
    assert parsed["sku_id"] == "SUIT-21-LS_XL"
    assert parsed["product_type"] == "CL"


def test_sales_parser_resolves_compact_beli_bundle_bucketed_size() -> None:
    parsed = extract_sku_from_article("LINE-31-TS-TRM-4XL-60")

    assert parsed["sku_key"] == "LINE-31-TS"
    assert parsed["my_size"] == "4XL"
    assert parsed["sku_id"] == "LINE-31-TS_4XL"


def test_order_export_parser_resolves_compact_bundle_articles() -> None:
    parsed = _extract_sku_parts("SUIT-31-TK-TRM-2XL-52")

    assert parsed["sku_key"] == "SUIT-31-TK"
    assert parsed["my_size"] == "2XL"
    assert parsed["sku_id"] == "SUIT-31-TK_2XL"
