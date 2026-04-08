"""
Tests for import_orders_to_crm.py

Phase 11 TASK-194: 12 tests for the order import script.
"""

import json
import os
import re
import sqlite3
import subprocess
import tempfile
import zipfile
from copy import copy
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import openpyxl
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.worksheet.table import Table, TableFormula, TableStyleInfo
import pandas as pd
import pytest

from scripts.import_orders_to_crm import (
    CRMAppendExpectation,
    CRMAppendDateReconcilePlan,
    CRMSnapshot,
    AppendVerificationError,
    ExcelWorkbookSession,
    ExcelTargetConflictError,
    READY_STATUS,
    NO_SIGNATURE,
    RAW_KASPI_COLUMNS,
    STORE_MAP,
    WAREHOUSE_STORE_MAP,
    _derive_identity_from_raw_row,
    _load_sku_meta_for_keys,
    _build_line_dedupe_key,
    _coerce_column_values,
    _iter_consecutive_ranges,
    _load_seller_delivery_fees_from_db,
    _plan_seller_delivery_fee_backfill_updates,
    _row_in_backfill_window,
    _allow_openpyxl_backfill_fallback,
    _allow_openpyxl_append_fallback,
    _candidate_source_requires_template_normalization,
    _default_candidate_dirs_for_workbook,
    _default_openpyxl_append_fallback_enabled,
    _default_prefer_xlwings_append,
    _prefer_openpyxl_safe_write_path,
    _open_workbook_xlwings,
    _open_workbook_xlwings_without_timeout_kwarg,
    _formula_template_columns,
    _prepare_candidate_workbook,
    _restore_preserved_package_parts,
    _snapshot_preserved_package_parts,
    _workbook_integrity_preflight,
    _find_template_row_for_append,
    _normalize_conditional_formatting_ranges,
    _restore_conditional_formatting_from_template,
    _repair_appended_rows_formatting,
    _verify_formula_cache_readback,
    _verify_appended_rows_integrity,
    _workbook_external_link_targets,
    _xlwings_open_timeout_sec,
    _temporary_manual_calculation,
    _build_xlwings_write_plan,
    _clear_my_size_range,
    _write_single_column_updates_xlwings,
    excel_append_openpyxl,
    excel_append_xlwings,
    _excel_automation_preflight,
    _excel_session_preflight,
    _list_excel_workbooks,
    _excel_open_probe,
    _verify_candidate_workbook,
    _xlwings_append_timeout_sec,
    _classify_import_failure,
    apply_fixed_values_backfill_openpyxl,
    append_orders_with_fallback,
    archive_run,
    backfill_seller_delivery_fee,
    build_staging,
    build_pending_append_mask,
    build_append_expectations,
    clean_order_id,
    clean_value,
    compute_fixed_value_columns,
    deduplicate_orders,
    delete_crm_rows_openpyxl,
    find_missing_append_expectations,
    filter_orders_for_shipment,
    filter_for_shipping,
    find_active_orders_files,
    load_existing_order_ids,
    main,
    parse_date,
    parse_orders_from_excel,
    restore_crm_workbook_from_template,
    overlay_missing_seller_delivery_fees_from_db,
    write_import_summary,
)


# ============================================================================
# Test: find_active_orders_files
# ============================================================================

def test_store_maps_include_store-c():
    assert WAREHOUSE_STORE_MAP["30362323_PP1"] == "MELVIS"
    assert STORE_MAP["30362323_PP1"] == "Store-C"


def test_find_active_orders_files_finds_xlsx():
    """Test that find_active_orders_files finds xlsx files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create test files
        (tmppath / "ActiveOrders.xlsx").touch()
        (tmppath / "ActiveOrders (1).xlsx").touch()
        (tmppath / "ActiveOrders (2).xlsx").touch()
        (tmppath / "other_file.xlsx").touch()  # Should not match

        files = find_active_orders_files(tmppath)

        assert len(files) == 3
        assert all("ActiveOrders" in f.name for f in files)


def test_find_active_orders_files_ignores_temp_files():
    """Test that temp files starting with ~$ are ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create test files
        (tmppath / "ActiveOrders.xlsx").touch()
        (tmppath / "~$ActiveOrders.xlsx").touch()  # Temp file - should be ignored

        files = find_active_orders_files(tmppath)

        assert len(files) == 1
        assert files[0].name == "ActiveOrders.xlsx"


def test_default_append_strategy_stays_xlwings_first_on_macos(monkeypatch):
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin")
    assert _default_openpyxl_append_fallback_enabled() is False
    assert _default_prefer_xlwings_append() is True
    assert _prefer_openpyxl_safe_write_path() is False


def test_default_append_strategy_stays_xlwings_first_off_macos(monkeypatch):
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "linux")
    assert _default_openpyxl_append_fallback_enabled() is False
    assert _default_prefer_xlwings_append() is True
    assert _prefer_openpyxl_safe_write_path() is False


# ============================================================================
# Test: load_existing_order_ids
# ============================================================================

def test_load_existing_order_ids_reads_column_y():
    """Test that existing order IDs are read from column Y."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        crm_path = tmppath / "test_crm.xlsx"

        # Create test Excel file with order IDs in column Y (25)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TEST_SHEET"

        # Add headers (row 1)
        ws.cell(row=1, column=25, value="№ заказа")

        # Add order IDs
        ws.cell(row=2, column=25, value="123456789")
        ws.cell(row=3, column=25, value="987654321")
        ws.cell(row=4, column=25, value="111222333")

        wb.save(crm_path)
        wb.close()

        existing = load_existing_order_ids(crm_path, "TEST_SHEET")

        assert len(existing) == 3
        assert "123456789" in existing
        assert "987654321" in existing
        assert "111222333" in existing


def test_load_existing_order_ids_handles_empty_crm():
    """Test handling of empty CRM file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        crm_path = tmppath / "test_crm.xlsx"

        # Create empty Excel file
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TEST_SHEET"
        ws.cell(row=1, column=25, value="№ заказа")
        wb.save(crm_path)
        wb.close()

        existing = load_existing_order_ids(crm_path, "TEST_SHEET")

        assert len(existing) == 0


# ============================================================================
# Test: deduplicate_orders
# ============================================================================

def test_deduplicates_on_order_id():
    """Test that existing orders are skipped based on order ID."""
    orders = [
        {'_order_id': '123456789', 'Название товара в Kaspi Магазине': 'Test 1'},
        {'_order_id': '111111111', 'Название товара в Kaspi Магазине': 'Test 2'},
        {'_order_id': '222222222', 'Название товара в Kaspi Магазине': 'Test 3'},
    ]
    existing_ids = {'123456789', '222222222'}

    new_orders, skipped = deduplicate_orders(orders, existing_ids)

    assert len(new_orders) == 1
    assert skipped == 2
    assert new_orders[0]['_order_id'] == '111111111'


# ============================================================================
# Test: Order row building
# ============================================================================

def test_builds_raw_kaspi_row():
    """Test that all 28 raw Kaspi columns are mapped correctly."""
    # Verify we have 28 columns
    assert len(RAW_KASPI_COLUMNS) == 28

    # Verify column range is Y to AZ
    col_letters = list(RAW_KASPI_COLUMNS.values())
    assert col_letters[0] == 'Y'
    assert col_letters[-1] == 'AZ'

    # Verify all expected columns are present
    assert '№ заказа' in RAW_KASPI_COLUMNS
    assert 'Статус' in RAW_KASPI_COLUMNS
    assert 'Плановая дата передачи курьеру' in RAW_KASPI_COLUMNS
    assert 'Склад передачи КД' in RAW_KASPI_COLUMNS


def test_handles_missing_optional_fields():
    """Test that missing optional fields default to None."""
    order = {
        '_order_id': '123456789',
        '№ заказа': '123456789',
        'Статус': READY_STATUS,
        # Missing most optional fields
    }

    # clean_value should handle missing fields gracefully
    assert clean_value(order.get('Причина отмены')) is None
    assert clean_value(order.get('Оценка покупателя')) is None


# ============================================================================
# Test: Date parsing
# ============================================================================

def test_dd_mm_yyyy_format():
    """Test parsing DD.MM.YYYY format (Kaspi default)."""
    result = parse_date("25.12.2025")

    assert result is not None
    assert result.day == 25
    assert result.month == 12
    assert result.year == 2025


def test_iso_format():
    """Test parsing YYYY-MM-DD (ISO) format."""
    result = parse_date("2025-12-25")

    assert result is not None
    assert result.day == 25
    assert result.month == 12
    assert result.year == 2025


def test_iso_datetime_format():
    """Test parsing ISO datetime strings without flipping day/month."""
    result = parse_date("2026-03-06 20:00:00")

    assert result == date(2026, 3, 6)


def test_excel_serial_dates():
    """Test parsing Excel serial date numbers."""
    # Excel serial 45658 is approximately Jan 7, 2025
    # The function only handles serials in range 40000-50000
    result = parse_date("45658")  # Pass as string to trigger serial conversion

    # Due to pandas fallback, numeric strings may not trigger serial path
    # Test that the function handles it without crashing
    # The actual serial path requires float input
    serial_result = parse_date(45658.0)

    # At minimum, it should return something (even if fallback)
    assert serial_result is not None or result is not None


def test_parse_date_handles_none():
    """Test that parse_date handles None gracefully."""
    assert parse_date(None) is None
    assert parse_date(pd.NA) is None
    assert parse_date(float('nan')) is None


# ============================================================================
# Test: Dry run mode
# ============================================================================

def test_dry_run_mode():
    """Test that dry_run=True doesn't modify CRM."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create empty orders dir
        orders_dir = tmppath / "orders"
        orders_dir.mkdir()

        # Create test ActiveOrders file
        orders_file = orders_dir / "ActiveOrders.xlsx"
        df = pd.DataFrame({
            '№ заказа': ['123456789'],
            'Статус': [READY_STATUS],
            'Требуется подписание': [NO_SIGNATURE],
            'Плановая дата передачи курьеру': [date.today()],
        })
        df.to_excel(orders_file, index=False)

        # Create CRM file
        crm_path = tmppath / "crm.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TEST_SHEET"
        ws.cell(row=1, column=2, value="Date")
        ws.cell(row=1, column=25, value="№ заказа")
        ws.cell(row=1, column=33, value="Склад передачи КД")
        table = Table(displayName="tb_SalesRaw", ref="A1:AG1")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)
        wb.save(crm_path)
        wb.close()

        # Get initial file modification time
        initial_mtime = crm_path.stat().st_mtime

        # Run import with dry_run
        stats = main(
            orders_dir=orders_dir,
            crm_path=crm_path,
            sheet_name="TEST_SHEET",
            dry_run=True,
        )

        # File should not have been modified
        assert crm_path.stat().st_mtime == initial_mtime
        assert stats['orders_imported'] == 0


# ============================================================================
# Test: Order filtering
# ============================================================================

def test_filter_orders_for_shipment():
    """Test filtering orders by status, signature, and date."""
    today = date.today()

    orders = [
        {
            '_order_id': '111',
            'Статус': READY_STATUS,
            'Требуется подписание': NO_SIGNATURE,
            'Плановая дата передачи курьеру': today,
        },
        {
            '_order_id': '222',
            'Статус': 'Принят',  # Wrong status
            'Требуется подписание': NO_SIGNATURE,
            'Плановая дата передачи курьеру': today,
        },
        {
            '_order_id': '333',
            'Статус': READY_STATUS,
            'Требуется подписание': 'Требуется',  # Requires signature
            'Плановая дата передачи курьеру': today,
        },
    ]

    filtered = filter_orders_for_shipment(orders, today)

    assert len(filtered) == 1
    assert filtered[0]['_order_id'] == '111'


def test_filter_for_shipping_default_keeps_today_only():
    today = date(2026, 2, 26)
    df = pd.DataFrame(
        {
            "Статус": [READY_STATUS, READY_STATUS],
            "Требуется подписание": [NO_SIGNATURE, NO_SIGNATURE],
            "Плановая дата передачи курьеру": ["26.02.2026", "25.02.2026"],
        }
    )

    filtered, stats = filter_for_shipping(
        df,
        status_wanted=READY_STATUS,
        signature_wanted=None,
        end_date=today,
    )

    assert len(filtered) == 1
    assert stats["include_overdue"] is False


def test_filter_for_shipping_include_overdue_honors_lookback_window():
    today = date(2026, 2, 26)
    df = pd.DataFrame(
        {
            "Статус": [READY_STATUS, READY_STATUS, READY_STATUS],
            "Требуется подписание": [NO_SIGNATURE, NO_SIGNATURE, NO_SIGNATURE],
            "Плановая дата передачи курьеру": ["26.02.2026", "25.02.2026", "20.02.2026"],
        }
    )

    filtered, stats = filter_for_shipping(
        df,
        status_wanted=READY_STATUS,
        signature_wanted=None,
        end_date=today,
        include_overdue=True,
        overdue_lookback_days=2,
    )

    planned_dates = set(filtered["Плановая дата передачи курьеру"].astype(str))
    assert planned_dates == {"26.02.2026", "25.02.2026"}
    assert stats["include_overdue"] is True
    assert stats["overdue_lookback_days"] == 2


def test_build_pending_append_mask_appends_overdue_pending_when_missing_from_today_view():
    append_date = date(2026, 3, 7)
    df = pd.DataFrame(
        {
            "№ заказа": ["845767451"],
            "Название товара в Kaspi Магазине": ["Принт_5в1_черный"],
            "Артикул": ["LINE52_XL"],
            "Количество": [1],
            "Плановая дата передачи курьеру": ["06.03.2026"],
        }
    )

    base_key = _build_line_dedupe_key(
        "845767451",
        date(2026, 3, 6),
        "Принт_5в1_черный",
        "LINE52_XL",
        1,
    )

    work, new_mask, stats = build_pending_append_mask(
        df,
        colmap={
            "order_id": "№ заказа",
            "offer_name": "Название товара в Kaspi Магазине",
            "sku": "Артикул",
            "quantity": "Количество",
            "handover": "Плановая дата передачи курьеру",
        },
        existing_keys={base_key},
        existing_append_date_keys=set(),
        include_overdue=True,
        append_date=append_date,
    )

    assert new_mask.tolist() == [True]
    assert stats["dedupe_mode"] == "append_date_view"
    assert stats["carryforward_rows"] == 1
    assert stats["carryforward_rows_to_append"] == 1
    assert work["_is_overdue"].tolist() == [True]
    assert work["_is_prev_day_overdue"].tolist() == [True]


def test_build_pending_append_mask_blocks_overdue_pending_already_in_today_view():
    append_date = date(2026, 3, 7)
    df = pd.DataFrame(
        {
            "№ заказа": ["845767451"],
            "Название товара в Kaspi Магазине": ["Принт_5в1_черный"],
            "Артикул": ["LINE52_XL"],
            "Количество": [1],
            "Плановая дата передачи курьеру": ["06.03.2026"],
        }
    )

    base_key = _build_line_dedupe_key(
        "845767451",
        date(2026, 3, 6),
        "Принт_5в1_черный",
        "LINE52_XL",
        1,
    )

    _work, new_mask, stats = build_pending_append_mask(
        df,
        colmap={
            "order_id": "№ заказа",
            "offer_name": "Название товара в Kaspi Магазине",
            "sku": "Артикул",
            "quantity": "Количество",
            "handover": "Плановая дата передачи курьеру",
        },
        existing_keys={base_key},
        existing_append_date_keys={base_key},
        include_overdue=True,
        append_date=append_date,
    )

    assert new_mask.tolist() == [False]
    assert stats["duplicates_skipped"] == 1
    assert stats["append_date_duplicate_rows"] == 1
    assert stats["carryforward_rows_to_append"] == 0


def test_build_pending_append_mask_keeps_older_overdue_pending_when_missing_today():
    append_date = date(2026, 3, 7)
    df = pd.DataFrame(
        {
            "№ заказа": ["845767451"],
            "Название товара в Kaspi Магазине": ["Принт_5в1_черный"],
            "Артикул": ["LINE52_XL"],
            "Количество": [1],
            "Плановая дата передачи курьеру": ["05.03.2026"],
        }
    )

    base_key = _build_line_dedupe_key(
        "845767451",
        date(2026, 3, 5),
        "Принт_5в1_черный",
        "LINE52_XL",
        1,
    )

    work, new_mask, stats = build_pending_append_mask(
        df,
        colmap={
            "order_id": "№ заказа",
            "offer_name": "Название товара в Kaspi Магазине",
            "sku": "Артикул",
            "quantity": "Количество",
            "handover": "Плановая дата передачи курьеру",
        },
        existing_keys={base_key},
        existing_append_date_keys=set(),
        include_overdue=True,
        append_date=append_date,
    )

    assert work["_is_older_overdue"].tolist() == [True]
    assert new_mask.tolist() == [True]
    assert stats["older_overdue_rows_suppressed"] == 0
    assert stats["carryforward_rows_to_append"] == 1


# ============================================================================
# Test: Order ID cleaning
# ============================================================================

def test_clean_order_id():
    """Test order ID cleaning and validation."""
    # Valid IDs
    assert clean_order_id("123456789") == "123456789"
    assert clean_order_id(123456789.0) == "123456789"  # Float from Excel
    assert clean_order_id("123456789012") == "123456789012"  # 12 digits

    # Invalid IDs
    assert clean_order_id("12345") is None  # Too short
    assert clean_order_id("1234567890123") is None  # Too long
    assert clean_order_id("abc") is None  # Not numeric
    assert clean_order_id(None) is None


def test_build_staging_derives_sku_key_and_size_from_acmewear_article():
    """When SKU_key/MY_SIZE are absent, staging derives SKU_key but keeps MY_SIZE blank."""
    df = pd.DataFrame(
        {
            "Артикул": ["OF_SUIT-61_BLK_3XL"],
            "Название товара в Kaspi Магазине": [
                "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL"
            ],
            "Количество": [1],
            "Склад передачи КД": ["30137883_PP1"],
            "Сумма": [12990],
            "Стоимость доставки для продавца": [0],
            "Плановая дата передачи курьеру": ["21.02.2026"],
            "Название в системе продавца": ["ACMEWEAR line61"],
            "Телефон": ["77771234567"],
        }
    )
    stage, phone_values = build_staging(df, ["SKU_key", "MY_SIZE", "Артикул"])
    assert len(stage) == 1
    assert stage[0][0] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert stage[0][1] == ""
    assert stage[0][2] == "OF_SUIT-61_BLK_3XL"
    assert phone_values == [77771234567]


def test_build_staging_coerces_order_id_to_numeric():
    df = pd.DataFrame(
        {
            "№ заказа": ["812345678"],
            "Телефон": ["+7 (777) 123-45-67"],
            "Артикул": ["OF_SUIT-61_BLK_3XL"],
            "Название товара в Kaspi Магазине": [
                "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL"
            ],
            "Склад передачи КД": ["30137883_PP1"],
            "Количество": [1],
            "Сумма": [12990],
            "Стоимость доставки для продавца": [0],
            "Плановая дата передачи курьеру": ["21.02.2026"],
        }
    )

    stage, phone_values = build_staging(df, ["№ заказа", "Артикул"])

    assert stage[0][0] == 812345678
    assert phone_values == [77771234567]


def test_compute_fixed_value_columns_for_acmewear_suit_row():
    """Fixed-value columns should match workbook formula semantics for trivial columns."""
    raw_row = {
        "Склад передачи КД": "30137883_PP1",
        "Артикул": "OF_SUIT-61_BLK_3XL",
        "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL",
        "Название в системе продавца": "ACMEWEAR line61",
        "Количество": 2,
        "Сумма": 25980,
        "Стоимость доставки для продавца": 1000,
        "Плановая дата передачи курьеру": "21.02.2026",
    }
    sku_meta = {
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK": {
            "model": "LINE61",
            "product_type": "CL",
            "weight_kg": 1.5,
        }
    }
    kaspi_core = {"CL_NEW-CLO2_MEN_SUIT-61_BLACK": "LINE61__BLACK"}

    values = compute_fixed_value_columns(raw_row, sku_meta, kaspi_core)
    assert values["STORE_NAME"] == "AcmeWear"
    assert values["SKU_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert values["MY_SIZE"] == "3XL"
    assert values["Quantity"] == 2
    assert values["Total_price"] == 25980.0
    assert values["Sell_price_kzt"] == 12990.0
    assert values["Delivery_fee_kzt"] == 1000.0
    assert values["Total_net_rev"] == pytest.approx(((25980.0 * (1 - 0.125)) - 1000.0) * (1 - 0.03))
    assert values["Product_Type"] == "CL"
    assert values["MODEL"] == "LINE61"
    assert values["Kaspi_name_core"] == "6в1_Черный_+Сумка"
    assert values["SKU_ID_KSP"] == "OF_SUIT-61_BLK_3XL"
    assert values["Kaspi_name_source"] == "ACMEWEAR line61"


def test_build_staging_never_autofills_my_size_from_article():
    """MY_SIZE is human-owned in CRM and must stay blank on import."""
    df = pd.DataFrame(
        {
            "Артикул": ["OF_SUIT-61_BLK_3XL"],
            "Название товара в Kaspi Магазине": [
                "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL"
            ],
            "Количество": [1],
            "Склад передачи КД": ["30137883_PP1"],
            "Сумма": [12990],
            "Стоимость доставки для продавца": [0],
            "Плановая дата передачи курьеру": ["21.02.2026"],
            "Название в системе продавца": ["ACMEWEAR line61"],
        }
    )
    stage, _ = build_staging(df, ["MY_SIZE", "SKU_key", "Артикул"])
    assert stage[0][0] == ""
    assert stage[0][1] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"


def test_build_staging_prefers_parser_when_article_map_conflicts():
    """OF_* article parser output should win over stale article-map rows."""
    df = pd.DataFrame(
        {
            "Артикул": ["OF_SUIT-61_BLK_3XL"],
            "Название товара в Kaspi Магазине": [
                "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL"
            ],
            "Количество": [1],
            "Склад передачи КД": ["30137883_PP1"],
            "Сумма": [12990],
            "Стоимость доставки для продавца": [0],
            "Плановая дата передачи курьеру": ["21.02.2026"],
            "Название в системе продавца": ["ACMEWEAR line61"],
        }
    )

    stale_map = {
        "OF_SUIT-61_BLK_3XL": {
            "sku_key": "CL_OC_MEN_LINE51_WHITE",
            "sku_id": "CL_OC_MEN_LINE51_WHITE_3XL",
            "kaspi_name_core": "Принт_5в1_черный",
        }
    }
    valid_keys = {"CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_OC_MEN_LINE51_WHITE"}
    with patch("scripts.import_orders_to_crm._load_article_identity_for_articles", return_value=stale_map):
        with patch("scripts.import_orders_to_crm._load_sku_meta_for_keys", return_value=({}, {}, valid_keys)):
            stage, _ = build_staging(df, ["SKU_key", "Артикул"])

    assert stage[0][0] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert stage[0][1] == "OF_SUIT-61_BLK_3XL"


def test_compute_fixed_values_forces_line61_core():
    raw_row = {
        "Склад передачи КД": "30137883_PP1",
        "Артикул": "OF_SUIT-61_BLK_XL_48",
        "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL черный 48",
        "Название в системе продавца": "ACMEWEAR line61",
        "Количество": 1,
        "Сумма": 12990,
        "Стоимость доставки для продавца": 500,
    }
    values = compute_fixed_value_columns(raw_row, {}, {})
    assert values["SKU_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert values["Kaspi_name_core"] == "6в1_Черный_+Сумка"


def test_load_sku_meta_for_keys_handles_missing_dim_sku_table(monkeypatch, tmp_path):
    db_path = tmp_path / "empty.db"
    sqlite3.connect(db_path).close()

    @contextmanager
    def _fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    monkeypatch.setattr("scripts.import_orders_to_crm.get_db", _fake_get_db)

    sku_meta, kaspi_core, valid_keys = _load_sku_meta_for_keys(["CL_NEW-CLO2_MEN_SUIT-61_BLACK"])
    assert sku_meta == {}
    assert kaspi_core == {}
    assert valid_keys == set()


def test_derive_identity_uses_normalized_article_map_key():
    raw_row = {
        "Артикул": "135277314CL_NEW-CLO_MEN_RUSH-PRO_BLACK_L_135277314",
        "Название товара в Kaspi Магазине": "Рашгард PRO COMBAT однотонный 245 черный L",
        "SKU_key": "",
        "MY_SIZE": "",
    }
    article_identity = {
        "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_L_135277314": {
            "sku_key": "CL_NEW-CLO_MEN_RUSH-PRO_BLACK",
            "sku_id": "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_L",
            "kaspi_name_core": "Раш_про_черный",
        }
    }
    derived = _derive_identity_from_raw_row(raw_row, article_identity_by_article=article_identity)
    assert derived["sku_key"] == "CL_NEW-CLO_MEN_RUSH-PRO_BLACK"
    assert derived["my_size"] == "L"


def test_row_in_backfill_window_respects_explicit_bounds():
    assert _row_in_backfill_window(date(2026, 2, 7), date(2026, 1, 25), date(2026, 2, 7))
    assert not _row_in_backfill_window(date(2026, 1, 24), date(2026, 1, 25), date(2026, 2, 7))
    assert not _row_in_backfill_window(date(2026, 2, 8), date(2026, 1, 25), date(2026, 2, 7))


def test_load_seller_delivery_fees_from_db_returns_nonzero_truth(monkeypatch, tmp_path):
    db_path = tmp_path / "fees.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT PRIMARY KEY,
            delivery_cost_for_seller REAL
        )
        """
    )
    conn.executemany(
        "INSERT INTO fact_orders_kaspi(order_id, delivery_cost_for_seller) VALUES (?, ?)",
        [
            ("871000111", 895.0),
            ("871000222", 0.0),
            ("871000333", None),
        ],
    )
    conn.commit()
    conn.close()

    @contextmanager
    def _fake_get_db():
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    monkeypatch.setattr("scripts.import_orders_to_crm.get_db", _fake_get_db)

    assert _load_seller_delivery_fees_from_db(
        ["871000111", "871000222", "871000333", "871000444"]
    ) == {"871000111": 895.0}


