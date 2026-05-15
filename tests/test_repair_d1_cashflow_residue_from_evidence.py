from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from scripts.repair_d1_cashflow_residue_from_evidence import repair_d1_residue_from_evidence


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE order_status_event (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            order_id TEXT,
            stage_code TEXT,
            event_ts TEXT,
            source TEXT,
            idempotency_key TEXT
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            total_price_kzt REAL,
            raw_json TEXT,
            delivery_cost_kzt REAL
        );
        CREATE TABLE fact_cashflow_events (
            event_date TEXT,
            event_type TEXT,
            account TEXT,
            amount_kzt REAL,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            ref_type TEXT,
            ref_id TEXT,
            source TEXT,
            event_hash TEXT
        );
        """
    )
    return conn


def _write_source(path: Path) -> None:
    rows = [
        {
            "line_id": "line-a",
            "order_id": "O_REPAIR",
            "sale_date": "2026-02-18",
            "store_code": "STOREB",
            "kd_warehouse": "PP1",
            "status_internal": "DELIVERED",
            "return_flag": "0",
            "quantity": "1",
            "gross_rev_kzt": "14980",
            "net_delivery_fee_kzt": "1507",
            "net_rev_kzt": "11846.12",
            "sku_key": "SKU_REPAIR",
            "sku_id": "SKU_REPAIR_XL",
            "my_size": "XL",
            "offer_name": "Repair fixture",
            "article": "ARTICLE-1",
            "date_source": "status_change_date",
            "sku_source": "mapped",
            "size_source": "mapped",
        }
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_repair_d1_residue_inserts_only_source_backed_missing_line_rows(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.db"
    source_path = tmp_path / "ocean_drop_reference_snapshot_delivered.csv"
    output_root = tmp_path / "repair_out"
    _write_source(source_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('STOREB', 'O_REPAIR', 'COMPLETED', '2026-02-18T10:00:00+05:00',
                  'fixture', 'ose-repair')
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_BLOCKED', 'COMPLETED', '2026-02-18T10:00:00+05:00',
                  'fixture', 'ose-blocked')
        """
    )
    conn.commit()
    conn.close()

    dry_run = repair_d1_residue_from_evidence(
        db_path=db_path,
        source_csv=source_path,
        as_of="2026-05-03",
        output_root=output_root,
        apply=False,
    )
    assert dry_run["would_insert_entry_rows"] == 1
    assert dry_run["still_blocked_source_missing_count"] == 1

    monkeypatch.setenv("ENABLE_D1_RESIDUE_REPAIR_WRITE", "1")
    applied = repair_d1_residue_from_evidence(
        db_path=db_path,
        source_csv=source_path,
        as_of="2026-05-03",
        output_root=output_root,
        apply=True,
    )
    assert applied["inserted_entry_rows"] == 1

    second = repair_d1_residue_from_evidence(
        db_path=db_path,
        source_csv=source_path,
        as_of="2026-05-03",
        output_root=output_root,
        apply=True,
    )
    assert second["inserted_entry_rows"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT order_id, store_code, offer_id, quantity, unit_price_kzt,
                   total_price_kzt, delivery_cost_kzt
            FROM fact_order_entries_kaspi
            """
        ).fetchone()
        assert row == ("O_REPAIR", "STOREB", "ARTICLE-1", 1.0, 14980.0, 14980.0, 1507.0)
    finally:
        conn.close()
