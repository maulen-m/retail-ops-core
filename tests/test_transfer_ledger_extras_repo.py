from datetime import date

from core.transfer_ledger import repository


def test_upsert_deposit_and_transfer(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    deposit = {
        "deposit_id": "dep-1",
        "coin": "USDT",
        "amount": 50.0,
        "insert_time": "2026-01-02T10:00:00+05:00",
        "account_label": "main",
        "raw_json": "{}",
    }
    assert repository.upsert_binance_deposit(deposit, db_path=db_path) is True
    assert repository.upsert_binance_deposit(deposit, db_path=db_path) is False

    transfer = {
        "transfer_id": "tr-1",
        "asset": "USDT",
        "amount": 25.0,
        "transfer_type": "MAIN_FUNDING",
        "timestamp": "2026-01-03T10:00:00+05:00",
        "account_label": "main",
        "raw_json": "{}",
    }
    assert repository.upsert_binance_transfer(transfer, db_path=db_path) is True
    assert repository.upsert_binance_transfer(transfer, db_path=db_path) is False

    deposits = repository.list_deposits(db_path=db_path)
    transfers = repository.list_transfers(db_path=db_path)
    assert len(deposits) == 1
    assert len(transfers) == 1


def test_funding_balance_snapshot(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    snapshot = {
        "snapshot_time": "2026-01-04T12:00:00+05:00",
        "asset": "USDT",
        "free": 10.0,
        "locked": 2.0,
        "total": 12.0,
        "raw_json": "{}",
    }
    repository.insert_funding_balance_snapshot(snapshot, db_path=db_path)
    repository.insert_funding_balance_snapshot(snapshot, db_path=db_path)

    rows = repository.list_funding_balance_snapshots(db_path=db_path, asset="USDT", limit=5)
    assert len(rows) == 1


def test_po_funding_plan_and_exchanger_allocations(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    plan = {
        "po_id": "PO-1",
        "message_date": "2026-01-05",
        "total_cny": 1000.0,
        "total_usdt": 150.0,
        "source": "TEST",
    }
    assert repository.upsert_po_funding_plan(plan, db_path=db_path) is True
    assert repository.upsert_po_funding_plan(plan, db_path=db_path) is False

    plans = repository.list_po_funding_plan(db_path=db_path)
    assert len(plans) == 1

    alloc = {
        "po_id": "PO-1",
        "exchanger_order_id": "UA:123",
        "amount_usdt": 150.0,
        "amount_cny": 1000.0,
        "source": "TEST",
    }
    assert repository.upsert_po_exchanger_allocation(alloc, db_path=db_path) is True
    assert repository.upsert_po_exchanger_allocation(alloc, db_path=db_path) is False

    allocs = repository.list_po_exchanger_allocations(db_path=db_path, po_id="PO-1")
    assert len(allocs) == 1


def test_insert_exchanger_event(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    event = {
        "exchanger_order_id": "UA:1",
        "exchanger": "UAChanger",
        "order_id": "1",
        "status": "NEW",
        "message_id": "<msg-1>",
        "message_date": "2026-01-05T10:00:00+05:00",
        "subject": "Order 1",
        "raw_json": "{}",
        "source": "GMAIL",
    }
    assert repository.insert_exchanger_event(event, db_path=db_path) is True
    assert repository.insert_exchanger_event(event, db_path=db_path) is False
