from datetime import datetime, timezone

from core.transfer_ledger import repository
from core.transfer_ledger.binance_deposit_import import normalize_binance_deposit, import_binance_deposits
from core.transfer_ledger.binance_transfer_import import normalize_binance_transfer, import_binance_transfers


def test_binance_deposit_import(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    raw = {
        "id": "dep-123",
        "coin": "USDT",
        "amount": "100.5",
        "insertTime": int(datetime(2026, 1, 5, tzinfo=timezone.utc).timestamp() * 1000),
        "status": 1,
    }

    deposit = normalize_binance_deposit(raw)
    assert deposit["deposit_id"] == "dep-123"
    assert deposit["amount"] == 100.5

    result = import_binance_deposits([raw], db_path=db_path)
    assert result["inserted"] == 1
    assert result["errors"] == []

    rows = repository.list_deposits(db_path=db_path)
    assert len(rows) == 1


def test_binance_transfer_import(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    raw = {
        "tranId": "tr-456",
        "asset": "USDT",
        "amount": "25",
        "type": "MAIN_FUNDING",
        "timestamp": int(datetime(2026, 1, 6, tzinfo=timezone.utc).timestamp() * 1000),
        "status": "SUCCESS",
    }

    transfer = normalize_binance_transfer(raw)
    assert transfer["transfer_id"] == "tr-456"
    assert transfer["amount"] == 25.0

    result = import_binance_transfers([raw], db_path=db_path)
    assert result["inserted"] == 1
    assert result["errors"] == []

    rows = repository.list_transfers(db_path=db_path)
    assert len(rows) == 1
