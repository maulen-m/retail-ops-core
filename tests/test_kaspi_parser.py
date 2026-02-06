"""
Unit tests for kaspi_parser.py
"""
import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import pandas as pd

from core.parsers.kaspi_parser import (
    extract_sku_from_article,
    parse_active_orders,
    _extract_size,
    _extract_model_from_offer,
    _extract_color_from_offer,
    _detect_gender,
)


class TestExtractSize:
    """Tests for size extraction from text."""

    def test_standard_sizes(self):
        """Test standard letter sizes."""
        assert _extract_size("XL") == "XL"
        assert _extract_size("размер M") == "M"
        assert _extract_size("2XL") == "2XL"
        assert _extract_size("3XL") == "3XL"

    def test_russian_xxl_conversion(self):
        """Test XXL → 2XL conversion."""
        assert _extract_size("XXL") == "2XL"
        assert _extract_size("XXXL") == "3XL"

    def test_numeric_sizes(self):
        """Test numeric sizes (48, 50, etc.)."""
        assert _extract_size("размер 48") == "48"
        assert _extract_size("черный 52") == "52"

    def test_size_in_context(self):
        """Test size extraction from full offer text."""
        assert _extract_size("Комплект ALPIKA 102492502 черный 48") == "48"
        assert _extract_size("Рашгард Line52 черный XL") == "XL"

    def test_no_size(self):
        """Test when no size present."""
        assert _extract_size("") is None
        assert _extract_size("Рашгард черный") is None


class TestExtractModelFromOffer:
    """Tests for model name extraction."""

    def test_print_models(self):
        """Test PRINT model extraction."""
        assert _extract_model_from_offer("Line52 черный XL") == "LINE52"
        assert _extract_model_from_offer("PRINT 51 белый") == "LINE52"

    def test_beli_models(self):
        """Test LINE model extraction."""
        assert _extract_model_from_offer("Line51 белый 2XL") == "LINE51"

    def test_generic_alphanumeric(self):
        """Test generic alphanumeric model codes."""
        # Model codes should be at least 2 letters + 2 digits
        assert _extract_model_from_offer("Product AB12 black") == "AB12"

    def test_no_model(self):
        """Test when no model pattern found."""
        assert _extract_model_from_offer("Simple product") is None
        assert _extract_model_from_offer("") is None


class TestExtractColorFromOffer:
    """Tests for color extraction."""

    def test_russian_colors(self):
        """Test Russian color names."""
        assert _extract_color_from_offer("черный") == "BLACK"
        assert _extract_color_from_offer("белый") == "WHITE"
        assert _extract_color_from_offer("серый") == "GREY"

    def test_english_colors(self):
        """Test English color names."""
        assert _extract_color_from_offer("BLACK shirt") == "BLACK"
        assert _extract_color_from_offer("navy blue") == "NAVY"

    def test_color_in_context(self):
        """Test color extraction from full offer."""
        assert _extract_color_from_offer("Комплект Line52 черный XL") == "BLACK"

    def test_no_color(self):
        """Test when no color found."""
        assert _extract_color_from_offer("Simple product XL") is None


class TestDetectGender:
    """Tests for gender detection."""

    def test_default_men(self):
        """Test default is MEN."""
        assert _detect_gender("Simple product") == "MEN"
        assert _detect_gender("") == "MEN"

    def test_women(self):
        """Test women detection."""
        assert _detect_gender("женский комплект") == "WOMEN"
        assert _detect_gender("Women's jacket") == "WOMEN"

    def test_kids(self):
        """Test kids detection."""
        assert _detect_gender("детская одежда") == "KIDS"


