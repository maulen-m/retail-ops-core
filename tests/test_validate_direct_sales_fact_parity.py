from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from openpyxl import Workbook

from scripts.feed_fact_orders_kaspi_to_sales_fact_v2 import SHADOW_COLUMNS, UNMAPPED_COLUMNS
from scripts.validate_direct_sales_fact_parity import compare_rows, validate_parity


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL
        );
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT,
            quantity INTEGER,
            sell_price_kzt REAL,
            delivery_fee REAL,
            net_rev REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        INSERT INTO dim_sku VALUES ('CL_LINE52_BLACK', 'Line52', 'CL', 1, 0.5, 1000);
        INSERT INTO dim_sku_size VALUES ('CL_LINE52_BLACK_M', 'CL_LINE52_BLACK', 'M');
        """
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path, rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    headers = [
        "Status",
        "Статус",
        "Дата изменения статуса",
        "Date",
        "STORE_NAME",
        "Quantity",
        "OrderID",
        "MY_SIZE",
        "KASPI_OFFER_NAME",
        "SKU_key",
        "SKU_ID",
        "Sell_price_kzt",
        "Total_price",
        "Total_net_rev",
        "PLANNED_SHIPPING_DATE",
        "Product_Type",
        "Return",
    ]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(header) for header in headers])
    wb.save(path)


def _write_shadow(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHADOW_COLUMNS)
        writer.writeheader()
        for row in rows:
            full = {column: "" for column in SHADOW_COLUMNS}
            full.update(row)
            writer.writerow(full)
    with (path.parent / "unmapped_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNMAPPED_COLUMNS)
        writer.writeheader()


def _write_unmapped(path: Path, rows: list[dict]) -> None:
    with (path.parent / "unmapped_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNMAPPED_COLUMNS)
        writer.writeheader()
        for row in rows:
            full = {column: "" for column in UNMAPPED_COLUMNS}
            full.update(row)
            writer.writerow(full)


def _base_direct_row(**overrides) -> dict:
    row = {
        "run_id": "test",
        "source_table": "fact_orders_kaspi",
        "source_row_id": "1",
        "order_id": "ORD-1",
        "store_code": "ACMEWEAR",
        "line_identity_key": "L1",
        "order_date": "2026-07-05",
        "order_date_basis": "planned_shipment_date",
        "source_order_date": "2026-07-04",
        "planned_shipment_date": "2026-07-05",
        "actual_shipment_date": "",
        "courier_transmission_date": "",
        "status_updated_date": "2026-07-05",
        "created_date": "2026-07-04",
        "sku_key": "CL_LINE52_BLACK",
        "sku_id": "CL_LINE52_BLACK_M",
        "my_size": "M",
        "final_my_size_source": "assigned_size",
        "kaspi_offer_name": "Offer Print",
        "quantity": 1,
        "quantity_source": "fact_orders_kaspi.quantity",
        "raw_unit_price_kzt": 10000,
        "sell_price_kzt": 10000,
        "sell_price_basis": "unit_price_kzt",
        "delivery_fee": 100,
        "delivery_fee_source": "delivery_cost_for_seller",
        "net_rev": "",
        "net_rev_source": "",
        "cogs": "",
        "cogs_source": "not_computed_phase1",
        "profit": "",
        "profit_source": "not_computed_phase1",
        "status": "DELIVERED",
        "kaspi_status": "ARCHIVE",
        "kaspi_status_detail": "COMPLETED",
        "internal_status": "COMPLETED",
        "return_flag": 0,
        "return_date": "",
        "source_file": "fact_orders_kaspi:test",
        "source_imported_at": "",
        "source_updated_at": "",
        "size_source": "GOOGLE_OPS_BOARD",
        "size_confidence": "HIGH",
        "logical_dedupe_key": "ORD-1|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
        "db_unique_key": "ORD-1|CL_LINE52_BLACK_M|ACMEWEAR|Offer Print",
        "existing_sale_id_logical": "",
        "existing_sale_id_db_unique": "",
    }
    row.update(overrides)
    return row


def _base_crm_row(**overrides) -> dict:
    row = {
        "source_lane": "crm_baseline",
        "order_id": "ORD-1",
        "order_date": "2026-07-04",
        "planned_shipment_date": "2026-07-04",
        "status_change_date": "",
        "store_code": "ACMEWEAR",
        "sku_key": "CL_LINE52_BLACK",
        "sku_id": "CL_LINE52_BLACK_M",
        "my_size": "M",
        "kaspi_offer_name": "Offer Print",
        "quantity": 1,
        "sell_price_kzt": "10000",
        "delivery_fee": "100",
        "net_rev": "",
        "status": "DELIVERED",
        "crm_status_raw": "",
        "return_flag": 0,
        "logical_dedupe_key": "ORD-1|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
        "db_unique_key": "ORD-1|ACMEWEAR|Offer Print|CL_LINE52_BLACK_M",
    }
    row.update(overrides)
    return row


def test_green_with_date_basis_diff_classification(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    crm = tmp_path / "crm.xlsx"
    _write_workbook(
        crm,
        [
            {
                "Date": "2026-07-04",
                "STORE_NAME": "AcmeWear",
                "Quantity": 1,
                "OrderID": "ORD-1",
                "MY_SIZE": "M",
                "KASPI_OFFER_NAME": "Offer Print",
                "SKU_key": "CL_LINE52_BLACK",
                "SKU_ID": "CL_LINE52_BLACK_M",
                "Sell_price_kzt": 10000,
                "PLANNED_SHIPPING_DATE": "2026-07-05",
                "Product_Type": "CL",
                "Return": 0,
            }
        ],
    )
    shadow = tmp_path / "run" / "direct_feeder_shadow_rows.csv"
    _write_shadow(shadow, [_base_direct_row()])

    summary = validate_parity(
        db_path=db,
        crm_file=crm,
        crm_sheet="SALES_KSP_CRM_1",
        direct_shadow=shadow,
        from_date="2026-07-04",
        to_date="2026-07-05",
        out_dir=tmp_path / "out",
    )

    assert summary["verdict"] == "GREEN_WITH_DATE_BASIS_DIFF"
    assert summary["date_basis_classified"] == 1
    date_diff = (tmp_path / "out" / "date_basis_diff.csv").read_text(encoding="utf-8")
    assert "crm_date_matches_created_date" in date_diff


def test_red_on_quantity_price_and_status_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    crm = tmp_path / "crm.xlsx"
    _write_workbook(
        crm,
        [
            {
                "Date": "2026-07-04",
                "STORE_NAME": "AcmeWear",
                "Quantity": 1,
                "OrderID": "ORD-1",
                "MY_SIZE": "M",
                "KASPI_OFFER_NAME": "Offer Print",
                "SKU_key": "CL_LINE52_BLACK",
                "SKU_ID": "CL_LINE52_BLACK_M",
                "Sell_price_kzt": 10000,
                "PLANNED_SHIPPING_DATE": "2026-07-04",
                "Product_Type": "CL",
                "Return": 0,
            }
        ],
    )
    shadow = tmp_path / "run" / "direct_feeder_shadow_rows.csv"
    _write_shadow(
        shadow,
        [
            _base_direct_row(
                order_date="2026-07-04",
                source_order_date="2026-07-04",
                planned_shipment_date="2026-07-04",
                quantity=2,
                sell_price_kzt=9000,
                status="RETURNED",
                return_flag=1,
            )
        ],
    )

    summary = validate_parity(
        db_path=db,
        crm_file=crm,
        crm_sheet="SALES_KSP_CRM_1",
        direct_shadow=shadow,
        from_date="2026-07-04",
        to_date="2026-07-05",
        out_dir=tmp_path / "out",
    )

    assert summary["verdict"] == "RED"
    diff_text = (tmp_path / "out" / "row_diff.csv").read_text(encoding="utf-8")
    assert "quantity" in diff_text
    assert "sell_price_kzt" in diff_text
    assert "status" in diff_text


def test_direct_status_fresher_is_classified_with_timestamp_evidence(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    crm = tmp_path / "crm.xlsx"
    _write_workbook(
        crm,
        [
            {
                "Date": "2026-07-04",
                "STORE_NAME": "AcmeWear",
                "Quantity": 1,
                "OrderID": "ORD-1",
                "MY_SIZE": "M",
                "KASPI_OFFER_NAME": "Offer Print",
                "SKU_key": "CL_LINE52_BLACK",
                "SKU_ID": "CL_LINE52_BLACK_M",
                "Sell_price_kzt": 10000,
                "PLANNED_SHIPPING_DATE": "2026-07-04",
                "Product_Type": "CL",
                "Return": 0,
                "Статус": "Ожидает передачи курьеру",
                "Дата изменения статуса": "2026-07-04",
            }
        ],
    )
    shadow = tmp_path / "run" / "direct_feeder_shadow_rows.csv"
    _write_shadow(
        shadow,
        [
            _base_direct_row(
                order_date="2026-07-04",
                source_order_date="2026-07-04",
                planned_shipment_date="2026-07-04",
                status="RETURNED",
                return_flag=1,
                status_updated_date="2026-07-05",
                internal_status="CANCELLED",
                kaspi_status_detail="CANCELLING",
            )
        ],
    )

    summary = validate_parity(
        db_path=db,
        crm_file=crm,
        crm_sheet="SALES_KSP_CRM_1",
        direct_shadow=shadow,
        from_date="2026-07-04",
        to_date="2026-07-05",
        out_dir=tmp_path / "out",
    )

    assert summary["verdict"] == "GREEN_WITH_CLASSIFIED_DIFFS"
    assert summary["true_mismatches"] == 0
    diff_text = (tmp_path / "out" / "row_diff.csv").read_text(encoding="utf-8")
    assert "direct_status_fresher" in diff_text
    assert "direct_status_updated_date=2026-07-05" in diff_text


def test_loose_identity_pair_is_classified_as_direct_size_assignment_diff(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    crm = tmp_path / "crm.xlsx"
    _write_workbook(
        crm,
        [
            {
                "Date": "2026-07-04",
                "STORE_NAME": "AcmeWear",
                "Quantity": 1,
                "OrderID": "ORD-1",
                "MY_SIZE": "M",
                "KASPI_OFFER_NAME": "Offer Print",
                "SKU_key": "CL_LINE52_BLACK",
                "SKU_ID": "CL_LINE52_BLACK_M",
                "Sell_price_kzt": 10000,
                "PLANNED_SHIPPING_DATE": "2026-07-04",
                "Product_Type": "CL",
                "Return": 0,
            }
        ],
    )
    shadow = tmp_path / "run" / "direct_feeder_shadow_rows.csv"
    _write_shadow(
        shadow,
        [
            _base_direct_row(
                order_date="2026-07-04",
                source_order_date="2026-07-04",
                planned_shipment_date="2026-07-04",
                my_size="XL",
                sku_id="CL_LINE52_BLACK_XL",
                final_my_size_source="assigned_size",
                logical_dedupe_key="ORD-1|ACMEWEAR|Offer Print|CL_LINE52_BLACK|XL",
                db_unique_key="ORD-1|CL_LINE52_BLACK_XL|ACMEWEAR|Offer Print",
            )
        ],
    )

    summary = validate_parity(
        db_path=db,
        crm_file=crm,
        crm_sheet="SALES_KSP_CRM_1",
        direct_shadow=shadow,
        from_date="2026-07-04",
        to_date="2026-07-05",
        out_dir=tmp_path / "out",
    )

    assert summary["true_mismatches"] == 0
    assert summary["diff_breakdown"]["direct_size_assignment_diff"] == 1


def test_one_sided_selector_rows_are_classified_not_unexplained(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    crm = tmp_path / "crm.xlsx"
    _write_workbook(
        crm,
        [
            {
                "Date": "2026-07-04",
                "STORE_NAME": "AcmeWear",
                "Quantity": 1,
                "OrderID": "CRM-ONLY",
                "MY_SIZE": "M",
                "KASPI_OFFER_NAME": "Offer Print",
                "SKU_key": "CL_LINE52_BLACK",
                "SKU_ID": "CL_LINE52_BLACK_M",
                "Sell_price_kzt": 10000,
                "PLANNED_SHIPPING_DATE": "2026-07-04",
                "Product_Type": "CL",
                "Return": 0,
            }
        ],
    )
    shadow = tmp_path / "run" / "direct_feeder_shadow_rows.csv"
    _write_shadow(
        shadow,
        [
            _base_direct_row(
                order_id="DIRECT-ONLY",
                logical_dedupe_key="DIRECT-ONLY|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
                db_unique_key="DIRECT-ONLY|CL_LINE52_BLACK_M|ACMEWEAR|Offer Print",
                order_date="2026-07-04",
                source_order_date="2026-07-04",
                planned_shipment_date="2026-07-04",
            )
        ],
    )

    summary = validate_parity(
        db_path=db,
        crm_file=crm,
        crm_sheet="SALES_KSP_CRM_1",
        direct_shadow=shadow,
        from_date="2026-07-04",
        to_date="2026-07-05",
        out_dir=tmp_path / "out",
    )

    assert summary["true_mismatches"] == 0
    assert summary["diff_breakdown"]["crm_only_no_fact_order_source"] == 1
    assert summary["diff_breakdown"]["direct_only_no_crm_append_row"] == 1


def test_direct_unmapped_without_crm_row_is_classified(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    crm = tmp_path / "crm.xlsx"
    _write_workbook(crm, [])
    shadow = tmp_path / "run" / "direct_feeder_shadow_rows.csv"
    _write_shadow(shadow, [])
    _write_unmapped(
        shadow,
        [
            {
                "source_lane": "direct_feeder",
                "reason": "missing_size",
                "order_id": "UNMAPPED-1",
                "store_code": "ACMEWEAR",
                "kaspi_offer_name": "",
                "planned_shipment_date": "2026-07-04",
            }
        ],
    )

    summary = validate_parity(
        db_path=db,
        crm_file=crm,
        crm_sheet="SALES_KSP_CRM_1",
        direct_shadow=shadow,
        from_date="2026-07-04",
        to_date="2026-07-05",
        out_dir=tmp_path / "out",
    )

    assert summary["verdict"] == "RED"
    assert summary["diff_breakdown"]["direct_unmapped_source_not_in_crm_selector"] == 1


def test_compare_rows_classifies_policy_bucket_ledger() -> None:
    crm_rows = [
        _base_crm_row(order_id="IDENTITY", logical_dedupe_key="IDENTITY|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M"),
        _base_crm_row(
            order_id="OLD-APPEND",
            logical_dedupe_key="OLD-APPEND|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
        ),
        _base_crm_row(
            order_id="HISTORY",
            logical_dedupe_key="HISTORY|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
        ),
        _base_crm_row(
            order_id="PRICE",
            quantity=2,
            sell_price_kzt="20000",
            logical_dedupe_key="PRICE|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
        ),
        _base_crm_row(
            order_id="UNMAPPED-MAPPED",
            logical_dedupe_key="UNMAPPED-MAPPED|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
        ),
    ]
    direct_rows = [
        _base_direct_row(
            order_id="IDENTITY",
            my_size="XL",
            sku_id="CL_LINE52_BLACK_XL",
            logical_dedupe_key="IDENTITY|ACMEWEAR|Offer Print|CL_LINE52_BLACK|XL",
            db_unique_key="IDENTITY|CL_LINE52_BLACK_XL|ACMEWEAR|Offer Print",
            final_my_size_source="my_size",
        ),
        _base_direct_row(
            order_id="PRICE",
            quantity=2,
            sell_price_kzt=10000,
            raw_unit_price_kzt=20000,
            sell_price_basis="unit_price_kzt_div_quantity",
            logical_dedupe_key="PRICE|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
            db_unique_key="PRICE|CL_LINE52_BLACK_M|ACMEWEAR|Offer Print",
        ),
        _base_direct_row(
            order_id="TERMINAL",
            status="CANCELLED",
            internal_status="CANCELLED",
            kaspi_status_detail="CANCELLED",
            logical_dedupe_key="TERMINAL|ACMEWEAR|Offer Print|CL_LINE52_BLACK|M",
            db_unique_key="TERMINAL|CL_LINE52_BLACK_M|ACMEWEAR|Offer Print",
        ),
    ]
    direct_unmapped = [
        {
            "order_id": "UNMAPPED-MAPPED",
            "store_code": "ACMEWEAR",
            "kaspi_offer_name": "Offer Print",
            "reason": "missing_size",
        },
        {
            "order_id": "UNMAPPED-BOTH",
            "store_code": "ACMEWEAR",
            "kaspi_offer_name": "Offer Print",
            "reason": "missing_size",
        },
    ]
    crm_unmapped = [
        {
            "order_id": "UNMAPPED-BOTH",
            "store_code": "ACMEWEAR",
            "kaspi_offer_name": "Offer Print",
            "reason": "unresolved_identity",
        }
    ]
    source_lookup = {
        "OLD-APPEND": [
            {
                "planned_shipment_date": "2026-06-30",
                "created_date": "2026-06-30",
                "status_updated_date": "2026-07-04",
                "internal_status": "COMPLETED",
                "kaspi_status_detail": "COMPLETED",
            }
        ],
        "HISTORY": [
            {
                "planned_shipment_date": "2026-07-04",
                "created_date": "2026-07-04",
                "status_updated_date": "2026-07-04",
                "internal_status": "COMPLETED",
                "kaspi_status_detail": "COMPLETED",
            }
        ],
    }

    diffs, _date_rows, counts = compare_rows(
        crm_rows=crm_rows,
        direct_rows=direct_rows,
        direct_unmapped=direct_unmapped,
        crm_unmapped=crm_unmapped,
        source_lookup=source_lookup,
        from_date="2026-07-01",
        to_date="2026-07-07",
    )

    buckets = {row["diff_type"] for row in diffs}
    assert counts["true_mismatches"] == 0
    assert {
        "identity_resolution_delta",
        "crm_append_date_outside_direct_planned_window",
        "crm_only_append_history_or_identity_delta",
        "crm_line_total_price_for_qty_gt1",
        "direct_terminal_status_not_booked_by_crm",
        "direct_unmapped_for_crm_mapped_row",
        "unmapped_in_both_lanes",
    }.issubset(buckets)
