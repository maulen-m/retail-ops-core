import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import scripts.rebuild_cashflow_calendar as cashflow_calendar
from scripts.rebuild_cashflow_calendar import rebuild_cashflow_calendar


DAILY_COLUMN_DEFS = {
    "date": "TEXT PRIMARY KEY",
    "cash_open": "REAL",
    "cash_close": "REAL",
    "receivables_open": "REAL",
    "receivables_close": "REAL",
    "inventory_cost_open": "REAL",
    "inventory_cost_close": "REAL",
    "capital_close": "REAL",
    "inventory_on_hand_open": "REAL",
    "inventory_on_hand_close": "REAL",
    "inventory_inbound_open": "REAL",
    "inventory_inbound_close": "REAL",
    "inventory_on_delivery_open": "REAL",
    "inventory_on_delivery_close": "REAL",
    "sales_accrued_kzt": "REAL",
    "payouts_received_kzt": "REAL",
    "refunds_kzt": "REAL",
    "po_payments_kzt": "REAL",
    "expenses_kzt": "REAL",
    "cogs_kzt": "REAL",
    "cash_flow_kzt": "REAL",
    "receivables_flow_kzt": "REAL",
    "inventory_cost_flow_kzt": "REAL",
    "profit_accrual_kzt": "REAL",
    "run_id": "TEXT",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _daily_columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(fact_cashflow_daily)")}
    finally:
        conn.close()


def _init_cashflow_db_missing_daily_column(db_path: Path, missing_column: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        daily_defs = [
            f"{name} {ddl}"
            for name, ddl in DAILY_COLUMN_DEFS.items()
            if name != missing_column
        ]
        conn.executescript(
            f"""
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
                notes TEXT,
                source TEXT,
                run_id TEXT,
                event_hash TEXT
            );

            CREATE TABLE fact_cashflow_daily (
                {", ".join(daily_defs)}
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_missing_daily_column_dry_run_fails_without_altering_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow_missing_column.db"
    missing_column = "inventory_on_delivery_close"
    _init_cashflow_db_missing_daily_column(db_path, missing_column)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    before_hash = _sha256(db_path)

    with pytest.raises(RuntimeError, match=missing_column):
        rebuild_cashflow_calendar(
            db_path=db_path,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            apply=False,
            run_id="dry-run",
        )

    assert _sha256(db_path) == before_hash
    assert missing_column not in _daily_columns(db_path)


def test_apply_without_env_gate_fails_before_schema_mutation(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow_missing_column.db"
    missing_column = "inventory_on_delivery_close"
    _init_cashflow_db_missing_daily_column(db_path, missing_column)
    monkeypatch.delenv("ENABLE_CASHFLOW_WRITE", raising=False)
    before_hash = _sha256(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_CASHFLOW_WRITE=1"):
        rebuild_cashflow_calendar(
            db_path=db_path,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            apply=True,
            run_id="blocked-apply",
        )

    assert _sha256(db_path) == before_hash
    assert missing_column not in _daily_columns(db_path)


def test_production_rebuild_requires_dedicated_prod_env(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    missing_column = "inventory_on_delivery_close"
    _init_cashflow_db_missing_daily_column(db_path, missing_column)
    monkeypatch.setattr(cashflow_calendar, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.delenv("ENABLE_CASHFLOW_PROD_WRITE", raising=False)
    before_hash = _sha256(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_CASHFLOW_PROD_WRITE=1"):
        rebuild_cashflow_calendar(
            db_path=db_path,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            apply=True,
            run_id="blocked-prod",
            expected_pre_sha256=before_hash,
            backup_dir=tmp_path / "backups",
        )

    assert _sha256(db_path) == before_hash
    assert missing_column not in _daily_columns(db_path)


def test_production_rebuild_requires_expected_sha_and_backup_dir(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    missing_column = "inventory_on_delivery_close"
    _init_cashflow_db_missing_daily_column(db_path, missing_column)
    monkeypatch.setattr(cashflow_calendar, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.setenv("ENABLE_CASHFLOW_PROD_WRITE", "1")
    before_hash = _sha256(db_path)

    with pytest.raises(RuntimeError, match="--expected-pre-sha256"):
        rebuild_cashflow_calendar(
            db_path=db_path,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            apply=True,
            run_id="missing-sha",
            backup_dir=tmp_path / "backups",
        )

    with pytest.raises(RuntimeError, match="--backup-dir"):
        rebuild_cashflow_calendar(
            db_path=db_path,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            apply=True,
            run_id="missing-backup",
            expected_pre_sha256=before_hash,
        )

    assert _sha256(db_path) == before_hash
    assert missing_column not in _daily_columns(db_path)


def test_production_rebuild_creates_verified_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    missing_column = "inventory_on_delivery_close"
    _init_cashflow_db_missing_daily_column(db_path, missing_column)
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(cashflow_calendar, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.setenv("ENABLE_CASHFLOW_PROD_WRITE", "1")

    rows, system_events = rebuild_cashflow_calendar(
        db_path=db_path,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        apply=True,
        run_id="prod-ok",
        expected_pre_sha256=_sha256(db_path),
        backup_dir=backup_dir,
    )

    metadata = rebuild_cashflow_calendar.last_apply_metadata
    backups = list(backup_dir.glob("app_*.db"))
    assert len(backups) == 1
    assert metadata["production_apply"] is True
    assert metadata["backup_path"] == str(backups[0])
    assert metadata["post_integrity_check"] == "ok"
    assert missing_column in _daily_columns(db_path)
    assert len(rows) == 1
    assert system_events == []


def test_env_gated_apply_can_backfill_existing_auto_migration_column(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow_missing_column.db"
    missing_column = "inventory_on_delivery_close"
    _init_cashflow_db_missing_daily_column(db_path, missing_column)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    rows, system_events = rebuild_cashflow_calendar(
        db_path=db_path,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        apply=True,
        run_id="allowed-apply",
    )

    assert missing_column in _daily_columns(db_path)
    assert len(rows) == 1
    assert system_events == []

    conn = sqlite3.connect(str(db_path))
    try:
        daily_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_daily WHERE date = ?",
            ("2026-01-01",),
        ).fetchone()[0]
    finally:
        conn.close()
    assert daily_count == 1
