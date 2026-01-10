from datetime import date

from core.transfer_ledger import repository, service
from core.transfer_ledger.models import LedgerEntry


def test_allocate_po_funding(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    entry = LedgerEntry(
        entry_id=None,
        entry_date=date(2026, 1, 5),
        amount=-100.0,
        currency="USDT",
        amount_kzt=-50000.0,
        fx_rate_to_kzt=500.0,
        fx_source="MANUAL",
        reference_type="BINANCE_P2P",
        reference_id="order:USDT",
        from_account="",
        to_account="",
        notes="",
    )

    entry_id = repository.insert_entry(entry, db_path=db_path)
    alloc_id = service.allocate_po_funding(
        po_id="PO-2026-001",
        entry_id=entry_id,
        amount=50.0,
        currency="USDT",
        amount_kzt=25000.0,
        notes="partial allocation",
        db_path=db_path,
    )

    assert alloc_id > 0
    rows = repository.list_po_funding_allocations(po_id="PO-2026-001", db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["amount"] == 50.0
