from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.repair_sales_fact_v2_lifecycle_residual_from_status_evidence import (
    build_lifecycle_repair_plan,
    repair_sales_fact_v2_lifecycle_residual,
)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity INTEGER,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT
        );
        CREATE TABLE order_status_event (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            stage_code TEXT NOT NULL,
            event_ts TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_status TEXT,
            source_row_hash TEXT,
            idempotency_key TEXT NOT NULL
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT
        );
        """
    )
    return conn


def _seed_sale(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str = "ACMEWEAR",
    stage_code: str = "CANCELLED",
) -> None:
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag, return_date, source_file
        ) VALUES (?, '2026-04-15', 'SKU_A', 'SKU_A_M', 'M', 'Offer',
                  ?, 1, 'DELIVERED', 0, NULL, 'SALES_KSP_CRM_V3.xlsx')
        """,
        (order_id, store_code),
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code)
        VALUES (?, ?, ?)
        """,
        (f"E-{order_id}", order_id, store_code),
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, raw_status,
            source_row_hash, idempotency_key
        ) VALUES (?, ?, ?, '2026-04-16T10:00:00+05:00',
                  'LOCAL_FACT_ORDERS_KASPI', ?, 'hash-source', ?)
        """,
        (store_code, order_id, stage_code, stage_code, f"ose-{order_id}-{stage_code}"),
    )


def test_lifecycle_repair_plan_uses_same_store_terminal_status(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_sale(conn, order_id="O_CANCEL", stage_code="CANCELLED")
    _seed_sale(conn, order_id="O_RETURN", stage_code="RETURNED")
    _seed_sale(conn, order_id="O_OPEN", stage_code="IN_DELIVERY")
    conn.commit()

    plan = build_lifecycle_repair_plan(conn, as_of="2026-05-03", run_id="test-run")

    assert plan.summary["candidate_count"] == 3
    assert plan.summary["repairable_count"] == 2
    assert plan.summary["blocked_count"] == 1
    assert {row["new_status"] for row in plan.repair_rows} == {"CANCELLED", "RETURNED"}


def test_lifecycle_repair_apply_updates_status_and_return_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_sale(conn, order_id="O_RETURN", stage_code="RETURNED")
    conn.commit()
    conn.close()

    result = repair_sales_fact_v2_lifecycle_residual(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="test-run",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status, return_flag, return_date FROM sales_fact_v2 WHERE order_id='O_RETURN'"
    ).fetchone()
    assert result["summary"]["applied_count"] == 1
    assert row == ("RETURNED", 1, "2026-04-16")


def test_lifecycle_repair_ledgers_store_conflicts_without_synthesizing_completion(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_sale(conn, order_id="O_CONFLICT", store_code="ACMEWEAR", stage_code="CANCELLED")
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, raw_status,
            source_row_hash, idempotency_key
        ) VALUES ('STOREB', 'O_CONFLICT', 'COMPLETED', '2026-04-16T11:00:00+05:00',
                  'LOCAL_FACT_ORDERS_KASPI', 'COMPLETED', 'hash-other', 'ose-other')
        """
    )
    conn.commit()

    plan = build_lifecycle_repair_plan(conn, as_of="2026-05-03", run_id="test-run")

    assert plan.summary["store_conflict_count"] == 1
    assert plan.conflict_rows[0]["same_store_stage_code"] == "CANCELLED"
    assert plan.conflict_rows[0]["other_store_completed_stage_count"] == 1
