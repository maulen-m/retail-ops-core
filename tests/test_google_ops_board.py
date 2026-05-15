from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.integrations.google_ops_board import (
    build_tab_reorder_requests,
    build_tab_ui_requests,
    extract_rows_from_matrix,
    extract_rows_with_positions_from_matrix,
    load_ops_board_contract,
    merge_rows_preserving_editables,
    rows_to_matrix,
    validate_contract_layout,
)
from scripts.sync_google_ops_board import (
    _invalid_layout_tabs,
    build_phase1_payload,
    build_publish_plan,
    write_rollover_archive,
)
from scripts.sync_google_ops_board_sizes_to_db import build_size_writeback_plan, plan_size_writeback


def _make_orders_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                planned_shipment_date TEXT,
                kaspi_status TEXT,
                internal_status TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                assigned_size TEXT,
                quantity INTEGER,
                waybill_url TEXT,
                waybill_downloaded INTEGER,
                actual_shipment_date TEXT,
                courier_transmission_date TEXT,
                kaspi_status_detail TEXT,
                signature_required INTEGER,
                delivery_mode TEXT,
                planned_delivery_date TEXT,
                payment_mode TEXT,
                returned_to_warehouse INTEGER,
                customer_first_name TEXT,
                customer_last_name TEXT,
                customer_phone TEXT,
                customer_height_cm INTEGER,
                customer_weight_kg INTEGER,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                product_type TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_offer_name TEXT,
                kaspi_article TEXT,
                sku_key TEXT,
                sku_id TEXT,
                kaspi_name_core TEXT,
                active_flag INTEGER,
                updated_at TEXT
            );
            CREATE TABLE fact_sales (
                kaspi_offer_name TEXT,
                sku_key TEXT,
                my_size TEXT,
                quantity INTEGER
            );
            CREATE TABLE dim_size_probability (
                level TEXT,
                key_value TEXT,
                mode_size TEXT,
                mode_share REAL,
                sample_count INTEGER,
                confidence TEXT,
                size_distribution TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO dim_sku (sku_key, product_type) VALUES (?, ?)",
            [
                ("SKU-1", "CL"),
                ("SKU-2", "CL"),
                ("SKU-3", "CL"),
                ("SKU-4", "CL"),
            ],
        )
        conn.execute(
            """
            INSERT INTO dim_size_probability (
                level, key_value, mode_size, mode_share, sample_count, confidence, size_distribution
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("PRODUCT_TYPE", "CL", "L", 0.35, 0, "LOW", '{"L": 0.35}'),
        )
        rows = [
            (
                1,
                "1001",
                "UNIVERSAL",
                "2026-04-15",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "Nike Tee Black",
                "SKU-1",
                "SKU-1-LINE-A",
                None,
                None,
                1,
                None,
                0,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Ali",
                "One",
                "+77000000001",
                176,
                78,
                "2026-04-15T10:00:00",
                "2026-04-15T10:00:00",
            ),
            (
                2,
                "1001",
                "UNIVERSAL",
                "2026-04-15",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "Nike Tee White",
                "SKU-2",
                "SKU-2-LINE-B",
                None,
                None,
                2,
                None,
                0,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Ali",
                "One",
                "+77000000001",
                176,
                78,
                "2026-04-15T10:00:00",
                "2026-04-15T10:00:00",
            ),
            (
                3,
                "1002",
                "STOREB",
                "2026-04-15",
                "KASPI_DELIVERY",
                "READY",
                "Berserk Rashguard",
                "SKU-3",
                "SKU-3-LINE-A",
                None,
                "XL",
                1,
                None,
                1,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Bea",
                "Two",
                "+77000000002",
                170,
                68,
                "2026-04-15T10:05:00",
                "2026-04-15T10:05:00",
            ),
            (
                4,
                "1003",
                "ACMEWEAR",
                "2026-04-15",
                "ARCHIVE",
                "SHIPPED",
                "AcmeWear Set",
                "SKU-4",
                "SKU-4-LINE-A",
                None,
                "M",
                1,
                "https://wb/1003",
                1,
                "2026-04-15",
                "2026-04-15T12:00:00",
                "COMPLETED",
                0,
                "DELIVERY",
                "2026-04-15",
                "PREPAID",
                0,
                "Cara",
                "Three",
                "+77000000003",
                165,
                58,
                "2026-04-15T12:00:00",
                "2026-04-15T12:10:00",
            ),
            (
                5,
                "0999",
                "ACMEWEAR",
                "2026-04-14",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "Too Old",
                "SKU-9",
                "SKU-9-LINE-A",
                None,
                None,
                1,
                None,
                0,
                None,
                None,
                "CANCELLED",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Old",
                "Order",
                "+77000000009",
                168,
                60,
                "2026-04-07T08:00:00",
                "2026-04-07T08:00:00",
            ),
            (
                6,
                "0900",
                "UNIVERSAL",
                "2026-04-14",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "Carry Forward Tee",
                "SKU-1",
                "SKU-1-LINE-C",
                None,
                "XL",
                1,
                "https://wb/0900",
                0,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Dana",
                "Four",
                "+77000000004",
                180,
                82,
                "2026-04-14T18:00:00",
                "2026-04-14T18:00:00",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_default_google_ops_board_contract_loads_expected_tabs():
    contract = load_ops_board_contract()

    assert contract.spreadsheet_id == "1zCKXkD7Ch8izX3CF_OwMgNb8pdrMLQOyw2clxbjF9Bg"
    assert contract.same_day_cutoff_default == "16:00"
    assert contract.same_day_cutoff_by_store == {"ACMEWEAR": "16:01"}
    assert list(contract.tabs) == [
        "SalesRaw_Today",
        "Run_Control",
        "README",
        "Orders_Today",
        "Needs_Size",
        "Shipping_Queue",
        "Exceptions",
        "Shipped_Today",
        "Config_Do_Not_Edit",
    ]
    assert contract.closeout_write_env_gate == "ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT"
    assert contract.tabs["SalesRaw_Today"].key_column == "_db_row_id"
    assert contract.tabs["SalesRaw_Today"].editable_columns == ["MY_SIZE"]
    assert contract.tabs["SalesRaw_Today"].headers == [
        "Status",
        "Date",
        "STORE_NAME",
        "HEIGHT",
        "WEIGHT",
        "Quantity",
        "Kaspi_name_core",
        "OrderID",
        "MY_SIZE",
        "PROBABLE_SIZE",
        "KASPI_OFFER_NAME",
        "SKU_key",
        "_db_row_id",
        "_line_key",
        "_probable_size_source",
        "_probable_size_confidence",
    ]
    assert contract.tabs["Run_Control"].editable_columns == [
        "ready_for_closeout",
        "ready_set_by",
        "ready_set_at",
        "notes",
        "last_verified_ready_at",
        "last_orchestrator_run_id",
        "last_orchestrator_status",
    ]
    assert contract.tabs["SalesRaw_Today"].ui["hidden_columns"] == [
        "_db_row_id",
        "_line_key",
        "_probable_size_source",
        "_probable_size_confidence",
    ]
    assert contract.tabs["Needs_Size"].editable_columns == ["my_size", "size_status", "assigned_to", "note"]


def test_build_tab_ui_requests_for_salesraw_sets_filter_hide_and_visual_grouping_without_size_dropdown():
    contract = load_ops_board_contract()
    tab = contract.tabs["SalesRaw_Today"]

    requests = build_tab_ui_requests(
        tab_contract=tab,
        sheet_id=123,
        row_count=117,
        column_count=20,
        existing_conditional_rule_count=2,
        existing_protected_range_ids=[77],
    )

    assert requests[0]["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] == 1
    assert requests[1]["setBasicFilter"]["filter"]["range"]["sheetId"] == 123
    assert requests[1]["setBasicFilter"]["filter"]["range"]["endColumnIndex"] == len(tab.headers)
    assert requests[2]["updateDimensionProperties"]["properties"]["hiddenByUser"] is False
    hide_requests = [req for req in requests if "updateDimensionProperties" in req and req["updateDimensionProperties"]["properties"]["hiddenByUser"] is True]
    assert len(hide_requests) == 1
    assert hide_requests[0]["updateDimensionProperties"]["range"]["startIndex"] == 12
    assert hide_requests[0]["updateDimensionProperties"]["range"]["endIndex"] == 16
    delete_requests = [req for req in requests if "deleteConditionalFormatRule" in req]
    assert [req["deleteConditionalFormatRule"]["index"] for req in delete_requests] == [1, 0]
    add_requests = [req for req in requests if "addConditionalFormatRule" in req]
    assert len(add_requests) == 8
    add_specs = [
        (
            req["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]["type"],
            (
                req["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]["values"][0]["userEnteredValue"]
                if req["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"].get("values")
                else ""
            ),
            req["addConditionalFormatRule"]["rule"]["ranges"][0]["startColumnIndex"],
        )
        for req in add_requests
    ]
    assert ("TEXT_EQ", "OVERDUE", 0) in add_specs
    assert ("BLANK", "", 8) in add_specs
    assert ("NOT_BLANK", "", 8) in add_specs
    assert ("TEXT_EQ", "AcmeWear", 2) in add_specs
    assert ("TEXT_EQ", "Universal", 2) in add_specs
    assert ("TEXT_EQ", "6в1_Черный_+Сумка", 6) in add_specs
    assert ("TEXT_EQ", "Принт_5в1_черный", 6) in add_specs
    assert ("TEXT_EQ", "Line51", 6) in add_specs
    validation_requests = [req for req in requests if "setDataValidation" in req]
    assert len(validation_requests) == 1
    assert validation_requests[0]["setDataValidation"]["range"]["startColumnIndex"] == 8
    assert validation_requests[0]["setDataValidation"]["rule"] is None
    delete_protection_requests = [req for req in requests if "deleteProtectedRange" in req]
    assert delete_protection_requests == [{"deleteProtectedRange": {"protectedRangeId": 77}}]
    add_protection_requests = [req for req in requests if "addProtectedRange" in req]
    assert len(add_protection_requests) == 1
    protected = add_protection_requests[0]["addProtectedRange"]["protectedRange"]
    assert protected["range"] == {"sheetId": 123}
    assert protected["unprotectedRanges"] == [
        {
            "sheetId": 123,
            "startRowIndex": 1,
            "endRowIndex": 2000,
            "startColumnIndex": 8,
            "endColumnIndex": 9,
        }
    ]


def test_build_tab_ui_requests_for_run_control_protects_status_columns():
    contract = load_ops_board_contract()
    tab = contract.tabs["Run_Control"]

    requests = build_tab_ui_requests(
        tab_contract=tab,
        sheet_id=456,
        row_count=20,
        column_count=8,
        existing_protected_range_ids=[],
    )

    add_protection_requests = [req for req in requests if "addProtectedRange" in req]
    assert len(add_protection_requests) == 1
    protected = add_protection_requests[0]["addProtectedRange"]["protectedRange"]
    assert protected["range"] == {"sheetId": 456}
    assert protected["unprotectedRanges"] == [
        {
            "sheetId": 456,
            "startRowIndex": 1,
            "endRowIndex": 20,
            "startColumnIndex": 1,
            "endColumnIndex": 2,
        }
    ]


def test_build_tab_reorder_requests_moves_salesraw_and_run_control_first():
    requests = build_tab_reorder_requests(
        current_sheets=[
            {"properties": {"sheetId": 10, "title": "README", "index": 0}},
            {"properties": {"sheetId": 11, "title": "SalesRaw_Today", "index": 1}},
            {"properties": {"sheetId": 12, "title": "Run_Control", "index": 2}},
        ],
        desired_titles=["SalesRaw_Today", "Run_Control", "README"],
    )

    assert requests == [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": 11, "index": 0},
                "fields": "index",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": 12, "index": 1},
                "fields": "index",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": 10, "index": 2},
                "fields": "index",
            }
        },
    ]


def test_validate_contract_layout_detects_collapsed_header_row():
    contract = load_ops_board_contract()
    live_headers = {
        "README": ["key value notes"],
        "SalesRaw_Today": contract.tabs["SalesRaw_Today"].headers,
        "Run_Control": contract.tabs["Run_Control"].headers,
        "Orders_Today": contract.tabs["Orders_Today"].headers,
        "Needs_Size": contract.tabs["Needs_Size"].headers,
        "Shipping_Queue": contract.tabs["Shipping_Queue"].headers,
        "Exceptions": contract.tabs["Exceptions"].headers,
        "Shipped_Today": contract.tabs["Shipped_Today"].headers,
        "Config_Do_Not_Edit": contract.tabs["Config_Do_Not_Edit"].headers,
    }

    report = validate_contract_layout(
        contract=contract,
        sheet_names=list(live_headers),
        header_rows=live_headers,
    )

    assert report["ok"] is False
    assert report["tabs"]["README"]["header_ok"] is False
    assert report["tabs"]["README"]["expected_headers"] == ["field", "value", "notes"]


def test_validate_contract_layout_tolerates_blank_spacer_column():
    contract = load_ops_board_contract()
    sales_headers = contract.tabs["SalesRaw_Today"].headers
    live_headers = {
        tab_name: tab_contract.headers
        for tab_name, tab_contract in contract.tabs.items()
    }
    live_headers["SalesRaw_Today"] = sales_headers[:7] + [""] + sales_headers[7:]

    report = validate_contract_layout(
        contract=contract,
        sheet_names=list(live_headers),
        header_rows=live_headers,
    )

    assert report["ok"] is True
    assert report["tabs"]["SalesRaw_Today"]["header_ok"] is True
    assert report["tabs"]["SalesRaw_Today"]["ignored_blank_header_columns"] == [8]


def test_extract_rows_from_matrix_maps_rows_with_blank_spacer_header_column():
    headers = ["Status", "Kaspi_name_core", "OrderID", "MY_SIZE", "PROBABLE_SIZE"]
    matrix = [
        ["Status", "Kaspi_name_core", "", "OrderID", "MY_SIZE", "PROBABLE_SIZE"],
        ["TODAY", "Принт_5в1_черный", "", "905583266", "L", "L"],
    ]

    rows = extract_rows_from_matrix(headers, matrix)

    assert rows == [
        {
            "Status": "TODAY",
            "Kaspi_name_core": "Принт_5в1_черный",
            "OrderID": "905583266",
            "MY_SIZE": "L",
            "PROBABLE_SIZE": "L",
        }
    ]


def test_extract_rows_with_positions_maps_rows_with_blank_spacer_header_column():
    headers = ["Status", "Kaspi_name_core", "OrderID", "MY_SIZE", "PROBABLE_SIZE"]
    matrix = [
        ["Status", "Kaspi_name_core", "", "OrderID", "MY_SIZE", "PROBABLE_SIZE"],
        ["TODAY", "Принт_5в1_черный", "", "905583266", "L", "L"],
    ]

    rows = extract_rows_with_positions_from_matrix(headers, matrix)

    assert rows == [
        {
            "sheet_row": 2,
            "row": {
                "Status": "TODAY",
                "Kaspi_name_core": "Принт_5в1_черный",
                "OrderID": "905583266",
                "MY_SIZE": "L",
                "PROBABLE_SIZE": "L",
            },
        }
    ]


def test_invalid_layout_tabs_returns_only_broken_tabs():
    invalid = _invalid_layout_tabs(
        {
            "missing_tabs": ["SalesRaw_Today"],
            "tabs": {
                "README": {"header_ok": True},
                "SalesRaw_Today": {"header_ok": False},
                "Orders_Today": {"header_ok": True},
            },
        }
    )

    assert invalid == {"SalesRaw_Today"}


def test_merge_rows_preserves_editable_columns_by_order_id():
    contract = load_ops_board_contract()
    tab = contract.tabs["Needs_Size"]
    existing_rows = [
        {
            "order_id": "1001",
            "store": "UNIVERSAL",
            "planned_date": "2026-04-15",
            "offer_name": "Old Name",
            "quantity": 1,
            "my_size": "L",
            "size_status": "assigned",
            "assigned_to": "worker-1",
            "note": "keep me",
            "last_sync_at": "old",
        }
    ]
    fresh_rows = [
        {
            "order_id": "1001",
            "store": "UNIVERSAL",
            "planned_date": "2026-04-15",
            "offer_name": "Fresh Name",
            "quantity": 3,
            "my_size": "",
            "size_status": "needs_size",
            "assigned_to": "",
            "note": "",
            "last_sync_at": "new",
        }
    ]

    merged = merge_rows_preserving_editables(tab_contract=tab, fresh_rows=fresh_rows, existing_rows=existing_rows)

    assert merged == [
        {
            "order_id": "1001",
            "store": "UNIVERSAL",
            "planned_date": "2026-04-15",
            "offer_name": "Fresh Name",
            "quantity": 3,
            "my_size": "L",
            "size_status": "assigned",
            "assigned_to": "worker-1",
            "note": "keep me",
            "last_sync_at": "new",
        }
    ]


def test_build_phase1_payload_groups_orders_into_board_tabs(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:00:00+05:00",
    )

    orders = payload["Orders_Today"]
    salesraw = payload["SalesRaw_Today"]
    needs_size = payload["Needs_Size"]
    shipping = payload["Shipping_Queue"]
    shipped = payload["Shipped_Today"]
    exceptions = payload["Exceptions"]
    run_control = payload["Run_Control"]

    assert [row["_db_row_id"] for row in salesraw] == ["6", "1", "2", "3"]
    assert [row["OrderID"] for row in salesraw] == ["0900", "1001", "1001", "1002"]
    assert [row["STORE_NAME"] for row in salesraw] == ["Universal", "Universal", "Universal", "STORE-B"]
    assert [row["Status"] for row in salesraw] == ["OVERDUE", "TODAY", "TODAY", "TODAY"]
    assert salesraw[0]["MY_SIZE"] == "XL"
    assert salesraw[0]["PROBABLE_SIZE"] == "XL"
    assert salesraw[1]["PROBABLE_SIZE"] == "L"
    assert salesraw[1]["_probable_size_source"] == "CUSTOMER"
    assert salesraw[1]["Kaspi_name_core"] == "Nike_Tee_Black"
    assert "Phone" not in salesraw[0]
    assert [row["order_id"] for row in orders] == ["0900", "1001", "1002"]
    order_1001 = next(row for row in orders if row["order_id"] == "1001")
    assert order_1001["offer_name"] == "Nike Tee Black +1 more"
    assert order_1001["quantity"] == 3
    assert [row["order_id"] for row in needs_size] == ["1001"]
    assert [row["order_id"] for row in shipping] == ["0900", "1002"]
    shipping_1002 = next(row for row in shipping if row["order_id"] == "1002")
    assert shipping_1002["waybill_ready"] == "yes"
    assert [row["order_id"] for row in shipped] == ["1003"]
    assert [row["exception_type"] for row in exceptions] == ["MISSING_SIZE"]
    assert run_control == [
        {
            "target_date": "2026-04-15",
            "ready_for_closeout": "HOLD",
            "ready_set_by": "",
            "ready_set_at": "",
            "notes": "",
            "last_verified_ready_at": "",
            "last_orchestrator_run_id": "",
            "last_orchestrator_status": "",
        }
    ]


def test_build_phase1_payload_drops_placeholder_shadow_rows_when_concrete_row_exists(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, created_at, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                "1001",
                "UNIVERSAL",
                "2026-04-15",
                "2026-04-15T10:00:00",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "nan",
                "",
                "",
                None,
                None,
                1,
                None,
                0,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Ali",
                "One",
                "+77000000001",
                176,
                78,
                "2026-04-15T10:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:00:00+05:00",
    )

    salesraw = payload["SalesRaw_Today"]

    assert [row["_db_row_id"] for row in salesraw] == ["6", "1", "2", "3"]
    assert all(row["KASPI_OFFER_NAME"] != "nan" for row in salesraw)
    assert all(row["Kaspi_name_core"] != "UNKNOWN" for row in salesraw)


def test_build_phase1_payload_respects_store_specific_same_day_cutoffs(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, created_at, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    9,
                    "1006",
                    "ACMEWEAR",
                    "2026-04-15",
                    "2026-04-15T16:01:00",
                    "KASPI_DELIVERY",
                    "ACCEPTED",
                    "AcmeWear Cutoff Edge",
                    "SKU-4",
                    "SKU-4-LINE-C",
                    None,
                    None,
                    1,
                    None,
                    0,
                    None,
                    None,
                    "ACCEPTED_BY_MERCHANT",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "Ira",
                    "Seven",
                    "",
                    None,
                    None,
                    "2026-04-15T16:01:00",
                ),
                (
                    10,
                    "1007",
                    "UNIVERSAL",
                    "2026-04-15",
                    "2026-04-15T16:45:00",
                    "KASPI_DELIVERY",
                    "ACCEPTED",
                    "Universal Too Late",
                    "SKU-1",
                    "SKU-1-LINE-D",
                    None,
                    None,
                    1,
                    None,
                    0,
                    None,
                    None,
                    "ACCEPTED_BY_MERCHANT",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "Uma",
                    "Eight",
                    "",
                    None,
                    None,
                    "2026-04-15T16:45:00",
                ),
                (
                    11,
                    "1008",
                    "ACMEWEAR",
                    "2026-04-15",
                    "2026-04-15T16:02:00",
                    "KASPI_DELIVERY",
                    "ACCEPTED",
                    "AcmeWear After Cutoff",
                    "SKU-4",
                    "SKU-4-LINE-D",
                    None,
                    None,
                    1,
                    None,
                    0,
                    None,
                    None,
                    "ACCEPTED_BY_MERCHANT",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "Olga",
                    "Nine",
                    "",
                    None,
                    None,
                    "2026-04-15T16:02:00",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T16:50:00+05:00",
    )

    order_ids = [row["OrderID"] for row in payload["SalesRaw_Today"]]

    assert "1006" in order_ids
    assert "1007" not in order_ids
    assert "1008" not in order_ids


def test_build_phase1_payload_carries_forward_pending_previous_day_rows_within_store_cutoff(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, created_at, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    30,
                    "0910",
                    "ACMEWEAR",
                    "2026-04-14",
                    "2026-04-14T16:01:00",
                    "KASPI_DELIVERY",
                    "ACCEPTED",
                    "AcmeWear Cutoff Carry",
                    "SKU-4",
                    "SKU-4-LINE-CARRY",
                    None,
                    None,
                    1,
                    None,
                    0,
                    None,
                    None,
                    "ACCEPTED_BY_MERCHANT",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "Carry",
                    "Forward",
                    "+77000000030",
                    170,
                    70,
                    "2026-04-14T16:01:00",
                ),
                (
                    31,
                    "0911",
                    "ACMEWEAR",
                    "2026-04-14",
                    "2026-04-14T16:02:00",
                    "KASPI_DELIVERY",
                    "ACCEPTED",
                    "AcmeWear After Cutoff",
                    "SKU-4",
                    "SKU-4-LINE-LATE",
                    None,
                    None,
                    1,
                    None,
                    0,
                    None,
                    None,
                    "ACCEPTED_BY_MERCHANT",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "After",
                    "Cutoff",
                    "+77000000031",
                    170,
                    70,
                    "2026-04-14T16:02:00",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:00:00+05:00",
    )

    salesraw_by_order = {row["OrderID"]: row for row in payload["SalesRaw_Today"]}

    assert salesraw_by_order["0910"]["Status"] == "OVERDUE"
    assert salesraw_by_order["0910"]["MY_SIZE"] == ""
    assert "0911" not in salesraw_by_order
    assert "0910" in {row["order_id"] for row in payload["Needs_Size"]}


def test_build_phase1_payload_excludes_stale_pending_sibling_when_order_was_handed_over(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, created_at, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    40,
                    "0912",
                    "UNIVERSAL",
                    "2026-04-14",
                    "2026-04-14T10:00:00",
                    "ARCHIVE",
                    "SHIPPED",
                    "Already Shipped Black",
                    "SKU-1",
                    "SKU-1-LINE-SHIPPED",
                    None,
                    "XL",
                    1,
                    "https://wb/0912",
                    1,
                    "2026-04-14",
                    "2026-04-14T18:30:00",
                    "COMPLETED",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "Sibling",
                    "Done",
                    "+77000000912",
                    180,
                    80,
                    "2026-04-14T18:30:00",
                ),
                (
                    41,
                    "0912",
                    "UNIVERSAL",
                    "2026-04-14",
                    "2026-04-14T10:00:00",
                    "KASPI_DELIVERY",
                    "ACCEPTED",
                    "Stale Pending White",
                    "SKU-2",
                    "SKU-2-LINE-STALE",
                    None,
                    None,
                    1,
                    None,
                    0,
                    None,
                    None,
                    "ACCEPTED_BY_MERCHANT",
                    0,
                    "DELIVERY",
                    None,
                    "PREPAID",
                    0,
                    "Sibling",
                    "Stale",
                    "+77000000912",
                    180,
                    80,
                    "2026-04-14T18:30:00",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:00:00+05:00",
    )

    assert "0912" not in {row["OrderID"] for row in payload["SalesRaw_Today"]}
    assert "0912" not in {row["order_id"] for row in payload["Needs_Size"]}


def test_build_phase1_payload_applies_order_specific_name_core_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)
    override_path = tmp_path / "order_core_overrides.yaml"
    override_path.write_text(
        """
version: 1
overrides:
  "1001":
    active: true
    kaspi_name_core: "Питер_положи_2-накладной-стикера-и_2-курьерпакета"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AB_KASPI_ORDER_NAME_CORE_OVERRIDES", str(override_path))

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:00:00+05:00",
    )

    rows_1001 = [row for row in payload["SalesRaw_Today"] if row["OrderID"] == "1001"]

    assert rows_1001
    assert {row["Kaspi_name_core"] for row in rows_1001} == {
        "Питер_положи_2-накладной-стикера-и_2-курьерпакета"
    }


