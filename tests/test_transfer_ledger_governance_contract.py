from __future__ import annotations

import sqlite3
from pathlib import Path
import sys

import scripts.generate_transfer_ledger_reports as transfer_reports


def test_transfer_ledger_governance_doc_contract() -> None:
    path = Path("docs/transfer_ledger/GOVERNANCE.md")
    assert path.exists(), "missing docs/transfer_ledger/GOVERNANCE.md"

    text = path.read_text(encoding="utf-8")
    assert "script-generated only" in text
    assert "no manual edits" in text
    assert "scripts/generate_transfer_ledger_reports.py" in text


def _create_minimal_transfer_ledger_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE binance_c2c_orders (
            order_number TEXT,
            create_time TEXT,
            fiat_amount REAL,
            crypto_amount REAL,
            unit_price REAL,
            counterparty TEXT,
            account_label TEXT,
            trade_type TEXT,
            asset TEXT,
            fiat TEXT,
            order_status TEXT
        );
        CREATE TABLE exchanger_orders (
            exchanger_order_id TEXT,
            exchanger TEXT,
            order_id TEXT,
            status TEXT,
            message_date TEXT,
            amount_usdt REAL,
            amount_cny REAL,
            deposit_address TEXT
        );
        CREATE TABLE binance_withdrawals (
            withdraw_id TEXT,
            amount REAL,
            transaction_fee REAL,
            address TEXT,
            apply_time TEXT,
            exchanger_order_id TEXT,
            account_label TEXT
        );
        CREATE TABLE binance_deposits (
            tx_id TEXT,
            insert_time TEXT,
            amount REAL,
            asset TEXT,
            status INTEGER,
            account_label TEXT
        );
        CREATE TABLE binance_transfers (
            tran_id TEXT,
            timestamp TEXT,
            asset TEXT,
            amount REAL,
            transfer_type TEXT,
            account_label TEXT
        );
        CREATE TABLE binance_funding_balances (
            snapshot_time TEXT,
            asset TEXT,
            total REAL,
            free REAL,
            account_label TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_transfer_ledger_generation_is_deterministic_for_same_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    _create_minimal_transfer_ledger_db(db_path)

    monkeypatch.setattr(transfer_reports, "list_deposits", lambda **_kwargs: [])
    monkeypatch.setattr(transfer_reports, "list_transfers", lambda **_kwargs: [])
    monkeypatch.setattr(transfer_reports, "list_funding_balance_snapshots", lambda **_kwargs: [])
    monkeypatch.setattr(transfer_reports, "list_pos_for_allocation", lambda **_kwargs: [])
    monkeypatch.setattr(transfer_reports, "get_po_total_cny_from_lines", lambda **_kwargs: None)
    monkeypatch.setattr(transfer_reports, "list_po_funding_plan", lambda **_kwargs: [])
    monkeypatch.setattr(transfer_reports, "list_po_exchanger_allocations", lambda **_kwargs: [])
    monkeypatch.setattr(transfer_reports, "_get_current_usdt_balance", lambda: None)

    argv = [
        "generate_transfer_ledger_reports.py",
        "--db",
        str(db_path),
        "--output-dir",
        str(out_dir),
        "--days",
        "0",
        "--current-usdt",
        "1000",
    ]

    old_argv = sys.argv
    try:
        sys.argv = argv
        rc1 = transfer_reports.main()
        assert rc1 == 0
        first = (out_dir / "TRANSFER_LEDGER_FULL_HISTORY.md").read_text(encoding="utf-8")

        sys.argv = argv
        rc2 = transfer_reports.main()
        assert rc2 == 0
        second = (out_dir / "TRANSFER_LEDGER_FULL_HISTORY.md").read_text(encoding="utf-8")
    finally:
        sys.argv = old_argv

    assert first == second
