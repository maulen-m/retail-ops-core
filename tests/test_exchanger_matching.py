from datetime import datetime, timezone

from core.transfer_ledger import repository
from core.transfer_ledger.exchanger_matching import label_withdrawals_for_order


def test_label_withdrawals_for_order(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    order = {
        "exchanger_order_id": "BTCCHANGE24:163665",
        "exchanger": "BTCChange24",
        "order_id": "163665",
        "status": "NEW",
        "direction": "Tether TRC20 -> WeChat",
        "amount_usdt": 779.41,
        "amount_cny": 5313.0,
        "rate_usdt_cny": 6.8615,
        "deposit_address": "TDUa2o74G3uN4SpHY2EML79aqfNujoP3Rg",
        "receiver_account": "w18672678719",
        "message_id": "<abc@btcchange24.com>",
        "message_date": "2026-01-07T15:00:00+05:00",
        "subject": "BTCChange24 - New exchange #163665 [Tether TRC20 -> WeChat]",
        "raw_json": "{}",
    }
    repository.upsert_exchanger_order(order, db_path=db_path)

    withdrawal = {
        "withdraw_id": "wd-1",
        "tx_id": "tx-1",
        "coin": "USDT",
        "network": "TRX",
        "amount": 779.41,
        "transaction_fee": 1.0,
        "address": "TDUa2o74G3uN4SpHY2EML79aqfNujoP3Rg",
        "address_tag": None,
        "apply_time": datetime(2026, 1, 7, tzinfo=timezone.utc).isoformat(),
        "success_time": None,
        "status": "6",
        "wallet_type": "0",
        "counterparty_label": None,
        "exchanger_order_id": None,
        "raw_json": "{}",
    }
    repository.upsert_binance_withdrawal(withdrawal, db_path=db_path)

    labeled = label_withdrawals_for_order(order, db_path=db_path)
    assert labeled == 1

    rows = repository.list_withdrawals(db_path=db_path, only_unlabeled=False)
    assert rows[0]["counterparty_label"] == "BTCChange24"
    assert rows[0]["exchanger_order_id"] == "BTCCHANGE24:163665"