def test_build_phase1_payload_prefers_store_offer_mapping_before_name_extraction(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                "1004",
                "ACMEWEAR",
                "2026-04-15",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "Комплект ACMEWEAR OF_SUIT-61_BLK_2XL",
                "SKU-4",
                "SKU-4-LINE-B",
                None,
                None,
                1,
                None,
                0,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Eli",
                "Five",
                "",
                None,
                None,
                "2026-04-15T13:30:00",
                "2026-04-15T13:30:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_offer_name, kaspi_article, sku_key, sku_id, kaspi_name_core, active_flag, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ACMEWEAR",
                "Комплект ACMEWEAR OF_SUIT-61_BLK_2XL",
                "OF_SUIT-61_BLK_2XL",
                "SKU-4",
                "SKU-4-LINE-B",
                "6в1_Черный_+Сумка",
                1,
                "2026-04-15T13:31:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:35:00+05:00",
    )

    salesraw = payload["SalesRaw_Today"]
    row_1004 = next(row for row in salesraw if row["OrderID"] == "1004")

    assert row_1004["STORE_NAME"] == "AcmeWear"
    assert row_1004["Kaspi_name_core"] == "6в1_Черный_+Сумка"


def test_build_phase1_payload_prefers_declared_offer_size_for_acmewear_variants(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_orders_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, planned_shipment_date, kaspi_status, internal_status,
                kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity,
                waybill_url, waybill_downloaded, actual_shipment_date, courier_transmission_date,
                kaspi_status_detail, signature_required, delivery_mode, planned_delivery_date, payment_mode, returned_to_warehouse,
                customer_first_name, customer_last_name, customer_phone,
                customer_height_cm, customer_weight_kg, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                8,
                "1005",
                "ACMEWEAR",
                "2026-04-15",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "Спортивный костюм ACMEWEAR OF_SUIT-61_BLK_K-O_4XL_58 черный, белый 4XL",
                "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2",
                "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_4XL",
                None,
                None,
                1,
                None,
                0,
                None,
                None,
                "ACCEPTED_BY_MERCHANT",
                0,
                "DELIVERY",
                None,
                "PREPAID",
                0,
                "Sati",
                "Six",
                "",
                None,
                None,
                "2026-04-15T13:36:00",
                "2026-04-15T13:36:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    contract = load_ops_board_contract()
    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date="2026-04-15",
        lookback_days=5,
        now_iso="2026-04-15T13:40:00+05:00",
    )

    salesraw = payload["SalesRaw_Today"]
    row_1005 = next(row for row in salesraw if row["OrderID"] == "1005")

    assert row_1005["STORE_NAME"] == "AcmeWear"
    assert row_1005["PROBABLE_SIZE"] == "4XL"
    assert row_1005["_probable_size_source"] == "DECLARED_ORDER"


