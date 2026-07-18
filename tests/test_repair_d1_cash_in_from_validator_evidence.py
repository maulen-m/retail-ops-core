import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.calc.economics import calc_delivery_fee, calc_net_rev
import scripts.repair_d1_cash_in_from_validator_evidence as d1_repair
from scripts.repair_d1_cash_in_from_validator_evidence import (
    D1CashInRepairError,
    repair_d1_cash_in_from_validator_evidence,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_db(
    db_path: Path,
    *,
    entry_id: str = "RECOV-CURRENT_CRM-test",
    seller_delivery_fee: float | None = 500.0,
    buyer_entry_delivery_fee: float | None = 0.0,
) -> None:
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
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                delivery_cost_for_seller REAL
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
            ) VALUES (?, 'ORDER1', 'UNIVERSAL', 'ART1', 1, 8150, 8150, ?)
            """,
            (entry_id, buyer_entry_delivery_fee),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (order_id, store_code, delivery_cost_for_seller)
            VALUES ('ORDER1', 'UNIVERSAL', ?)
            """,
            (seller_delivery_fee,),
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
            SELECT event_type, ref_type, ref_id, source, run_id, amount_kzt
            FROM fact_cashflow_events
            """
        ).fetchone()
    finally:
        conn.close()
    assert row[:5] == (
        "CASH_IN",
        "ORDER_ENTRY",
        "RECOV-CURRENT_CRM-test",
        "ORDER_MODELLED",
        "test-repair",
    )
    assert row[5] == round(
        calc_net_rev(8150, delivery_fee=500, weight_kg=0, as_of_date=date(2026, 5, 6)),
        2,
    )


def test_repair_accepts_source_stable_workbook_recovery_prefix(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_db(db_path, entry_id="RECOV-WORKBOOK-stable")
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="stable-workbook-recovery",
        apply=True,
        expected_missing_count=1,
    )

    assert summary["status"] == "PASS"
    assert summary["allowed_recovered_entry_count"] == 1
    assert summary["allowed_fact_order_entry_count"] == 0


def test_repair_preserves_missing_seller_fee_and_ignores_buyer_entry_delivery(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_db(
        db_path,
        seller_delivery_fee=None,
        buyer_entry_delivery_fee=999.0,
    )
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")

    repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="missing-seller-fee",
        apply=True,
        expected_missing_count=1,
    )

    with sqlite3.connect(str(db_path)) as conn:
        amount = conn.execute("SELECT amount_kzt FROM fact_cashflow_events").fetchone()[0]
    model_fee = calc_delivery_fee(8150, weight_kg=0, delivery_type="city")
    expected = round(
        calc_net_rev(8150, delivery_fee=model_fee, weight_kg=0, as_of_date=date(2026, 5, 6)),
        2,
    )
    buyer_fee_wrong = round(
        calc_net_rev(8150, delivery_fee=999, weight_kg=0, as_of_date=date(2026, 5, 6)),
        2,
    )
    assert amount == expected
    assert amount != buyer_fee_wrong


def test_partial_order_repair_allocates_seller_fee_across_all_order_entries(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "cashflow.db"
    _init_db(
        db_path,
        entry_id="RECOV-CURRENT_CRM-first",
        seller_delivery_fee=1500.0,
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity,
                unit_price_kzt, total_price_kzt, delivery_cost_kzt
            ) VALUES ('RECOV-CURRENT_CRM-second', 'ORDER1', 'UNIVERSAL',
                      'ART2', 1, 8150, 8150, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id
            ) VALUES ('UNIVERSAL', 'ART2', '', 'SKU1', 'SKU1_XL')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code,
                sku_key, sku_id, ref_type, ref_id, source, run_id, event_hash
            ) VALUES ('2026-05-06', 'CASH_IN', 'KASPI_PAY_UNIVERSAL', 1,
                      'UNIVERSAL', 'SKU1', 'SKU1_XL', 'ORDER_ENTRY',
                      'RECOV-CURRENT_CRM-first', 'ORDER_MODELLED', 'existing',
                      'existing-first')
            """
        )
        conn.commit()
    monkeypatch.setenv("ENABLE_D1_CASH_IN_REPAIR_WRITE", "1")

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=db_path,
        as_of="2026-05-06",
        output_root=tmp_path / "evidence",
        run_id="partial-order-fee-allocation",
        apply=True,
        expected_missing_count=1,
    )

    assert summary["apply"]["inserted_event_rows"] == 1
    with sqlite3.connect(str(db_path)) as conn:
        amount = conn.execute(
            "SELECT amount_kzt FROM fact_cashflow_events WHERE ref_id='RECOV-CURRENT_CRM-second'"
        ).fetchone()[0]
    expected = round(
        calc_net_rev(
            8150,
            delivery_fee=750,
            weight_kg=0,
            as_of_date=date(2026, 5, 6),
        ),
        2,
    )
    wrong_full_fee = round(
        calc_net_rev(
            8150,
            delivery_fee=1500,
            weight_kg=0,
            as_of_date=date(2026, 5, 6),
        ),
        2,
    )
    assert amount == expected
    assert amount != wrong_full_fee


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
