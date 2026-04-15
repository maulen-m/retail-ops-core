"""
Unit tests for kaspi_export_parser.py (Phase 9.5)

TASK-117: Tests for the order tracking parser.
"""
import pytest
from datetime import date, datetime
from pathlib import Path
import tempfile
import pandas as pd

from core.parsers.kaspi_export_parser import (
    parse_active_orders,
    filter_for_shipment,
    normalize_order,
    get_dedup_key,
    deduplicate_orders,
    load_column_config,
    _parse_date,
    _normalize_store_code,
    _map_status_to_internal,
    _extract_size_from_article,
    _extract_sku_parts,
    ParseResult,
)


class TestDateParsing:
    """Tests for date parsing with dayfirst=True."""

    @pytest.fixture
    def config(self):
        """Load column config."""
        return load_column_config()

    def test_dd_mm_yyyy_format(self, config):
        """Test DD.MM.YYYY format (Kaspi default)."""
        # This is the critical test - dayfirst=True is required
        result = _parse_date("06.12.2025", config)
        assert result == "2025-12-06"  # December 6th, not June 12th

    def test_yyyy_mm_dd_format(self, config):
        """Test YYYY-MM-DD format."""
        result = _parse_date("2025-12-06", config)
        assert result == "2025-12-06"

    def test_datetime_object(self, config):
        """Test datetime object input."""
        dt = datetime(2025, 12, 6, 14, 30)
        result = _parse_date(dt, config)
        assert result == "2025-12-06"

    def test_date_object(self, config):
        """Test date object input."""
        d = date(2025, 12, 6)
        result = _parse_date(d, config)
        assert result == "2025-12-06"

    def test_none_value(self, config):
        """Test None input."""
        result = _parse_date(None, config)
        assert result is None

    def test_empty_string(self, config):
        """Test empty string input."""
        import pandas as pd
        result = _parse_date(pd.NA, config)
        assert result is None

    def test_with_time(self, config):
        """Test date with time component."""
        result = _parse_date("06.12.2025 14:30:00", config)
        assert result == "2025-12-06"


class TestStoreCodeNormalization:
    """Tests for store code normalization."""

    @pytest.fixture
    def config(self):
        """Load column config."""
        return load_column_config()

    def test_pp1_variations(self, config):
        """Test PP1 store name variations."""
        assert _normalize_store_code("AcmeWear PP1", config) == "PP1"
        assert _normalize_store_code("PP1", config) == "PP1"
        assert _normalize_store_code("ПП1", config) == "PP1"

    def test_universal_variations(self, config):
        """Test Universal store name variations."""
        assert _normalize_store_code("Universal", config) == "UNIVERSAL"
        assert _normalize_store_code("Универсал", config) == "UNIVERSAL"

    def test_case_insensitive(self, config):
        """Test case-insensitive matching."""
        assert _normalize_store_code("universal", config) == "UNIVERSAL"
        assert _normalize_store_code("UNIVERSAL", config) == "UNIVERSAL"

    def test_kaspi_warehouse_codes_map_to_canonical_store_codes(self, config):
        """ActiveOrders warehouse ids should resolve to canonical store codes."""
        assert _normalize_store_code("30000001_PP1", config) == "UNIVERSAL"
        assert _normalize_store_code("30137883_PP1", config) == "ACMEWEAR"
        assert _normalize_store_code("30000002_PP1", config) == "STOREB"
        assert _normalize_store_code("30000002_PP2", config) == "STOREB"
        assert _normalize_store_code("30362323_PP1", config) == "MELVIS"

    def test_unknown_store(self, config):
        """Test unknown store name."""
        result = _normalize_store_code("SomeUnknownStore", config)
        # Should return default or the original
        assert result in ["UNKNOWN", "SomeUnknownStore"]

    def test_none_value(self, config):
        """Test None input."""
        result = _normalize_store_code(None, config)
        assert result == "UNKNOWN"


