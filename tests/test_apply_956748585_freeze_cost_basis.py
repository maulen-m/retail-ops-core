from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.apply_956748585_freeze_cost_basis import (
    ENV_GATE,
    FreezeCostBasisError,
    ORDER_ID,
    UNIT_COGS_KZT,
    _sha256_file,
    run_repair,
)


def _seed_db(db_path: Path, *, status: str = "SHIPPED", existing_event: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            internal_status TEXT,
            created_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,
            status_updated_at TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            sku_key TEXT,
            sku_id TEXT
        );
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_ts TEXT,
            event_type TEXT NOT NULL,
            account TEXT NOT NULL,
            amount_kzt REAL NOT NULL,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            ref_type TEXT,
            ref_id TEXT,
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'SYSTEM',
            run_id TEXT,
            event_hash TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
            created_at, planned_shipment_date, actual_shipment_date, status_updated_at,
            quantity, unit_price_kzt, sku_key, sku_id
        ) VALUES (
            ?, 'ACMEWEAR', 'KASPI_DELIVERY', 'ACCEPTED_BY_MERCHANT', ?,
            '2026-06-12 12:58:49', '2026-06-12', '2026-06-12 19:34:44', '2026-06-12 17:04:21',
            1, 8490.0, 'LINE-21-TS', 'LINE-21-TS_3XL'
        )
        """,
        (ORDER_ID, status),
    )
    if existing_event:
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key,
                sku_id, ref_type, ref_id, notes, source, run_id, event_hash
            ) VALUES (
                '2026-06-12', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST',
                1.0, 'ACMEWEAR', 'LINE-21-TS', 'LINE-21-TS_3XL',
                'ORDER', ?, 'existing', 'TEST', 'test', 'existing-hash'
            )
            """,
            (ORDER_ID,),
        )
    conn.commit()
    conn.close()


def _events(db_path: Path) -> list[tuple[str, float]]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT account, amount_kzt
        FROM fact_cashflow_events
        WHERE ref_id = ?
        ORDER BY account
        """,
        (ORDER_ID,),
    ).fetchall()
    conn.close()
    return [(str(row[0]), float(row[1])) for row in rows]


def test_dry_run_uses_simulation_db_and_does_not_mutate_source(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)

    report = run_repair(db_path=db, output_dir=tmp_path / "dry_run")

    assert report["status"] == "DRY_RUN"
    assert report["rows_inserted"] == 2
    assert report["post"]["freeze_errors"] == []
    assert report["db_sha256_changed"] is False
    assert _events(db) == []


def test_apply_requires_env_gate_and_backup_dir(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)

    with pytest.raises(FreezeCostBasisError, match=ENV_GATE):
        run_repair(db_path=db, output_dir=tmp_path / "missing_gate", backup_dir=tmp_path / "backups", apply=True)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(ENV_GATE, "1")
        with pytest.raises(FreezeCostBasisError, match="--backup-dir"):
            run_repair(db_path=db, output_dir=tmp_path / "missing_backup", apply=True)


def test_apply_enforces_pre_sha_and_inserts_exact_two_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    monkeypatch.setenv(ENV_GATE, "1")

    with pytest.raises(FreezeCostBasisError, match="pre-SHA mismatch"):
        run_repair(
            db_path=db,
            output_dir=tmp_path / "wrong_sha",
            backup_dir=tmp_path / "backups_wrong",
            expected_pre_sha256="0" * 64,
            apply=True,
        )

    report = run_repair(
        db_path=db,
        output_dir=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256_file(db),
        apply=True,
    )

    assert report["status"] == "APPLIED"
    assert Path(report["gate"]["backup_path"]).exists()
    assert report["post"]["freeze_errors"] == []
    assert _events(db) == [
        ("INVENTORY_ON_DELIVERY_COST", UNIT_COGS_KZT),
        ("INVENTORY_ON_HAND_COST", -UNIT_COGS_KZT),
    ]


def test_refuses_if_order_preconditions_drift(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, status="COMPLETED")

    with pytest.raises(FreezeCostBasisError, match="internal_status mismatch"):
        run_repair(db_path=db, output_dir=tmp_path / "bad_status")


def test_refuses_existing_inventory_events(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, existing_event=True)

    with pytest.raises(FreezeCostBasisError, match="already has target inventory events"):
        run_repair(db_path=db, output_dir=tmp_path / "existing")