def test_build_size_writeback_plan_only_emits_changed_non_empty_sizes():
    sheet_rows = [
        {"_db_row_id": "1", "MY_SIZE": "L"},
        {"_db_row_id": "2", "MY_SIZE": " "},
        {"_db_row_id": "3", "MY_SIZE": "xxl"},
        {"_db_row_id": "", "MY_SIZE": "XL"},
    ]
    db_rows = {
        "1": {"assigned_size": None, "store_code": "UNIVERSAL", "product_type": "CL", "sku_key": "SKU-1"},
        "2": {"assigned_size": None, "store_code": "STOREB", "product_type": "CL", "sku_key": "SKU-2"},
        "3": {"assigned_size": "2XL", "store_code": "ACMEWEAR", "product_type": "CL", "sku_key": "SKU-3"},
    }

    updates = build_size_writeback_plan(
        sheet_rows=sheet_rows,
        db_rows=db_rows,
        key_column="_db_row_id",
        source_column="MY_SIZE",
    )

    assert updates == [
        {
            "target_key": "1",
            "new_assigned_size": "L",
            "raw_input_size": "L",
            "old_assigned_size": "",
            "store_code": "UNIVERSAL",
            "product_type": "CL",
        }
    ]


def test_build_size_writeback_plan_skips_invalid_manual_sizes():
    sheet_rows = [
        {"_db_row_id": "1", "MY_SIZE": "black"},
        {"_db_row_id": "2", "MY_SIZE": " 46 "},
    ]
    db_rows = {
        "1": {"assigned_size": None, "store_code": "UNIVERSAL", "product_type": "CL", "sku_key": "SKU-1"},
        "2": {"assigned_size": "L", "store_code": "STOREB", "product_type": "CL", "sku_key": "SKU-2"},
    }

    updates = build_size_writeback_plan(
        sheet_rows=sheet_rows,
        db_rows=db_rows,
        key_column="_db_row_id",
        source_column="MY_SIZE",
    )

    assert updates == []