class TestStatusMapping:
    """Tests for status to internal mapping."""

    @pytest.fixture
    def config(self):
        """Load column config."""
        return load_column_config()

    def test_awaiting_courier_status(self, config):
        """Test the critical status for shipment filtering."""
        result = _map_status_to_internal("Ожидает передачи курьеру", config)
        assert result == "READY"

    def test_accepted_status(self, config):
        """Test accepted status."""
        result = _map_status_to_internal("Принят", config)
        assert result == "NEW"

    def test_shipped_status(self, config):
        """Test shipped status."""
        result = _map_status_to_internal("Передан курьеру", config)
        assert result == "SHIPPED"

    def test_completed_status(self, config):
        """Test completed status."""
        result = _map_status_to_internal("Завершен", config)
        assert result == "COMPLETED"

    def test_cancelled_status(self, config):
        """Test cancelled status."""
        result = _map_status_to_internal("Отменен", config)
        assert result == "CANCELLED"

    def test_unknown_status(self, config):
        """Test unknown status defaults to NEW."""
        result = _map_status_to_internal("SomeUnknownStatus", config)
        assert result == "NEW"


class TestSizeExtraction:
    """Tests for size extraction from article."""

    def test_suffix_size(self):
        """Test size as suffix with underscore."""
        assert _extract_size_from_article("CL_OC_MEN_LINE52_BLACK_XL") == "XL"
        assert _extract_size_from_article("CL_OC_MEN_LINE52_BLACK_2XL") == "2XL"

    def test_standalone_size(self):
        """Test standalone size codes."""
        assert _extract_size_from_article("PRODUCT_2XL") == "2XL"
        assert _extract_size_from_article("PRODUCT_3XL") == "3XL"

    def test_numeric_size(self):
        """Test numeric sizes."""
        assert _extract_size_from_article("PRODUCT_48") == "48"

    def test_no_size(self):
        """Test when no size present."""
        assert _extract_size_from_article("CL_OC_MEN_LINE52_BLACK") is None
        assert _extract_size_from_article("12345") is None


