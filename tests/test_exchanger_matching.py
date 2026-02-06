from datetime import datetime, timezone

from core.transfer_ledger import repository
from core.transfer_ledger.exchanger_matching import (
    label_withdrawals_for_order,
    repair_withdrawal_labels,
)


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


def test_label_withdrawals_skips_order_without_address(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    order = {
        "exchanger_order_id": "BTCCHANGE24:163323",
        "exchanger": "BTCChange24",
        "order_id": "163323",
        "status": "NEW",
        "amount_usdt": 734.91,
        "deposit_address": None,
        "message_date": "2026-01-07T20:00:00+05:00",
        "subject": "BTCChange24 - New exchange #163323",
        "raw_json": "{}",
    }
    repository.upsert_exchanger_order(order, db_path=db_path)

    for idx, amount in enumerate([734.91, 735.03], start=1):
        repository.upsert_binance_withdrawal(
            {
                "withdraw_id": f"wd-{idx}",
                "tx_id": f"tx-{idx}",
                "coin": "USDT",
                "network": "TRX",
                "amount": amount,
                "transaction_fee": 1.0,
                "address": f"T{idx}23456789012345678901234567890123",
                "address_tag": None,
                "apply_time": datetime(2026, 1, 7, 21, idx, tzinfo=timezone.utc).isoformat(),
                "success_time": None,
                "status": "6",
                "wallet_type": "0",
                "counterparty_label": None,
                "exchanger_order_id": None,
                "raw_json": "{}",
            },
            db_path=db_path,
        )

    labeled = label_withdrawals_for_order(order, db_path=db_path)
    assert labeled == 0
    rows = repository.list_withdrawals(db_path=db_path, only_unlabeled=False)
    assert all(not r["exchanger_order_id"] for r in rows)


def test_repair_withdrawal_labels_clears_mismatch_and_duplicate(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()

    order_a = {
        "exchanger_order_id": "BTCCHANGE24:100001",
        "exchanger": "BTCChange24",
        "order_id": "100001",
        "status": "NEW",
        "amount_usdt": 500.0,
        "deposit_address": "TAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "message_date": "2026-01-08T10:00:00+05:00",
        "subject": "BTCChange24 - New exchange #100001",
        "raw_json": "{}",
    }
    order_b = {
        "exchanger_order_id": "BTCCHANGE24:100002",
        "exchanger": "BTCChange24",
        "order_id": "100002",
        "status": "NEW",
        "amount_usdt": 500.0,
        "deposit_address": "TBbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "message_date": "2026-01-08T10:05:00+05:00",
        "subject": "BTCChange24 - New exchange #100002",
        "raw_json": "{}",
    }
    repository.upsert_exchanger_order(order_a, db_path=db_path)
    repository.upsert_exchanger_order(order_b, db_path=db_path)

    repository.upsert_binance_withdrawal(
        {
            "withdraw_id": "wd-good-a",
            "tx_id": "tx-good-a",
            "coin": "USDT",
            "network": "TRX",
            "amount": 500.0,
            "transaction_fee": 1.0,
            "address": order_a["deposit_address"],
            "apply_time": datetime(2026, 1, 8, 10, 10, tzinfo=timezone.utc).isoformat(),
            "status": "6",
            "wallet_type": "0",
            "counterparty_label": "BTCChange24",
            "exchanger_order_id": order_a["exchanger_order_id"],
            "raw_json": "{}",
        },
        db_path=db_path,
    )
    repository.upsert_binance_withdrawal(
        {
            "withdraw_id": "wd-bad-dup",
            "tx_id": "tx-bad-dup",
            "coin": "USDT",
            "network": "TRX",
            "amount": 500.0,
            "transaction_fee": 1.0,
            "address": order_b["deposit_address"],
            "apply_time": datetime(2026, 1, 8, 10, 11, tzinfo=timezone.utc).isoformat(),
            "status": "6",
            "wallet_type": "0",
            "counterparty_label": "BTCChange24",
            "exchanger_order_id": order_a["exchanger_order_id"],
            "raw_json": "{}",
        },
        db_path=db_path,
    )

    result = repair_withdrawal_labels(db_path=db_path)
    assert result["cleared"] == 1

    rows = {r["withdraw_id"]: r for r in repository.list_withdrawals(db_path=db_path, only_unlabeled=False)}
    assert rows["wd-good-a"]["exchanger_order_id"] == order_a["exchanger_order_id"]
    assert not rows["wd-bad-dup"]["exchanger_order_id"]

    relabeled = label_withdrawals_for_order(order_b, db_path=db_path)
    assert relabeled == 1
    rows = {r["withdraw_id"]: r for r in repository.list_withdrawals(db_path=db_path, only_unlabeled=False)}
    assert rows["wd-bad-dup"]["exchanger_order_id"] == order_b["exchanger_order_id"]