def test_plan_size_writeback_reports_invalid_manual_sizes():
    sheet_rows = [
        {"_db_row_id": "1", "MY_SIZE": "black"},
        {"_db_row_id": "2", "MY_SIZE": "46"},
        {"_db_row_id": "3", "MY_SIZE": "2xlб"},
    ]
    db_rows = {
        "1": {"assigned_size": None, "store_code": "UNIVERSAL", "product_type": "CL", "sku_key": "SKU-1"},
        "2": {"assigned_size": None, "store_code": "STOREB", "product_type": "CL", "sku_key": "SKU-2"},
        "3": {"assigned_size": "", "store_code": "ACMEWEAR", "product_type": "CL", "sku_key": "SKU-3"},
    }

    plan = plan_size_writeback(
        sheet_rows=sheet_rows,
        db_rows=db_rows,
        key_column="_db_row_id",
        source_column="MY_SIZE",
    )

    assert plan["invalid_rows"] == [
        {
            "target_key": "1",
            "raw_input_size": "black",
            "product_type": "CL",
            "store_code": "UNIVERSAL",
        }
    ]
    assert plan["updates"] == [
        {
            "target_key": "2",
            "raw_input_size": "46",
            "new_assigned_size": "L",
            "old_assigned_size": "",
            "store_code": "STOREB",
            "product_type": "CL",
        },
        {
            "target_key": "3",
            "raw_input_size": "2xlб",
            "new_assigned_size": "2XL",
            "old_assigned_size": "",
            "store_code": "ACMEWEAR",
            "product_type": "CL",
        },
    ]


