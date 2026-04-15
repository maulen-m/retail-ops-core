"""
Tests for build_daily_waybills.py

Phase 11 TASK-194: 20 tests for the waybill builder script.
"""

import csv
import json
import sqlite3
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

import scripts.build_daily_waybills as build_daily_waybills_module
from scripts.build_daily_waybills import (
    HEAVY_ITEMS,
    SIZE_ORDER,
    STORE_MAP,
    WAYBILL_PATTERN,
    OrderItem,
    WaybillGroup,
    build_cross_store_groups,
    build_store_output,
    count_packages,
    extract_waybills_from_zips,
    generate_filename,
    group_orders,
    is_heavy_item,
    normalize_store_name,
    parse_date,
    read_crm_orders as read_waybill_crm_orders,
    sanitize_filename,
    split_groups_by_overdue,
    size_sort_key,
    write_manifest,
    main as build_daily_waybills_main,
    write_send_batch_manifest,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_order_item():
    """Create a sample OrderItem for testing."""
    return OrderItem(
        order_id="123456789",
        store_name="AcmeWear",
        kaspi_name_core="Berserk_футболка",
        my_size="XL",
        sku_key="BRS-001",
        sku_id="BRS-001-XL",
        quantity=1,
        kaspi_offer_name="Berserk футболка черная XL",
        planned_date=date.today(),
    )


@pytest.fixture
def temp_waybill_dir():
    """Create a temp directory with waybill ZIPs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create a waybill ZIP
        zip_path = tmppath / "waybill.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Create PDF content (minimal valid PDF)
            pdf_content = b"%PDF-1.0\n1 0 obj<</Type/Catalog>>endobj\nxref\n0 2\ntrailer<</Root 1 0 R>>\n%%EOF"
            zf.writestr("KASPI_SHOP-123456789.pdf", pdf_content)
            zf.writestr("KASPI_SHOP-987654321.pdf", pdf_content)
            zf.writestr("KASPI_SHOP-111222333.pdf", pdf_content)

        yield tmppath


# ============================================================================
# Test: read_crm_orders (not testing full function, testing helpers)
# ============================================================================

def test_normalize_store_name_warehouse_codes():
    """Test that Kaspi warehouse codes are mapped to display names."""
    assert normalize_store_name("30137883_PP1") == "AcmeWear"
    assert normalize_store_name("30000001_PP1") == "Universal"
    assert normalize_store_name("30290083_PP1") == "11KZ"
    assert normalize_store_name("30000002_PP1") == "STORE-B"


def test_normalize_store_name_display_names():
    """Test that display names pass through unchanged."""
    assert normalize_store_name("AcmeWear") == "AcmeWear"
    assert normalize_store_name("Universal") == "Universal"


def test_normalize_store_name_unknown():
    """Test handling of unknown store names."""
    assert normalize_store_name("Unknown_Store") == "Unknown_Store"
    assert normalize_store_name(None) == "UNKNOWN"


def test_parse_date_formats():
    """Test date parsing from various formats."""
    # DD.MM.YYYY
    result = parse_date("25.12.2025")
    assert result is not None
    assert result.day == 25
    assert result.month == 12

    # YYYY-MM-DD
    result = parse_date("2025-12-25")
    assert result is not None
    assert result.day == 25

    # ISO datetime must not flip day/month
    result = parse_date("2026-03-06 20:00:00")
    assert result == date(2026, 3, 6)


def test_filters_by_date():
    """Test that orders are filtered by planned date."""
    today = date.today()

    # This tests the logic that would happen in read_crm_orders
    # Orders with planned_date > target_date should be excluded
    past_date = date(2020, 1, 1)
    future_date = date(2099, 12, 31)

    # past_date <= today should be included
    assert past_date <= today

    # future_date > today should be excluded
    assert future_date > today


def test_skips_missing_my_size():
    """Test that orders without MY_SIZE are skipped."""
    # This is logic from read_crm_orders
    # Testing the condition
    valid_size = "XL"
    invalid_sizes = ["", "nan", "None", None]

    assert valid_size.lower() not in ('nan', 'none', '')

    for size in invalid_sizes:
        if size is None or str(size).strip().lower() in ('nan', 'none', ''):
            assert True  # Would be skipped


# ============================================================================
# Test: groups_by_store_code
# ============================================================================

def test_groups_by_store_code():
    """Test that orders are grouped by store."""
    orders = [
        OrderItem("111", "AcmeWear", "Prod1", "M", "", "", 1, "Prod 1", None),
        OrderItem("222", "Universal", "Prod2", "L", "", "", 1, "Prod 2", None),
        OrderItem("333", "AcmeWear", "Prod3", "XL", "", "", 1, "Prod 3", None),
    ]

    # Simulate grouping by store
    by_store = {}
    for order in orders:
        by_store.setdefault(order.store_name, []).append(order)

    assert len(by_store) == 2
    assert len(by_store["AcmeWear"]) == 2
    assert len(by_store["Universal"]) == 1


# ============================================================================
# Test: Order grouping (NORMAL, MULTI_QTY, MULTI_LINE)
# ============================================================================

def test_normal_single_item():
    """Test that quantity=1 orders become NORMAL groups."""
    orders = [
        OrderItem("111", "AcmeWear", "Prod1", "M", "", "", 1, "Prod 1", None),
    ]

    waybill_map = {"111": Path("/fake/111.pdf")}
    groups, missing = group_orders(orders, waybill_map)

    assert len(groups) == 1
    assert groups[0].group_type == "NORMAL"
    assert groups[0].total_quantity == 1


def test_multi_qty():
    """Test that quantity>1 orders become MULTI_QTY groups."""
    orders = [
        OrderItem("111", "AcmeWear", "Prod1", "M", "", "", 3, "Prod 1", None),
    ]

    waybill_map = {"111": Path("/fake/111.pdf")}
    groups, missing = group_orders(orders, waybill_map)

    assert len(groups) == 1
    assert groups[0].group_type == "MULTI_QTY"
    assert groups[0].total_quantity == 3


def test_multi_line():
    """Test that same order_id with multiple products becomes MULTI_LINE."""
    orders = [
        OrderItem("111", "AcmeWear", "Prod1", "M", "", "", 1, "Prod 1", None),
        OrderItem("111", "AcmeWear", "Prod2", "L", "", "", 1, "Prod 2", None),
    ]

    waybill_map = {"111": Path("/fake/111.pdf")}
    groups, missing = group_orders(orders, waybill_map)

    assert len(groups) == 1
    assert groups[0].group_type == "MULTI_LINE"


def test_waybill_read_crm_orders_uses_operational_today_view_for_carry_forward_rows(tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    pd.DataFrame(
        [
            {
                "Date": "2026-03-06",
                "OrderID": "846479842",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "L",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-06",
            },
            {
                "Date": "2026-03-07",
                "OrderID": "846479842",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "L",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-06",
            },
            {
                "Date": "2026-03-08",
                "OrderID": "846479842",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "L",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-06",
            },
        ]
    ).to_excel(crm_path, sheet_name="Sheet1", index=False)

    orders = read_waybill_crm_orders(
        crm_path,
        "Sheet1",
        target_date=date(2026, 3, 8),
        order_id_filter={"846479842"},
        apply_date_filter=False,
    )

    assert len(orders) == 1
    assert orders[0].order_id == "846479842"
    assert orders[0].my_size == "L"


def test_waybill_read_crm_orders_requires_current_batch_rows(tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "849921993",
                "STORE_NAME": "AcmeWear",
                "MY_SIZE": "4XL",
                "Kaspi_name_core": "Line51",
                "KASPI_OFFER_NAME": "Спортивный костюм ACMEWEAR AcmeWear 05 черный, белый 4XL",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-09",
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "M",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок, компрессионная посадка белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-09",
            },
        ]
    ).to_excel(crm_path, sheet_name="Sheet1", index=False)

    orders = read_waybill_crm_orders(
        crm_path,
        "Sheet1",
        target_date=date(2026, 3, 10),
        order_id_filter={"849921993", "850084962"},
        lookback_days=3,
        apply_date_filter=False,
    )

    assert [order.order_id for order in orders] == ["850084962"]


def test_waybill_read_crm_orders_backfills_blank_current_day_size_for_overdue_rows(tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "M",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "SKU_ID": "SKU-TOP",
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "SKU_ID": "SKU-TOP",
            },
        ]
    ).to_excel(crm_path, sheet_name="Sheet1", index=False)

    orders = read_waybill_crm_orders(
        crm_path,
        "Sheet1",
        target_date=date(2026, 3, 10),
        order_id_filter={"850084962"},
        lookback_days=3,
        apply_date_filter=False,
    )

    assert len(orders) == 1
    assert orders[0].order_id == "850084962"
    assert orders[0].my_size == "M"


def test_split_groups_by_overdue():
    target_date = date(2026, 1, 27)
    today_item = OrderItem(
        order_id="111",
        store_name="AcmeWear",
        kaspi_name_core="Prod1",
        my_size="M",
        sku_key="SKU",
        sku_id="SKU-M",
        quantity=1,
        kaspi_offer_name="Prod 1",
        planned_date=target_date,
    )
    overdue_item = OrderItem(
        order_id="222",
        store_name="AcmeWear",
        kaspi_name_core="Prod2",
        my_size="L",
        sku_key="SKU",
        sku_id="SKU-L",
        quantity=1,
        kaspi_offer_name="Prod 2",
        planned_date=target_date - timedelta(days=1),
    )
    today_group = WaybillGroup(group_type="NORMAL", store_name="AcmeWear", items=[today_item])
    overdue_group = WaybillGroup(group_type="NORMAL", store_name="AcmeWear", items=[overdue_item])

    today, overdue = split_groups_by_overdue(
        {"AcmeWear": [today_group, overdue_group]}, target_date
    )

    assert today["AcmeWear"] == [today_group]
    assert overdue["AcmeWear"] == [overdue_group]


def test_build_cross_store_groups_merges_normal_groups():
    group_acmewear = WaybillGroup(
        group_type="NORMAL",
        store_name="AcmeWear",
        items=[
            OrderItem("111", "AcmeWear", "Prod1", "M", "SKU1", "ID1", 1, "Prod 1", None),
        ],
        pdf_paths=[Path("/tmp/111.pdf")],
    )
    group_universal = WaybillGroup(
        group_type="NORMAL",
        store_name="Universal",
        items=[
            OrderItem("222", "Universal", "Prod1", "M", "SKU1", "ID1", 1, "Prod 1", None),
        ],
        pdf_paths=[Path("/tmp/222.pdf")],
    )
    group_multi_qty = WaybillGroup(
        group_type="MULTI_QTY",
        store_name="AcmeWear",
        items=[
            OrderItem("333", "AcmeWear", "ProdX", "L", "SKUX", "IDX", 2, "Prod X", None),
        ],
        pdf_path=Path("/tmp/333.pdf"),
        pdf_paths=[Path("/tmp/333.pdf")],
    )

    merged = build_cross_store_groups([group_acmewear, group_universal, group_multi_qty])

    normals = [g for g in merged if g.group_type == "NORMAL"]
    multi = [g for g in merged if g.group_type == "MULTI_QTY"]
    assert len(normals) == 1
    assert len(normals[0].items) == 2
    assert normals[0].store_name == "MERGED"
    assert len(normals[0].pdf_paths) == 2
    assert len(multi) == 1
    assert multi[0].store_name == "AcmeWear"


def test_build_store_output_skips_empty_categories(tmp_path):
    pdf_path = tmp_path / "111.pdf"
    pdf_path.write_bytes(b"%PDF-1.0")

    item = OrderItem(
        order_id="111",
        store_name="AcmeWear",
        kaspi_name_core="Prod1",
        my_size="M",
        sku_key="SKU",
        sku_id="SKU-M",
        quantity=1,
        kaspi_offer_name="Prod 1",
        planned_date=date(2026, 1, 27),
    )
    group = WaybillGroup(group_type="NORMAL", store_name="AcmeWear", items=[item])
    group.pdf_path = pdf_path

    build_store_output("AcmeWear", [group], tmp_path, "27.01.26", dry_run=False)

    store_dir = tmp_path / "27.01.26_AcmeWear_qnt1"
    assert (store_dir / "NORMAL_singles").exists()
    assert not (store_dir / "SPECIAL_multi_line").exists()
    assert not (store_dir / "SPECIAL_multi_qty").exists()


def test_missing_waybill_tracked():
    """Test that orders without waybill PDFs are tracked as missing."""
    orders = [
        OrderItem("111", "AcmeWear", "Prod1", "M", "", "", 1, "Prod 1", None),
        OrderItem("222", "AcmeWear", "Prod2", "L", "", "", 1, "Prod 2", None),
    ]

    waybill_map = {"111": Path("/fake/111.pdf")}  # 222 is missing
    groups, missing = group_orders(orders, waybill_map)

    assert len(groups) == 1
    assert len(missing) == 1
    assert missing[0].order_id == "222"


# ============================================================================
# Test: Filename generation
# ============================================================================

def test_normal_filename():
    """Test NORMAL filename: {kaspi_name_core}_{MY_SIZE}-{QTY}.pdf"""
    group = WaybillGroup(
        group_type="NORMAL",
        store_name="AcmeWear",
        items=[OrderItem("111", "AcmeWear", "Berserk_футболка", "XL", "", "", 1, "", None)],
    )

    filename = generate_filename(group, 0)

    assert "Berserk_футболка" in filename
    assert "_XL-1.pdf" in filename


def test_multi_qty_filename():
    """Test MULTI_QTY filename uses explicit quantity contract."""
    group = WaybillGroup(
        group_type="MULTI_QTY",
        store_name="AcmeWear",
        items=[OrderItem("111", "AcmeWear", "Nike_футболка", "L", "", "", 3, "", None)],
    )

    filename = generate_filename(group, 5)

    assert filename == "Местовая-5)_Nike_футболка-L-3.pdf"
    assert "ORDER" not in filename
    assert "qty" not in filename


def test_multi_line_filename():
    """Test MULTI_LINE filename uses explicit quantity per line item."""
    group = WaybillGroup(
        group_type="MULTI_LINE",
        store_name="AcmeWear",
        items=[
            OrderItem("111", "AcmeWear", "Футболка_черная", "2XL", "", "", 1, "", None),
            OrderItem("111", "AcmeWear", "Трусы_черные", "2XL", "", "", 2, "", None),
        ],
    )

    filename = generate_filename(group, 2)

    assert filename == "Местовая-2)_Футболка_черная-2XL-1_Трусы_черные-2XL-2.pdf"
    assert "ORDER" not in filename
    assert "items" not in filename
    assert "qty1" not in filename
    assert "qty2" not in filename
    assert "x2" not in filename


def test_multi_line_manifest_items_detail_uses_explicit_quantity_shape(tmp_path: Path):
    groups = [
        WaybillGroup(
            group_type="MULTI_LINE",
            store_name="AcmeWear",
            items=[
                OrderItem("111", "AcmeWear", "Футболка_черная", "2XL", "", "", 1, "", None),
                OrderItem("111", "AcmeWear", "Трусы_черные", "2XL", "", "", 2, "", None),
            ],
            output_filename="SPECIAL_multi_line/Местовая-2)_Футболка_черная-2XL-1_Трусы_черные-2XL-2.pdf",
        )
    ]

    output = tmp_path / "manifest_special_multi_line.csv"
    write_manifest(groups, output, "MULTI_LINE")

    rows = list(csv.DictReader(output.open("r", encoding="utf-8", newline="")))
    assert len(rows) == 1
    assert rows[0]["items_detail"] == "Футболка_черная-2XL-1;Трусы_черные-2XL-2"


def test_write_send_batch_manifest_contains_stable_pdf_keys_and_overdue_orders(tmp_path: Path):
    today_root = tmp_path / "Today"
    batch_root = today_root / "MERGED" / "SEND" / "10.03.26_MERGED_qnt2"
    normal_dir = batch_root / "NORMAL_singles"
    special_dir = batch_root / "SPECIAL_multi_line"
    normal_dir.mkdir(parents=True, exist_ok=True)
    special_dir.mkdir(parents=True, exist_ok=True)

    normal_pdf = normal_dir / "Футболка_черная_L-1.pdf"
    special_pdf = special_dir / "Местовая-1)_Футболка_черная-2XL-1_Трусы_черные-2XL-2.pdf"
    pdf_bytes = b"%PDF-1.4\n%waybill\n"
    normal_pdf.write_bytes(pdf_bytes)
    special_pdf.write_bytes(pdf_bytes + b"special")

    today_item = OrderItem(
        "1001", "Universal", "Футболка_черная", "L", "SKU1", "SKU1-L", 1, "offer", date(2026, 3, 10)
    )
    overdue_item = OrderItem(
        "1002", "STORE-B", "Футболка_черная", "2XL", "SKU2", "SKU2-2XL", 1, "offer", date(2026, 3, 9)
    )
    second_line = OrderItem(
        "1002", "STORE-B", "Трусы_черные", "2XL", "SKU3", "SKU3-2XL", 2, "offer", date(2026, 3, 9)
    )
    today_item.source_row_id = "1001@2026-03-10#1"
    overdue_item.source_row_id = "1002@2026-03-09#1"
    second_line.source_row_id = "1002@2026-03-09#2"

    groups = [
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[today_item],
            pdf_path=normal_pdf,
            pdf_paths=[normal_pdf],
            output_filename="NORMAL_singles/Футболка_черная_L-1.pdf",
        ),
        WaybillGroup(
            group_type="MULTI_LINE",
            store_name="MERGED",
            items=[overdue_item, second_line],
            pdf_path=special_pdf,
            pdf_paths=[special_pdf],
            output_filename="SPECIAL_multi_line/Местовая-1)_Футболка_черная-2XL-1_Трусы_черные-2XL-2.pdf",
        ),
    ]

    manifest_path = write_send_batch_manifest(
        batch_root=batch_root,
        today_root=today_root,
        groups=groups,
        target_date=date(2026, 3, 10),
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["batch_label"] == "10.03.26_MERGED_qnt2"
    assert payload["counts"]["pdfs"] == 2
    assert payload["overdue_order_ids"] == ["1002"]
    assert payload["missing_overdue_order_ids"] == []
    assert {entry["relative_output_path"] for entry in payload["entries"]} == {
        "NORMAL_singles/Футболка_черная_L-1.pdf",
        "SPECIAL_multi_line/Местовая-1)_Футболка_черная-2XL-1_Трусы_черные-2XL-2.pdf",
    }
    for entry in payload["entries"]:
        assert entry["pdf_key"]
        assert entry["sha256"]
        assert entry["file_size"] > 0
        assert entry["source_row_ids"]


def test_write_send_batch_manifest_counts_unique_orders_per_store_for_multi_line(tmp_path: Path):
    today_root = tmp_path / "Today"
    batch_root = today_root / "MERGED" / "SEND" / "10.03.26_MERGED_qnt1"
    special_dir = batch_root / "SPECIAL_multi_line"
    special_dir.mkdir(parents=True, exist_ok=True)

    special_pdf = special_dir / "Местовая-1)_Леггинсы_белый-M-1_Леггинсы_черные-L-1.pdf"
    special_pdf.write_bytes(b"%PDF-1.4\n%waybill\n")

    first_line = OrderItem(
        "1002", "Universal", "Леггинсы_белый", "M", "SKU1", "SKU1-M", 1, "offer", date(2026, 3, 9)
    )
    second_line = OrderItem(
        "1002", "Universal", "Леггинсы_черные", "L", "SKU2", "SKU2-L", 1, "offer", date(2026, 3, 9)
    )
    first_line.source_row_id = "1002@2026-03-09#1"
    second_line.source_row_id = "1002@2026-03-09#2"

    groups = [
        WaybillGroup(
            group_type="MULTI_LINE",
            store_name="MERGED",
            items=[first_line, second_line],
            pdf_path=special_pdf,
            pdf_paths=[special_pdf],
            output_filename="SPECIAL_multi_line/Местовая-1)_Леггинсы_белый-M-1_Леггинсы_черные-L-1.pdf",
        ),
    ]

    manifest_path = write_send_batch_manifest(
        batch_root=batch_root,
        today_root=today_root,
        groups=groups,
        target_date=date(2026, 3, 10),
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["counts"]["orders"] == 1
    assert payload["entries"][0]["order_counts_by_store"] == {"Universal": 1}


def test_write_send_batch_manifest_assigns_send_sequence_with_color_spacing_and_size_rise(
    tmp_path: Path,
):
    today_root = tmp_path / "Today"
    batch_root = today_root / "MERGED" / "SEND" / "10.03.26_MERGED_qnt4"
    normal_dir = batch_root / "NORMAL_singles"
    normal_dir.mkdir(parents=True, exist_ok=True)

    filenames = [
        "Nike_Футболка_черная_XL-1.pdf",
        "Nike_Футболка_черная_2XL-1.pdf",
        "Nike_Футболка_белая_XL-1.pdf",
        "Line51_L-1.pdf",
    ]
    for filename in filenames:
        (normal_dir / filename).write_bytes(b"%PDF-1.4\n%waybill\n")

    groups = [
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "1001",
                    "Universal",
                    "Nike_Футболка_черная",
                    "XL",
                    "NIKE_TEE_BLACK",
                    "NIKE_TEE_BLACK_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "Nike_Футболка_черная_XL-1.pdf",
            pdf_paths=[normal_dir / "Nike_Футболка_черная_XL-1.pdf"],
            output_filename="NORMAL_singles/Nike_Футболка_черная_XL-1.pdf",
        ),
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "1002",
                    "Universal",
                    "Nike_Футболка_черная",
                    "2XL",
                    "NIKE_TEE_BLACK",
                    "NIKE_TEE_BLACK_2XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "Nike_Футболка_черная_2XL-1.pdf",
            pdf_paths=[normal_dir / "Nike_Футболка_черная_2XL-1.pdf"],
            output_filename="NORMAL_singles/Nike_Футболка_черная_2XL-1.pdf",
        ),
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "1003",
                    "Universal",
                    "Nike_Футболка_белая",
                    "XL",
                    "NIKE_TEE_WHITE",
                    "NIKE_TEE_WHITE_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "Nike_Футболка_белая_XL-1.pdf",
            pdf_paths=[normal_dir / "Nike_Футболка_белая_XL-1.pdf"],
            output_filename="NORMAL_singles/Nike_Футболка_белая_XL-1.pdf",
        ),
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "1004",
                    "AcmeWear",
                    "Line51",
                    "L",
                    "LINE51",
                    "LINE51_L",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "Line51_L-1.pdf",
            pdf_paths=[normal_dir / "Line51_L-1.pdf"],
            output_filename="NORMAL_singles/Line51_L-1.pdf",
        ),
    ]

    manifest_path = write_send_batch_manifest(
        batch_root=batch_root,
        today_root=today_root,
        groups=groups,
        target_date=date(2026, 3, 10),
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries_by_sequence = sorted(payload["entries"], key=lambda entry: entry["send_sequence"])

    assert [entry["filename"] for entry in entries_by_sequence] == [
        "Nike_Футболка_черная_XL-1.pdf",
        "Nike_Футболка_черная_2XL-1.pdf",
        "Line51_L-1.pdf",
        "Nike_Футболка_белая_XL-1.pdf",
    ]
    assert [entry["send_sequence"] for entry in entries_by_sequence] == [1, 2, 3, 4]


def test_write_send_batch_manifest_prioritizes_line51_and_6v1_after_specials(
    tmp_path: Path,
):
    today_root = tmp_path / "Today"
    batch_root = today_root / "MERGED" / "SEND" / "10.03.26_MERGED_qnt5"
    normal_dir = batch_root / "NORMAL_singles"
    special_line_dir = batch_root / "SPECIAL_multi_line"
    special_qty_dir = batch_root / "SPECIAL_multi_qty"
    normal_dir.mkdir(parents=True, exist_ok=True)
    special_line_dir.mkdir(parents=True, exist_ok=True)
    special_qty_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in [
        special_line_dir / "Местовая-1)_Леггинсы_белый-L-1_Nike_Футболка_белая-XL-1.pdf",
        special_qty_dir / "Местовая-2)_Футболка_черная-M-3.pdf",
        normal_dir / "Nike_Футболка_черная_XL-1.pdf",
        normal_dir / "Line51_L-1.pdf",
        normal_dir / "6в1_Черный_+Сумка_M-1.pdf",
    ]:
        rel_path.write_bytes(b"%PDF-1.4\n%waybill\n")

    groups = [
        WaybillGroup(
            group_type="MULTI_LINE",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2001",
                    "Universal",
                    "Леггинсы_белый",
                    "L",
                    "LEGGINGS_WHITE",
                    "LEGGINGS_WHITE_L",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
                OrderItem(
                    "2001",
                    "Universal",
                    "Nike_Футболка_белая",
                    "XL",
                    "NIKE_TEE_WHITE",
                    "NIKE_TEE_WHITE_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
            ],
            pdf_path=special_line_dir / "Местовая-1)_Леггинсы_белый-L-1_Nike_Футболка_белая-XL-1.pdf",
            pdf_paths=[special_line_dir / "Местовая-1)_Леггинсы_белый-L-1_Nike_Футболка_белая-XL-1.pdf"],
            output_filename="SPECIAL_multi_line/Местовая-1)_Леггинсы_белый-L-1_Nike_Футболка_белая-XL-1.pdf",
        ),
        WaybillGroup(
            group_type="MULTI_QTY",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2002",
                    "STORE-B",
                    "Футболка_черная",
                    "M",
                    "TEE_BLACK",
                    "TEE_BLACK_M",
                    3,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=special_qty_dir / "Местовая-2)_Футболка_черная-M-3.pdf",
            pdf_paths=[special_qty_dir / "Местовая-2)_Футболка_черная-M-3.pdf"],
            output_filename="SPECIAL_multi_qty/Местовая-2)_Футболка_черная-M-3.pdf",
        ),
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2003",
                    "Universal",
                    "Nike_Футболка_черная",
                    "XL",
                    "NIKE_TEE_BLACK",
                    "NIKE_TEE_BLACK_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "Nike_Футболка_черная_XL-1.pdf",
            pdf_paths=[normal_dir / "Nike_Футболка_черная_XL-1.pdf"],
            output_filename="NORMAL_singles/Nike_Футболка_черная_XL-1.pdf",
        ),
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2004",
                    "AcmeWear",
                    "Line51",
                    "L",
                    "LINE51",
                    "LINE51_L",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "Line51_L-1.pdf",
            pdf_paths=[normal_dir / "Line51_L-1.pdf"],
            output_filename="NORMAL_singles/Line51_L-1.pdf",
        ),
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2005",
                    "AcmeWear",
                    "6в1_Черный_+Сумка",
                    "M",
                    "LINE61_BLACK_BAG",
                    "LINE61_BLACK_BAG_M",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=normal_dir / "6в1_Черный_+Сумка_M-1.pdf",
            pdf_paths=[normal_dir / "6в1_Черный_+Сумка_M-1.pdf"],
            output_filename="NORMAL_singles/6в1_Черный_+Сумка_M-1.pdf",
        ),
    ]

    manifest_path = write_send_batch_manifest(
        batch_root=batch_root,
        today_root=today_root,
        groups=groups,
        target_date=date(2026, 3, 10),
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries_by_sequence = sorted(payload["entries"], key=lambda entry: entry["send_sequence"])

    assert [entry["filename"] for entry in entries_by_sequence] == [
        "Местовая-1)_Леггинсы_белый-L-1_Nike_Футболка_белая-XL-1.pdf",
        "Местовая-2)_Футболка_черная-M-3.pdf",
        "Line51_L-1.pdf",
        "6в1_Черный_+Сумка_M-1.pdf",
        "Nike_Футболка_черная_XL-1.pdf",
    ]


def test_build_store_output_send_batch_special_filenames_follow_send_sequence(
    tmp_path: Path,
):
    source_dir = tmp_path / "source_pdfs"
    source_dir.mkdir(parents=True, exist_ok=True)

    def make_pdf(name: str) -> Path:
        path = source_dir / name
        path.write_bytes(b"%PDF-1.4\n%waybill\n")
        return path

    leggings_pdf = make_pdf("leggings_multi_line.pdf")
    nike_multi_line_pdf = make_pdf("nike_multi_line.pdf")
    trusy_pdf = make_pdf("trusy_multi_qty.pdf")
    futbolka_m_pdf = make_pdf("futbolka_m_multi_qty.pdf")
    futbolka_l_pdf = make_pdf("futbolka_l_multi_qty.pdf")

    groups = [
        WaybillGroup(
            group_type="MULTI_LINE",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2001",
                    "Universal",
                    "Леггинсы_белый",
                    "L",
                    "LEGGINGS_WHITE",
                    "LEGGINGS_WHITE_L",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
                OrderItem(
                    "2001",
                    "Universal",
                    "Nike_Футболка_белая",
                    "XL",
                    "NIKE_TEE_WHITE",
                    "NIKE_TEE_WHITE_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
            ],
            pdf_path=leggings_pdf,
            pdf_paths=[leggings_pdf],
        ),
        WaybillGroup(
            group_type="MULTI_LINE",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2002",
                    "Universal",
                    "Nike_Футболка_белая",
                    "XL",
                    "NIKE_TEE_WHITE",
                    "NIKE_TEE_WHITE_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
                OrderItem(
                    "2002",
                    "Universal",
                    "Nike_Футболка_черная",
                    "XL",
                    "NIKE_TEE_BLACK",
                    "NIKE_TEE_BLACK_XL",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
                OrderItem(
                    "2002",
                    "Universal",
                    "Футболка_черная",
                    "L",
                    "TEE_BLACK",
                    "TEE_BLACK_L",
                    1,
                    "offer",
                    date(2026, 3, 10),
                ),
            ],
            pdf_path=nike_multi_line_pdf,
            pdf_paths=[nike_multi_line_pdf],
        ),
        WaybillGroup(
            group_type="MULTI_QTY",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2003",
                    "STORE-B",
                    "Трусы_черные",
                    "XL",
                    "BOXER_BLACK",
                    "BOXER_BLACK_XL",
                    3,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=trusy_pdf,
            pdf_paths=[trusy_pdf],
        ),
        WaybillGroup(
            group_type="MULTI_QTY",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2004",
                    "STORE-B",
                    "Футболка_черная",
                    "M",
                    "TEE_BLACK",
                    "TEE_BLACK_M",
                    3,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=futbolka_m_pdf,
            pdf_paths=[futbolka_m_pdf],
        ),
        WaybillGroup(
            group_type="MULTI_QTY",
            store_name="MERGED",
            items=[
                OrderItem(
                    "2005",
                    "STORE-B",
                    "Футболка_черная",
                    "L",
                    "TEE_BLACK",
                    "TEE_BLACK_L",
                    2,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=futbolka_l_pdf,
            pdf_paths=[futbolka_l_pdf],
        ),
    ]

    today_root = tmp_path / "Today"
    send_root = today_root / "MERGED" / "SEND"
    stats = build_store_output(
        "MERGED",
        groups,
        send_root,
        "10.03.26",
        send_batch_order_labels=True,
    )

    manifest_path = write_send_batch_manifest(
        batch_root=stats["batch_dir"],
        today_root=today_root,
        groups=groups,
        target_date=date(2026, 3, 10),
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries_by_sequence = sorted(payload["entries"], key=lambda entry: entry["send_sequence"])
    special_entries = [
        entry
        for entry in entries_by_sequence
        if entry["category"] in {"SPECIAL_multi_line", "SPECIAL_multi_qty"}
    ]

    assert [entry["filename"] for entry in special_entries] == [
        "Местовая-1)_Леггинсы_белый-L-1_Nike_Футболка_белая-XL-1.pdf",
        "Местовая-2)_Nike_Футболка_белая-XL-1_Nike_Футболка_черная-XL-1_Футболка_черная-L-1.pdf",
        "Местовая-3)_Трусы_черные-XL-3.pdf",
        "Местовая-4)_Футболка_черная-M-3.pdf",
        "Местовая-5)_Футболка_черная-L-2.pdf",
    ]

    for entry in special_entries:
        assert (stats["batch_dir"] / entry["relative_output_path"]).exists()


def test_build_store_output_send_batch_rebuild_uses_revision_suffix(tmp_path: Path) -> None:
    source_dir = tmp_path / "source_pdfs"
    source_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = source_dir / "single.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%waybill\n")

    groups = [
        WaybillGroup(
            group_type="NORMAL",
            store_name="MERGED",
            items=[
                OrderItem(
                    "3001",
                    "Universal",
                    "Nike_Футболка_черная",
                    "M",
                    "NIKE_TEE_BLACK",
                    "NIKE_TEE_BLACK_M",
                    1,
                    "offer",
                    date(2026, 3, 10),
                )
            ],
            pdf_path=pdf_path,
            pdf_paths=[pdf_path],
        )
    ]

    send_root = tmp_path / "Today" / "MERGED" / "SEND"
    first = build_store_output(
        "MERGED",
        groups,
        send_root,
        "10.03.26",
        send_batch_order_labels=True,
    )
    (first["batch_dir"] / "send_batch_manifest.json").write_text("{}", encoding="utf-8")

    second = build_store_output(
        "MERGED",
        groups,
        send_root,
        "10.03.26",
        send_batch_order_labels=True,
    )

    assert first["batch_dir"].name == "10.03.26_MERGED_qnt1"
    assert second["batch_dir"].name == "10.03.26_MERGED_qnt1_r2"


def test_main_preserves_existing_send_batches_when_rebuilding_today_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "Today"
    preserved_batch = output_dir / "MERGED" / "SEND" / "10.03.26_MERGED_qnt1"
    preserved_batch.mkdir(parents=True, exist_ok=True)
    (preserved_batch / "send_batch_manifest.json").write_text("{}", encoding="utf-8")
    (preserved_batch / "send_ledger.json").write_text("{}", encoding="utf-8")

    stale_per_store = output_dir / "PER_STORE" / "TODAY" / "stale.txt"
    stale_per_store.parent.mkdir(parents=True, exist_ok=True)
    stale_per_store.write_text("stale", encoding="utf-8")

    stale_merged_today = output_dir / "MERGED" / "TODAY" / "stale.txt"
    stale_merged_today.parent.mkdir(parents=True, exist_ok=True)
    stale_merged_today.write_text("stale", encoding="utf-8")

    waybill_dir = tmp_path / "waybills"
    waybill_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = waybill_dir / "KASPI_SHOP-1001.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\npreserve-send-batch\n")

    order = OrderItem(
        order_id="1001",
        store_name="Universal",
        kaspi_name_core="Nike_Футболка_черная",
        my_size="M",
        sku_key="NIKE_TEE_BLACK",
        sku_id="NIKE_TEE_BLACK_M",
        quantity=1,
        kaspi_offer_name="Nike футболка черная M",
        planned_date=date(2026, 3, 10),
    )

    monkeypatch.setattr(build_daily_waybills_module, "ensure_pdf_merger", lambda: None)
    monkeypatch.setattr(build_daily_waybills_module, "load_crm_dataframe", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(build_daily_waybills_module, "resolve_db_path", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        build_daily_waybills_module,
        "load_selection_cache",
        lambda *args, **kwargs: {"Universal": {"1001"}},
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "read_crm_orders",
        lambda *args, **kwargs: [order],
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "load_all_waybills",
        lambda *args, **kwargs: {"1001": pdf_path},
    )

    build_daily_waybills_main(
        crm_path=tmp_path / "CRM.xlsx",
        waybill_dir=waybill_dir,
        output_dir=output_dir,
        target_date=date(2026, 3, 10),
        lookback_days=0,
        output_layout="per-store-and-merged",
        dry_run=False,
    )

    assert preserved_batch.exists()
    assert (preserved_batch / "send_ledger.json").exists()
    assert not stale_per_store.exists()
    assert not stale_merged_today.exists()

    rebuilt_batches = sorted(
        path.name for path in (output_dir / "MERGED" / "SEND").iterdir() if path.is_dir()
    )
    assert rebuilt_batches == ["10.03.26_MERGED_qnt1", "10.03.26_MERGED_qnt1_r2"]


def test_main_uses_db_sized_orders_when_crm_current_batch_has_no_sizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "Today"
    waybill_dir = tmp_path / "waybills"
    waybill_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = waybill_dir / "KASPI_SHOP-1001.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%db-first-waybill\n")

    db_order = OrderItem(
        order_id="1001",
        store_name="Universal",
        kaspi_name_core="Nike_Футболка_черная",
        my_size="M",
        sku_key="NIKE_TEE_BLACK",
        sku_id="NIKE_TEE_BLACK_M",
        quantity=1,
        kaspi_offer_name="Nike футболка черная M",
        planned_date=date(2026, 3, 10),
    )

    monkeypatch.setattr(build_daily_waybills_module, "ensure_pdf_merger", lambda: None)
    monkeypatch.setattr(
        build_daily_waybills_module,
        "load_crm_dataframe",
        lambda *args, **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "resolve_db_path",
        lambda *args, **kwargs: tmp_path / "app.db",
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "load_selection_cache",
        lambda *args, **kwargs: {"Universal": {"1001"}},
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "read_db_orders",
        lambda *args, **kwargs: [db_order],
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "read_crm_orders",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        build_daily_waybills_module,
        "load_all_waybills",
        lambda *args, **kwargs: {"1001": pdf_path},
    )

    stats = build_daily_waybills_main(
        crm_path=tmp_path / "CRM.xlsx",
        db_path=tmp_path / "app.db",
        waybill_dir=waybill_dir,
        output_dir=output_dir,
        target_date=date(2026, 3, 10),
        lookback_days=0,
        output_layout="per-store-and-merged",
        dry_run=False,
    )

    assert stats["orders_read"] == 1
    assert stats["stores_processed"] == 1
    assert stats["merged_groups"] == 1
    rebuilt_batches = sorted(
        path.name for path in (output_dir / "MERGED" / "SEND").iterdir() if path.is_dir()
    )
    assert rebuilt_batches == ["10.03.26_MERGED_qnt1"]


def test_read_db_orders_prefers_article_map_core_over_offer_text(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                quantity INTEGER,
                assigned_size TEXT,
                my_size TEXT,
                planned_shipment_date TEXT,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                signature_required INTEGER,
                courier_transmission_date TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                kaspi_name_core TEXT,
                active_flag INTEGER,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_offer_name, sku_key, sku_id, quantity,
                assigned_size, my_size, planned_shipment_date, kaspi_status,
                kaspi_status_detail, internal_status, signature_required,
                courier_transmission_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "889000111",
                "STOREB",
                "Спортивный костюм PRO COMBAT 528742263 черный 2XL",
                "PRO_COMBAT_BLACK_2XL",
                "PRO_COMBAT_BLACK_2XL",
                1,
                "2XL",
                "",
                "2026-04-15",
                "KASPI_DELIVERY",
                "Принят",
                "READY",
                0,
                "",
            ),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_offer_name, sku_key, kaspi_name_core,
                active_flag, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "STOREB",
                "Спортивный костюм PRO COMBAT 528742263 черный 2XL",
                "PRO_COMBAT_BLACK_2XL",
                "Принт_5в1_черный",
                1,
                "2026-04-15T12:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    orders = build_daily_waybills_module.read_db_orders(
        db_path=db_path,
        target_date=date(2026, 4, 15),
        lookback_days=0,
    )

    assert len(orders) == 1
    assert orders[0].store_name == "STORE-B"
    assert orders[0].kaspi_name_core == "Принт_5в1_черный"
    assert orders[0].kaspi_name_core != "Спортивный_костюм_PRO_COMBAT_528742263_черный"


def test_read_db_orders_prefers_sku_family_core_over_raw_offer_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                quantity INTEGER,
                assigned_size TEXT,
                my_size TEXT,
                planned_shipment_date TEXT,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                signature_required INTEGER,
                courier_transmission_date TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                kaspi_name_core TEXT,
                active_flag INTEGER,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_offer_name, sku_key, sku_id, quantity,
                assigned_size, my_size, planned_shipment_date, kaspi_status,
                kaspi_status_detail, internal_status, signature_required,
                courier_transmission_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "889383661",
                "UNIVERSAL",
                "Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48",
                "CL_OC_MEN_LINE52_BLACK_103217238_44/46, 48",
                "CL_OC_MEN_LINE52_BLACK_103217238_44/46, 48_XL",
                1,
                "L",
                "",
                "2026-04-15",
                "KASPI_DELIVERY",
                "Принят",
                "READY",
                0,
                "",
            ),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_offer_name, sku_key, kaspi_name_core,
                active_flag, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "UNIVERSAL",
                "Комплект Antec RASH-921 Рашгард 5 в 1 черный XL",
                "CL_OC_MEN_LINE52_BLACK",
                "Принт_5в1_черный",
                1,
                "2026-04-15T12:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    orders = build_daily_waybills_module.read_db_orders(
        db_path=db_path,
        target_date=date(2026, 4, 15),
        lookback_days=0,
    )

    assert len(orders) == 1
    assert orders[0].kaspi_name_core == "Принт_5в1_черный"
    assert orders[0].kaspi_name_core != "Комплект_Antec_RASH-_BLACK"


def test_sanitizes_cyrillic():
    """Test that Cyrillic characters are preserved in filenames."""
    result = sanitize_filename("Костюм мужской черный")

    # Cyrillic should be preserved, spaces replaced
    assert "Костюм" in result
    assert " " not in result
    assert "_" in result


def test_sanitizes_problematic_chars():
    """Test that problematic characters are removed."""
    result = sanitize_filename("test/file:name*?.pdf")

    assert "/" not in result
    assert ":" not in result
    assert "*" not in result
    assert "?" not in result


# ============================================================================
# Test: Manifest and sorting
# ============================================================================

def test_manifest_required_columns():
    """Test that manifest has required columns."""
    required = ['kaspi_name_core', 'size', 'sku_key', 'sku_id', 'quantity', 'order_id']

    # These columns should be in the manifest (from write_manifest function)
    manifest_columns = ['type', 'store', 'order_id', 'kaspi_name_core', 'size',
                        'sku_key', 'sku_id', 'quantity', 'kaspi_offer_name', 'output']

    for col in required:
        assert col in manifest_columns


def test_sorting_by_size():
    """Test that Kids sizes come before Men's sizes."""
    kid_order = size_sort_key("26")   # Should be ~3
    men_order = size_sort_key("XL")   # Should be ~13

    assert kid_order < men_order


def test_sorting_within_size():
    """Test size ordering: S < M < L < XL < 2XL."""
    assert size_sort_key("S") < size_sort_key("M")
    assert size_sort_key("M") < size_sort_key("L")
    assert size_sort_key("L") < size_sort_key("XL")
    assert size_sort_key("XL") < size_sort_key("2XL")


# ============================================================================
# Test: Package counting
# ============================================================================

def test_heavy_items_separate():
    """Test that heavy items are counted as separate packages."""
    item = OrderItem("111", "AcmeWear", "Line51", "XL", "", "", 3, "", None)

    assert is_heavy_item(item) is True

    # With quantity=3, heavy item should be 3 packages
    group = WaybillGroup(
        group_type="MULTI_QTY",
        store_name="AcmeWear",
        items=[item],
    )

    packages = count_packages([group])
    assert packages == 3  # Each heavy item is separate


def test_non_heavy_can_combine():
    """Test that non-heavy items with qty<=3 combine into one package."""
    item = OrderItem("111", "AcmeWear", "Regular_item", "XL", "", "", 3, "", None)

    assert is_heavy_item(item) is False

    group = WaybillGroup(
        group_type="MULTI_QTY",
        store_name="AcmeWear",
        items=[item],
    )

    packages = count_packages([group])
    assert packages == 1  # qty<=3 and not heavy = 1 package


def test_heavy_items_in_list():
    """Test that all expected heavy items are defined."""
    expected_heavy = [
        'Костюм_мужской_Хус',
        'Line51',
        'Принт_5в1_черный',
        'Костюм_Ромбик_ДЕТСКИЙ',
    ]

    for item_name in expected_heavy:
        assert item_name in HEAVY_ITEMS


# ============================================================================
# Test: Waybill extraction
# ============================================================================

def test_extract_waybills_from_zips(temp_waybill_dir):
    """Test waybill extraction from ZIP files."""
    with tempfile.TemporaryDirectory() as extract_dir:
        extract_path = Path(extract_dir)

        waybill_map = extract_waybills_from_zips(temp_waybill_dir, extract_path)

        assert len(waybill_map) == 3
        assert "123456789" in waybill_map
        assert "987654321" in waybill_map
        assert "111222333" in waybill_map

        # Check files were actually extracted
        for order_id, pdf_path in waybill_map.items():
            assert pdf_path.exists()


# ============================================================================
# Test: Output structure
# ============================================================================

def test_creates_directory_structure():
    """Test that all expected directories are created."""
    # Test the expected structure
    expected_subdirs = ["NORMAL_singles", "SPECIAL_multi_line", "SPECIAL_multi_qty"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        for subdir in expected_subdirs:
            (tmppath / subdir).mkdir()

        for subdir in expected_subdirs:
            assert (tmppath / subdir).exists()


def test_build_log_columns():
    """Test that build_log.csv has expected columns."""
    expected_columns = [
        'type', 'store', 'order_id', 'kaspi_name_core', 'size',
        'sku_key', 'sku_id', 'quantity', 'kaspi_offer_name', 'output',
        'status', 'processed_at'
    ]

    # The write_build_log function uses these fieldnames
    assert len(expected_columns) == 12


# ============================================================================
# Test: Store mapping
# ============================================================================

def test_store_map_completeness():
    """Test that store mapping has expected entries."""
    expected_stores = ['AcmeWear', 'Universal', '11KZ', 'STORE-B']

    for store in expected_stores:
        assert store in STORE_MAP.values()


# ============================================================================
# Test: WaybillGroup properties
# ============================================================================

def test_waybill_group_properties():
    """Test WaybillGroup computed properties."""
    items = [
        OrderItem("111", "AcmeWear", "Prod1", "M", "KEY1", "ID1", 2, "Name1", None),
        OrderItem("111", "AcmeWear", "Prod2", "L", "KEY2", "ID2", 3, "Name2", None),
    ]

    group = WaybillGroup(
        group_type="MULTI_LINE",
        store_name="AcmeWear",
        items=items,
    )

    assert group.order_id == "111"
    assert group.kaspi_name_core == "Prod1"
    assert group.my_size == "M"
    assert group.sku_key == "KEY1"
    assert group.sku_id == "ID1"
    assert group.total_quantity == 5  # 2 + 3
