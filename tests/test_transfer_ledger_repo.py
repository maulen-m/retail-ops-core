from datetime import date

from core.transfer_ledger import repository
from core.transfer_ledger.models import LedgerEntry


def test_insert_list_balance(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    entry = LedgerEntry(
        entry_id=None,
        entry_date=date(2026, 1, 1),
        amount=100.0,
        currency="USD",
        amount_kzt=50000.0,
        fx_rate_to_kzt=500.0,
        fx_source="MANUAL",
        reference_type="PO",
        reference_id="PO-1",
        from_account="",
        to_account="",
        notes="",
    )

    entry_id = repository.insert_entry(entry, db_path=db_path)
    assert entry_id > 0

    entries = repository.list_entries(db_path=db_path)
    assert len(entries) == 1
    assert entries[0].reference_id == "PO-1"

    balance_kzt = repository.get_balance(db_path=db_path)
    assert balance_kzt == 50000.0

    balance_usd = repository.get_balance(currency="USD", db_path=db_path)
    assert balance_usd == 100.0
