from datetime import date

from core.transfer_ledger import repository, service


def test_service_posts(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    po_id = "PO-2026-001"

    entry_po = service.post_po_payment_cny(
        po_id=po_id,
        amount_cny=120.0,
        fx_rate_cny_kzt=80.0,
        paid_at=date(2026, 1, 2),
        source="MANUAL",
        db_path=db_path,
    )
    assert entry_po > 0

    entry_cargo = service.post_cargo_payment_usd(
        po_id=po_id,
        amount_usd=10.0,
        fx_rate_usd_kzt=500.0,
        paid_at=date(2026, 1, 3),
        source="MANUAL",
        db_path=db_path,
    )
    assert entry_cargo > 0

    entry_transfer = service.post_transfer(
        amount=1000.0,
        currency="KZT",
        fx_rate_to_kzt=1.0,
        from_account="wallet",
        to_account="bank",
        paid_at=date(2026, 1, 4),
        source="MANUAL",
        db_path=db_path,
    )
    assert entry_transfer > 0

    po_entries = repository.list_entries(reference_type="PO", db_path=db_path)
    assert po_entries[0].amount == 120.0
    assert po_entries[0].amount_kzt == 9600.0

    cargo_entries = repository.list_entries(reference_type="CARGO", db_path=db_path)
    assert cargo_entries[0].amount_kzt == 5000.0

    transfer_entries = repository.list_entries(reference_type="TRANSFER", db_path=db_path)
    assert transfer_entries[0].from_account == "wallet"
    assert transfer_entries[0].to_account == "bank"
