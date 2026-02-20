from datetime import date
from pathlib import Path
import sys

from core.transfer_ledger import repository
from core.transfer_ledger.models import LedgerEntry


def _seed_src_db(src_path: Path) -> None:
    repository.ensure_schema(src_path)
    order = {
        "order_number": "p2p-1",
        "adv_no": "adv-1",
        "trade_type": "BUY",
        "asset": "USDT",
        "fiat": "KZT",
        "fiat_amount": 100000.0,
        "crypto_amount": 200.0,
        "unit_price": 500.0,
        "order_status": "COMPLETED",
        "create_time": "2026-01-10T10:00:00+05:00",
        "commission": None,
        "counterparty": "TestUser",
        "advertisement_role": "maker",
        "raw_json": "{}",
        "source": "BINANCE_P2P",
    }
    repository.upsert_binance_c2c_order(order, db_path=src_path)

    entry = LedgerEntry(
        entry_id=None,
        entry_date=date(2026, 1, 10),
        amount=200.0,
        currency="USDT",
        amount_kzt=100000.0,
        fx_rate_to_kzt=500.0,
        fx_source="BINANCE_P2P",
        reference_type="BINANCE_P2P",
        reference_id="p2p-1",
        from_account="external",
        to_account="binance_funding",
        notes="counterparty=TestUser",
    )
    repository.insert_entry(entry, db_path=src_path)


def test_import_binance_p2p_from_db_idempotent(tmp_path, monkeypatch):
    src_path = tmp_path / "src.db"
    dest_path = tmp_path / "dest.db"
    src_path.touch()
    dest_path.touch()
    _seed_src_db(src_path)
    repository.ensure_schema(dest_path)

    from scripts import import_binance_p2p_from_db

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_binance_p2p_from_db.py",
            "--src-db",
            str(src_path),
            "--dest-db",
            str(dest_path),
            "--apply",
        ],
    )
    assert import_binance_p2p_from_db.main() == 0

    # Re-run should not duplicate
    assert import_binance_p2p_from_db.main() == 0

    import sqlite3

    with sqlite3.connect(str(dest_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM binance_c2c_orders").fetchone()
        assert row[0] == 1
    entries = repository.list_entries(reference_type="BINANCE_P2P", db_path=dest_path)
    assert len(entries) == 1
