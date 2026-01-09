from datetime import date
import sqlite3

from core.transfer_ledger import repository, service
from core.transfer_ledger.models import LedgerEntry


def seed_po_header(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS po_header (
                po_id TEXT PRIMARY KEY,
                message_date TEXT,
                total_cost_cny REAL,
                total_cost_kzt_supplier REAL,
                fx_rate_cny_plan REAL,
                created_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO po_header (po_id, message_date, total_cost_kzt_supplier, fx_rate_cny_plan) VALUES (?,?,?,?)",
            ("PO-4", "2026-01-01", 30000.0, 78.0),
        )
        conn.execute(
            "INSERT OR REPLACE INTO po_header (po_id, message_date, total_cost_kzt_supplier, fx_rate_cny_plan) VALUES (?,?,?,?)",
            ("PO-5", "2026-01-10", 40000.0, 78.0),
        )
        conn.commit()
    finally:
        conn.close()


def test_auto_allocate_spills_to_next_po(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    seed_po_header(db_path)

    entry = LedgerEntry(
        entry_id=None,
        entry_date=date(2026, 1, 9),
        amount=-100.0,
        currency="USDT",
        amount_kzt=-50000.0,
        fx_rate_to_kzt=500.0,
        fx_source="MANUAL",
        reference_type="BINANCE_WITHDRAWAL",
        reference_id="wd-1",
        from_account="",
        to_account="",
        notes="",
    )

    entry_id = repository.insert_entry(entry, db_path=db_path)
    alloc_ids = service.auto_allocate_entry_to_active_po(entry_id, db_path=db_path)

    assert len(alloc_ids) == 2
    rows = repository.list_po_funding_allocations(db_path=db_path)
    # PO-4 should be fully funded (30,000 KZT) and remainder to PO-5 (20,000 KZT)
    po4 = [r for r in rows if r["po_id"] == "PO-4"][0]
    po5 = [r for r in rows if r["po_id"] == "PO-5"][0]
    assert po4["amount_kzt"] == 30000.0
    assert po5["amount_kzt"] == 20000.0
