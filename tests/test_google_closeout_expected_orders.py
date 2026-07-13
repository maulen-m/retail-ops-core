from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

from core.ops.waybill_shipping_obligations import (
    load_required_orders_file,
    required_line_scope_hash,
)
from scripts.validate_google_closeout_expected_orders import (
    build_expected_orders_from_db,
    validate_manifest_against_expected,
    validate_required_orders_against_db,
)


def _make_expected_orders_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            signature_required INTEGER,
            courier_transmission_date TEXT,
            returned_to_warehouse INTEGER
            ,kaspi_offer_name TEXT
            ,sku_key TEXT
            ,sku_id TEXT
            ,quantity INTEGER
        )
        """
    )
    rows = [
        (1, "TODAY100", "UNIVERSAL", "L", "", "2026-04-20", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0, "Nike Tee", "SKU-TODAY", "SKU-TODAY-L", 1),
        (2, "OVERDUE101", "ACMEWEAR", "3XL", "", "2026-04-19", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0, "Berserk Tee", "SKU-OVERDUE", "SKU-OVERDUE-3XL", 1),
        (3, "BLANK102", "ACMEWEAR", "", "", "2026-04-19", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0, "Blank Tee", "SKU-BLANK", "SKU-BLANK-L", 1),
        (4, "OLD103", "ACMEWEAR", "XL", "", "2026-04-10", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0, "Old Tee", "SKU-OLD", "SKU-OLD-XL", 1),
        (5, "HANDED104", "UNIVERSAL", "M", "", "2026-04-20", "KASPI_DELIVERY", "TRANSMITTED_TO_COURIER", 0, "2026-04-20T18:00:00+05:00", 0, "Handed Tee", "SKU-HANDED", "SKU-HANDED-M", 1),
    ]
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse
            ,kaspi_offer_name, sku_key, sku_id, quantity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_build_expected_orders_from_db_includes_sized_today_and_overdue_pending_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)

    report = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=5,
    )

    assert report["expected_order_ids"] == ["OVERDUE101", "TODAY100"]
    assert report["counts"]["orders"] == 2
    assert report["counts"]["overdue_orders"] == 1
    assert report["counts_by_store"] == {"ACMEWEAR": 1, "UNIVERSAL": 1}


def test_build_expected_orders_from_db_has_unbounded_obligation_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)

    report = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 12, 31),
        lookback_days=None,
        active_order_ids_by_store={"ACMEWEAR": {"OVERDUE101"}, "UNIVERSAL": {"TODAY100"}},
    )

    assert report["expected_order_ids"] == ["OVERDUE101", "TODAY100"]
    assert report["lookback_days"] is None
    assert report["min_planned_shipment_date"] is None


def test_build_expected_orders_blocks_when_active_obligation_has_no_db_or_size_truth(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)

    report = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=None,
        active_order_ids_by_store={
            "ACMEWEAR": {"BLANK102", "MISSING999", "OVERDUE101"},
            "UNIVERSAL": {"TODAY100"},
        },
    )

    assert report["ok"] is False
    assert report["missing_active_order_ids_by_store"] == {
        "ACMEWEAR": ["BLANK102", "MISSING999"]
    }
    assert report["active_order_blockers"]["ACMEWEAR:BLANK102"] == ["missing_size"]
    assert report["active_order_blockers"]["ACMEWEAR:MISSING999"] == ["missing_db_row"]


def test_build_expected_orders_excludes_duplicate_order_if_any_row_has_physical_handover(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            6,
            "TODAY100",
            "UNIVERSAL",
            "L",
            "",
            "2026-04-20",
            "KASPI_DELIVERY",
            "ACCEPTED_BY_MERCHANT",
            0,
            "2026-04-20T18:00:00+05:00",
            0,
        ),
    )
    conn.commit()
    conn.close()

    report = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=None,
        active_order_ids_by_store={"UNIVERSAL": {"TODAY100"}},
    )

    assert report["ok"] is False
    assert report["expected_order_ids"] == []
    assert report["active_order_blockers"]["UNIVERSAL:TODAY100"] == ["already_handed_over"]


def test_build_expected_orders_from_db_can_filter_to_api_active_order_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse, sku_key, kaspi_offer_name
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            6,
            "STALE105",
            "UNIVERSAL",
            "XL",
            "",
            "2026-04-20",
            "KASPI_DELIVERY",
            "ACCEPTED_BY_MERCHANT",
            0,
            "",
            0,
            "SKU-STALE",
            "Stale offer",
        ),
    )
    conn.commit()
    conn.close()

    report = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=5,
        active_order_ids_by_store={
            "ACMEWEAR": {"OVERDUE101"},
            "UNIVERSAL": {"TODAY100"},
        },
    )

    assert report["expected_order_ids"] == ["OVERDUE101", "TODAY100"]
    assert report["counts"]["orders"] == 2
    assert report["excluded_counts"]["not_api_active"] == 1


def test_expected_orders_allows_multiline_distinct_sizes(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse, kaspi_offer_name, sku_key, sku_id, quantity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (6, "TODAY100", "UNIVERSAL", "XL", "", "2026-04-20", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0, "Nike Shorts", "SKU-SHORT", "SKU-SHORT-XL", 1),
    )
    conn.commit()
    conn.close()

    first = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=None,
        active_order_ids_by_store={"UNIVERSAL": {"TODAY100"}},
        request_identity={
            "target_date": "2026-04-20",
            "ready_set_at": "2026-04-20T17:00:00+05:00",
        },
    )
    second = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=None,
        active_order_ids_by_store={"UNIVERSAL": {"TODAY100"}},
        request_identity=first["request_identity"],
    )

    assert first["ok"] is True
    assert first["orders"][0]["final_size"] == "MULTI"
    assert [line["final_size"] for line in first["orders"][0]["lines"]] == ["L", "XL"]
    assert first["counts"]["order_lines"] == 2
    assert first["line_scope_hash"] == second["line_scope_hash"]


def test_required_line_scope_detects_size_drift(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)
    expected = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=None,
        active_order_ids_by_store={"UNIVERSAL": {"TODAY100"}},
        request_identity={
            "target_date": "2026-04-20",
            "ready_set_at": "2026-04-20T17:00:00+05:00",
        },
    )
    expected_path = tmp_path / "expected_closeout_orders.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    required = load_required_orders_file(
        expected_path,
        target_date=date(2026, 4, 20),
    )
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE fact_orders_kaspi SET assigned_size = 'XL' WHERE id = 1")
    conn.commit()
    conn.close()

    validation = validate_required_orders_against_db(
        required_orders=required,
        db_path=db_path,
        target_date=date(2026, 4, 20),
    )

    assert validation["ok"] is False
    assert validation["issues"] == ["required_orders_db_line_scope_mismatch"]
    assert validation["expected_line_scope_hash"] != validation["observed_line_scope_hash"]


def test_manifest_gate_rejects_same_orders_with_different_line_size(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_expected_orders_db(db_path)
    expected = build_expected_orders_from_db(
        db_path=db_path,
        target_date=date(2026, 4, 20),
        lookback_days=None,
        active_order_ids_by_store={"UNIVERSAL": {"TODAY100"}},
        request_identity={
            "target_date": "2026-04-20",
            "ready_set_at": "2026-04-20T17:00:00+05:00",
        },
    )
    expected_path = tmp_path / "expected_closeout_orders.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    wrong_lines = [dict(expected["orders"][0]["lines"][0], final_size="XL")]
    manifest_path = tmp_path / "send_batch_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-20",
                "request_identity": expected["request_identity"],
                "expected_orders_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
                "counts": {"orders": 1},
                "send_order_ids": ["TODAY100"],
                "line_scope_hash": required_line_scope_hash(wrong_lines),
                "entries": [
                    {
                        "pdf_key": "pdf-1",
                        "order_ids": ["TODAY100"],
                        "source_lines": wrong_lines,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    validation = validate_manifest_against_expected(
        expected_path=expected_path,
        manifest_path=manifest_path,
    )

    assert validation["ok"] is False
    assert "manifest_line_size_scope_mismatch" in validation["issue_codes"]


def test_validate_manifest_against_expected_fails_when_manifest_is_self_consistent_but_missing_overdue_order(
    tmp_path: Path,
) -> None:
    expected_path = tmp_path / "expected_closeout_orders.json"
    manifest_path = tmp_path / "send_batch_manifest.json"
    expected_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-20",
                "expected_order_ids": ["OVERDUE101", "TODAY100"],
                "overdue_order_ids": ["OVERDUE101"],
                "counts": {"orders": 2, "overdue_orders": 1},
                "counts_by_store": {"ACMEWEAR": 1, "UNIVERSAL": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-20",
                "counts": {"pdfs": 1, "orders": 1, "overdue_orders": 0},
                "send_order_ids": ["TODAY100"],
                "overdue_order_ids": [],
                "missing_overdue_order_ids": [],
                "terminal_orders_excluded": True,
                "entries": [
                    {
                        "pdf_key": "pdf-1",
                        "filename": "testing.pdf",
                        "send_sequence": 1,
                        "order_ids": ["TODAY100"],
                        "order_counts_by_store": {"UNIVERSAL": 1},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = validate_manifest_against_expected(
        expected_path=expected_path,
        manifest_path=manifest_path,
    )

    assert report["ok"] is False
    assert report["missing_order_ids"] == ["OVERDUE101"]
    assert report["extra_order_ids"] == []
    assert "expected_orders_missing_from_manifest" in report["issue_codes"]


def test_validate_manifest_against_expected_accepts_exact_order_set(tmp_path: Path) -> None:
    expected_path = tmp_path / "expected_closeout_orders.json"
    manifest_path = tmp_path / "send_batch_manifest.json"
    expected_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-20",
                "expected_order_ids": ["OVERDUE101", "TODAY100"],
                "overdue_order_ids": ["OVERDUE101"],
                "counts": {"orders": 2, "overdue_orders": 1},
                "counts_by_store": {"ACMEWEAR": 1, "UNIVERSAL": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-20",
                "counts": {"pdfs": 2, "orders": 2, "overdue_orders": 1},
                "send_order_ids": ["TODAY100", "OVERDUE101"],
                "overdue_order_ids": ["OVERDUE101"],
                "missing_overdue_order_ids": [],
                "terminal_orders_excluded": True,
                "entries": [
                    {
                        "pdf_key": "pdf-1",
                        "filename": "today.pdf",
                        "send_sequence": 1,
                        "order_ids": ["TODAY100"],
                        "order_counts_by_store": {"UNIVERSAL": 1},
                    },
                    {
                        "pdf_key": "pdf-2",
                        "filename": "overdue.pdf",
                        "send_sequence": 2,
                        "order_ids": ["OVERDUE101"],
                        "order_counts_by_store": {"ACMEWEAR": 1},
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = validate_manifest_against_expected(
        expected_path=expected_path,
        manifest_path=manifest_path,
    )

    assert report["ok"] is True
    assert report["missing_order_ids"] == []
    assert report["extra_order_ids"] == []
