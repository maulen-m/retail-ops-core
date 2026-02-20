from datetime import datetime, timezone

from core.transfer_ledger.binance_import import normalize_binance_order, import_binance_orders
from core.transfer_ledger import repository


def test_binance_import_creates_ledger_entries(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    raw = {
        "orderNumber": "1234567890",
        "advNo": "ADV123",
        "tradeType": "BUY",
        "asset": "USDT",
        "fiat": "KZT",
        "amount": "100.0",
        "totalPrice": "50000",
        "unitPrice": "500",
        "orderStatus": "COMPLETED",
        "createTime": int(datetime(2026, 1, 9, tzinfo=timezone.utc).timestamp() * 1000),
        "counterPartNickName": "seller_one",
        "advertisementRole": "TAKER",
    }

    order = normalize_binance_order(raw)
    assert order["order_number"] == "1234567890"
    assert order["fiat_amount"] == 50000.0
    assert order["crypto_amount"] == 100.0

    result = import_binance_orders([raw], db_path=db_path, write_ledger=True)
    assert result["inserted"] == 1
    assert result["ledger_entries"] == 2

    entries = repository.list_entries(db_path=db_path)
    assert len(entries) == 2


def test_binance_import_idempotent_ledger(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    raw = {
        "orderNumber": "ABC123",
        "advNo": "ADV456",
        "tradeType": "BUY",
        "asset": "USDT",
        "fiat": "KZT",
        "amount": "50.0",
        "totalPrice": "25000",
        "unitPrice": "500",
        "orderStatus": "COMPLETED",
        "createTime": int(datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp() * 1000),
        "counterPartNickName": "seller_two",
        "advertisementRole": "MAKER",
    }

    first = import_binance_orders([raw], db_path=db_path, write_ledger=True)
    assert first["inserted"] == 1
    assert first["ledger_entries"] == 2

    second = import_binance_orders([raw], db_path=db_path, write_ledger=True)
    assert second["inserted"] == 0
    assert second["ledger_entries"] == 0
    assert len(repository.list_entries(db_path=db_path)) == 2


def test_binance_import_backfills_missing_ledger(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    raw = {
        "orderNumber": "XYZ987",
        "advNo": "ADV999",
        "tradeType": "SELL",
        "asset": "USDT",
        "fiat": "KZT",
        "amount": "20.0",
        "totalPrice": "10000",
        "unitPrice": "500",
        "orderStatus": "COMPLETED",
        "createTime": int(datetime(2026, 1, 11, tzinfo=timezone.utc).timestamp() * 1000),
        "counterPartNickName": "buyer_one",
        "advertisementRole": "TAKER",
    }

    result = import_binance_orders([raw], db_path=db_path, write_ledger=False)
    assert result["inserted"] == 1
    assert len(repository.list_entries(db_path=db_path)) == 0

    result = import_binance_orders([raw], db_path=db_path, write_ledger=True)
    assert result["ledger_entries"] == 2
    assert len(repository.list_entries(db_path=db_path)) == 2