class TestExtractSkuFromArticle:
    """Tests for full SKU extraction."""

    def test_formatted_sku(self):
        """Test already-formatted SKU codes."""
        result = extract_sku_from_article("CL_OC_MEN_LINE52_BLACK_XL", None)
        assert result["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
        assert result["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
        assert result["my_size"] == "XL"
        assert result["product_type"] == "CL"

    def test_sku_without_size(self):
        """Test SKU format without size suffix."""
        result = extract_sku_from_article("CL_OC_MEN_LINE52_BLACK", None)
        assert result["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
        assert result["sku_id"] is None
        assert result["my_size"] is None

    def test_numeric_article_with_offer(self):
        """Test numeric Kaspi article with offer context."""
        result = extract_sku_from_article(
            "12345", "Рашгард Line52 черный XL"
        )
        assert result["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
        assert result["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
        assert result["my_size"] == "XL"

    def test_beli_model(self):
        """Test LINE model extraction."""
        result = extract_sku_from_article("ABC123", "Line51 белый 2XL")
        assert result["sku_key"] == "CL_OC_MEN_LINE51_WHITE"
        assert result["sku_id"] == "CL_OC_MEN_LINE51_WHITE_2XL"
        assert result["my_size"] == "2XL"

    def test_unknown_article(self):
        """Test unknown article format."""
        result = extract_sku_from_article("102492502", "Unknown product черный 48")
        assert result["my_size"] == "48"
        # sku_key may be None if model not recognized
        assert result["product_type"] is None or result["product_type"] == "CL"

    def test_empty_article(self):
        """Test empty/None article."""
        result = extract_sku_from_article("", None)
        assert result["sku_key"] is None
        assert result["sku_id"] is None

        result = extract_sku_from_article(None, None)
        assert result["sku_key"] is None

    def test_acmewear_line61_article_maps_to_canonical_sku(self):
        """New ACMEWEAR line61 article aliases should map to canonical sku_key."""
        result = extract_sku_from_article(
            "OF_SUIT-61_BLK_3XL",
            "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL",
        )
        assert result["sku_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
        assert result["my_size"] == "3XL"
        assert result["sku_id"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL"

    def test_acmewear_line61_article_maps_xl_numeric_variant(self):
        """XL numeric variants should normalize to XL for canonical mapping."""
        result = extract_sku_from_article(
            "OF_SUIT-61_BLK_XL_48",
            "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL_48 черный 48",
        )
        assert result["sku_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
        assert result["my_size"] == "XL"
        assert result["sku_id"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL"


class TestParseActiveOrders:
    """Tests for full file parsing."""

    @pytest.fixture
    def sample_excel_file(self, tmp_path):
        """Create a sample Excel file for testing."""
        df = pd.DataFrame({
            "№ заказа": ["123456", "789012", ""],
            "Дата поступления заказа": ["2025-01-15", "15.01.2025", None],
            "Название товара в Kaspi Магазине": [
                "Line52 черный XL",
                "Line51 белый M",
                "Empty row",
            ],
            "Артикул": [
                "CL_OC_MEN_LINE52_BLACK_XL",
                "12345",
                "",
            ],
            "Сумма": [8000, 9000, 0],
            "Количество": [1, 2, 0],
            "Стоимость доставки для продавца": [855.8, 0, 0],
            "Стоимость доставки для покупателя": [0, 500, 0],
            "Статус": ["Завершен", "Доставка", ""],
        })
        file_path = tmp_path / "test_orders.xlsx"
        df.to_excel(file_path, index=False)
        return file_path

    def test_parse_basic(self, sample_excel_file):
        """Test basic parsing functionality."""
        records = parse_active_orders(sample_excel_file, "UNIVERSAL")

        # Should have 2 records (empty order_id row skipped)
        assert len(records) == 2

        # Check first record
        r1 = records[0]
        assert r1["order_id"] == "123456"
        assert r1["store_code"] == "UNIVERSAL"
        assert r1["order_date"] == "2025-01-15"
        assert r1["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
        assert r1["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
        assert r1["quantity"] == 1
        assert r1["sell_price_kzt"] == 8000
        assert r1["delivery_fee_seller"] == 855.8
        assert r1["channel"] == "kaspi"

    def test_parse_date_formats(self, sample_excel_file):
        """Test different date format handling."""
        records = parse_active_orders(sample_excel_file, "UNIVERSAL")

        # First record: ISO format
        assert records[0]["order_date"] == "2025-01-15"
        # Second record: Russian format (dd.mm.yyyy)
        assert records[1]["order_date"] == "2025-01-15"

    def test_parse_with_inference(self, sample_excel_file):
        """Test SKU inference from offer when article is numeric."""
        records = parse_active_orders(sample_excel_file, "UNIVERSAL")

        # Second record should infer SKU from offer
        r2 = records[1]
        assert r2["order_id"] == "789012"
        assert r2["sku_key"] == "CL_OC_MEN_LINE51_WHITE"
        assert r2["my_size"] == "M"

    def test_file_not_found(self):
        """Test error on missing file."""
        with pytest.raises(FileNotFoundError):
            parse_active_orders("/nonexistent/file.xlsx", "UNIVERSAL")

    def test_missing_columns_validation(self, tmp_path):
        """Test validation of required columns."""
        # Create file missing required columns
        df = pd.DataFrame({
            "SomeColumn": [1, 2, 3],
            "OtherColumn": ["a", "b", "c"],
        })
        file_path = tmp_path / "bad_columns.xlsx"
        df.to_excel(file_path, index=False)

        with pytest.raises(ValueError) as exc_info:
            parse_active_orders(file_path, "UNIVERSAL", validate=True)

        assert "Missing required columns" in str(exc_info.value)

    def test_skip_validation(self, tmp_path):
        """Test skipping validation."""
        df = pd.DataFrame({
            "SomeColumn": [1, 2, 3],
        })
        file_path = tmp_path / "minimal.xlsx"
        df.to_excel(file_path, index=False)

        # Should not raise when validate=False
        records = parse_active_orders(file_path, "UNIVERSAL", validate=False)
        assert len(records) == 0  # No order_id column, so all rows skipped


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