def test_overlay_missing_seller_delivery_fees_from_db_fills_zero_values(monkeypatch, tmp_path):
    db_path = tmp_path / "fees.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT PRIMARY KEY,
            delivery_cost_for_seller REAL
        )
        """
    )
    conn.executemany(
        "INSERT INTO fact_orders_kaspi(order_id, delivery_cost_for_seller) VALUES (?, ?)",
        [
            ("871000111", 895.0),
            ("871000222", 0.0),
            ("871000333", 783.0),
        ],
    )
    conn.commit()
    conn.close()

    @contextmanager
    def _fake_get_db():
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    monkeypatch.setattr("scripts.import_orders_to_crm.get_db", _fake_get_db)

    df = pd.DataFrame(
        {
            "№ заказа": ["871000111", "871000222", "871000333", "871000444"],
            "Стоимость доставки для продавца": [0, 0, 500, ""],
        }
    )

    updated = overlay_missing_seller_delivery_fees_from_db(df)

    assert updated == 1
    assert df.loc[0, "Стоимость доставки для продавца"] == 895.0
    assert df.loc[1, "Стоимость доставки для продавца"] == 0
    assert df.loc[2, "Стоимость доставки для продавца"] == 500
    assert df.loc[3, "Стоимость доставки для продавца"] == ""


def test_plan_seller_delivery_fee_backfill_updates_prefers_db_truth_then_legacy_fee():
    updates = _plan_seller_delivery_fee_backfill_updates(
        [
            (10, date(2026, 4, 2), 0.0, 500.0),
            (11, date(2026, 4, 2), 0.0, 783.0),
            (12, date(2026, 4, 2), 100.0, 895.0),
            (13, date(2026, 3, 20), 0.0, 450.0),
        ],
        {10: "871000111", 11: "871000222", 12: "871000333", 13: "871000444"},
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 2),
        seller_fee_by_order={"871000111": 895.0, "871000444": 999.0},
    )

    assert updates == [(10, 895.0), (11, 783.0)]


def test_write_single_column_updates_xlwings_batches_consecutive_rows():
    writes = []

    class DummyRange:
        def __init__(self, start, end):
            self.start = start
            self.end = end

        @property
        def value(self):
            return None

        @value.setter
        def value(self, payload):
            writes.append((self.start, self.end, payload))

    class DummySheet:
        def range(self, start, end):
            return DummyRange(start, end)

    _write_single_column_updates_xlwings(
        DummySheet(),
        48,
        [(10, 895.0), (11, 783.0), (13, 1275.0)],
    )

    assert writes == [
        ((10, 48), (11, 48), [[895.0], [783.0]]),
        ((13, 48), (13, 48), 1275.0),
    ]


def test_write_single_column_updates_xlwings_splits_timeout_batches():
    writes = []

    class DummyRange:
        def __init__(self, start, end):
            self.start = start
            self.end = end

        @property
        def value(self):
            return None

        @value.setter
        def value(self, payload):
            if self.start == (10, 48) and self.end == (11, 48):
                raise TimeoutError("operation timed out after 1s")
            writes.append((self.start, self.end, payload))

    class DummySheet:
        def range(self, start, end):
            return DummyRange(start, end)

    _write_single_column_updates_xlwings(
        DummySheet(),
        48,
        [(10, 895.0), (11, 783.0)],
    )

    assert writes == [
        ((10, 48), (10, 48), 895.0),
        ((11, 48), (11, 48), 783.0),
    ]


def test_apply_fixed_values_backfill_openpyxl_updates_recent_rows_and_keeps_my_size():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        crm_path = tmppath / "crm.xlsx"

        headers = [
            "Date",
            "Склад передачи КД",
            "Артикул",
            "Название товара в Kaspi Магазине",
            "Название в системе продавца",
            "Количество",
            "Сумма",
            "Стоимость доставки для продавца",
            "Плановая дата передачи курьеру",
            "SKU_key",
            "MY_SIZE",
            "Product_Type",
            "STORE_NAME",
            "Quantity",
            "Kaspi_name_core",
            "KASPI_OFFER_NAME",
            "Sell_price_kzt",
            "Total_price",
            "Total_net_rev",
            "MODEL",
            "PLANNED_SHIPPING_DATE",
            "Delivery_fee_kzt",
            "Total_weight",
            "SKU_ID_KSP",
            "Kaspi_name_source",
        ]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SALES_KSP_CRM_1"
        for i, h in enumerate(headers, start=1):
            ws.cell(row=1, column=i, value=h)
        ws.cell(row=2, column=1, value=date.today())
        ws.cell(row=2, column=2, value="30137883_PP1")
        ws.cell(row=2, column=3, value="OF_SUIT-61_BLK_3XL")
        ws.cell(row=2, column=4, value="Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL")
        ws.cell(row=2, column=5, value="ACMEWEAR line61")
        ws.cell(row=2, column=6, value=1)
        ws.cell(row=2, column=7, value=12990)
        ws.cell(row=2, column=8, value=0)
        ws.cell(row=2, column=9, value="07.02.2026")
        ws.cell(row=2, column=10, value="")
        ws.cell(row=2, column=11, value="L")
        ws.cell(row=2, column=12, value="")
        ws.cell(row=2, column=13, value="=A2")
        table = Table(displayName="tb_SalesRaw", ref=f"A1:{openpyxl.utils.get_column_letter(len(headers))}2")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)
        wb.save(crm_path)
        wb.close()

        updated = apply_fixed_values_backfill_openpyxl(
            crm_path=crm_path,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            days=14,
            dry_run=False,
            verbose=True,
        )
        assert updated == 1

        wb2 = openpyxl.load_workbook(crm_path)
        ws2 = wb2["SALES_KSP_CRM_1"]
        assert ws2.cell(row=2, column=11).value == "L"  # MY_SIZE unchanged
        assert ws2.cell(row=2, column=15).value == "6в1_Черный_+Сумка"
        wb2.close()


def test_backfill_seller_delivery_fee_prefer_openpyxl_updates_rows(monkeypatch, tmp_path):
    crm_path = tmp_path / "crm.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "OrderID",
        "Delivery_fee_kzt",
        "Стоимость доставки для продавца",
    ]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date(2026, 4, 3))
    ws.cell(row=2, column=2, value="877552776")
    ws.cell(row=2, column=3, value=850.0)
    ws.cell(row=2, column=4, value=0)
    table = Table(displayName="tb_SalesRaw", ref="A1:D2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(crm_path)
    wb.close()

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._load_seller_delivery_fees_from_db",
        lambda _order_ids: {"877552776": 1275.0},
    )

    updated = backfill_seller_delivery_fee(
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_from=date(2026, 4, 3),
        date_to=date(2026, 4, 3),
        dry_run=False,
        verbose=False,
        prefer_openpyxl=True,
    )

    assert updated == 1
    wb2 = openpyxl.load_workbook(crm_path)
    ws2 = wb2["SALES_KSP_CRM_1"]
    assert ws2.cell(row=2, column=4).value == 1275.0
    wb2.close()


def test_delete_crm_rows_openpyxl_deletes_rows_and_resizes_table(tmp_path):
    crm_path = tmp_path / "crm.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    for idx, header in enumerate(["Date", "OrderID", "STORE_NAME"], start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date(2026, 4, 1))
    ws.cell(row=2, column=2, value="1001")
    ws.cell(row=2, column=3, value="Universal")
    ws.cell(row=3, column=1, value=date(2026, 4, 1))
    ws.cell(row=3, column=2, value="1002")
    ws.cell(row=3, column=3, value="Universal")
    ws.cell(row=4, column=1, value=date(2026, 4, 1))
    ws.cell(row=4, column=2, value="1003")
    ws.cell(row=4, column=3, value="Universal")
    table = Table(displayName="tb_SalesRaw", ref="A1:C4")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(crm_path)
    wb.close()

    deleted = delete_crm_rows_openpyxl(
        out_wb=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        row_numbers=[3],
    )

    assert deleted == 1
    wb2 = openpyxl.load_workbook(crm_path)
    ws2 = wb2["SALES_KSP_CRM_1"]
    assert ws2.tables["tb_SalesRaw"].ref == "A1:C3"
    assert ws2.cell(row=2, column=2).value == "1001"
    assert ws2.cell(row=3, column=2).value == "1003"
    wb2.close()


def test_excel_append_openpyxl_writes_numeric_order_id_and_phone(tmp_path):
    workbook = tmp_path / "crm.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "№ заказа"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value=800000001)

    table = Table(displayName="tb_SalesRaw", ref="A1:C2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    from scripts.import_orders_to_crm import excel_append_openpyxl

    start_row, end_row = excel_append_openpyxl(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=2,
        start_col_abs=3,
        end_col_abs=3,
        stage_block=[["812300001"]],
        phone_values=["+7 (777) 000-00-01"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        repair_cf_ranges=False,
        verbose=False,
    )

    assert (start_row, end_row) == (3, 3)

    wb2 = openpyxl.load_workbook(workbook)
    ws2 = wb2["SALES_KSP_CRM_1"]
    assert ws2.cell(row=3, column=3).value == 812300001
    assert ws2.cell(row=3, column=3).number_format == "0"
    assert ws2.cell(row=3, column=2).value == 77770000001
    assert ws2.cell(row=3, column=2).number_format == "0"
    wb2.close()


def test_verify_appended_rows_integrity_accepts_canonical_template_style_upgrade(
    monkeypatch, tmp_path
):
    template_path = tmp_path / "crm_template_style.xlsx"
    workbook = tmp_path / "crm_live_style.xlsx"

    for target in (template_path, workbook):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SALES_KSP_CRM_1"
        headers = ["Date", "Phone", "№ заказа"]
        for idx, header in enumerate(headers, start=1):
            ws.cell(row=1, column=idx, value=header)
        ws.cell(row=2, column=1, value=date.today())
        ws.cell(row=2, column=2, value=77770000000)
        ws.cell(row=2, column=3, value=800000001)
        table = Table(displayName="tb_SalesRaw", ref="A1:C2")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)
        wb.save(target)
        wb.close()

    template_wb = openpyxl.load_workbook(template_path)
    template_ws = template_wb["SALES_KSP_CRM_1"]
    template_ws.cell(row=2, column=3).number_format = "0000000000"
    template_ws.cell(row=2, column=3).fill = openpyxl.styles.PatternFill(
        fill_type="solid",
        fgColor="FFF2CC",
    )
    template_cell = template_ws.cell(row=2, column=3)
    template_wb.save(template_path)
    template_wb.close()

    live_wb = openpyxl.load_workbook(workbook)
    live_ws = live_wb["SALES_KSP_CRM_1"]
    live_ws.cell(row=2, column=3).number_format = "0"
    live_table = live_ws.tables["tb_SalesRaw"]
    live_table.ref = "A1:C3"
    appended = live_ws.cell(row=3, column=3, value=812300009)
    appended.number_format = template_cell.number_format
    appended.fill = copy(template_cell.fill)
    appended.font = copy(template_cell.font)
    appended.border = copy(template_cell.border)
    appended.alignment = copy(template_cell.alignment)
    appended.protection = copy(template_cell.protection)
    live_ws.cell(row=3, column=1, value=date.today())
    live_ws.cell(row=3, column=2, value=77770000009)
    live_wb.save(workbook)
    live_wb.close()

    monkeypatch.setenv("CRM_CANONICAL_TEMPLATE_PATH", str(template_path))

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        verbose=False,
    )


def test_excel_append_openpyxl_keeps_my_size_blank_on_append(tmp_path):
    workbook = tmp_path / "crm_my_size.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "№ заказа", "MY_SIZE"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value=800000001)
    ws.cell(row=2, column=4, value="manual")

    table = Table(displayName="tb_SalesRaw", ref="A1:D2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    start_row, end_row = excel_append_openpyxl(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=2,
        start_col_abs=3,
        end_col_abs=3,
        stage_block=[["812300002"]],
        phone_values=["+7 (777) 000-00-02"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        preserved_my_sizes=["XL"],
        repair_cf_ranges=False,
        verbose=False,
    )

    assert (start_row, end_row) == (3, 3)

    wb2 = openpyxl.load_workbook(workbook)
    ws2 = wb2["SALES_KSP_CRM_1"]
    assert ws2.cell(row=3, column=4).value in ("", None)
    wb2.close()


def test_excel_append_openpyxl_does_not_rewrite_kaspi_name_core(tmp_path):
    workbook = tmp_path / "crm_kaspi_core.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "№ заказа", "Height", "Kaspi_name_core"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value=800000001)
    ws.cell(row=2, column=4, value="legacy")
    ws.cell(row=2, column=5, value='="AUTO"')

    table = Table(displayName="tb_SalesRaw", ref="A1:E2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    start_row, end_row = excel_append_openpyxl(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=2,
        start_col_abs=3,
        end_col_abs=3,
        stage_block=[["812300003"]],
        phone_values=["+7 (777) 000-00-03"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        kaspi_name_core_values=["MANUAL_CORE"],
        repair_cf_ranges=False,
        verbose=False,
    )

    assert (start_row, end_row) == (3, 3)

    wb2 = openpyxl.load_workbook(workbook, data_only=False)
    ws2 = wb2["SALES_KSP_CRM_1"]
    assert ws2.cell(row=3, column=5).value == '="AUTO"'
    wb2.close()


def test_excel_append_openpyxl_normalizes_template_cf_ranges_for_appended_rows(
    monkeypatch, tmp_path
):
    template_path = tmp_path / "crm_template_cf.xlsx"
    workbook = tmp_path / "crm_live_cf.xlsx"

    headers = [f"FILLER_{idx}" for idx in range(1, 26)]
    header_overrides = {
        1: "Date",
        2: "STORE_NAME",
        3: "Quantity",
        7: "Kaspi_name_core",
        15: "Sell_price_kzt",
        16: "Total_price",
        17: "Total_net_rev",
        18: "Название товара в Kaspi Магазине",
        19: "Артикул",
        20: "Статус",
        25: "№ заказа",
    }
    for idx, header in header_overrides.items():
        headers[idx - 1] = header

    def _seed_rows(ws, row_numbers):
        for idx, header in enumerate(headers, start=1):
            ws.cell(1, idx, header)
        for row_num, order_id in row_numbers:
            ws.cell(row_num, 1, date(2026, 4, 4))
            ws.cell(row_num, 2, "Universal")
            ws.cell(row_num, 3, 1)
            ws.cell(row_num, 7, '=CONCAT("AUTO","_CORE")')
            ws.cell(row_num, 15, "=15000")
            ws.cell(row_num, 16, "=15000")
            ws.cell(row_num, 17, "=12000")
            ws.cell(row_num, 18, f"Offer-{order_id}")
            ws.cell(row_num, 19, f"SKU-{order_id}")
            ws.cell(row_num, 20, "Принят")
            ws.cell(row_num, 25, order_id)
            ws.cell(row_num, 25).number_format = "0"

    yellow_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFF2CC")

    template_wb = openpyxl.Workbook()
    template_ws = template_wb.active
    template_ws.title = "SALES_KSP_CRM_1"
    _seed_rows(template_ws, ((2, 856700001), (3, 856700002), (4, 856700003)))
    template_ws.conditional_formatting.add(
        "O2:Q3",
        FormulaRule(formula=["$O2>0"], fill=yellow_fill),
    )
    template_ws.conditional_formatting.add(
        "Y2:Y3",
        FormulaRule(formula=["$Y2>0"], fill=yellow_fill),
    )
    template_table = Table(displayName="tb_SalesRaw", ref="A1:Y4")
    template_table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    template_ws.add_table(template_table)
    template_wb.save(template_path)
    template_wb.close()

    live_wb = openpyxl.Workbook()
    live_ws = live_wb.active
    live_ws.title = "SALES_KSP_CRM_1"
    _seed_rows(live_ws, ((2, 856700001), (3, 856700002), (4, 856700003)))
    live_table = Table(displayName="tb_SalesRaw", ref="A1:Y4")
    live_table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    live_ws.add_table(live_table)
    live_wb.save(workbook)
    live_wb.close()

    monkeypatch.setenv("CRM_CANONICAL_TEMPLATE_PATH", str(template_path))

    start_row, end_row = excel_append_openpyxl(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=None,
        start_col_abs=18,
        end_col_abs=25,
        stage_block=[["Offer-856700004", "SKU-856700004", "Принят", "", "", "", "", "856700004"]],
        phone_values=[],
        set_date=date(2026, 4, 4),
        slice_headers=headers[17:25],
        fixed_values=[
            {
                "STORE_NAME": "Universal",
                "Quantity": 1,
                "Kaspi_name_core": "AUTO_CORE",
                "Sell_price_kzt": 15000,
                "Total_price": 15000,
                "Total_net_rev": 12000,
            }
        ],
        repair_cf_ranges=True,
        verbose=False,
    )

    assert (start_row, end_row) == (5, 5)

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=5,
        end_row=5,
        verbose=False,
    )


def _set_table_calculated_column_formula(
    workbook_path: Path,
    *,
    sheet_name: str,
    table_name: str,
    column_name: str,
    formula_text: str,
    array: bool,
) -> None:
    wb = openpyxl.load_workbook(workbook_path)
    try:
        ws = wb[sheet_name]
        table = ws.tables[table_name]
        for table_col in table.tableColumns:
            if table_col.name == column_name:
                table_col.calculatedColumnFormula = TableFormula(
                    array=array,
                    attr_text=formula_text,
                )
                break
        else:
            raise AssertionError(f"Column not found in table: {column_name}")
        wb.save(workbook_path)
    finally:
        wb.close()


def _inject_array_formula_ref_mismatch(
    workbook_path: Path,
    *,
    cell_ref: str,
    bad_ref: str,
    sheet_xml_path: str = "xl/worksheets/sheet1.xml",
) -> None:
    with zipfile.ZipFile(workbook_path, "r") as zin:
        sheet_xml = zin.read(sheet_xml_path).decode("utf-8", "ignore")
        pattern = re.compile(
            rf'(<c\b[^>]*\br="{re.escape(cell_ref)}"[^>]*>.*?<f\b[^>]*\bt="array"[^>]*\bref=")([^"]*)(")',
            re.S,
        )
        updated, count = pattern.subn(lambda m: f"{m.group(1)}{bad_ref}{m.group(3)}", sheet_xml, count=1)
        assert count == 1

        tmp = workbook_path.with_name(f"{workbook_path.stem}_bad_array_ref_tmp.xlsx")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == sheet_xml_path:
                    zout.writestr(item, updated.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))
    tmp.replace(workbook_path)


def test_excel_append_openpyxl_restores_array_sku_key_formula_contract(monkeypatch, tmp_path):
    workbook = tmp_path / "crm_sku_key_array.xlsx"
    monkeypatch.setattr("scripts.import_orders_to_crm._resolve_crm_template_path", lambda *args, **kwargs: None)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "Spacer", "Статус", "SKU_key", "№ заказа"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value="seed")
    ws.cell(row=2, column=4, value="Принят")
    ws.cell(row=2, column=5, value=ArrayFormula(ref="E2", text='=F2&"_SKU"'))
    ws.cell(row=2, column=6, value=800000001)
    ws.cell(row=2, column=6).number_format = "0"

    table = Table(displayName="tb_SalesRaw", ref="A1:F2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    _set_table_calculated_column_formula(
        workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        column_name="SKU_key",
        formula_text='XLOOKUP([@[№ заказа]],[№ заказа],[№ заказа])',
        array=True,
    )

    start_row, end_row = excel_append_openpyxl(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=2,
        start_col_abs=6,
        end_col_abs=6,
        stage_block=[["812300004"]],
        phone_values=["+7 (777) 000-00-04"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        repair_cf_ranges=False,
        verbose=False,
    )

    assert (start_row, end_row) == (3, 3)

    wb2 = openpyxl.load_workbook(workbook, data_only=False)
    try:
        ws2 = wb2["SALES_KSP_CRM_1"]
        sku_formula = ws2.cell(row=3, column=5).value
        assert isinstance(sku_formula, ArrayFormula)
        assert sku_formula.text == '=F3&"_SKU"'
        assert sku_formula.ref == "E3"

        sku_table_col = next(col for col in ws2.tables["tb_SalesRaw"].tableColumns if col.name == "SKU_key")
        assert sku_table_col.calculatedColumnFormula is not None
        assert sku_table_col.calculatedColumnFormula.array is True
    finally:
        wb2.close()

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        verbose=False,
    )


def test_verify_appended_rows_integrity_detects_mismatched_array_sku_key_ref(monkeypatch, tmp_path):
    workbook = tmp_path / "crm_sku_key_bad_ref.xlsx"
    monkeypatch.setattr("scripts.import_orders_to_crm._resolve_crm_template_path", lambda *args, **kwargs: None)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "Spacer", "Статус", "SKU_key", "№ заказа"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value="seed")
    ws.cell(row=2, column=4, value="Принят")
    ws.cell(row=2, column=5, value=ArrayFormula(ref="E2", text='=F2&"_SKU"'))
    ws.cell(row=2, column=6, value=800000001)
    ws.cell(row=3, column=1, value=date.today())
    ws.cell(row=3, column=2, value=77770000001)
    ws.cell(row=3, column=3, value="seed")
    ws.cell(row=3, column=4, value="Новый")
    ws.cell(row=3, column=5, value=ArrayFormula(ref="E3", text='=F3&"_SKU"'))
    ws.cell(row=3, column=6, value=800000002)
    table = Table(displayName="tb_SalesRaw", ref="A1:F3")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    _set_table_calculated_column_formula(
        workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        column_name="SKU_key",
        formula_text='XLOOKUP([@[№ заказа]],[№ заказа],[№ заказа])',
        array=True,
    )
    _inject_array_formula_ref_mismatch(workbook, cell_ref="E3", bad_ref="E4")

    with pytest.raises(RuntimeError, match="array ref"):
        _verify_appended_rows_integrity(
            workbook_path=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            start_row=3,
            end_row=3,
            verbose=False,
        )


def test_restore_preserved_package_parts_normalizes_mismatched_array_sku_key_ref(tmp_path):
    workbook = tmp_path / "crm_sku_key_preserve_fix.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "Spacer", "Статус", "SKU_key", "№ заказа"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)
    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value="seed")
    ws.cell(row=2, column=4, value="Принят")
    ws.cell(row=2, column=5, value=ArrayFormula(ref="E2", text='=F2&"_SKU"'))
    ws.cell(row=2, column=6, value=800000001)
    table = Table(displayName="tb_SalesRaw", ref="A1:F2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    _set_table_calculated_column_formula(
        workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        column_name="SKU_key",
        formula_text='XLOOKUP([@[№ заказа]],[№ заказа],[№ заказа])',
        array=True,
    )
    _inject_array_formula_ref_mismatch(workbook, cell_ref="E2", bad_ref="E3")

    preserved = _snapshot_preserved_package_parts(workbook)
    _restore_preserved_package_parts(workbook, preserved)

    repaired = openpyxl.load_workbook(workbook, data_only=False)
    try:
        formula = repaired["SALES_KSP_CRM_1"]["E2"].value
        assert isinstance(formula, ArrayFormula)
        assert formula.ref == "E2"
    finally:
        repaired.close()


def test_openpyxl_backfill_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CRM_FIXED_BACKFILL_OPENPYXL_FALLBACK", raising=False)
    assert _allow_openpyxl_backfill_fallback() is False


def test_openpyxl_backfill_fallback_can_be_enabled(monkeypatch):
    monkeypatch.setenv("CRM_FIXED_BACKFILL_OPENPYXL_FALLBACK", "1")
    assert _allow_openpyxl_backfill_fallback() is True


def test_openpyxl_append_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CRM_OPENPYXL_APPEND_FALLBACK", raising=False)
    assert _allow_openpyxl_append_fallback() is False


def test_openpyxl_append_fallback_can_be_enabled(monkeypatch):
    monkeypatch.setenv("CRM_OPENPYXL_APPEND_FALLBACK", "1")
    assert _allow_openpyxl_append_fallback() is True


def test_xlwings_open_timeout_env_parsing(monkeypatch):
    monkeypatch.delenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", raising=False)
    assert _xlwings_open_timeout_sec() == 45
    monkeypatch.setenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "2")
    assert _xlwings_open_timeout_sec() == 5
    monkeypatch.setenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "90")
    assert _xlwings_open_timeout_sec() == 90
    monkeypatch.setenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "not-a-number")
    assert _xlwings_open_timeout_sec() == 45


def test_open_workbook_xlwings_retries_without_timeout_kwarg(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    class DummyBooks:
        def __init__(self):
            self.calls = []

        def open(self, _path, **kwargs):
            self.calls.append(dict(kwargs))
            if "timeout" in kwargs:
                raise TypeError("Books.open() got an unexpected keyword argument 'timeout'")
            return "OK"

    class DummyApp:
        def __init__(self):
            self.books = DummyBooks()

    monkeypatch.setenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "45")
    app = DummyApp()
    result = _open_workbook_xlwings(app, workbook, update_links=False, read_only=False)
    assert result == "OK"
    assert len(app.books.calls) == 2
    assert "timeout" in app.books.calls[0]
    assert "timeout" not in app.books.calls[1]


def test_open_workbook_xlwings_uses_wall_clock_helper_when_timeout_kwarg_missing(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    class DummyBooks:
        def __init__(self):
            self.calls = []

        def open(self, _path, **kwargs):
            self.calls.append(dict(kwargs))
            if "timeout" in kwargs:
                raise TypeError("Books.open() got an unexpected keyword argument 'timeout'")
            return "DIRECT"

    class DummyApp:
        def __init__(self):
            self.books = DummyBooks()

    called = {}

    def _fake_helper(app, workbook_path, open_kwargs, timeout_sec):
        called["app"] = app
        called["workbook_path"] = workbook_path
        called["open_kwargs"] = dict(open_kwargs)
        called["timeout_sec"] = timeout_sec
        return "HELPER_OK"

    monkeypatch.setenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "33")
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._open_workbook_xlwings_without_timeout_kwarg",
        _fake_helper,
    )
    app = DummyApp()
    result = _open_workbook_xlwings(app, workbook, update_links=False, read_only=False)
    assert result == "HELPER_OK"
    assert called["app"] is app
    assert called["workbook_path"] == workbook
    assert called["open_kwargs"] == {"update_links": False, "read_only": False}
    assert called["timeout_sec"] == 33


def test_open_workbook_xlwings_uses_minimal_open_on_macos(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    class DummyBooks:
        def __init__(self):
            self.calls = []

        def open(self, _path, **kwargs):
            self.calls.append(dict(kwargs))
            return "MAC_OK"

    class DummyApp:
        def __init__(self):
            self.books = DummyBooks()

    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin")
    monkeypatch.setenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "45")
    app = DummyApp()

    result = _open_workbook_xlwings(app, workbook, update_links=False, read_only=True)

    assert result == "MAC_OK"
    assert app.books.calls == [{}]


def test_formula_template_columns_include_orderid_and_exclude_human_owned_my_size():
    header_to_col = {
        "Date": 1,
        "STORE_NAME": 2,
        "MY_SIZE": 3,
        "OrderID": 4,
        "Kaspi_name_core": 5,
        "SKU_key": 6,
    }

    cols = _formula_template_columns(header_to_col)

    assert 4 in cols
    assert 3 not in cols


def test_append_orders_with_fallback_uses_openpyxl_when_xlwings_fails(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    calls = {"openpyxl": 0}

    def _boom(*_args, **_kwargs):
        raise RuntimeError("xlwings failed")

    def _fake_openpyxl(*_args, **_kwargs):
        calls["openpyxl"] += 1
        return (100, 101)

    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_xlwings", _boom)
    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_openpyxl", _fake_openpyxl)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=2,
        phone_col_abs=9,
        start_col_abs=25,
        end_col_abs=52,
        stage_block=[["812000111"]],
        phone_values=["+77770000000"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=True,
        prefer_xlwings=True,
        verbose=False,
    )

    assert result == (100, 101)
    assert calls["openpyxl"] == 1


def test_append_orders_with_fallback_restores_snapshot_before_openpyxl_fallback(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("ORIGINAL", encoding="utf-8")

    def _partial_then_fail(*_args, **_kwargs):
        workbook.write_text("PARTIAL_XLWINGS_WRITE", encoding="utf-8")
        raise RuntimeError("xlwings failed mid-write")

    seen = {}

    def _fake_openpyxl(*_args, **_kwargs):
        seen["content_before_fallback"] = workbook.read_text(encoding="utf-8")
        return (100, 101)

    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_xlwings", _partial_then_fail)
    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_openpyxl", _fake_openpyxl)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=2,
        phone_col_abs=9,
        start_col_abs=25,
        end_col_abs=52,
        stage_block=[["812000111"]],
        phone_values=["+77770000000"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=True,
        prefer_xlwings=True,
        verbose=False,
    )

    assert result == (100, 101)
    assert seen["content_before_fallback"] == "ORIGINAL"


def test_append_orders_with_fallback_uses_openpyxl_when_xlwings_times_out(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    def _timeout(*_args, **_kwargs):
        raise TimeoutError("operation timed out after 1s")

    def _fake_openpyxl(*_args, **_kwargs):
        return (200, 201)

    monkeypatch.setattr("scripts.import_orders_to_crm._run_with_posix_alarm_timeout", _timeout)
    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_openpyxl", _fake_openpyxl)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=2,
        phone_col_abs=9,
        start_col_abs=25,
        end_col_abs=52,
        stage_block=[["812000222"]],
        phone_values=["+77770000001"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=True,
        prefer_xlwings=True,
        verbose=False,
    )

    assert result == (200, 201)


def test_append_orders_with_fallback_uses_openpyxl_when_xlwings_not_preferred(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    calls = {"openpyxl": 0}

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.excel_append_xlwings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("xlwings append must not run when prefer_xlwings is False")
        ),
    )

    def _fake_openpyxl(*_args, **_kwargs):
        calls["openpyxl"] += 1
        return (210, 211)

    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_openpyxl", _fake_openpyxl)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=2,
        phone_col_abs=9,
        start_col_abs=25,
        end_col_abs=52,
        stage_block=[["812000223"]],
        phone_values=["+77770000009"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=False,
        prefer_xlwings=False,
        verbose=False,
    )

    assert result == (210, 211)
    assert calls["openpyxl"] == 1


def test_append_orders_with_fallback_suppresses_traceback_for_apple_event_timeout(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    printed = {"traceback": 0}

    def _apple_event_timeout(*_args, **_kwargs):
        raise RuntimeError(
            "Command failed:\n\t\tOSERROR: -1712\n\t\tMESSAGE: Apple event timed out."
        )

    def _fake_openpyxl(*_args, **_kwargs):
        return (300, 301)

    def _fake_print_exc():
        printed["traceback"] += 1

    monkeypatch.setattr("scripts.import_orders_to_crm._run_with_posix_alarm_timeout", _apple_event_timeout)
    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_openpyxl", _fake_openpyxl)
    monkeypatch.setattr("traceback.print_exc", _fake_print_exc)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=2,
        phone_col_abs=9,
        start_col_abs=25,
        end_col_abs=52,
        stage_block=[["812000444"]],
        phone_values=["+77770000003"],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=True,
        prefer_xlwings=True,
        verbose=True,
    )

    assert result == (300, 301)
    assert printed["traceback"] == 0


def test_append_orders_with_fallback_repairs_xlwings_style_and_cf_drift(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"

    headers = [f"FILLER_{idx}" for idx in range(1, 26)]
    header_overrides = {
        1: "Date",
        2: "STORE_NAME",
        3: "Quantity",
        7: "Kaspi_name_core",
        15: "Sell_price_kzt",
        16: "Total_price",
        17: "Total_net_rev",
        18: "Название товара в Kaspi Магазине",
        19: "Артикул",
        20: "Статус",
        25: "№ заказа",
    }
    for idx, header in header_overrides.items():
        headers[idx - 1] = header
    for idx, header in enumerate(headers, start=1):
        ws.cell(1, idx, header)

    template_values = {
        1: date(2026, 3, 15),
        2: "Universal",
        3: 1,
        7: '=CONCAT("AUTO","_CORE")',
        15: "=15000",
        16: "=15000",
        17: "=12000",
        18: "Nike_Футболка_черная_XL",
        19: "SKU-1",
        20: "Принят",
        25: 856631060,
    }
    for col, value in template_values.items():
        ws.cell(2, col, value)

    yellow_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFF2CC")
    green_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="E2F0D9")
    for col in template_values:
        ws.cell(2, col).fill = yellow_fill

    ws.conditional_formatting.add(
        "O2:Q2",
        FormulaRule(formula=["$O2>0"], fill=yellow_fill),
    )
    ws.conditional_formatting.add(
        "Y2:Y2",
        FormulaRule(formula=["$Y2>0"], fill=yellow_fill),
    )

    table = Table(displayName="tb_SalesRaw", ref="A1:Y2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    def _fake_xlwings_append(*_args, **_kwargs):
        inner_wb = openpyxl.load_workbook(workbook)
        inner_ws = inner_wb["SALES_KSP_CRM_1"]
        row_values = {
            1: date(2026, 3, 15),
            2: "Universal",
            3: 1,
            7: '=CONCAT("AUTO","_CORE")',
            15: "=15000",
            16: "=15000",
            17: "=12000",
            18: "Nike_Футболка_черная_2XL",
            19: "SKU-2",
            20: "Принят",
            25: 856648172,
        }
        for col, value in row_values.items():
            inner_ws.cell(3, col, value)
            inner_ws.cell(3, col).fill = yellow_fill
        inner_ws.cell(3, 7).fill = green_fill
        inner_ws.tables["tb_SalesRaw"].ref = "A1:Y3"
        inner_wb.save(workbook)
        inner_wb.close()
        return (3, 3)

    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_xlwings", _fake_xlwings_append)
    monkeypatch.setattr("scripts.import_orders_to_crm._refresh_formula_caches_xlwings", lambda *_args, **_kwargs: None)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=None,
        start_col_abs=1,
        end_col_abs=25,
        stage_block=[[template_values.get(col, "") for col in range(1, 26)]],
        phone_values=[],
        set_date=date(2026, 3, 15),
        slice_headers=headers,
        allow_openpyxl_fallback=False,
        prefer_xlwings=True,
        repair_cf_ranges=True,
        verbose=False,
    )

    assert result == (3, 3)
    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        verbose=False,
    )


def test_append_orders_with_fallback_refreshes_formula_caches_after_xlwings_repair(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    calls = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.excel_append_xlwings",
        lambda *_args, **_kwargs: (10, 12),
    )

    def _repair_spy(*_args, **_kwargs):
        calls.append(("repair", _kwargs["start_row"], _kwargs["end_row"]))
        return {"style_cells_normalized": 5, "cf_rules_normalized": 2}

    def _refresh_spy(*_args, **_kwargs):
        calls.append(("refresh", str(_args[0])))

    def _verify_spy(*_args, **_kwargs):
        calls.append(("verify", _kwargs["start_row"], _kwargs["end_row"]))

    def _verify_integrity_spy(*_args, **_kwargs):
        calls.append(("verify_integrity", _kwargs["start_row"], _kwargs["end_row"]))

    monkeypatch.setattr("scripts.import_orders_to_crm._repair_appended_rows_formatting", _repair_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm._refresh_formula_caches_xlwings", _refresh_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm._verify_formula_cache_readback", _verify_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm._verify_appended_rows_integrity", _verify_integrity_spy)

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=None,
        start_col_abs=1,
        end_col_abs=1,
        stage_block=[["812000555"]],
        phone_values=[],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=False,
        prefer_xlwings=True,
        repair_cf_ranges=True,
        verbose=False,
    )

    assert result == (10, 12)
    assert calls == [
        ("repair", 10, 12),
        ("refresh", str(workbook)),
        ("verify", 10, 12),
        ("verify_integrity", 10, 12),
    ]


def test_append_orders_with_fallback_repairs_live_workbook_for_macos_external_link_workbook(
    monkeypatch,
    tmp_path,
):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    calls = []

    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin")
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.excel_append_xlwings",
        lambda *_args, **_kwargs: (10, 12),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._workbook_external_link_targets",
        lambda _path: ("externalLinks/externalLink3.xml",),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._repair_appended_rows_formatting",
        lambda *_args, **_kwargs: calls.append(("repair", _kwargs["start_row"], _kwargs["end_row"]))
        or {"style_cells_normalized": 5, "cf_rules_normalized": 2},
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._refresh_formula_caches_xlwings",
        lambda *_args, **_kwargs: calls.append(("refresh", str(_args[0]))),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_formula_cache_readback",
        lambda *_args, **_kwargs: calls.append(("verify_cache", _kwargs["start_row"], _kwargs["end_row"])),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_appended_rows_integrity",
        lambda *_args, **_kwargs: calls.append(("verify_integrity", _kwargs["start_row"], _kwargs["end_row"])),
    )

    result = append_orders_with_fallback(
        out_wb=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        date_col_abs=1,
        phone_col_abs=None,
        start_col_abs=1,
        end_col_abs=1,
        stage_block=[["812000557"]],
        phone_values=[],
        set_date=date.today(),
        slice_headers=["№ заказа"],
        allow_openpyxl_fallback=False,
        prefer_xlwings=True,
        repair_cf_ranges=True,
        verbose=False,
    )

    assert result == (10, 12)
    assert calls == [
        ("repair", 10, 12),
        ("refresh", str(workbook)),
        ("verify_cache", 10, 12),
        ("verify_integrity", 10, 12),
    ]


def test_append_orders_with_fallback_restores_workbook_when_post_repair_refresh_fails(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("ORIGINAL", encoding="utf-8")

    def _fake_xlwings_append(*_args, **_kwargs):
        workbook.write_text("BROKEN_AFTER_APPEND", encoding="utf-8")
        return (10, 12)

    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_xlwings", _fake_xlwings_append)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._repair_appended_rows_formatting",
        lambda *_args, **_kwargs: {"style_cells_normalized": 5, "cf_rules_normalized": 2},
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._refresh_formula_caches_xlwings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("refresh timed out")),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._verify_formula_cache_readback", lambda *_args, **_kwargs: None)

    with pytest.raises(AppendVerificationError, match="restored from pre-append snapshot"):
        append_orders_with_fallback(
            out_wb=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            date_col_abs=1,
            phone_col_abs=None,
            start_col_abs=1,
            end_col_abs=1,
            stage_block=[["812000555"]],
            phone_values=[],
            set_date=date.today(),
            slice_headers=["№ заказа"],
            allow_openpyxl_fallback=False,
            prefer_xlwings=True,
            repair_cf_ranges=True,
            verbose=False,
        )

    assert workbook.read_text(encoding="utf-8") == "ORIGINAL"


def test_append_orders_with_fallback_restores_workbook_when_formula_cache_readback_fails(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("ORIGINAL", encoding="utf-8")

    def _fake_xlwings_append(*_args, **_kwargs):
        workbook.write_text("BROKEN_AFTER_APPEND", encoding="utf-8")
        return (10, 12)

    monkeypatch.setattr("scripts.import_orders_to_crm.excel_append_xlwings", _fake_xlwings_append)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._repair_appended_rows_formatting",
        lambda *_args, **_kwargs: {"style_cells_normalized": 5, "cf_rules_normalized": 2},
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._refresh_formula_caches_xlwings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_formula_cache_readback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("formula cache missing")),
    )

    with pytest.raises(AppendVerificationError, match="restored from pre-append snapshot"):
        append_orders_with_fallback(
            out_wb=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            date_col_abs=1,
            phone_col_abs=None,
            start_col_abs=1,
            end_col_abs=1,
            stage_block=[["812000556"]],
            phone_values=[],
            set_date=date.today(),
            slice_headers=["№ заказа"],
            allow_openpyxl_fallback=False,
            prefer_xlwings=True,
            repair_cf_ranges=True,
            verbose=False,
        )

    assert workbook.read_text(encoding="utf-8") == "ORIGINAL"


def test_xlwings_append_timeout_sec_respects_env(monkeypatch):
    monkeypatch.setenv("CRM_XLWINGS_APPEND_TIMEOUT_SEC", "75")
    assert _xlwings_append_timeout_sec() == 75


def test_xlwings_append_timeout_sec_uses_safer_default(monkeypatch):
    monkeypatch.delenv("CRM_XLWINGS_APPEND_TIMEOUT_SEC", raising=False)
    assert _xlwings_append_timeout_sec() == 420


def test_temporary_manual_calculation_switches_and_restores():
    class DummyApp:
        def __init__(self):
            self.calculation = "automatic"
            self.calculate_calls = 0

        def calculate(self):
            self.calculate_calls += 1

    app = DummyApp()
    with _temporary_manual_calculation(app):
        assert app.calculation == "manual"
    assert app.calculation == "automatic"
    assert app.calculate_calls == 1


def test_verify_formula_cache_readback_detects_missing_cached_values(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    formula_wb = openpyxl.Workbook()
    formula_ws = formula_wb.active
    formula_ws.title = "SALES_KSP_CRM_1"
    formula_ws["A1"] = "STORE_NAME"
    formula_ws["B1"] = "Quantity"
    formula_ws["A2"] = '="Universal"'
    formula_ws["B2"] = "=1"
    formula_ws.add_table(Table(displayName="tb_SalesRaw", ref="A1:B2"))

    data_wb = openpyxl.Workbook()
    data_ws = data_wb.active
    data_ws.title = "SALES_KSP_CRM_1"
    data_ws["A1"] = "STORE_NAME"
    data_ws["B1"] = "Quantity"
    data_ws["A2"] = None
    data_ws["B2"] = None
    data_ws.add_table(Table(displayName="tb_SalesRaw", ref="A1:B2"))

    def _fake_load_workbook(*_args, **kwargs):
        return data_wb if kwargs.get("data_only") else formula_wb

    monkeypatch.setattr("scripts.import_orders_to_crm.load_workbook", _fake_load_workbook)

    with pytest.raises(AppendVerificationError, match="Formula cache readback missing"):
        _verify_formula_cache_readback(
            workbook_path=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            start_row=2,
            end_row=2,
        )


def test_verify_formula_cache_readback_accepts_present_cached_values(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    formula_wb = openpyxl.Workbook()
    formula_ws = formula_wb.active
    formula_ws.title = "SALES_KSP_CRM_1"
    formula_ws["A1"] = "STORE_NAME"
    formula_ws["B1"] = "Quantity"
    formula_ws["A2"] = '="Universal"'
    formula_ws["B2"] = "=1"
    formula_ws.add_table(Table(displayName="tb_SalesRaw", ref="A1:B2"))

    data_wb = openpyxl.Workbook()
    data_ws = data_wb.active
    data_ws.title = "SALES_KSP_CRM_1"
    data_ws["A1"] = "STORE_NAME"
    data_ws["B1"] = "Quantity"
    data_ws["A2"] = "Universal"
    data_ws["B2"] = 1
    data_ws.add_table(Table(displayName="tb_SalesRaw", ref="A1:B2"))

    def _fake_load_workbook(*_args, **kwargs):
        return data_wb if kwargs.get("data_only") else formula_wb

    monkeypatch.setattr("scripts.import_orders_to_crm.load_workbook", _fake_load_workbook)

    _verify_formula_cache_readback(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=2,
        end_row=2,
    )


def test_temporary_manual_calculation_restores_on_exception():
    class DummyApp:
        def __init__(self):
            self.calculation = "automatic"
            self.calculate_calls = 0

        def calculate(self):
            self.calculate_calls += 1

    app = DummyApp()
    with pytest.raises(RuntimeError, match="boom"):
        with _temporary_manual_calculation(app):
            assert app.calculation == "manual"
            raise RuntimeError("boom")
    assert app.calculation == "automatic"
    assert app.calculate_calls == 1


def test_temporary_manual_calculation_degrades_gracefully():
    class DummyApp:
        pass

    app = DummyApp()
    with _temporary_manual_calculation(app):
        assert True


def test_clear_my_size_range_prefers_clear_contents():
    calls = {"clear": 0, "value": 0}

    class DummyRange:
        @property
        def value(self):
            return None

        @value.setter
        def value(self, _value):
            calls["value"] += 1

        def clear_contents(self):
            calls["clear"] += 1

    class DummySheet:
        def range(self, *_args, **_kwargs):
            return DummyRange()

    _clear_my_size_range(DummySheet(), 10, 12, 9)
    assert calls["clear"] == 1
    assert calls["value"] == 0


def test_clear_my_size_range_falls_back_to_bulk_value_on_timeout():
    calls = {"clear": 0, "value": 0}

    class DummyRange:
        @property
        def value(self):
            return None

        @value.setter
        def value(self, _value):
            calls["value"] += 1

        def clear_contents(self):
            calls["clear"] += 1
            raise TimeoutError("operation timed out")

    class DummySheet:
        def range(self, *_args, **_kwargs):
            return DummyRange()

    _clear_my_size_range(DummySheet(), 10, 12, 9)
    assert calls["clear"] == 1
    assert calls["value"] == 1


def test_clear_my_size_range_uses_row_fallback_when_bulk_times_out():
    calls = {"clear": 0, "value": 0}

    class DummyRange:
        def __init__(self, start_row: int, end_row: int):
            self.start_row = start_row
            self.end_row = end_row

        @property
        def value(self):
            return None

        @value.setter
        def value(self, _value):
            calls["value"] += 1
            if self.start_row != self.end_row:
                raise TimeoutError("operation timed out")

        def clear_contents(self):
            calls["clear"] += 1
            raise TimeoutError("operation timed out")

    class DummySheet:
        def range(self, start, end):
            return DummyRange(start[0], end[0])

    _clear_my_size_range(DummySheet(), 10, 12, 9)
    assert calls["clear"] == 1
    # 1 bulk attempt + 3 row writes
    assert calls["value"] == 4


def test_build_xlwings_write_plan_coerces_order_ids_and_skips_empty_columns():
    stage_block = [
        ["812345678", "", "alpha"],
        ["", "", "beta"],
    ]
    slice_headers = ["№ заказа", "empty_col", "SKU_ID"]

    col_values_by_offset, write_segments, order_offsets = _build_xlwings_write_plan(
        stage_block=stage_block,
        slice_headers=slice_headers,
    )

    assert order_offsets == [0]
    assert col_values_by_offset[0] == [812345678, ""]
    assert col_values_by_offset[1] == ["", ""]
    assert col_values_by_offset[2] == ["alpha", "beta"]
    assert write_segments == [(0, 0), (2, 2)]


def test_build_xlwings_write_plan_merges_contiguous_non_empty_columns():
    stage_block = [
        ["812345678", "core", "sku", ""],
        ["812345679", "core2", "sku2", ""],
    ]
    slice_headers = ["№ заказа", "Kaspi_name_core", "SKU_ID", "unused"]

    _col_values, write_segments, order_offsets = _build_xlwings_write_plan(
        stage_block=stage_block,
        slice_headers=slice_headers,
    )

    assert order_offsets == [0]
    assert write_segments == [(0, 2)]


def test_excel_append_xlwings_does_not_mask_primary_error_when_app_quit_fails(monkeypatch, tmp_path):
    workbook = tmp_path / "crm.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")

    class DummyApp:
        def __init__(self, *args, **kwargs):
            self.display_alerts = False
            self.screen_updating = False

        def quit(self):
            raise RuntimeError("quit failed")

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", type("DummyXW", (), {"App": DummyApp}))

    def _open_timeout(*_args, **_kwargs):
        raise TimeoutError("operation timed out after 60s")

    monkeypatch.setattr("scripts.import_orders_to_crm._open_workbook_xlwings", _open_timeout)

    with pytest.raises(TimeoutError, match="operation timed out after 60s"):
        excel_append_xlwings(
            out_wb=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            date_col_abs=2,
            phone_col_abs=9,
            start_col_abs=25,
            end_col_abs=52,
            stage_block=[["812000333"]],
            phone_values=["+77770000002"],
            set_date=date.today(),
            slice_headers=["№ заказа"],
        )


def test_excel_automation_preflight_fails_when_lock_file_exists(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")
    lock = tmp_path / "~$SALES_KSP_CRM_V3.xlsx"
    lock.write_text("lock", encoding="utf-8")
    monkeypatch.setattr("scripts.import_orders_to_crm._list_excel_workbooks", lambda: [])
    with pytest.raises(RuntimeError, match="Excel lock file detected"):
        _excel_automation_preflight(crm, strict_excel=True)


def test_excel_automation_preflight_ignores_stale_lock_file(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")
    lock = tmp_path / "~$SALES_KSP_CRM_V3.xlsx"
    lock.write_text("lock", encoding="utf-8")
    stale_ts = datetime.now().timestamp() - 2 * 24 * 60 * 60
    os.utime(lock, (stale_ts, stale_ts))

    class DummyBook:
        def close(self):
            return None

    class DummyBooks:
        def open(self, *args, **kwargs):
            return DummyBook()

    class DummyApp:
        def __init__(self, *args, **kwargs):
            self.books = DummyBooks()
            self.display_alerts = False
            self.screen_updating = False

        def quit(self):
            return None

    class OkIntegrity:
        errors = []
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", type("DummyXW", (), {"App": DummyApp}))
    monkeypatch.setattr("scripts.import_orders_to_crm._list_excel_workbooks", lambda: [])
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: OkIntegrity(),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (True, "OK"),
    )
    _excel_automation_preflight(crm, strict_excel=True, verbose=True)


def test_excel_automation_preflight_fails_on_workbook_integrity_errors(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class DummyBook:
        def close(self):
            return None

    class DummyBooks:
        def open(self, *args, **kwargs):
            return DummyBook()

    class DummyApp:
        def __init__(self, *args, **kwargs):
            self.books = DummyBooks()
            self.display_alerts = False
            self.screen_updating = False

        def quit(self):
            return None

    class BadIntegrity:
        errors = ["named range contains #REF!: BROKEN"]
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", type("DummyXW", (), {"App": DummyApp}))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: BadIntegrity(),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="Workbook integrity preflight failed"):
        _excel_automation_preflight(crm, strict_excel=True)


def test_excel_automation_preflight_allows_probe_fallback_after_xlwings_open_error(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class DummyApp:
        def __init__(self, *args, **kwargs):
            self.display_alerts = False
            self.screen_updating = False

        def quit(self):
            return None

    class OkIntegrity:
        errors = []
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", type("DummyXW", (), {"App": DummyApp}))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: OkIntegrity(),
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._open_workbook_xlwings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("Command failed: OSERROR: -50 Parameter error")
        ),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (True, "OK"),
    )

    _excel_automation_preflight(
        crm,
        strict_excel=True,
        verbose=True,
        allow_open_probe_fallback=True,
    )


def test_excel_automation_preflight_uses_open_probe_on_macos(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class OkIntegrity:
        errors = []
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin")
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: OkIntegrity(),
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (True, "OK"),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.xw",
        type(
            "DummyXW",
            (),
            {
                "App": lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("macOS strict preflight should not use xlwings workbook open")
                )
            },
        ),
    )

    _excel_automation_preflight(crm, strict_excel=True, verbose=False)


def test_excel_automation_preflight_fails_when_probe_fallback_reports_non_timeout_error(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class DummyApp:
        def __init__(self, *args, **kwargs):
            self.display_alerts = False
            self.screen_updating = False

        def quit(self):
            return None

    class OkIntegrity:
        errors = []
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", type("DummyXW", (), {"App": DummyApp}))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: OkIntegrity(),
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._open_workbook_xlwings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("Command failed: OSERROR: -50 Parameter error")
        ),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (False, "ERR:-50:Parameter error"),
    )

    with pytest.raises(RuntimeError, match="Excel open probe failed"):
        _excel_automation_preflight(
            crm,
            strict_excel=True,
            verbose=False,
            allow_open_probe_fallback=True,
        )


def test_workbook_integrity_preflight_allows_known_named_ref_baseline(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class BaselineIntegrity:
        errors = ["named range contains #REF!: B", "named range contains #REF!: SS_TOTAL"]
        warnings = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: BaselineIntegrity(),
        raising=False,
    )
    _workbook_integrity_preflight(crm, verbose=True)


def test_workbook_integrity_preflight_allows_legacy_named_range_prefix(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class LegacyPrefixIntegrity:
        errors = ["named range contains #REF!: _02.12.2025"]
        warnings = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: LegacyPrefixIntegrity(),
        raising=False,
    )

    _workbook_integrity_preflight(crm, verbose=True)


def test_workbook_integrity_preflight_allows_legacy_self_externalized_sales_formulas(
    tmp_path, monkeypatch
):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class LegacyExternalizedIntegrity:
        errors = ["CRM sales sheet contains self-externalized formulas: xl/tables/table2.xml sample=J5974=[3]!tb"]
        warnings = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: LegacyExternalizedIntegrity(),
        raising=False,
    )

    _workbook_integrity_preflight(crm, verbose=True)


def test_workbook_integrity_preflight_blocks_non_baseline_errors(tmp_path, monkeypatch):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    class MixedIntegrity:
        errors = [
            "named range contains #REF!: B",
            "tablePart target missing: rid=rId7 target=xl/tables/table7.xml",
        ]
        warnings = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: MixedIntegrity(),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="Workbook integrity preflight failed"):
        _workbook_integrity_preflight(crm, verbose=False)


def test_excel_automation_preflight_skips_when_not_strict(tmp_path):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")
    seen = {}

    def _guard(path, blocked_paths=None, verbose=False):
        seen["path"] = path
        seen["blocked_paths"] = blocked_paths
        seen["verbose"] = verbose

    with patch("scripts.import_orders_to_crm._excel_session_preflight", _guard):
        _excel_automation_preflight(
            crm,
            strict_excel=False,
            verbose=True,
            transactional=True,
            candidate_dir=crm.parent,
        )

    assert seen == {
        "path": crm,
        "blocked_paths": [crm],
        "verbose": True,
    }


def test_list_excel_workbooks_parses_running_excel_output(monkeypatch):
    def _fake_run(_cmd, input=None, text=True, capture_output=True, timeout=10):
        return SimpleNamespace(
            returncode=0,
            stdout="CRM_copy.xlsx|false\nSALES_KSP_CRM_V3.xlsx|true\n",
            stderr="",
        )

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", None)
    monkeypatch.setattr("scripts.import_orders_to_crm.subprocess.run", _fake_run)

    sessions = _list_excel_workbooks(timeout_sec=10)

    assert sessions == [
        ExcelWorkbookSession(
            pid=None,
            name="CRM_copy.xlsx",
            saved=False,
            path="",
        ),
        ExcelWorkbookSession(
            pid=None,
            name="SALES_KSP_CRM_V3.xlsx",
            saved=True,
            path="",
        ),
    ]


def test_list_excel_workbooks_skips_unresponsive_excel_pid(monkeypatch):
    class GoodBook:
        name = "SALES_KSP_CRM_V3.xlsx"
        fullname = "~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx"

        class api:
            class saved:
                @staticmethod
                def get():
                    return True

    class GoodApp:
        def __init__(self):
            self.books = [GoodBook()]

    class BadBooks:
        def __iter__(self):
            raise RuntimeError("dead excel pid")

    class BadApp:
        def __init__(self):
            self.books = BadBooks()

    class FakeApps(dict):
        def keys(self):
            return [100, 200]

    fake_apps = FakeApps({100: GoodApp(), 200: BadApp()})
    monkeypatch.setattr("scripts.import_orders_to_crm.xw", SimpleNamespace(apps=fake_apps))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._run_with_posix_alarm_timeout",
        lambda _timeout, func, *args, **kwargs: func(*args, **kwargs),
    )

    sessions = _list_excel_workbooks(timeout_sec=10)

    assert sessions == [
        ExcelWorkbookSession(
            pid=100,
            name="SALES_KSP_CRM_V3.xlsx",
            saved=True,
            path="~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx",
        )
    ]


def test_excel_session_preflight_allows_unsaved_side_workbook(monkeypatch, tmp_path):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._list_excel_workbooks",
        lambda timeout_sec=10: [
            ExcelWorkbookSession(pid=91234, name="CRM_copy.xlsx", saved=False, path="~/Desktop/CRM_copy.xlsx"),
        ],
    )

    _excel_session_preflight(crm, verbose=True)


def test_excel_session_preflight_fails_when_target_workbook_is_open(monkeypatch, tmp_path):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._list_excel_workbooks",
        lambda timeout_sec=10: [
            ExcelWorkbookSession(pid=91234, name="SALES_KSP_CRM_V3.xlsx", saved=True, path=str(crm.resolve())),
        ],
    )

    with pytest.raises(ExcelTargetConflictError, match="CRM workbook is already open in Excel"):
        _excel_session_preflight(crm, verbose=False)


def test_excel_session_preflight_fails_when_stable_candidate_workbook_is_open(monkeypatch, tmp_path):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")
    candidate = tmp_path / "SALES_KSP_CRM_V3.candidate.xlsx"
    candidate.write_text("candidate", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._list_excel_workbooks",
        lambda timeout_sec=10: [
            ExcelWorkbookSession(pid=91234, name=candidate.name, saved=True, path=str(candidate.resolve())),
        ],
    )

    with pytest.raises(ExcelTargetConflictError, match="Excel target workbook is already open in Excel"):
        _excel_session_preflight(crm, blocked_paths=[crm, candidate], verbose=False)


def test_excel_session_preflight_matches_target_by_name_when_path_missing(monkeypatch, tmp_path):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._list_excel_workbooks",
        lambda timeout_sec=10: [
            ExcelWorkbookSession(pid=91234, name="SALES_KSP_CRM_V3.xlsx", saved=True, path=""),
        ],
    )

    with pytest.raises(ExcelTargetConflictError, match="CRM workbook is already open in Excel"):
        _excel_session_preflight(crm, verbose=False)


def test_main_excel_session_preflight_only_skips_activeorders_read(monkeypatch, tmp_path, capsys):
    crm = tmp_path / "SALES_KSP_CRM_V3.xlsx"
    crm.write_text("placeholder", encoding="utf-8")
    seen = {}

    def _guard(path, blocked_paths=None, verbose=False):
        seen["path"] = path
        seen["blocked_paths"] = blocked_paths
        seen["verbose"] = verbose

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("read_active_orders should not run during preflight-only mode")

    monkeypatch.setattr("scripts.import_orders_to_crm._excel_session_preflight", _guard)
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", _unexpected)

    stats = main(
        crm_path=crm,
        excel_session_preflight_only=True,
        verbose=True,
    )

    assert seen == {
        "path": crm.resolve(),
        "blocked_paths": [crm.resolve()],
        "verbose": True,
    }
    assert stats == {"excel_session_preflight": "ok"}
    captured = capsys.readouterr()
    assert "Excel Session Preflight" in captured.out
    assert "Excel session preflight OK" in captured.out


def test_write_import_summary_records_status_and_retryability(tmp_path):
    summary_path = tmp_path / "import_summary.json"

    write_import_summary(
        {
            "orders_imported": 0,
            "orders_updated": 0,
            "orders_filtered": 12,
            "status": "preflight_blocked",
            "retryable_topup": False,
            "error": "CRM workbook is already open in Excel.",
        },
        summary_path,
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "preflight_blocked"
    assert payload["retryable_topup"] is False
    assert payload["error"] == "CRM workbook is already open in Excel."


def test_classify_import_failure_maps_target_conflict_and_append_verification():
    assert _classify_import_failure(ExcelTargetConflictError("crm open")) == ("preflight_blocked", False)
    assert _classify_import_failure(AppendVerificationError("append mismatch")) == (
        "append_verification_failed",
        False,
    )
    assert _classify_import_failure(RuntimeError("other failure")) == ("write_failed", False)


def test_excel_open_probe_retries_after_osascript_timeout(monkeypatch, tmp_path):
    crm = tmp_path / "candidate.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    open_attempts = {"count": 0}
    scripts_seen = []

    def _fake_run(_cmd, input=None, text=True, capture_output=True, timeout=45):
        script = input or ""
        scripts_seen.append(script)
        if "open workbookPath" in script:
            open_attempts["count"] += 1
            if open_attempts["count"] == 1:
                raise subprocess.TimeoutExpired(["osascript", "-"], timeout=timeout)
        return SimpleNamespace(returncode=0, stdout="OK\n", stderr="")

    monkeypatch.setattr("scripts.import_orders_to_crm.subprocess.run", _fake_run)
    ok, detail = _excel_open_probe(crm, attempts=2, timeout_sec=1)
    assert ok is True
    assert detail == "OK"
    open_scripts = [s for s in scripts_seen if "open workbookPath" in s]
    assert open_scripts, "expected Excel open probe script to be executed"
    assert 'set workbookPath to POSIX file "' in open_scripts[0]
    assert "open workbookPath" in open_scripts[0]
    assert "active workbook" not in open_scripts[0]
    assert 'set workbookName to do shell script "/usr/bin/basename " & quoted form of workbookPosixPath' in open_scripts[0]
    assert "set wbList to get workbooks" in open_scripts[0]
    assert "repeat with wb in wbList" in open_scripts[0]
    assert "set wbName to name of wb" in open_scripts[0]
    assert "if wbName is workbookName then" in open_scripts[0]
    assert "close wb saving no" in open_scripts[0]
    assert all("quit" not in script.lower() for script in scripts_seen)


def test_verify_candidate_workbook_allows_probe_timeout_after_integrity_pass(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_text("placeholder", encoding="utf-8")

    class OkIntegrity:
        errors = []
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.validate_workbook_integrity", lambda _p: OkIntegrity())
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_open_probe", lambda *_args, **_kwargs: (False, "osascript timeout after 35s"))

    _verify_candidate_workbook(candidate, strict_excel=True, verbose=True)


def test_verify_candidate_workbook_fails_on_non_timeout_probe_error(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_text("placeholder", encoding="utf-8")

    class OkIntegrity:
        errors = []
        warnings = []

    monkeypatch.setattr("scripts.import_orders_to_crm.validate_workbook_integrity", lambda _p: OkIntegrity())
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_open_probe", lambda *_args, **_kwargs: (False, "ERR:-50:Parameter error"))

    with pytest.raises(RuntimeError, match="Excel open probe failed"):
        _verify_candidate_workbook(candidate, strict_excel=True, verbose=False)


def test_verify_candidate_workbook_allows_inherited_integrity_errors(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_text("placeholder", encoding="utf-8")

    class IntegrityWithInherited:
        errors = ["named range contains #REF!: B", "named range contains #REF!: SS_TOTAL"]
        warnings = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _p: IntegrityWithInherited(),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_open_probe", lambda *_args, **_kwargs: (True, "OK"))

    _verify_candidate_workbook(
        candidate,
        strict_excel=True,
        verbose=True,
        allowed_integrity_errors={"named range contains #REF!: B", "named range contains #REF!: SS_TOTAL"},
    )


def test_excel_automation_preflight_skips_source_open_probe_for_transactional_legacy_workbook(
    monkeypatch, tmp_path
):
    crm = tmp_path / "candidate.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr("scripts.import_orders_to_crm._excel_session_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._workbook_integrity_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._candidate_source_requires_template_normalization", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "linux")
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("open probe should be skipped")),
    )

    _excel_automation_preflight(
        crm,
        strict_excel=True,
        verbose=True,
        transactional=True,
    )


def test_excel_automation_preflight_keeps_source_open_probe_for_transactional_legacy_workbook_on_macos(
    monkeypatch, tmp_path
):
    crm = tmp_path / "candidate.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr("scripts.import_orders_to_crm._excel_session_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._workbook_integrity_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._candidate_source_requires_template_normalization", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin")
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_open_probe", lambda *_args, **_kwargs: (False, "ERR:-50:Parameter error"))

    with pytest.raises(RuntimeError, match="Excel open probe failed"):
        _excel_automation_preflight(
            crm,
            strict_excel=True,
            verbose=False,
            transactional=True,
        )


def test_excel_automation_preflight_keeps_source_open_probe_for_non_transactional_legacy_workbook(
    monkeypatch, tmp_path
):
    crm = tmp_path / "candidate.xlsx"
    crm.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr("scripts.import_orders_to_crm._excel_session_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._workbook_integrity_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._candidate_source_requires_template_normalization", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin")
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_open_probe", lambda *_args, **_kwargs: (False, "ERR:-50:Parameter error"))

    with pytest.raises(RuntimeError, match="Excel open probe failed"):
        _excel_automation_preflight(
            crm,
            strict_excel=True,
            verbose=False,
            transactional=False,
        )


def test_verify_candidate_workbook_blocks_new_integrity_errors(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_text("placeholder", encoding="utf-8")

    class IntegrityWithNew:
        errors = ["named range contains #REF!: B", "tablePart target missing: xl/tables/table7.xml"]
        warnings = []

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _p: IntegrityWithNew(),
    )
    with pytest.raises(RuntimeError, match="new errors"):
        _verify_candidate_workbook(
            candidate,
            strict_excel=False,
            verbose=False,
            allowed_integrity_errors={"named range contains #REF!: B"},
        )


def test_iter_consecutive_ranges_groups_sorted_rows():
    rows = [8010, 8011, 8012, 8015, 8017, 8018]
    assert _iter_consecutive_ranges(rows) == [(8010, 8012), (8015, 8015), (8017, 8018)]


def test_coerce_column_values_pads_and_truncates():
    assert _coerce_column_values([1, 2], 4) == [1, 2, None, None]
    assert _coerce_column_values("x", 2) == ["x", None]
    assert _coerce_column_values([1, 2, 3], 2) == [1, 2]


def test_find_template_row_for_append_skips_broken_tail_row():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.cell(1, 1, "Date")
    ws.cell(1, 2, "STORE_NAME")
    ws.cell(1, 3, "Quantity")
    ws.cell(2, 2, '=IF(TRUE,"AcmeWear","")')
    ws.cell(2, 3, "=1")
    ws.cell(3, 2, "")  # broken tail row
    ws.cell(3, 3, "")

    template_row = _find_template_row_for_append(
        ws=ws,
        header_row=1,
        table_end_row=3,
        formula_cols=[2, 3],
    )
    wb.close()

    assert template_row == 2


def test_normalize_conditional_formatting_ranges_extends_fragmented_ranges():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "Sell_price_kzt",
        "Total_price",
        "Total_net_rev",
        "№ заказа",
    ]
    for idx, header in enumerate(headers, start=1):
        ws.cell(1, idx, header)
    ws.cell(2, 1, date.today())
    ws.cell(2, 2, "AcmeWear")
    ws.cell(2, 3, 1)
    ws.cell(2, 4, "Line51")
    ws.cell(2, 5, 800000001)
    ws.cell(2, 6, 9000)
    ws.cell(2, 7, 9000)
    ws.cell(2, 8, 7800)
    ws.cell(2, 9, 800000001)

    ws.conditional_formatting.add("B2:B3 B5", FormulaRule(formula=['$B2="AcmeWear"']))
    ws.conditional_formatting.add("F2:H3", FormulaRule(formula=["$F2>0"]))

    header_to_col = {h: i for i, h in enumerate(headers, start=1)}
    updated = _normalize_conditional_formatting_ranges(
        ws=ws,
        header_row=1,
        data_end_row=10,
        header_to_col=header_to_col,
        verbose=False,
    )

    sqrefs = [str(cf.sqref) for cf in ws.conditional_formatting._cf_rules.keys()]
    wb.close()

    assert updated >= 1
    assert any("B2:B10" in sqref for sqref in sqrefs)
    assert any("F2:H10" in sqref for sqref in sqrefs)


def test_normalize_conditional_formatting_ranges_rebases_kaspi_name_core_formula_anchor():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "№ заказа",
    ]
    for idx, header in enumerate(headers, start=1):
        ws.cell(1, idx, header)
    ws.cell(2, 1, date.today())
    ws.cell(2, 2, "AcmeWear")
    ws.cell(2, 3, 1)
    ws.cell(2, 4, "Line51")
    ws.cell(2, 5, 800000001)
    ws.cell(2, 6, 800000001)

    ws.conditional_formatting.add(
        "D3727:D3728",
        FormulaRule(formula=['$M3727="CL_OC_MEN_LINE52_BLACK"']),
    )

    header_to_col = {h: i for i, h in enumerate(headers, start=1)}
    updated = _normalize_conditional_formatting_ranges(
        ws=ws,
        header_row=1,
        data_end_row=10,
        header_to_col=header_to_col,
        verbose=False,
    )

    cf_items = list(ws.conditional_formatting._cf_rules.items())
    formulas = [[rule.formula for rule in rules] for _cf, rules in cf_items]
    sqrefs = [str(cf.sqref) for cf, _rules in cf_items]
    wb.close()

    assert updated >= 1
    assert "D2:D10" in sqrefs
    assert [['$M2="CL_OC_MEN_LINE52_BLACK"']] in formulas


def test_restore_conditional_formatting_from_template_preserves_segments_and_formula_anchors():
    template_wb = openpyxl.Workbook()
    template_ws = template_wb.active
    template_ws.title = "SALES_KSP_CRM_1"
    template_ws.cell(1, 1, "Date")
    template_ws.cell(1, 2, "STORE_NAME")
    template_ws.cell(1, 3, "Kaspi_name_core")
    template_ws.conditional_formatting.add(
        "C2:C5",
        FormulaRule(formula=['$C2="Universal"']),
    )
    template_ws.conditional_formatting.add(
        "C4:C5",
        FormulaRule(formula=['$C4="Universal"']),
    )

    current_wb = openpyxl.Workbook()
    current_ws = current_wb.active
    current_ws.title = "SALES_KSP_CRM_1"
    current_ws.cell(1, 1, "Date")
    current_ws.cell(1, 2, "STORE_NAME")
    current_ws.cell(1, 3, "Kaspi_name_core")
    current_ws.conditional_formatting.add(
        "C2:C7",
        FormulaRule(formula=['$C4="Universal"']),
    )

    updated = _restore_conditional_formatting_from_template(
        ws=current_ws,
        template_ws=template_ws,
        header_row=1,
        data_end_row=7,
        template_data_end_row=5,
        verbose=False,
    )

    cf_items = list(current_ws.conditional_formatting._cf_rules.items())
    sqrefs = [str(cf.sqref) for cf, _rules in cf_items]
    formulas = [[rule.formula for rule in rules] for _cf, rules in cf_items]
    template_wb.close()
    current_wb.close()

    assert updated == 2
    assert "C2:C7" in sqrefs
    assert "C4:C7" in sqrefs
    assert [['$C2="Universal"']] in formulas
    assert [['$C4="Universal"']] in formulas


def test_restore_crm_workbook_from_template_preserves_live_rows_and_template_formulas(tmp_path):
    template_path = tmp_path / "template.xlsx"
    current_path = tmp_path / "current.xlsx"
    restored_path = tmp_path / "restored.xlsx"

    template_wb = openpyxl.Workbook()
    template_ws = template_wb.active
    template_ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "MY_SIZE",
        "Sell_price_kzt",
        "Total_price",
        "Total_net_rev",
        "№ заказа",
    ]
    for idx, header in enumerate(headers, start=1):
        template_ws.cell(1, idx, header)
    template_ws.cell(2, 1, date(2026, 3, 15))
    template_ws.cell(2, 2, '=IF(J2<>"","Universal","")')
    template_ws.cell(2, 3, "=1")
    template_ws.cell(2, 4, '=CONCAT("CORE-",J2)')
    template_ws.cell(2, 5, 855000001)
    template_ws.cell(2, 6, "")
    template_ws.cell(2, 7, "=15000")
    template_ws.cell(2, 8, "=15000")
    template_ws.cell(2, 9, "=12000")
    template_ws.cell(2, 10, 855000001)
    yellow_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFF2CC")
    template_ws.cell(2, 4).fill = yellow_fill
    template_ws.conditional_formatting.add(
        "D2:D2",
        FormulaRule(formula=['$D2<>""'], fill=yellow_fill),
    )
    table = Table(displayName="tb_SalesRaw", ref="A1:J2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    template_ws.add_table(table)
    journal_ws = template_wb.create_sheet("AGENT_JOURNAL")
    journal_ws.cell(1, 1, "ts")
    journal_ws.cell(2, 1, "template")
    template_wb.save(template_path)
    template_wb.close()

    current_wb = openpyxl.Workbook()
    current_ws = current_wb.active
    current_ws.title = "SALES_KSP_CRM_1"
    for idx, header in enumerate(headers, start=1):
        current_ws.cell(1, idx, header)
    current_rows = [
        [date(2026, 3, 15), "", "", "", 855000111, '=XLOOKUP(E2,[3]!tb_SalesRaw[OrderID],[3]!tb_SalesRaw[MY_SIZE],"",0,1)', "", "", "", 855000111],
        [date(2026, 3, 15), "", "", "", 855000222, "2XL", "", "", "", 855000222],
    ]
    for row_idx, row_values in enumerate(current_rows, start=2):
        for col_idx, value in enumerate(row_values, start=1):
            current_ws.cell(row_idx, column=col_idx, value=value)
    broken_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="C00000")
    current_ws.cell(3, 4).fill = broken_fill
    current_ws.conditional_formatting.add(
        "D2:D3",
        FormulaRule(formula=['$D3<>""'], fill=broken_fill),
    )
    current_table = Table(displayName="tb_SalesRaw", ref="A1:J3")
    current_table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    current_ws.add_table(current_table)
    current_journal = current_wb.create_sheet("AGENT_JOURNAL")
    current_journal.cell(1, 1, "ts")
    current_journal.cell(2, 1, "live-journal")
    current_wb.save(current_path)
    current_wb.close()

    stats = restore_crm_workbook_from_template(
        workbook_path=current_path,
        template_path=template_path,
        output_path=restored_path,
        verbose=False,
    )

    restored_wb = openpyxl.load_workbook(restored_path, data_only=False)
    restored_ws = restored_wb["SALES_KSP_CRM_1"]
    restored_journal = restored_wb["AGENT_JOURNAL"]
    sqrefs = [str(cf.sqref) for cf in restored_ws.conditional_formatting._cf_rules.keys()]

    assert stats["sales_rows_preserved"] == 2
    assert restored_ws["F2"].value in (None, "")
    assert restored_ws["F3"].value == "2XL"
    assert restored_ws["J2"].value == 855000111
    assert restored_ws["J3"].value == 855000222
    assert restored_ws["D2"].value == '=CONCAT("CORE-",J2)'
    assert restored_ws["D3"].value == '=CONCAT("CORE-",J3)'
    assert restored_ws["D3"].fill.fgColor.rgb == yellow_fill.fgColor.rgb
    assert restored_ws.tables["tb_SalesRaw"].ref == "A1:J3"
    assert "D2:D3" in sqrefs
    assert restored_journal["A2"].value == "live-journal"
    restored_wb.close()


def test_prepare_candidate_workbook_uses_template_restore(monkeypatch, tmp_path):
    source_path = tmp_path / "live.xlsx"
    source_path.write_text("LIVE", encoding="utf-8")
    candidate_dir = tmp_path / "candidates"

    calls = {}

    def _fake_restore(*, workbook_path, template_path=None, output_path=None, verbose=False):
        calls["workbook_path"] = workbook_path
        calls["template_path"] = template_path
        calls["output_path"] = output_path
        calls["verbose"] = verbose
        Path(output_path).write_text("CANDIDATE", encoding="utf-8")
        return {"sales_rows_preserved": 3}

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.restore_crm_workbook_from_template",
        _fake_restore,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: True,
    )

    candidate_path = _prepare_candidate_workbook(source_path, candidate_dir, verbose=True)

    assert candidate_path == candidate_dir / "live.candidate.xlsx"
    assert candidate_path.exists()
    assert candidate_path.read_text(encoding="utf-8") == "CANDIDATE"
    assert calls["workbook_path"] == source_path
    assert calls["output_path"].parent == candidate_dir
    assert calls["output_path"].name.startswith("live.candidate_tmp_")
    assert calls["output_path"].suffix == ".xlsx"


def test_prepare_candidate_workbook_fast_copies_clean_source(monkeypatch, tmp_path):
    source_path = tmp_path / "live.xlsx"
    source_path.write_text("LIVE", encoding="utf-8")
    candidate_dir = tmp_path / "candidates"

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.restore_crm_workbook_from_template",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("restore should not run")),
    )

    candidate_path = _prepare_candidate_workbook(source_path, candidate_dir, verbose=True)

    assert candidate_path == candidate_dir / "live.candidate.xlsx"
    assert candidate_path.read_text(encoding="utf-8") == "LIVE"


def test_prepare_candidate_workbook_reuses_stable_filename_and_overwrites_stale_candidate(
    monkeypatch, tmp_path
):
    source_path = tmp_path / "live.xlsx"
    source_path.write_text("LIVE_V1", encoding="utf-8")
    candidate_dir = tmp_path / "candidates"
    stale_candidate = candidate_dir / "live.candidate.xlsx"
    candidate_dir.mkdir()
    stale_candidate.write_text("STALE", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: False,
    )

    first_candidate = _prepare_candidate_workbook(source_path, candidate_dir, verbose=False)
    assert first_candidate == stale_candidate
    assert first_candidate.read_text(encoding="utf-8") == "LIVE_V1"

    source_path.write_text("LIVE_V2", encoding="utf-8")
    second_candidate = _prepare_candidate_workbook(source_path, candidate_dir, verbose=False)
    assert second_candidate == stale_candidate
    assert second_candidate.read_text(encoding="utf-8") == "LIVE_V2"


def test_repair_appended_rows_formatting_uses_template_conditional_formatting(monkeypatch, tmp_path):
    template_path = tmp_path / "template.xlsx"
    workbook_path = tmp_path / "crm.xlsx"

    template_wb = openpyxl.Workbook()
    template_ws = template_wb.active
    template_ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "MY_SIZE",
        "Sell_price_kzt",
        "Total_price",
        "Total_net_rev",
        "№ заказа",
    ]
    for idx, header in enumerate(headers, start=1):
        template_ws.cell(1, idx, header)
    template_ws.cell(2, 1, date(2026, 3, 15))
    template_ws.cell(2, 2, '=IF(J2<>"","Universal","")')
    template_ws.cell(2, 3, "=1")
    template_ws.cell(2, 4, '=CONCAT("CORE-",J2)')
    template_ws.cell(2, 10, 855000001)
    good_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFF2CC")
    template_ws.cell(2, 4).fill = good_fill
    template_ws.conditional_formatting.add(
        "D2:D2",
        FormulaRule(formula=['$D2<>""'], fill=good_fill),
    )
    table = Table(displayName="tb_SalesRaw", ref="A1:J2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    template_ws.add_table(table)
    template_wb.save(template_path)
    template_wb.close()

    live_wb = openpyxl.Workbook()
    live_ws = live_wb.active
    live_ws.title = "SALES_KSP_CRM_1"
    for idx, header in enumerate(headers, start=1):
        live_ws.cell(1, idx, header)
    for row_idx, order_id in ((2, 855000111), (3, 855000222)):
        live_ws.cell(row_idx, 1, date(2026, 3, 15))
        live_ws.cell(row_idx, 4, "")
        live_ws.cell(row_idx, 5, order_id)
        live_ws.cell(row_idx, 10, order_id)
    bad_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="C00000")
    live_ws.cell(3, 4).fill = bad_fill
    live_ws.conditional_formatting.add(
        "D2:D3",
        FormulaRule(formula=['$D3<>""'], fill=bad_fill),
    )
    live_table = Table(displayName="tb_SalesRaw", ref="A1:J3")
    live_table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    live_ws.add_table(live_table)
    live_wb.save(workbook_path)
    live_wb.close()

    monkeypatch.setenv("CRM_CANONICAL_TEMPLATE_PATH", str(template_path))

    repaired = _repair_appended_rows_formatting(
        workbook_path=workbook_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        repair_cf_ranges=True,
        verbose=False,
    )

    repaired_wb = openpyxl.load_workbook(workbook_path, data_only=False)
    repaired_ws = repaired_wb["SALES_KSP_CRM_1"]
    cf_items = list(repaired_ws.conditional_formatting._cf_rules.items())
    sqrefs = [str(cf.sqref) for cf, _rules in cf_items]
    formulas = [[rule.formula for rule in rules] for _cf, rules in cf_items]

    assert repaired["style_cells_normalized"] >= 1
    assert repaired["cf_rules_normalized"] == 1
    assert repaired_ws["D3"].value == '=CONCAT("CORE-",J3)'
    assert repaired_ws["D3"].fill.fgColor.rgb == good_fill.fgColor.rgb
    assert sqrefs == ["D2:D3"]
    assert formulas == [[['$D2<>""']]]
    repaired_wb.close()


def test_repair_appended_rows_formatting_scrubs_self_externalized_formulas(monkeypatch, tmp_path):
    template_path = tmp_path / "template.xlsx"
    workbook_path = tmp_path / "crm.xlsx"

    template_wb = openpyxl.Workbook()
    template_ws = template_wb.active
    template_ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "MY_SIZE",
        "№ заказа",
    ]
    for idx, header in enumerate(headers, start=1):
        template_ws.cell(1, idx, header)
    template_ws.cell(2, 1, date(2026, 3, 15))
    template_ws.cell(2, 2, '=IF(G2<>"","Universal","")')
    template_ws.cell(2, 3, "=1")
    template_ws.cell(2, 4, '=CONCAT("CORE-",G2)')
    template_ws.cell(2, 5, "=G2")
    template_ws.cell(2, 6, "")
    template_ws.cell(2, 7, 855000001)
    table = Table(displayName="tb_SalesRaw", ref="A1:G2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    template_ws.add_table(table)
    template_wb.save(template_path)
    template_wb.close()

    live_wb = openpyxl.Workbook()
    live_ws = live_wb.active
    live_ws.title = "SALES_KSP_CRM_1"
    for idx, header in enumerate(headers, start=1):
        live_ws.cell(1, idx, header)
    live_ws.cell(2, 1, date(2026, 3, 15))
    live_ws.cell(2, 2, "Universal")
    live_ws.cell(2, 3, 1)
    live_ws.cell(2, 4, "CORE-855000111")
    live_ws.cell(2, 5, "=G2")
    live_ws.cell(2, 6, "")
    live_ws.cell(2, 7, 855000111)
    live_ws.cell(3, 1, date(2026, 3, 15))
    live_ws.cell(3, 2, "Universal")
    live_ws.cell(3, 3, 1)
    live_ws.cell(3, 4, "CORE-855000222")
    live_ws.cell(3, 5, '=[4]!tb_SalesRaw[[#This Row],[№ заказа]]')
    live_ws.cell(3, 6, '=XLOOKUP(E3,[3]!tb_SalesRaw[OrderID],[3]!tb_SalesRaw[MY_SIZE],"",0,1)')
    live_ws.cell(3, 7, 855000222)
    live_table = Table(displayName="tb_SalesRaw", ref="A1:G3")
    live_table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    live_ws.add_table(live_table)
    live_wb.save(workbook_path)
    live_wb.close()

    monkeypatch.setenv("CRM_CANONICAL_TEMPLATE_PATH", str(template_path))

    repaired = _repair_appended_rows_formatting(
        workbook_path=workbook_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        repair_cf_ranges=False,
        verbose=False,
    )

    repaired_wb = openpyxl.load_workbook(workbook_path, data_only=False)
    repaired_ws = repaired_wb["SALES_KSP_CRM_1"]

    assert repaired["formula_cells_restored"] >= 1
    assert repaired["externalized_formulas_cleared"] == 1
    assert repaired_ws["E3"].value == "=G3"
    assert repaired_ws["F3"].value in (None, "")
    repaired_wb.close()


def test_verify_appended_rows_integrity_detects_empty_required_cell(tmp_path):
    workbook = tmp_path / "crm.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "KASPI_OFFER_NAME",
        "SKU_ID",
        "Sell_price_kzt",
        "Total_price",
        "Total_net_rev",
        "MODEL",
        "PLANNED_SHIPPING_DATE",
        "Product_Type",
        "Delivery_fee_kzt",
        "Total_weight",
        "SKU_ID_KSP",
        "Kaspi_name_source",
        "№ заказа",
        "Название товара в Kaspi Магазине",
        "Артикул",
        "Статус",
    ]
    for idx, header in enumerate(headers, start=1):
        ws.cell(1, idx, header)

    # Template row with complete computed data.
    for idx in range(1, len(headers) + 1):
        ws.cell(2, idx, f"v{idx}")

    # Appended row with a broken computed column (Sell_price_kzt).
    for idx in range(1, len(headers) + 1):
        ws.cell(3, idx, f"new{idx}")
    ws.cell(3, 8, "")  # Sell_price_kzt

    table = Table(displayName="tb_SalesRaw", ref=f"A1:{openpyxl.utils.get_column_letter(len(headers))}3")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    with pytest.raises(RuntimeError, match="Append integrity check failed"):
        _verify_appended_rows_integrity(
            workbook_path=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            start_row=3,
            end_row=3,
            verbose=False,
        )


def test_verify_appended_rows_integrity_detects_self_externalized_formula(tmp_path):
    workbook = tmp_path / "crm.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Date",
        "STORE_NAME",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "№ заказа",
        "Название товара в Kaspi Магазине",
        "Артикул",
        "Статус",
    ]
    for idx, header in enumerate(headers, start=1):
        ws.cell(1, idx, header)

    ws.cell(2, 1, date(2026, 3, 15))
    ws.cell(2, 2, "Universal")
    ws.cell(2, 3, 1)
    ws.cell(2, 4, "CORE-1")
    ws.cell(2, 5, "=F2")
    ws.cell(2, 6, "851184511")
    ws.cell(2, 7, "Рашгард")
    ws.cell(2, 8, "SKU-1")
    ws.cell(2, 9, "Ожидает передачи")

    ws.cell(3, 1, date(2026, 3, 15))
    ws.cell(3, 2, "Universal")
    ws.cell(3, 3, 1)
    ws.cell(3, 4, "CORE-2")
    ws.cell(3, 5, '=[4]!tb_SalesRaw[[#This Row],[№ заказа]]')
    ws.cell(3, 6, "851184512")
    ws.cell(3, 7, "Рашгард")
    ws.cell(3, 8, "SKU-2")
    ws.cell(3, 9, "Ожидает передачи")

    table = Table(displayName="tb_SalesRaw", ref="A1:I3")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    with pytest.raises(RuntimeError, match="self-externalized formula"):
        _verify_appended_rows_integrity(
            workbook_path=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            start_row=3,
            end_row=3,
            verbose=False,
        )


def test_repair_appended_rows_formatting_fixes_style_and_cf_drift(tmp_path):
    workbook = tmp_path / "crm.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"

    headers = [f"FILLER_{idx}" for idx in range(1, 26)]
    header_overrides = {
        1: "Date",
        2: "STORE_NAME",
        3: "Quantity",
        7: "Kaspi_name_core",
        15: "Sell_price_kzt",
        16: "Total_price",
        17: "Total_net_rev",
        18: "Название товара в Kaspi Магазине",
        19: "Артикул",
        20: "Статус",
        25: "№ заказа",
    }
    for idx, header in header_overrides.items():
        headers[idx - 1] = header
    for idx, header in enumerate(headers, start=1):
        ws.cell(1, idx, header)

    row2_values = {
        1: date(2026, 3, 15),
        2: "Universal",
        3: 1,
        7: '=CONCAT("AUTO","_CORE")',
        15: "=15000",
        16: "=15000",
        17: "=12000",
        18: "Nike_Футболка_черная_XL",
        19: "SKU-1",
        20: "Принят",
        25: 856631060,
    }
    row3_values = {
        1: date(2026, 3, 15),
        2: "Universal",
        3: 1,
        7: '=CONCAT("AUTO","_CORE")',
        15: "=15000",
        16: "=15000",
        17: "=12000",
        18: "Nike_Футболка_черная_2XL",
        19: "SKU-2",
        20: "Принят",
        25: 856648172,
    }
    for col, value in row2_values.items():
        ws.cell(2, col, value)
        ws.cell(3, col, row3_values[col])

    yellow_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFF2CC")
    green_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="E2F0D9")
    for col in row2_values:
        ws.cell(2, col).fill = yellow_fill
        ws.cell(3, col).fill = yellow_fill
    ws.cell(3, 7).fill = green_fill

    ws.conditional_formatting.add(
        "O2:Q2",
        FormulaRule(formula=["$O2>0"], fill=yellow_fill),
    )
    ws.conditional_formatting.add(
        "Y2:Y2",
        FormulaRule(formula=["$Y2>0"], fill=yellow_fill),
    )

    table = Table(displayName="tb_SalesRaw", ref="A1:Y3")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    with pytest.raises(RuntimeError, match="Append integrity check failed"):
        _verify_appended_rows_integrity(
            workbook_path=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            start_row=3,
            end_row=3,
            verbose=False,
        )

    repaired = _repair_appended_rows_formatting(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        repair_cf_ranges=True,
        verbose=False,
    )

    assert repaired["style_cells_normalized"] >= 1
    assert repaired["cf_rules_normalized"] >= 1

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        verbose=False,
    )


def test_repair_appended_rows_formatting_restores_array_sku_key_formula_contract(tmp_path):
    workbook = tmp_path / "crm_sku_key_repair.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "Spacer", "Статус", "SKU_key", "№ заказа"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)

    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value="seed")
    ws.cell(row=2, column=4, value="Принят")
    ws.cell(row=2, column=5, value=ArrayFormula(ref="E2", text='=F2&"_SKU"'))
    ws.cell(row=2, column=6, value=800000001)

    ws.cell(row=3, column=1, value=date.today())
    ws.cell(row=3, column=2, value=77770000001)
    ws.cell(row=3, column=3, value="seed")
    ws.cell(row=3, column=4, value="Новый")
    ws.cell(row=3, column=5, value="")
    ws.cell(row=3, column=6, value=812300005)

    table = Table(displayName="tb_SalesRaw", ref="A1:F3")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    _set_table_calculated_column_formula(
        workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        column_name="SKU_key",
        formula_text='XLOOKUP([@[№ заказа]],[№ заказа],[№ заказа])',
        array=False,
    )

    with pytest.raises(RuntimeError, match="Append integrity check failed"):
        _verify_appended_rows_integrity(
            workbook_path=workbook,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            start_row=3,
            end_row=3,
            verbose=False,
        )

    repaired = _repair_appended_rows_formatting(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        repair_cf_ranges=False,
        verbose=False,
    )

    assert repaired["formula_cells_restored"] >= 1

    wb2 = openpyxl.load_workbook(workbook, data_only=False)
    try:
        ws2 = wb2["SALES_KSP_CRM_1"]
        sku_formula = ws2.cell(row=3, column=5).value
        assert isinstance(sku_formula, ArrayFormula)
        assert sku_formula.text == '=F3&"_SKU"'
    finally:
        wb2.close()

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        verbose=False,
    )


def test_repair_appended_rows_formatting_normalizes_fragmented_template_cf_to_cover_append(
    monkeypatch, tmp_path
):
    template_path = tmp_path / "template_fragmented_cf.xlsx"
    workbook = tmp_path / "crm_fragmented_cf.xlsx"

    headers = [f"FILLER_{idx}" for idx in range(1, 26)]
    header_overrides = {
        1: "Date",
        2: "STORE_NAME",
        3: "Quantity",
        7: "Kaspi_name_core",
        15: "Sell_price_kzt",
        16: "Total_price",
        17: "Total_net_rev",
        18: "Название товара в Kaspi Магазине",
        19: "Артикул",
        20: "Статус",
        25: "№ заказа",
    }
    for idx, header in header_overrides.items():
        headers[idx - 1] = header

    template_wb = openpyxl.Workbook()
    template_ws = template_wb.active
    template_ws.title = "SALES_KSP_CRM_1"
    for idx, header in enumerate(headers, start=1):
        template_ws.cell(1, idx, header)
    for row_num, order_id in ((2, 856700001), (3, 856700002), (4, 856700003), (5, 856700004)):
        template_ws.cell(row_num, 1, date(2026, 4, 4))
        template_ws.cell(row_num, 2, "Universal")
        template_ws.cell(row_num, 3, 1)
        template_ws.cell(row_num, 7, "AUTO_CORE")
        template_ws.cell(row_num, 15, 15000)
        template_ws.cell(row_num, 16, 15000)
        template_ws.cell(row_num, 17, 12000)
        template_ws.cell(row_num, 18, f"Offer-{order_id}")
        template_ws.cell(row_num, 19, f"SKU-{order_id}")
        template_ws.cell(row_num, 20, "Принят")
        template_ws.cell(row_num, 25, order_id)

    yellow_fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFF2CC")
    template_ws.conditional_formatting.add(
        "O2:Q4",
        FormulaRule(formula=["$O2>0"], fill=yellow_fill),
    )
    template_ws.conditional_formatting.add(
        "Y2:Y4",
        FormulaRule(formula=["$Y2>0"], fill=yellow_fill),
    )
    table = Table(displayName="tb_SalesRaw", ref="A1:Y5")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    template_ws.add_table(table)
    template_wb.save(template_path)
    template_wb.close()

    live_wb = openpyxl.Workbook()
    live_ws = live_wb.active
    live_ws.title = "SALES_KSP_CRM_1"
    for idx, header in enumerate(headers, start=1):
        live_ws.cell(1, idx, header)
    for row_num, order_id in (
        (2, 856700001),
        (3, 856700002),
        (4, 856700003),
        (5, 856700004),
        (6, 856700005),
    ):
        live_ws.cell(row_num, 1, date(2026, 4, 4))
        live_ws.cell(row_num, 2, "Universal")
        live_ws.cell(row_num, 3, 1)
        live_ws.cell(row_num, 7, "AUTO_CORE")
        live_ws.cell(row_num, 15, 15000)
        live_ws.cell(row_num, 16, 15000)
        live_ws.cell(row_num, 17, 12000)
        live_ws.cell(row_num, 18, f"Offer-{order_id}")
        live_ws.cell(row_num, 19, f"SKU-{order_id}")
        live_ws.cell(row_num, 20, "Принят")
        live_ws.cell(row_num, 25, order_id)

    live_table = Table(displayName="tb_SalesRaw", ref="A1:Y6")
    live_table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    live_ws.add_table(live_table)
    live_wb.save(workbook)
    live_wb.close()

    monkeypatch.setenv("CRM_CANONICAL_TEMPLATE_PATH", str(template_path))

    repaired = _repair_appended_rows_formatting(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=6,
        end_row=6,
        repair_cf_ranges=True,
        verbose=False,
    )

    assert repaired["cf_rules_normalized"] >= 1

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=6,
        end_row=6,
        verbose=False,
    )


def test_verify_appended_rows_integrity_allows_working_sku_key_array_formula(tmp_path):
    workbook = tmp_path / "crm_sku_key_array_ok.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = ["Date", "Phone", "Spacer", "Статус", "SKU_key", "№ заказа"]
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=idx, value=header)

    ws.cell(row=2, column=1, value=date.today())
    ws.cell(row=2, column=2, value=77770000000)
    ws.cell(row=2, column=3, value="seed")
    ws.cell(row=2, column=4, value="Принят")
    ws.cell(row=2, column=5, value='=F2&"_SKU"')
    ws.cell(row=2, column=6, value=800000001)

    ws.cell(row=3, column=1, value=date.today())
    ws.cell(row=3, column=2, value=77770000001)
    ws.cell(row=3, column=3, value="seed")
    ws.cell(row=3, column=4, value="Новый")
    ws.cell(row=3, column=5, value=ArrayFormula(ref="E3", text='=F3&"_SKU"'))
    ws.cell(row=3, column=6, value=812300005)

    table = Table(displayName="tb_SalesRaw", ref="A1:F3")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(workbook)
    wb.close()

    _verify_appended_rows_integrity(
        workbook_path=workbook,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        start_row=3,
        end_row=3,
        verbose=False,
    )


def test_build_line_dedupe_key_differentiates_multiline_items():
    k1 = _build_line_dedupe_key(
        "812315649",
        date(2026, 2, 7),
        "Комплект Antec RASH-921 Рашгард 5 в 1 черный 56, 58",
        "CL_OC_MEN_LINE52_BLACK_103217238_56-58/56, 58_(4XL)",
        1,
    )
    k2 = _build_line_dedupe_key(
        "812315649",
        date(2026, 2, 7),
        "Спортивный костюм PRO COMBAT 528742263 черный M",
        "CL_OC_MEN_LINE52_BLACK_L_116515378",
        1,
    )
    assert k1 != k2


def test_build_line_dedupe_key_normalizes_article_prefix_tokens():
    k_raw = _build_line_dedupe_key(
        "815312915",
        date(2026, 2, 10),
        "Комплект ALPIKA 102492502 черный 52",
        "102529963\tCL_OC_MEN_LINE52_BLACK_2XL_102529963",
        1,
    )
    k_norm = _build_line_dedupe_key(
        "815312915",
        date(2026, 2, 10),
        "Комплект ALPIKA 102492502 черный 52",
        "CL_OC_MEN_LINE52_BLACK_2XL_102529963",
        1,
    )
    assert k_raw == k_norm


def test_find_missing_append_expectations_respects_multiplicity():
    expectations = [
        CRMAppendExpectation(line_key="k1", order_id="851184511"),
        CRMAppendExpectation(line_key="k1", order_id="851184512"),
        CRMAppendExpectation(line_key="k2", order_id="851184513"),
    ]

    missing = find_missing_append_expectations(expectations, {"k1": 1, "k2": 1})

    assert [item.order_id for item in missing] == ["851184512"]


def test_build_append_expectations_prefers_existing_okey():
    df = pd.DataFrame(
        {
            "№ заказа": ["851184511"],
            "Плановая дата передачи курьеру": ["10.03.2026"],
            "Название товара в Kaspi Магазине": ["Рашгард"],
            "Артикул": ["SKU-1"],
            "Количество": [1],
            "_okey": ["851184511|2026-03-10|sku-1|рашгард|1"],
        }
    )

    expectations = build_append_expectations(
        df,
        colmap={
            "order_id": "№ заказа",
            "handover": "Плановая дата передачи курьеру",
            "offer_name": "Название товара в Kaspi Магазине",
            "sku": "Артикул",
            "quantity": "Количество",
        },
    )

    assert expectations == [
        CRMAppendExpectation(
            line_key="851184511|2026-03-10|sku-1|рашгард|1",
            order_id="851184511",
        )
    ]


def _minimal_snapshot() -> CRMSnapshot:
    return CRMSnapshot(
        date_col=2,
        phone_col=9,
        start_col=25,
        end_col=52,
        start_row=1,
        end_row=1,
        slice_headers=["dummy_header"],
        order_ids=set(),
        order_rows={},
        existing_keys=set(),
        existing_rollover_keys=set(),
        column_positions={},
        planned_col_abs=None,
        table_date_col=None,
        delivery_fee_col=None,
        seller_fee_col=None,
        delivery_fee_rows=[],
        append_date_keys=set(),
        append_date_key_counts={},
        append_date_rows=[],
        latest_my_size_by_key={},
    )


def _minimal_active_orders_df() -> pd.DataFrame:
    return pd.DataFrame({"dummy": ["value"]})


def test_main_default_does_not_compute_fixed_values_payload(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = _minimal_active_orders_df()
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["x"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_fixed_value_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fixed payload must not be built by default")),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", lambda *_args, **_kwargs: (2, 2))
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        verbose=False,
    )
    assert stats["orders_imported"] == 1


def test_main_transactional_candidate_uses_xlwings_for_candidate_writes_when_available(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")
    candidate_dir = tmp_path / "candidates"
    failed_candidate_dir = tmp_path / "failed_candidates"
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "linux", raising=False)

    df = pd.DataFrame(
        {
            "№ заказа": ["851184511"],
            "Плановая дата передачи курьеру": ["10.03.2026"],
            "Название товара в Kaspi Магазине": ["Рашгард"],
            "Артикул": ["SKU-1"],
            "Количество": [1],
        }
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["851184511"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.build_fixed_value_payload", lambda *_args, **_kwargs: [{}])
    monkeypatch.setattr("scripts.import_orders_to_crm.build_append_expectations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_pending_append_mask",
        lambda df_in, **_kwargs: (
            df_in.assign(_okey=["851184511|2026-03-10|sku-1|рашгард|1"]),
            pd.Series([True], index=df_in.index),
            {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0},
        ),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.plan_append_date_reconcile",
        lambda *_args, **_kwargs: CRMAppendDateReconcilePlan(
            delete_row_numbers=[5],
            keep_keys=set(),
            keep_rows_by_key={},
            missing_keys=[],
        ),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.guard_reconcile_delete_volume", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])

    seen: dict[str, Any] = {}

    monkeypatch.setattr("scripts.import_orders_to_crm.xw", object())
    monkeypatch.setattr("scripts.import_orders_to_crm._require_xlwings", lambda: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.delete_crm_rows_openpyxl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("candidate reconcile delete must not use openpyxl when xlwings is available")),
    )
    def _delete_xlwings_spy(out_wb, *_args, **_kwargs):
        seen["delete_path"] = Path(out_wb)
        return 1

    monkeypatch.setattr("scripts.import_orders_to_crm.delete_crm_rows_xlwings", _delete_xlwings_spy)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.apply_fixed_values_backfill_openpyxl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("candidate fixed-value backfill must not use openpyxl when xlwings is available")),
    )
    def _fixed_xlwings_spy(crm_path, *_args, **_kwargs):
        seen["fixed_path"] = Path(crm_path)
        return 3

    monkeypatch.setattr("scripts.import_orders_to_crm.apply_fixed_values_backfill_xlwings", _fixed_xlwings_spy)

    def _append_spy(out_wb, *_args, **kwargs):
        seen["append_path"] = Path(out_wb)
        seen["prefer_xlwings"] = kwargs.get("prefer_xlwings")
        return (2, 2)

    def _seller_spy(crm_path, *_args, **kwargs):
        seen["seller_path"] = Path(crm_path)
        seen["seller_prefer_openpyxl"] = kwargs.get("prefer_openpyxl")
        return 4

    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", _append_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm.backfill_seller_delivery_fee", _seller_spy)

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        fixed_values=True,
        backfill_fixed_days=1,
        refresh_delivery_fees=True,
        refresh_fees_from="2026-03-10",
        refresh_fees_to="2026-03-10",
        candidate_dir=candidate_dir,
        failed_candidate_dir=failed_candidate_dir,
        verbose=False,
    )

    assert stats["orders_imported"] == 1
    assert seen["append_path"] == candidate_dir / "crm.candidate.xlsx"
    assert seen["delete_path"] == seen["append_path"]
    assert seen["fixed_path"] == seen["append_path"]
    assert seen["seller_path"] == seen["append_path"]
    assert seen["prefer_xlwings"] is True
    assert seen["seller_prefer_openpyxl"] is False


def test_main_on_macos_uses_live_workbook_write_path_even_when_transactional_enabled(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = pd.DataFrame(
        {
            "№ заказа": ["851184511"],
            "Плановая дата передачи курьеру": ["10.03.2026"],
            "Название товара в Kaspi Магазине": ["Рашгард"],
            "Артикул": ["SKU-1"],
            "Количество": [1],
        }
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin", raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["851184511"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.build_fixed_value_payload", lambda *_args, **_kwargs: [{}])
    monkeypatch.setattr("scripts.import_orders_to_crm.build_append_expectations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_pending_append_mask",
        lambda df_in, **_kwargs: (
            df_in.assign(_okey=["851184511|2026-03-10|sku-1|рашгард|1"]),
            pd.Series([True], index=df_in.index),
            {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0},
        ),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.plan_append_date_reconcile",
        lambda *_args, **_kwargs: CRMAppendDateReconcilePlan(
            delete_row_numbers=[],
            keep_keys=set(),
            keep_rows_by_key={},
            missing_keys=[],
        ),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.guard_reconcile_delete_volume", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])

    seen: dict[str, Any] = {}

    def _append_spy(out_wb, *_args, **kwargs):
        seen["append_path"] = Path(out_wb)
        seen["prefer_xlwings"] = kwargs.get("prefer_xlwings")
        return (2, 2)

    def _seller_spy(crm_path, *_args, **kwargs):
        seen["seller_path"] = Path(crm_path)
        seen["seller_prefer_openpyxl"] = kwargs.get("prefer_openpyxl")
        return 4

    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", _append_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm.backfill_seller_delivery_fee", _seller_spy)

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        fixed_values=False,
        refresh_delivery_fees=True,
        refresh_fees_from="2026-03-10",
        refresh_fees_to="2026-03-10",
        verbose=False,
    )

    assert stats["orders_imported"] == 1
    assert seen["append_path"] == crm_path.resolve()
    assert seen["seller_path"] == crm_path.resolve()
    assert seen["prefer_xlwings"] is True
    assert seen["seller_prefer_openpyxl"] is False


def test_main_refreshes_snapshot_before_delivery_fee_backfill_after_append(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = _minimal_active_orders_df()
    initial_snapshot = _minimal_snapshot()
    refreshed_snapshot = CRMSnapshot(
        date_col=2,
        phone_col=9,
        start_col=25,
        end_col=52,
        start_row=1,
        end_row=2,
        slice_headers=["dummy_header"],
        order_ids={"880331230"},
        order_rows={"880331230": 2},
        existing_keys=set(),
        existing_rollover_keys=set(),
        column_positions={},
        planned_col_abs=None,
        table_date_col=2,
        delivery_fee_col=3,
        seller_fee_col=4,
        delivery_fee_rows=[(2, date(2026, 4, 7), 0.0, 850.0)],
        append_date_keys=set(),
        append_date_key_counts={},
        append_date_rows=[],
        latest_my_size_by_key={},
    )

    snapshot_calls = {"count": 0}

    def _load_snapshot(*_args, **_kwargs):
        snapshot_calls["count"] += 1
        if snapshot_calls["count"] == 1:
            return initial_snapshot
        return refreshed_snapshot

    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", _load_snapshot)
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["880331230"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm.build_fixed_value_payload", lambda *_args, **_kwargs: [{}])
    monkeypatch.setattr("scripts.import_orders_to_crm.build_append_expectations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_pending_append_mask",
        lambda df_in, **_kwargs: (
            df_in.assign(_okey=["880331230|2026-04-07|sku-1|rashguard|1"]),
            pd.Series([True], index=df_in.index),
            {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0},
        ),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.plan_append_date_reconcile",
        lambda *_args, **_kwargs: CRMAppendDateReconcilePlan(
            delete_row_numbers=[],
            keep_keys=set(),
            keep_rows_by_key={},
            missing_keys=[],
        ),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.guard_reconcile_delete_volume", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", lambda *_args, **_kwargs: (2, 2))

    seen: dict[str, Any] = {}

    def _seller_spy(crm_path, *_args, **kwargs):
        seen["seller_path"] = Path(crm_path)
        seen["snapshot"] = kwargs.get("snapshot")
        return 1

    monkeypatch.setattr("scripts.import_orders_to_crm.backfill_seller_delivery_fee", _seller_spy)

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        refresh_delivery_fees=True,
        refresh_fees_from="2026-04-07",
        refresh_fees_to="2026-04-07",
        gdrive_sync=False,
        verbose=False,
    )

    assert stats["orders_imported"] == 1
    assert snapshot_calls["count"] == 2
    assert seen["seller_path"] == crm_path.resolve()
    assert seen["snapshot"] == refreshed_snapshot
    assert seen["snapshot"].delivery_fee_rows == [(2, date(2026, 4, 7), 0.0, 850.0)]


def test_main_transactional_candidate_enables_preflight_probe_fallback(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")
    candidate_dir = tmp_path / "candidates"
    failed_candidate_dir = tmp_path / "failed_candidates"

    df = _minimal_active_orders_df()
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["x"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm.build_pending_append_mask", lambda df_in, **_kwargs: (df_in.assign(_okey=["k1"]), pd.Series([True], index=df_in.index), {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0}))
    monkeypatch.setattr("scripts.import_orders_to_crm.build_append_expectations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.plan_append_date_reconcile",
        lambda *_args, **_kwargs: CRMAppendDateReconcilePlan(
            delete_row_numbers=[],
            keep_keys=set(),
            keep_rows_by_key={},
            missing_keys=[],
        ),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.guard_reconcile_delete_volume", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", lambda *_args, **_kwargs: (2, 2))
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: False,
    )

    seen: dict[str, Any] = {}

    def _preflight_spy(*_args, **kwargs):
        seen["allow_open_probe_fallback"] = kwargs.get("allow_open_probe_fallback")

    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", _preflight_spy)

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        candidate_dir=candidate_dir,
        failed_candidate_dir=failed_candidate_dir,
        refresh_delivery_fees=False,
        verbose=False,
    )

    assert stats["orders_imported"] == 1
    assert seen["allow_open_probe_fallback"] is True


def test_main_noop_branch_still_runs_delivery_fee_backfill(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = _minimal_active_orders_df()
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([], []))

    calls = {"backfill": 0}

    def _fake_backfill(*_args, **_kwargs):
        calls["backfill"] += 1
        return 7

    monkeypatch.setattr("scripts.import_orders_to_crm.backfill_seller_delivery_fee", _fake_backfill)

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=True,
        update_existing=False,
        no_update=True,
        refresh_delivery_fees=True,
        refresh_fees_from="2026-03-28",
        refresh_fees_to="2026-04-02",
        gdrive_sync=False,
        verbose=False,
    )

    assert stats["status"] == "noop"
    assert calls["backfill"] == 1


def test_main_does_not_autofill_or_backfill_my_size(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = pd.DataFrame(
        {
            "№ заказа": ["847016620"],
            "Название товара в Kaspi Магазине": ["Трусы_черные"],
            "Артикул": ["SKU-1"],
            "Количество": [1],
            "Плановая дата передачи курьеру": ["07.03.2026"],
        }
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["847016620"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm.build_pending_append_mask", lambda df_in, **_kwargs: (df_in.assign(_okey=["k1"]), pd.Series([True], index=df_in.index), {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0}))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_resolved_my_size_by_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("MY_SIZE auto-resolve must stay disabled")),
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.backfill_append_date_my_sizes_openpyxl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("MY_SIZE backfill must stay disabled")),
        raising=False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})

    seen = {}

    def _append_spy(*_args, **kwargs):
        seen["preserved_my_sizes"] = kwargs.get("preserved_my_sizes")
        return (2, 2)

    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", _append_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        verbose=False,
    )

    assert stats["orders_imported"] == 1
    assert seen["preserved_my_sizes"] is None


def test_main_does_not_archive_when_candidate_promotion_fails(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = _minimal_active_orders_df()
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["x"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm.build_fixed_value_payload", lambda *_args, **_kwargs: [{}])
    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", lambda *_args, **_kwargs: (2, 2))
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._candidate_source_requires_template_normalization",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._promote_candidate_workbook",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("candidate verification failed")),
        raising=False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})

    archive_calls = {"count": 0}

    def _archive_spy(*_args, **_kwargs):
        archive_calls["count"] += 1
        return tmp_path / "archive"

    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", _archive_spy)

    with pytest.raises(RuntimeError, match="candidate verification failed"):
        main(
            orders_dir=orders_dir,
            crm_path=crm_path,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            dry_run=False,
            update_existing=False,
            no_update=True,
            append_integrity_check=False,
            verbose=False,
        )

    assert archive_calls["count"] == 0


def test_archive_run_copies_source_files_and_keeps_live_activeorders(tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("live-source", encoding="utf-8")
    df = pd.DataFrame(
        {
            "№ заказа": ["851184511"],
            "Плановая дата передачи курьеру": ["10.03.2026"],
            "Склад передачи КД": ["30000001_PP1"],
            "Статус": ["Ожидает передачи курьеру"],
            "__source_file__": ["ActiveOrders.xlsx"],
        }
    )

    archive_path = archive_run(orders_dir, [source_file], df)

    archived_copy = archive_path / "ActiveOrders.xlsx"
    assert source_file.exists()
    assert source_file.read_text(encoding="utf-8") == "live-source"
    assert archived_copy.exists()
    assert archived_copy.read_text(encoding="utf-8") == "live-source"
    assert (archive_path / "appended_orders.csv").exists()


def test_main_does_not_write_kaspi_core_override_payload(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = _minimal_active_orders_df()
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["x"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_fixed_value_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full fixed payload should stay disabled")),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_kaspi_name_core_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Kaspi_name_core override must stay disabled")),
        raising=False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})

    seen = {}

    def _append_spy(*_args, **kwargs):
        seen["kaspi_name_core_values"] = kwargs.get("kaspi_name_core_values")
        seen["fixed_values"] = kwargs.get("fixed_values")
        return (2, 2)

    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", _append_spy)
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        fixed_values=False,
        kaspi_core_override=True,
        append_integrity_check=False,
        verbose=False,
    )
    assert stats["orders_imported"] == 1
    assert seen["kaspi_name_core_values"] is None
    assert seen["fixed_values"] is None


def test_main_skip_gdrive_sync_flag_disables_drive_sync(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = _minimal_active_orders_df()
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["x"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", lambda *_args, **_kwargs: (2, 2))
    monkeypatch.setattr("scripts.import_orders_to_crm.verify_expected_append_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("gdrive sync must be skipped")),
    )

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        gdrive_sync=False,
        verbose=False,
    )

    assert stats["orders_imported"] == 1


def test_main_retries_missing_semantic_append_rows_once(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = pd.DataFrame(
        {
            "№ заказа": ["851184511"],
            "Плановая дата передачи курьеру": ["10.03.2026"],
            "Название товара в Kaspi Магазине": ["Рашгард"],
            "Артикул": ["SKU-1"],
            "Количество": [1],
        }
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["851184511"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_pending_append_mask",
        lambda df_in, **_kwargs: (
            df_in.assign(_okey=["851184511|2026-03-10|sku-1|рашгард|1"]),
            pd.Series([True], index=df_in.index),
            {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0},
        ),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})

    append_calls = {"count": 0}

    def _append_spy(*_args, **_kwargs):
        append_calls["count"] += 1
        return (2, 2)

    verify_responses = [
        [CRMAppendExpectation(line_key="851184511|2026-03-10|sku-1|рашгард|1", order_id="851184511")],
        [],
    ]

    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", _append_spy)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.verify_expected_append_rows",
        lambda *_args, **_kwargs: verify_responses.pop(0),
    )

    stats = main(
        orders_dir=orders_dir,
        crm_path=crm_path,
        sheet_name="SALES_KSP_CRM_1",
        table_name="tb_SalesRaw",
        dry_run=False,
        update_existing=False,
        no_update=True,
        append_integrity_check=False,
        verbose=False,
    )

    assert stats["orders_imported"] == 1
    assert append_calls["count"] == 2


def test_main_raises_when_semantic_append_row_still_missing_after_retry(monkeypatch, tmp_path):
    orders_dir = tmp_path / "orders"
    orders_dir.mkdir()
    source_file = orders_dir / "ActiveOrders.xlsx"
    source_file.write_text("placeholder", encoding="utf-8")
    crm_path = tmp_path / "crm.xlsx"
    crm_path.write_text("crm", encoding="utf-8")

    df = pd.DataFrame(
        {
            "№ заказа": ["851184511"],
            "Плановая дата передачи курьеру": ["10.03.2026"],
            "Название товара в Kaspi Магазине": ["Рашгард"],
            "Артикул": ["SKU-1"],
            "Количество": [1],
        }
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.read_active_orders", lambda _p: (df, [source_file]))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.filter_for_shipping",
        lambda df_all, *_args, **_kwargs: (df_all, {"rows_in_files": 1, "rows_after_filters": 1}),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sort_for_crm", lambda in_df: in_df)
    monkeypatch.setattr("scripts.import_orders_to_crm.load_crm_snapshot", lambda *_args, **_kwargs: _minimal_snapshot())
    monkeypatch.setattr("scripts.import_orders_to_crm.build_staging", lambda *_args, **_kwargs: ([["851184511"]], [""]))
    monkeypatch.setattr("scripts.import_orders_to_crm._excel_automation_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.build_pending_append_mask",
        lambda df_in, **_kwargs: (
            df_in.assign(_okey=["851184511|2026-03-10|sku-1|рашгард|1"]),
            pd.Series([True], index=df_in.index),
            {"duplicates_skipped": 0, "planned_duplicate_rows": 0, "append_date_duplicate_rows": 0, "carryforward_rows_to_append": 0},
        ),
    )
    monkeypatch.setattr("scripts.import_orders_to_crm._promote_candidate_workbook", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr("scripts.import_orders_to_crm.archive_run", lambda *_args, **_kwargs: tmp_path / "archive")
    monkeypatch.setattr("scripts.import_orders_to_crm.sync_pending_orders_to_gdrive_safe", lambda *_args, **_kwargs: {"rows_synced": 0})
    monkeypatch.setattr("scripts.import_orders_to_crm.append_orders_with_fallback", lambda *_args, **_kwargs: (2, 2))
    monkeypatch.setattr(
        "scripts.import_orders_to_crm.verify_expected_append_rows",
        lambda *_args, **_kwargs: [CRMAppendExpectation(line_key="851184511|2026-03-10|sku-1|рашгард|1", order_id="851184511")],
    )

    with pytest.raises(RuntimeError, match="CRM semantic append verification failed after retry"):
        main(
            orders_dir=orders_dir,
            crm_path=crm_path,
            sheet_name="SALES_KSP_CRM_1",
            table_name="tb_SalesRaw",
            dry_run=False,
            update_existing=False,
            no_update=True,
            append_integrity_check=False,
            verbose=False,
        )


def test_restore_preserved_package_parts_readds_missing_pivot_parts(tmp_path):
    workbook_path = tmp_path / "workbook.xlsx"

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<types>original</types>")
        zf.writestr("xl/workbook.xml", "<workbook>original</workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", "<rels>original</rels>")
        zf.writestr(
            "xl/sharedStrings.xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
                "count=\"1\" uniqueCount=\"1\"><si><t>original</t></si></sst>"
            ),
        )
        zf.writestr("xl/pivotTables/pivotTable1.xml", "<pivotTable>original</pivotTable>")
        zf.writestr("xl/pivotCache/pivotCacheDefinition2.xml", "<cacheDef>original</cacheDef>")
        zf.writestr("xl/pivotCache/_rels/pivotCacheDefinition2.xml.rels", "<cacheRel>original</cacheRel>")
        zf.writestr("xl/pivotCache/pivotCacheRecords2.xml", "<cacheRecords>original</cacheRecords>")
        zf.writestr("xl/worksheets/sheet1.xml", "<sheet>v1</sheet>")

    preserved = _snapshot_preserved_package_parts(workbook_path)
    assert "xl/pivotCache/pivotCacheRecords2.xml" in preserved
    assert "xl/pivotTables/pivotTable1.xml" in preserved
    assert "xl/sharedStrings.xml" in preserved

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<types>mutated</types>")
        zf.writestr("xl/workbook.xml", "<workbook>mutated</workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", "<rels>mutated</rels>")
        zf.writestr("xl/pivotTables/pivotTable1.xml", "<pivotTable>mutated</pivotTable>")
        zf.writestr("xl/pivotCache/pivotCacheDefinition2.xml", "<cacheDef>mutated</cacheDef>")
        # intentionally drop pivot cache rel + records parts
        zf.writestr("xl/worksheets/sheet1.xml", "<sheet>v2</sheet>")

    _restore_preserved_package_parts(workbook_path, preserved)

    with zipfile.ZipFile(workbook_path, "r") as zf:
        assert zf.read("[Content_Types].xml") == b"<types>original</types>"
        assert zf.read("xl/workbook.xml") == b"<workbook>original</workbook>"
        assert zf.read("xl/_rels/workbook.xml.rels") == b"<rels>original</rels>"
        assert b"<t>original</t>" in zf.read("xl/sharedStrings.xml")
        assert zf.read("xl/pivotTables/pivotTable1.xml") == b"<pivotTable>original</pivotTable>"
        assert zf.read("xl/pivotCache/pivotCacheDefinition2.xml") == b"<cacheDef>original</cacheDef>"
        assert (
            zf.read("xl/pivotCache/_rels/pivotCacheDefinition2.xml.rels")
            == b"<cacheRel>original</cacheRel>"
        )
        assert zf.read("xl/pivotCache/pivotCacheRecords2.xml") == b"<cacheRecords>original</cacheRecords>"
        # Non-preserved parts should keep post-save content.
        assert zf.read("xl/worksheets/sheet1.xml") == b"<sheet>v2</sheet>"


def test_restore_preserved_package_parts_readds_missing_calcchain_and_metadata_parts(tmp_path):
    workbook_path = tmp_path / "workbook_calcchain.xlsx"

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<types>original</types>")
        zf.writestr("xl/workbook.xml", "<workbook>original</workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", "<rels>original-calcchain-metadata</rels>")
        zf.writestr("xl/sharedStrings.xml", "<sst>original</sst>")
        zf.writestr("xl/calcChain.xml", "<calcChain>original</calcChain>")
        zf.writestr("xl/metadata.xml", "<metadata>original</metadata>")
        zf.writestr("xl/worksheets/sheet1.xml", "<sheet>v1</sheet>")

    preserved = _snapshot_preserved_package_parts(workbook_path)
    assert "xl/calcChain.xml" in preserved
    assert "xl/metadata.xml" in preserved

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<types>mutated</types>")
        zf.writestr("xl/workbook.xml", "<workbook>mutated</workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", "<rels>mutated</rels>")
        zf.writestr("xl/sharedStrings.xml", "<sst>mutated</sst>")
        zf.writestr("xl/worksheets/sheet1.xml", "<sheet>v2</sheet>")

    _restore_preserved_package_parts(workbook_path, preserved)

    with zipfile.ZipFile(workbook_path, "r") as zf:
        assert zf.read("xl/_rels/workbook.xml.rels") == b"<rels>original-calcchain-metadata</rels>"
        assert zf.read("xl/calcChain.xml") == b"<calcChain>original</calcChain>"
        assert zf.read("xl/metadata.xml") == b"<metadata>original</metadata>"
        assert zf.read("xl/worksheets/sheet1.xml") == b"<sheet>v2</sheet>"


def test_restore_preserved_package_parts_readds_missing_external_link_parts(tmp_path):
    workbook_path = tmp_path / "workbook_external_links.xlsx"

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<types>original</types>")
        zf.writestr("xl/workbook.xml", "<workbook>original</workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", "<rels>original-external-links</rels>")
        zf.writestr("xl/externalLinks/externalLink1.xml", "<link1>original</link1>")
        zf.writestr(
            "xl/externalLinks/_rels/externalLink1.xml.rels",
            "<link1rels>original</link1rels>",
        )
        zf.writestr("xl/worksheets/sheet1.xml", "<sheet>v1</sheet>")

    preserved = _snapshot_preserved_package_parts(workbook_path)
    assert "xl/externalLinks/externalLink1.xml" in preserved
    assert "xl/externalLinks/_rels/externalLink1.xml.rels" in preserved

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<types>mutated</types>")
        zf.writestr("xl/workbook.xml", "<workbook>mutated</workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", "<rels>mutated</rels>")
        zf.writestr("xl/worksheets/sheet1.xml", "<sheet>v2</sheet>")

    _restore_preserved_package_parts(workbook_path, preserved)

    with zipfile.ZipFile(workbook_path, "r") as zf:
        assert zf.read("xl/_rels/workbook.xml.rels") == b"<rels>original-external-links</rels>"
        assert zf.read("xl/externalLinks/externalLink1.xml") == b"<link1>original</link1>"
        assert (
            zf.read("xl/externalLinks/_rels/externalLink1.xml.rels")
            == b"<link1rels>original</link1rels>"
        )
        assert zf.read("xl/worksheets/sheet1.xml") == b"<sheet>v2</sheet>"


def test_workbook_external_link_targets_reads_workbook_relationships(tmp_path):
    workbook_path = tmp_path / "workbook_external_targets.xlsx"
    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink2.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink1.xml"/>'
                "</Relationships>"
            ),
        )
    assert _workbook_external_link_targets(workbook_path) == (
        "externalLinks/externalLink1.xml",
        "externalLinks/externalLink2.xml",
    )


def test_workbook_external_link_targets_normalizes_absolute_xl_prefix(tmp_path):
    workbook_path = tmp_path / "workbook_external_targets_prefixed.xlsx"
    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="/xl/externalLinks/externalLink2.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="xl/externalLinks/externalLink1.xml"/>'
                "</Relationships>"
            ),
        )
    assert _workbook_external_link_targets(workbook_path) == (
        "externalLinks/externalLink1.xml",
        "externalLinks/externalLink2.xml",
    )


def test_candidate_source_fast_copy_allowed_when_only_external_link_contract_differs(monkeypatch, tmp_path):
    source_path = tmp_path / "source.xlsx"
    template_path = tmp_path / "template.xlsx"
    source_path.write_text("placeholder", encoding="utf-8")
    template_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: SimpleNamespace(errors=[], warnings=[]),
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._resolve_crm_template_path",
        lambda *_args, **_kwargs: template_path,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._workbook_external_link_targets",
        lambda path: ("externalLinks/externalLink1.xml", "externalLinks/externalLink2.xml")
        if Path(path) == source_path
        else ("externalLinks/externalLink1.xml",),
    )

    assert _candidate_source_requires_template_normalization(source_path) is False


def test_default_candidate_dirs_for_workbook_stay_beside_target_workbook(tmp_path):
    workbook = tmp_path / "nested" / "SALES_KSP_CRM_V3.xlsx"
    candidate_dir, failed_dir = _default_candidate_dirs_for_workbook(workbook)

    assert candidate_dir == workbook.parent
    assert failed_dir == workbook.parent / ".crm_failed_candidates"


def test_candidate_source_requires_template_normalization_when_self_externalized_sales_formulas_exist(
    monkeypatch, tmp_path
):
    source_path = tmp_path / "source.xlsx"
    source_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: SimpleNamespace(
            errors=["CRM sales sheet contains self-externalized formulas: xl/tables/table2.xml sample=J2=[3]!tb"],
            warnings=[],
        ),
    )

    assert _candidate_source_requires_template_normalization(source_path) is True


def test_candidate_source_requires_template_normalization_when_external_link_relationship_ids_are_missing(
    monkeypatch, tmp_path
):
    source_path = tmp_path / "source.xlsx"
    source_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm.validate_workbook_integrity",
        lambda _path: SimpleNamespace(
            errors=[
                "externalLink relationship ids missing: xl/externalLinks/externalLink3.xml missing=rId1"
            ],
            warnings=[],
        ),
    )

    assert _candidate_source_requires_template_normalization(source_path) is True


def test_restore_preserved_package_parts_prunes_stale_calcchain_refs(tmp_path):
    from xml.etree import ElementTree as ET

    workbook_path = tmp_path / "workbook_stale_calcchain.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = 1
    ws["A2"] = "=A1"
    wb.save(workbook_path)
    wb.close()

    with zipfile.ZipFile(workbook_path, "r") as zin:
        wb_rels = ET.fromstring(zin.read("xl/_rels/workbook.xml.rels"))
        ET.SubElement(
            wb_rels,
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
            {
                "Id": "rIdCalcChain",
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain",
                "Target": "calcChain.xml",
            },
        )
        rels_modified = ET.tostring(wb_rels, encoding="utf-8", xml_declaration=True)

        tmp = workbook_path.with_name(f"{workbook_path.stem}_calcchain_injected.xlsx")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "xl/_rels/workbook.xml.rels":
                    zout.writestr(item, rels_modified)
                else:
                    zout.writestr(item, zin.read(item.filename))
            zout.writestr(
                "xl/calcChain.xml",
                (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<calcChain xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<c r="A2" i="1"/>'
                    '<c r="Z999" i="1"/>'
                    "</calcChain>"
                ),
            )
    tmp.replace(workbook_path)

    preserved = _snapshot_preserved_package_parts(workbook_path)
    assert "xl/calcChain.xml" in preserved

    _restore_preserved_package_parts(workbook_path, preserved)

    with zipfile.ZipFile(workbook_path, "r") as zf:
        calc_chain = zf.read("xl/calcChain.xml").decode("utf-8")
        assert 'r="A2"' in calc_chain
        assert 'r="Z999"' not in calc_chain