def test_build_publish_plan_same_day_preserves_existing_rows_and_only_appends_new():
    contract = load_ops_board_contract()
    before_snapshot = {
        "README": rows_to_matrix(
            contract.tabs["README"].headers,
            [
                {"field": "target_date", "value": "2026-04-15", "notes": "Operational date"},
                {"field": "last_sync_at", "value": "2026-04-15T14:01:00+05:00", "notes": ""},
            ],
        ),
        "SalesRaw_Today": rows_to_matrix(
            contract.tabs["SalesRaw_Today"].headers,
            [
                {
                    "Status": "TODAY",
                    "Date": "2026-04-15",
                    "STORE_NAME": "UNIVERSAL",
                    "HEIGHT": "176",
                    "WEIGHT": "78",
                    "Quantity": 1,
                    "Kaspi_name_core": "Nike_Tee_Black",
                    "OrderID": "1001",
                    "Phone": "+77000000001",
                    "MY_SIZE": "L",
                    "PROBABLE_SIZE": "XL",
                    "KASPI_OFFER_NAME": "Nike Tee Black",
                    "SKU_key": "SKU-1",
                    "_db_row_id": "1",
                    "_line_key": "1001|2026-04-15|SKU-1|Nike Tee Black|1",
                    "_probable_size_source": "CUSTOMER",
                    "_probable_size_confidence": "HIGH",
                }
            ],
        ),
        "Run_Control": rows_to_matrix(
            contract.tabs["Run_Control"].headers,
            [
                {
                    "target_date": "2026-04-15",
                    "ready_for_closeout": "READY",
                    "ready_set_by": "employee-1",
                    "ready_set_at": "2026-04-15T17:55:00+05:00",
                    "notes": "all sizes done",
                    "last_verified_ready_at": "",
                    "last_orchestrator_run_id": "",
                    "last_orchestrator_status": "",
                }
            ],
        ),
        "Orders_Today": rows_to_matrix(
            contract.tabs["Orders_Today"].headers,
            [
                {
                    "order_id": "1001",
                    "store": "UNIVERSAL",
                    "planned_date": "2026-04-15",
                    "status": "ACCEPTED",
                    "customer_name": "Ali One",
                    "phone": "+77000000001",
                    "offer_name": "Nike Tee Black",
                    "sku": "SKU-1",
                    "quantity": 1,
                    "my_size": "",
                    "package_qty": "",
                    "waybill_status": "pending",
                    "whatsapp_status": "",
                    "exception_flag": "keep-existing-flag",
                    "last_sync_at": "2026-04-15T14:01:00+05:00",
                }
            ],
        ),
        "Needs_Size": rows_to_matrix(
            contract.tabs["Needs_Size"].headers,
            [
                {
                    "order_id": "1001",
                    "store": "UNIVERSAL",
                    "planned_date": "2026-04-15",
                    "offer_name": "Nike Tee Black",
                    "quantity": 1,
                    "my_size": "L",
                    "size_status": "assigned",
                    "assigned_to": "employee-1",
                    "note": "keep me",
                    "last_sync_at": "2026-04-15T14:01:00+05:00",
                }
            ],
        ),
        "Shipping_Queue": rows_to_matrix(contract.tabs["Shipping_Queue"].headers, []),
        "Exceptions": rows_to_matrix(contract.tabs["Exceptions"].headers, []),
        "Shipped_Today": rows_to_matrix(contract.tabs["Shipped_Today"].headers, []),
        "Config_Do_Not_Edit": rows_to_matrix(contract.tabs["Config_Do_Not_Edit"].headers, []),
    }
    fresh_payload = {
        "README": [
            {"field": "target_date", "value": "2026-04-15", "notes": "Operational date"},
            {"field": "last_sync_at", "value": "2026-04-15T15:01:00+05:00", "notes": ""},
        ],
        "SalesRaw_Today": [
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "UNIVERSAL",
                "HEIGHT": "176",
                "WEIGHT": "78",
                "Quantity": 3,
                "Kaspi_name_core": "Nike_Tee_Black",
                "OrderID": "1001",
                "Phone": "+77000000001",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "XL",
                "KASPI_OFFER_NAME": "Nike Tee Black +1 more",
                "SKU_key": "MULTI",
                "_db_row_id": "1",
                "_line_key": "1001|2026-04-15|SKU-1|Nike Tee Black|1",
                "_probable_size_source": "CUSTOMER",
                "_probable_size_confidence": "HIGH",
            },
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "STOREB",
                "HEIGHT": "170",
                "WEIGHT": "68",
                "Quantity": 1,
                "Kaspi_name_core": "Berserk_Rashguard",
                "OrderID": "1002",
                "Phone": "+77000000002",
                "MY_SIZE": "XL",
                "PROBABLE_SIZE": "L",
                "KASPI_OFFER_NAME": "Berserk Rashguard",
                "SKU_key": "SKU-3",
                "_db_row_id": "3",
                "_line_key": "1002|2026-04-15|SKU-3|Berserk Rashguard|1",
                "_probable_size_source": "CUSTOMER",
                "_probable_size_confidence": "HIGH",
            },
        ],
        "Run_Control": [
            {
                "target_date": "2026-04-15",
                "ready_for_closeout": "HOLD",
                "ready_set_by": "",
                "ready_set_at": "",
                "notes": "",
                "last_verified_ready_at": "",
                "last_orchestrator_run_id": "",
                "last_orchestrator_status": "",
            }
        ],
        "Orders_Today": [
            {
                "order_id": "1001",
                "store": "UNIVERSAL",
                "planned_date": "2026-04-15",
                "status": "READY",
                "customer_name": "Ali One",
                "phone": "+77000000001",
                "offer_name": "Nike Tee Black",
                "sku": "SKU-1",
                "quantity": 3,
                "my_size": "",
                "package_qty": "",
                "waybill_status": "ready",
                "whatsapp_status": "",
                "exception_flag": "",
                "last_sync_at": "2026-04-15T15:01:00+05:00",
            },
            {
                "order_id": "1002",
                "store": "STOREB",
                "planned_date": "2026-04-15",
                "status": "ACCEPTED",
                "customer_name": "Bea Two",
                "phone": "+77000000002",
                "offer_name": "Berserk Rashguard",
                "sku": "SKU-2",
                "quantity": 1,
                "my_size": "",
                "package_qty": "",
                "waybill_status": "pending",
                "whatsapp_status": "",
                "exception_flag": "",
                "last_sync_at": "2026-04-15T15:01:00+05:00",
            },
        ],
        "Needs_Size": [
            {
                "order_id": "1001",
                "store": "UNIVERSAL",
                "planned_date": "2026-04-15",
                "offer_name": "Nike Tee Black",
                "quantity": 3,
                "my_size": "",
                "size_status": "needs_size",
                "assigned_to": "",
                "note": "",
                "last_sync_at": "2026-04-15T15:01:00+05:00",
            },
            {
                "order_id": "1002",
                "store": "STOREB",
                "planned_date": "2026-04-15",
                "offer_name": "Berserk Rashguard",
                "quantity": 1,
                "my_size": "",
                "size_status": "needs_size",
                "assigned_to": "",
                "note": "",
                "last_sync_at": "2026-04-15T15:01:00+05:00",
            },
        ],
        "Shipping_Queue": [],
        "Exceptions": [],
        "Shipped_Today": [],
        "Config_Do_Not_Edit": [],
    }

    plan = build_publish_plan(
        contract=contract,
        before_snapshot=before_snapshot,
        fresh_payload=fresh_payload,
        target_date="2026-04-15",
    )

    assert plan["rollover"] is False
    assert plan["previous_target_date"] == "2026-04-15"
    assert plan["tab_actions"]["README"]["mode"] == "rewrite"
    assert plan["tab_actions"]["SalesRaw_Today"]["mode"] == "upsert_preserve"
    assert plan["tab_actions"]["Run_Control"]["mode"] == "upsert_preserve"
    assert plan["tab_actions"]["Orders_Today"]["mode"] == "rewrite"
    assert plan["tab_actions"]["Needs_Size"]["mode"] == "rewrite"
    assert plan["tab_actions"]["SalesRaw_Today"]["append_rows"] == [fresh_payload["SalesRaw_Today"][1]]
    assert plan["tab_actions"]["SalesRaw_Today"]["update_rows"][0]["sheet_row"] == 2
    assert plan["tab_actions"]["Run_Control"]["final_rows"][0]["ready_for_closeout"] == "READY"
    assert plan["tab_actions"]["Run_Control"]["final_rows"][0]["notes"] == "all sizes done"
    assert plan["tab_actions"]["Orders_Today"]["append_rows"] == []
    assert plan["tab_actions"]["Needs_Size"]["append_rows"] == []
    assert plan["tab_actions"]["Needs_Size"]["final_rows"][0]["my_size"] == ""
    assert plan["tab_actions"]["Needs_Size"]["final_rows"][0]["note"] == ""
    assert plan["tab_actions"]["Orders_Today"]["final_rows"][0]["status"] == "READY"
    assert plan["tab_actions"]["Orders_Today"]["final_rows"][0]["exception_flag"] == ""
    assert plan["tab_actions"]["SalesRaw_Today"]["final_rows"][0]["MY_SIZE"] == "L"
    assert plan["tab_actions"]["SalesRaw_Today"]["final_rows"][0]["Quantity"] == 3
    assert [row["order_id"] for row in plan["tab_actions"]["Orders_Today"]["final_rows"]] == ["1001", "1002"]


