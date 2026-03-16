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


def test_kaspi_parser_normalizes_known_acmewear_alias_suffixes() -> None:
    cases = [
        (
            "CL_OC_MEN_LINE51_WHITE_K-O_XL_2",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_XL",
            "XL",
        ),
        (
            "CL_OC_MEN_LINE51_WHITE_K-O_3XL",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_3XL",
            "3XL",
        ),
        (
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK_K-O_TRM_M",
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK_M",
            "M",
        ),
        (
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK_K-O_TRM_4XL_2",
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL",
            "4XL",
        ),
    ]

    for article, expected_key, expected_id, expected_size in cases:
        out = extract_sku_from_article(article, article)
        assert out["sku_key"] == expected_key
        assert out["sku_id"] == expected_id
        assert out["my_size"] == expected_size
