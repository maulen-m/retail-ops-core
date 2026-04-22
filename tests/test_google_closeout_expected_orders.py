from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from scripts.validate_google_closeout_expected_orders import (
    build_expected_orders_from_db,
    validate_manifest_against_expected,
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
        )
        """
    )
    rows = [
        (1, "TODAY100", "UNIVERSAL", "L", "", "2026-04-20", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
        (2, "OVERDUE101", "ACMEWEAR", "3XL", "", "2026-04-19", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
        (3, "BLANK102", "ACMEWEAR", "", "", "2026-04-19", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
        (4, "OLD103", "ACMEWEAR", "XL", "", "2026-04-10", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
        (5, "HANDED104", "UNIVERSAL", "M", "", "2026-04-20", "KASPI_DELIVERY", "TRANSMITTED_TO_COURIER", 0, "2026-04-20T18:00:00+05:00", 0),
    ]
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def test_build_expected_orders_from_db_can_filter_to_api_active_order_ids(tmp_path: Path) -> None:
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
        (6, "STALE105", "UNIVERSAL", "XL", "", "2026-04-20", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
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