def test_build_publish_plan_same_day_appends_new_salesraw_rows_only_at_bottom():
    contract = load_ops_board_contract()
    before_snapshot = {
        "README": rows_to_matrix(
            contract.tabs["README"].headers,
            [{"field": "target_date", "value": "2026-04-15", "notes": "Operational date"}],
        ),
        "SalesRaw_Today": rows_to_matrix(
            contract.tabs["SalesRaw_Today"].headers,
            [
                {
                    "Status": "TODAY",
                    "Date": "2026-04-15",
                    "STORE_NAME": "Universal",
                    "HEIGHT": "",
                    "WEIGHT": "",
                    "Quantity": 1,
                    "Kaspi_name_core": "Nike_Tee_Black",
                    "OrderID": "1001",
                    "MY_SIZE": "L",
                    "PROBABLE_SIZE": "L",
                    "KASPI_OFFER_NAME": "Nike Tee Black",
                    "SKU_key": "SKU-1",
                    "_db_row_id": "1",
                    "_line_key": "1001|1",
                    "_probable_size_source": "CUSTOMER",
                    "_probable_size_confidence": "HIGH",
                }
            ],
        ),
        "Run_Control": rows_to_matrix(
            contract.tabs["Run_Control"].headers,
            [{"target_date": "2026-04-15", "ready_for_closeout": "HOLD"}],
        ),
    }
    fresh_payload = {
        "README": [{"field": "target_date", "value": "2026-04-15", "notes": "Operational date"}],
        "SalesRaw_Today": [
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "AcmeWear",
                "HEIGHT": "",
                "WEIGHT": "",
                "Quantity": 1,
                "Kaspi_name_core": "AcmeWear_Set",
                "OrderID": "0900",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "M",
                "KASPI_OFFER_NAME": "AcmeWear Set",
                "SKU_key": "SKU-2",
                "_db_row_id": "2",
                "_line_key": "0900|2",
                "_probable_size_source": "PRODUCT_TYPE",
                "_probable_size_confidence": "LOW",
            },
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "Universal",
                "HEIGHT": "",
                "WEIGHT": "",
                "Quantity": 1,
                "Kaspi_name_core": "Nike_Tee_Black",
                "OrderID": "1001",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "L",
                "KASPI_OFFER_NAME": "Nike Tee Black",
                "SKU_key": "SKU-1",
                "_db_row_id": "1",
                "_line_key": "1001|1",
                "_probable_size_source": "CUSTOMER",
                "_probable_size_confidence": "HIGH",
            },
        ],
        "Run_Control": [{"target_date": "2026-04-15", "ready_for_closeout": "HOLD"}],
    }

    plan = build_publish_plan(
        contract=contract,
        before_snapshot=before_snapshot,
        fresh_payload=fresh_payload,
        target_date="2026-04-15",
    )

    assert plan["tab_actions"]["SalesRaw_Today"]["append_rows"] == [fresh_payload["SalesRaw_Today"][0]]
    assert [row["OrderID"] for row in plan["tab_actions"]["SalesRaw_Today"]["final_rows"]] == ["1001", "0900"]