class TestSkuExtraction:
    """Tests for SKU parts extraction."""

    def test_full_sku_format(self):
        """Test complete SKU format extraction."""
        result = _extract_sku_parts("CL_OC_MEN_LINE52_BLACK_XL")
        assert result["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
        assert result["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
        assert result["my_size"] == "XL"

    def test_sku_without_size(self):
        """Test SKU without size suffix."""
        result = _extract_sku_parts("CL_OC_MEN_LINE52_BLACK")
        assert result["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
        assert result["sku_id"] is None
        assert result["my_size"] is None

    def test_numeric_article(self):
        """Test numeric article (no SKU extraction)."""
        result = _extract_sku_parts("12345678")
        assert result["sku_key"] is None
        assert result["sku_id"] is None


class TestDedupKey:
    """Tests for deduplication key generation."""

    def test_standard_key(self):
        """Test standard dedup key generation."""
        order = {
            "order_id": "123456",
            "sku_id": "CL_OC_MEN_LINE52_BLACK_XL",
            "store_code": "PP1"
        }
        key = get_dedup_key(order)
        assert key == ("123456", "CL_OC_MEN_LINE52_BLACK_XL", "PP1")

    def test_key_with_fallback(self):
        """Test dedup key with kaspi_offer_name fallback."""
        order = {
            "order_id": "123456",
            "sku_id": None,
            "kaspi_offer_name": "Line52 черный XL",
            "store_code": "PP1"
        }
        key = get_dedup_key(order)
        assert key == ("123456", "Line52 черный XL", "PP1")

    def test_multi_line_different_keys(self):
        """Test that multi-line orders have different dedup keys."""
        order1 = {
            "order_id": "123456",
            "sku_id": "CL_OC_MEN_LINE52_BLACK_XL",
            "store_code": "PP1"
        }
        order2 = {
            "order_id": "123456",  # Same order
            "sku_id": "CL_OC_MEN_LINE51_WHITE_M",  # Different SKU
            "store_code": "PP1"
        }
        key1 = get_dedup_key(order1)
        key2 = get_dedup_key(order2)
        assert key1 != key2  # Different keys for multi-line orders


class TestDeduplication:
    """Tests for order deduplication."""

    def test_no_duplicates(self):
        """Test list without duplicates."""
        orders = [
            {"order_id": "1", "sku_id": "A", "store_code": "PP1"},
            {"order_id": "2", "sku_id": "B", "store_code": "PP1"},
        ]
        unique, dupes = deduplicate_orders(orders)
        assert len(unique) == 2
        assert len(dupes) == 0

    def test_with_duplicates(self):
        """Test list with duplicates."""
        orders = [
            {"order_id": "1", "sku_id": "A", "store_code": "PP1"},
            {"order_id": "1", "sku_id": "A", "store_code": "PP1"},  # Duplicate
            {"order_id": "2", "sku_id": "B", "store_code": "PP1"},
        ]
        unique, dupes = deduplicate_orders(orders)
        assert len(unique) == 2
        assert len(dupes) == 1

    def test_multi_line_not_duplicate(self):
        """Test that multi-line orders are not marked as duplicates."""
        orders = [
            {"order_id": "1", "sku_id": "A", "store_code": "PP1"},
            {"order_id": "1", "sku_id": "B", "store_code": "PP1"},  # Same order, different SKU
        ]
        unique, dupes = deduplicate_orders(orders)
        assert len(unique) == 2  # Both should be kept
        assert len(dupes) == 0


class TestFilterForShipment:
    """Tests for shipment filtering."""

    def test_ready_status_filter(self):
        """Test that only READY orders are included."""
        orders = [
            {"internal_status": "READY", "planned_shipment_date": "2025-12-06"},
            {"internal_status": "NEW", "planned_shipment_date": "2025-12-06"},
            {"internal_status": "SHIPPED", "planned_shipment_date": "2025-12-06"},
        ]
        result = filter_for_shipment(orders, target_date=date(2025, 12, 6))
        assert len(result) == 1
        assert result[0]["internal_status"] == "READY"

    def test_date_filter(self):
        """Test that future orders are excluded."""
        orders = [
            {"internal_status": "READY", "planned_shipment_date": "2025-12-05"},
            {"internal_status": "READY", "planned_shipment_date": "2025-12-06"},
            {"internal_status": "READY", "planned_shipment_date": "2025-12-07"},  # Future
        ]
        result = filter_for_shipment(orders, target_date=date(2025, 12, 6))
        assert len(result) == 2

    def test_signature_filter(self):
        """Test that signature-required orders are excluded by default."""
        orders = [
            {"internal_status": "READY", "planned_shipment_date": "2025-12-06", "signature_required": False},
            {"internal_status": "READY", "planned_shipment_date": "2025-12-06", "signature_required": True},
        ]
        result = filter_for_shipment(orders, target_date=date(2025, 12, 6))
        assert len(result) == 1

    def test_signature_filter_include(self):
        """Test including signature-required orders."""
        orders = [
            {"internal_status": "READY", "planned_shipment_date": "2025-12-06", "signature_required": True},
        ]
        result = filter_for_shipment(
            orders,
            target_date=date(2025, 12, 6),
            include_signature_required=True
        )
        assert len(result) == 1


class TestParseActiveOrders:
    """Tests for full file parsing."""

    @pytest.fixture
    def sample_excel_file(self, tmp_path):
        """Create a sample Excel file with Russian columns."""
        df = pd.DataFrame({
            "№ заказа": ["123456789", "987654321", ""],
            "Статус": [
                "Ожидает передачи курьеру",  # READY
                "Принят",  # NEW
                "",
            ],
            "Дата создания": ["01.12.2025", "02.12.2025", None],
            "Плановая дата передачи курьеру": ["06.12.2025", "07.12.2025", None],
            "Название товара": [
                "Комплект Line52 черный XL",
                "Комплект Line51 белый M",
                "Empty",
            ],
            "Артикул": [
                "CL_OC_MEN_LINE52_BLACK_XL",
                "12345",
                "",
            ],
            "Цена": [8000, 9000, 0],
            "Склад": ["AcmeWear PP1", "Universal", ""],
            "Требуется подписание": ["Не требуется", "Не требуется", ""],
        })
        file_path = tmp_path / "ActiveOrders_test.xlsx"
        df.to_excel(file_path, index=False)
        return file_path

    def test_parse_basic(self, sample_excel_file):
        """Test basic parsing functionality."""
        result = parse_active_orders(sample_excel_file)

        assert isinstance(result, ParseResult)
        assert result.total_rows == 3
        assert result.parsed_rows == 2  # Empty order_id row skipped

    def test_parse_order_fields(self, sample_excel_file):
        """Test that order fields are correctly parsed."""
        result = parse_active_orders(sample_excel_file)
        orders = result.orders

        # First order
        o1 = orders[0]
        assert o1["order_id"] == "123456789"
        assert o1["store_code"] == "PP1"
        assert o1["kaspi_article"] == "CL_OC_MEN_LINE52_BLACK_XL"
        assert o1["internal_status"] == "READY"
        assert o1["planned_shipment_date"] == "2025-12-06"
        assert o1["unit_price_kzt"] == 8000.0

    def test_parse_date_dayfirst(self, sample_excel_file):
        """Test that dates are parsed with dayfirst=True."""
        result = parse_active_orders(sample_excel_file)
        orders = result.orders

        # 06.12.2025 should be December 6th, not June 12th
        assert orders[0]["planned_shipment_date"] == "2025-12-06"

    def test_parse_store_normalization(self, sample_excel_file):
        """Test that store names are normalized."""
        result = parse_active_orders(sample_excel_file)
        orders = result.orders

        assert orders[0]["store_code"] == "PP1"
        assert orders[1]["store_code"] == "UNIVERSAL"

    def test_parse_preserves_raw_kaspi_article_for_article_map_reconciliation(self, tmp_path):
        df = pd.DataFrame({
            "№ заказа": ["889181585"],
            "Статус": ["Ожидает передачи курьеру"],
            "Дата создания": ["15.04.2026"],
            "Плановая дата передачи курьеру": ["15.04.2026"],
            "Название товара": ["Спортивный костюм ACMEWEAR OF_SUIT-61_BLK_K-O_4XL_58 черный, белый 4XL"],
            "Артикул": ["CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_159720193"],
            "Цена": [13990],
            "Склад": ["30137883_PP1"],
            "Требуется подписание": ["Не требуется"],
        })
        file_path = tmp_path / "ActiveOrders_acmewear_alias.xlsx"
        df.to_excel(file_path, index=False)

        result = parse_active_orders(file_path)

        assert result.parsed_rows == 1
        order = result.orders[0]
        assert order["kaspi_article"] == "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_159720193"
        assert order["sku_key"] == "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2"
        assert order["sku_id"] == "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_4XL"
        assert order["my_size"] == "4XL"

    def test_file_not_found(self):
        """Test error on missing file."""
        with pytest.raises(FileNotFoundError):
            parse_active_orders(Path("/nonexistent/file.xlsx"))

    def test_missing_columns(self, tmp_path):
        """Test validation of required columns."""
        df = pd.DataFrame({
            "SomeColumn": [1, 2, 3],
            "OtherColumn": ["a", "b", "c"],
        })
        file_path = tmp_path / "bad_columns.xlsx"
        df.to_excel(file_path, index=False)

        with pytest.raises(ValueError) as exc_info:
            parse_active_orders(file_path)

        assert "Missing required columns" in str(exc_info.value)


class TestNormalizeOrder:
    """Tests for order normalization."""

    def test_normalize_preserves_fields(self):
        """Test that normalize_order preserves important fields."""
        raw = {
            "order_id": "123456",
            "store_code": "PP1",
            "channel_code": "KSP",
            "kaspi_offer_name": "Test Product",
            "sku_key": "CL_OC_MEN_LINE52_BLACK",
            "sku_id": "CL_OC_MEN_LINE52_BLACK_XL",
            "my_size": "XL",
            "quantity": 1,
            "unit_price_kzt": 8000.0,
            "created_at": "2025-12-01",
            "planned_shipment_date": "2025-12-06",
            "kaspi_status": "Ожидает передачи курьеру",
            "internal_status": "READY",
            "source": "EXCEL_EXPORT",
        }
        normalized = normalize_order(raw)

        assert normalized["order_id"] == "123456"
        assert normalized["store_code"] == "PP1"
        assert normalized["internal_status"] == "READY"
        assert normalized["source"] == "EXCEL_EXPORT"

    def test_normalize_defaults(self):
        """Test that normalize_order applies defaults."""
        raw = {"order_id": "123456", "store_code": "PP1"}
        normalized = normalize_order(raw)

        assert normalized["quantity"] == 1
        assert normalized["internal_status"] == "NEW"
        assert normalized["channel_code"] == "KSP"
        assert normalized["source"] == "EXCEL_EXPORT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
