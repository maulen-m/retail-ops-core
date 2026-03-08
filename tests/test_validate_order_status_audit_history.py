from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.validate_order_status_audit_history import (
    OrderStatusAuditHistoryError,
    validate_order_status_audit_history,
)


def _seed_db(path: Path, *, include_api: bool) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_order_status_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                status_internal TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source TEXT NOT NULL,
                ledger_run_id TEXT,
                source_detail TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, store_code, status_internal, observed_at, source)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_status_observations
            (order_id, store_code, status_internal, observed_at, source, ledger_run_id, source_detail)
            VALUES ('1', 'ACMEWEAR', 'DELIVERED', '2026-01-05', 'WEBUI', 'ledger1', 'webui_status_ledger')
            """
        )
        if include_api:
            conn.execute(
                """
                INSERT INTO fact_order_status_observations
                (order_id, store_code, status_internal, observed_at, source, ledger_run_id, source_detail)
                VALUES ('1', 'ACMEWEAR', 'DELIVERED', '2026-03-06', 'API', NULL, 'fact_orders_kaspi')
                """
            )
        conn.commit()
    finally:
        conn.close()


def test_validate_order_status_audit_history_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, include_api=True)

    report = validate_order_status_audit_history(
        db_path=db,
        as_of="2026-03-06",
        output_root=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"


def test_validate_order_status_audit_history_strict_fail_without_api(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, include_api=False)

    with pytest.raises(OrderStatusAuditHistoryError):
        validate_order_status_audit_history(
            db_path=db,
            as_of="2026-03-06",
            output_root=tmp_path / "out",
            strict=True,
        )