def test_build_publish_plan_uses_run_control_target_when_readme_is_empty():
    contract = load_ops_board_contract()
    before_snapshot = {
        "README": [],
        "SalesRaw_Today": rows_to_matrix(
            contract.tabs["SalesRaw_Today"].headers,
            [
                {
                    "Status": "TODAY",
                    "Date": "2026-04-15",
                    "STORE_NAME": "Universal",
                    "HEIGHT": "",
                    "WEIGHT": "",
                    "Quantity": 1,
                    "Kaspi_name_core": "Nike_Tee_Black",
                    "OrderID": "1001",
                    "MY_SIZE": "L",
                    "PROBABLE_SIZE": "L",
                    "KASPI_OFFER_NAME": "Nike Tee Black",
                    "SKU_key": "SKU-1",
                    "_db_row_id": "1",
                    "_line_key": "1001|1",
                    "_probable_size_source": "CUSTOMER",
                    "_probable_size_confidence": "HIGH",
                }
            ],
        ),
        "Run_Control": rows_to_matrix(
            contract.tabs["Run_Control"].headers,
            [{"target_date": "2026-04-15", "ready_for_closeout": "READY", "notes": "operator done"}],
        ),
    }
    fresh_payload = {
        "README": [{"field": "target_date", "value": "2026-04-15", "notes": "Operational date"}],
        "SalesRaw_Today": [
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "Universal",
                "HEIGHT": "",
                "WEIGHT": "",
                "Quantity": 1,
                "Kaspi_name_core": "Nike_Tee_Black",
                "OrderID": "1001",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "L",
                "KASPI_OFFER_NAME": "Nike Tee Black",
                "SKU_key": "SKU-1",
                "_db_row_id": "1",
                "_line_key": "1001|1",
                "_probable_size_source": "CUSTOMER",
                "_probable_size_confidence": "HIGH",
            },
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "STORE-B",
                "HEIGHT": "",
                "WEIGHT": "",
                "Quantity": 1,
                "Kaspi_name_core": "Berserk_Rashguard",
                "OrderID": "1002",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "XL",
                "KASPI_OFFER_NAME": "Berserk Rashguard",
                "SKU_key": "SKU-3",
                "_db_row_id": "3",
                "_line_key": "1002|1",
                "_probable_size_source": "CUSTOMER",
                "_probable_size_confidence": "HIGH",
            },
        ],
        "Run_Control": [{"target_date": "2026-04-15", "ready_for_closeout": "HOLD"}],
    }

    plan = build_publish_plan(
        contract=contract,
        before_snapshot=before_snapshot,
        fresh_payload=fresh_payload,
        target_date="2026-04-15",
    )

    assert plan["previous_target_date"] == "2026-04-15"
    assert plan["same_day_preserve"] is True
    assert plan["tab_actions"]["SalesRaw_Today"]["mode"] == "upsert_preserve"
    assert plan["tab_actions"]["SalesRaw_Today"]["append_rows"] == [fresh_payload["SalesRaw_Today"][1]]
    assert plan["tab_actions"]["SalesRaw_Today"]["final_rows"][0]["MY_SIZE"] == "L"
    assert plan["tab_actions"]["Run_Control"]["final_rows"][0]["ready_for_closeout"] == "READY"


