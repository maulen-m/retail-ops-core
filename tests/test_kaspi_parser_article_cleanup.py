from __future__ import annotations

from core.parsers.kaspi_export_parser import _extract_sku_parts as export_extract_sku_parts
from core.parsers.kaspi_parser import extract_sku_from_article


def test_kaspi_parser_strips_numeric_article_prefix_before_sku_extraction() -> None:
    out = extract_sku_from_article(
        "102492502 CL_OC_MEN_LINE52_BLACK_XL",
        "Комплект Line52 черный XL",
    )
    assert out["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert out["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
    assert out["my_size"] == "XL"


def test_kaspi_export_parser_strips_numeric_article_prefix_before_sku_extraction() -> None:
    out = export_extract_sku_parts(
        "102492502 CL_OC_MEN_LINE52_BLACK_XL",
        "Комплект Line52 черный XL",
    )
    assert out["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert out["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
    assert out["my_size"] == "XL"
