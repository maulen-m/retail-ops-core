import hashlib
import sqlite3
from pathlib import Path

import pytest

import scripts.repair_d1_cash_in_from_validator_evidence as d1_repair
from scripts.repair_d1_cash_in_from_validator_evidence import (
    D1CashInRepairError,
    repair_d1_cash_in_from_validator_evidence,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_db(db_path: Path, *, entry_id: str = "RECOV-CURRENT_CRM-test") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
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
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT,
                order_id TEXT,
                store_code TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                raw_json TEXT,
                delivery_cost_kzt REAL
            );
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_article TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT
            );
            CREATE TABLE dim_sku (
                sku_key TEXT,
                weight_kg REAL,
                cogs_kzt REAL,
                base_cost_cny REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO order_status_event (store_code, order_id, stage_code, event_ts, source, idempotency_key)
            VALUES ('UNIVERSAL', 'ORDER1', 'COMPLETED', '2026-05-06T10:00:00+05:00', 'test', 'ose1')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt, delivery_cost_kzt
            ) VALUES (?, 'ORDER1', 'UNIVERSAL', 'ART1', 1, 8150, 8150, 0)
            """,
            (entry_id,),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id)
            VALUES ('UNIVERSAL', 'ART1', '', 'SKU1', 'SKU1_XL')
            """
        )
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES ('SKU1', 0, 1000, 0)"
        )
        conn.commit()
    finally:
        conn.close()


def test_repair_inserts_only_recovered_entry_cash_in(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_db(db_path)
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="test-repair",
        apply=True,
        expected_missing_count=1,
    )

    assert summary["status"] == "PASS"
    assert summary["apply"]["inserted_event_rows"] == 1
    assert summary["coverage_before"]["cash_in_missing_count"] == 1
    assert summary["coverage_after"]["cash_in_missing_count"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT event_type, ref_type, ref_id, source, run_id
            FROM fact_cashflow_events
            """
        ).fetchone()
    finally:
        conn.close()
    assert row == ("CASH_IN", "ORDER_ENTRY", "RECOV-CURRENT_CRM-test", "ORDER_MODELLED", "test-repair")


def test_repair_refuses_non_recovered_entry_candidate(tmp_path):
    db_path = tmp_path / "cashflow.db"
    _init_db(db_path, entry_id="API-ENTRY-1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="dry-run",
        apply=False,
    )

    assert summary["status"] == "FAIL"
    assert summary["blocked_candidate_count"] == 1
    assert summary["allowed_recovered_entry_count"] == 0
    assert summary["allowed_fact_order_entry_count"] == 0


def test_repair_allows_fact_order_entry_candidate_only_with_explicit_flag(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_db(db_path, entry_id="API-ENTRY-1")
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="api-entry-repair",
        apply=True,
        expected_missing_count=1,
        allow_fact_order_entries=True,
    )

    assert summary["status"] == "PASS"
    assert summary["allowed_recovered_entry_count"] == 0
    assert summary["allowed_fact_order_entry_count"] == 1
    assert summary["blocked_candidate_count"] == 0
    assert summary["apply"]["inserted_event_rows"] == 1
    assert summary["coverage_after"]["cash_in_missing_count"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT event_type, ref_type, ref_id, source, run_id
            FROM fact_cashflow_events
            """
        ).fetchone()
    finally:
        conn.close()
    assert row == ("CASH_IN", "ORDER_ENTRY", "API-ENTRY-1", "ORDER_MODELLED", "api-entry-repair")


def test_repair_allows_fact_order_entry_cash_in_even_when_sku_identity_is_blank(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_db(db_path, entry_id="API-BLANK-SKU")
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DELETE FROM dim_kaspi_article_map")
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "blank_sku_evidence",
        run_id="api-blank-sku-repair",
        apply=True,
        expected_missing_count=1,
        allow_fact_order_entries=True,
    )

    assert summary["status"] == "PASS"
    assert summary["allowed_fact_order_entry_count"] == 1
    assert summary["blocked_candidate_count"] == 0
    assert summary["coverage_after"]["cash_in_missing_count"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT ref_id, sku_key, sku_id
            FROM fact_cashflow_events
            """
        ).fetchone()
    finally:
        conn.close()
    assert row == ("API-BLANK-SKU", "", "")


def test_production_apply_requires_prod_gate_sha_and_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    monkeypatch.setattr(d1_repair, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")
    monkeypatch.delenv("ENABLE_D1_CASH_IN_REPAIR_PROD_WRITE", raising=False)

    with pytest.raises(D1CashInRepairError, match="ENABLE_D1_CASH_IN_REPAIR_PROD_WRITE=1"):
        repair_d1_cash_in_from_validator_evidence(
            db_path=db_path,
            as_of="2026-05-06",
            output_root=tmp_path / "blocked",
            apply=True,
            expected_missing_count=1,
            expected_pre_sha256=_sha256(db_path),
            backup_dir=tmp_path / "backups",
        )


def test_production_apply_creates_verified_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(d1_repair, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_PROD_WRITE", "1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="prod-ok",
        apply=True,
        expected_missing_count=1,
        expected_pre_sha256=_sha256(db_path),
        backup_dir=backup_dir,
    )

    backups = list(backup_dir.glob("app_*.db"))
    assert len(backups) == 1
    assert summary["apply"]["production_apply"] is True
    assert summary["apply"]["backup_path"] == str(backups[0])
    assert summary["apply"]["post_integrity_check"] == "ok"