def test_build_publish_plan_force_rewrite_operational_tabs_rewrites_same_day_salesraw():
    contract = load_ops_board_contract()
    before_snapshot = {
        "README": rows_to_matrix(
            contract.tabs["README"].headers,
            [{"field": "target_date", "value": "2026-04-15", "notes": "Operational date"}],
        ),
        "SalesRaw_Today": rows_to_matrix(
            contract.tabs["SalesRaw_Today"].headers,
            [
                {
                    "Status": "TODAY",
                    "Date": "2026-04-15",
                    "STORE_NAME": "UNIVERSAL",
                    "HEIGHT": "176",
                    "WEIGHT": "78",
                    "Quantity": 1,
                    "Kaspi_name_core": "Old",
                    "OrderID": "1001",
                    "Phone": "+77000000001",
                    "MY_SIZE": "L",
                    "PROBABLE_SIZE": "XL",
                    "KASPI_OFFER_NAME": "Old Offer",
                    "SKU_key": "SKU-1",
                    "_db_row_id": "1",
                    "_line_key": "old",
                    "_probable_size_source": "DEFAULT",
                    "_probable_size_confidence": "LOW",
                }
            ],
        ),
        "Orders_Today": rows_to_matrix(contract.tabs["Orders_Today"].headers, []),
        "Needs_Size": rows_to_matrix(contract.tabs["Needs_Size"].headers, []),
        "Shipping_Queue": rows_to_matrix(contract.tabs["Shipping_Queue"].headers, []),
        "Exceptions": rows_to_matrix(contract.tabs["Exceptions"].headers, []),
        "Shipped_Today": rows_to_matrix(contract.tabs["Shipped_Today"].headers, []),
        "Config_Do_Not_Edit": rows_to_matrix(contract.tabs["Config_Do_Not_Edit"].headers, []),
    }
    fresh_payload = {
        "README": [{"field": "target_date", "value": "2026-04-15", "notes": "Operational date"}],
        "SalesRaw_Today": [
            {
                "Status": "TODAY",
                "Date": "2026-04-15",
                "STORE_NAME": "UNIVERSAL",
                "HEIGHT": "176",
                "WEIGHT": "78",
                "Quantity": 3,
                "Kaspi_name_core": "Nike_Tee_Black",
                "OrderID": "1001",
                "Phone": "+77000000001",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "XL",
                "KASPI_OFFER_NAME": "Nike Tee Black +1 more",
                "SKU_key": "MULTI",
                "_db_row_id": "1",
                "_line_key": "new",
                "_probable_size_source": "CUSTOMER",
                "_probable_size_confidence": "HIGH",
            }
        ],
        "Orders_Today": [],
        "Needs_Size": [],
        "Shipping_Queue": [],
        "Exceptions": [],
        "Shipped_Today": [],
        "Config_Do_Not_Edit": [],
    }

    plan = build_publish_plan(
        contract=contract,
        before_snapshot=before_snapshot,
        fresh_payload=fresh_payload,
        target_date="2026-04-15",
        force_rewrite_operational_tabs=True,
    )

    assert plan["same_day_preserve"] is False
    assert plan["force_rewrite_operational_tabs"] is True
    assert plan["tab_actions"]["SalesRaw_Today"]["mode"] == "rewrite"
    assert plan["tab_actions"]["SalesRaw_Today"]["append_rows"] == []
    assert plan["tab_actions"]["SalesRaw_Today"]["final_rows"] == fresh_payload["SalesRaw_Today"]


def test_build_publish_plan_new_day_rolls_over_to_fresh_rows(tmp_path: Path):
    contract = load_ops_board_contract()
    before_snapshot = {
        "README": rows_to_matrix(
            contract.tabs["README"].headers,
            [{"field": "target_date", "value": "2026-04-15", "notes": "Operational date"}],
        ),
        "SalesRaw_Today": rows_to_matrix(contract.tabs["SalesRaw_Today"].headers, []),
        "Orders_Today": rows_to_matrix(
            contract.tabs["Orders_Today"].headers,
            [
                {
                    "order_id": "1001",
                    "store": "UNIVERSAL",
                    "planned_date": "2026-04-15",
                    "status": "ACCEPTED",
                    "customer_name": "Ali One",
                    "phone": "+77000000001",
                    "offer_name": "Nike Tee Black",
                    "sku": "SKU-1",
                    "quantity": 1,
                    "my_size": "L",
                    "package_qty": "",
                    "waybill_status": "pending",
                    "whatsapp_status": "",
                    "exception_flag": "",
                    "last_sync_at": "2026-04-15T14:01:00+05:00",
                }
            ],
        ),
        "Needs_Size": rows_to_matrix(contract.tabs["Needs_Size"].headers, []),
        "Shipping_Queue": rows_to_matrix(contract.tabs["Shipping_Queue"].headers, []),
        "Exceptions": rows_to_matrix(contract.tabs["Exceptions"].headers, []),
        "Shipped_Today": rows_to_matrix(contract.tabs["Shipped_Today"].headers, []),
        "Config_Do_Not_Edit": rows_to_matrix(contract.tabs["Config_Do_Not_Edit"].headers, []),
    }
    fresh_payload = {
        "README": [{"field": "target_date", "value": "2026-04-16", "notes": "Operational date"}],
        "SalesRaw_Today": [
            {
                "Status": "TODAY",
                "Date": "2026-04-16",
                "STORE_NAME": "STOREB",
                "HEIGHT": "170",
                "WEIGHT": "68",
                "Quantity": 1,
                "Kaspi_name_core": "Berserk_Rashguard",
                "OrderID": "2001",
                "Phone": "+77000000002",
                "MY_SIZE": "",
                "PROBABLE_SIZE": "L",
                "KASPI_OFFER_NAME": "Berserk Rashguard",
                "SKU_key": "SKU-2",
                "_db_row_id": "9",
                "_line_key": "2001|2026-04-16|SKU-2|Berserk Rashguard|1",
                "_probable_size_source": "DEFAULT",
                "_probable_size_confidence": "LOW",
            }
        ],
        "Orders_Today": [
            {
                "order_id": "2001",
                "store": "STOREB",
                "planned_date": "2026-04-16",
                "status": "ACCEPTED",
                "customer_name": "Bea Two",
                "phone": "+77000000002",
                "offer_name": "Berserk Rashguard",
                "sku": "SKU-2",
                "quantity": 1,
                "my_size": "",
                "package_qty": "",
                "waybill_status": "pending",
                "whatsapp_status": "",
                "exception_flag": "",
                "last_sync_at": "2026-04-16T14:01:00+05:00",
            }
        ],
        "Needs_Size": [],
        "Shipping_Queue": [],
        "Exceptions": [],
        "Shipped_Today": [],
        "Config_Do_Not_Edit": [],
    }

    plan = build_publish_plan(
        contract=contract,
        before_snapshot=before_snapshot,
        fresh_payload=fresh_payload,
        target_date="2026-04-16",
    )

    assert plan["rollover"] is True
    assert plan["previous_target_date"] == "2026-04-15"
    assert plan["tab_actions"]["SalesRaw_Today"]["mode"] == "rewrite"
    assert plan["tab_actions"]["SalesRaw_Today"]["append_rows"] == []
    assert plan["tab_actions"]["SalesRaw_Today"]["final_rows"] == fresh_payload["SalesRaw_Today"]
    assert plan["tab_actions"]["Orders_Today"]["mode"] == "rewrite"
    assert plan["tab_actions"]["Orders_Today"]["append_rows"] == []
    assert plan["tab_actions"]["Orders_Today"]["final_rows"] == fresh_payload["Orders_Today"]

    archive_path = write_rollover_archive(
        archive_root=tmp_path,
        previous_target_date=plan["previous_target_date"],
        before_snapshot=before_snapshot,
    )
    archive = archive_path.read_text(encoding="utf-8")
    assert "2026-04-15" in archive
    assert "1001" in archive
