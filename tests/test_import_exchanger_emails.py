import sys
from datetime import datetime, timezone

from core.transfer_ledger import repository


def test_import_exchanger_emails_labels_withdrawal(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()

    address = "T" + "A" * 33
    withdrawal = {
        "withdraw_id": "wd-email-1",
        "tx_id": "tx-1",
        "coin": "USDT",
        "network": "TRX",
        "amount": 100.0,
        "transaction_fee": 0.0,
        "address": address,
        "address_tag": None,
        "apply_time": datetime(2026, 1, 8, tzinfo=timezone.utc).isoformat(),
        "success_time": None,
        "status": "6",
        "wallet_type": None,
        "counterparty_label": "",
        "exchanger_order_id": "",
        "raw_json": "{}",
        "source": "BINANCE_WITHDRAW",
    }
    repository.upsert_binance_withdrawal(withdrawal, db_path=db_path)

    msg = {
        "subject": "Completed order #123456 UAChanger",
        "from": "UAChanger <noreply@uachanger.com>",
        "body_text": (
            "Order ID: 123456\n"
            "Direction: USDT -> WeChat\n"
            "1 USDT = 6.9 CNY\n"
            "You sent 100 USDT\n"
            f"Deposit address {address}\n"
            "WeChat account test_user"
        ),
        "body_html": "",
        "date": "2026-01-08T12:00:00+05:00",
        "message_id": "<msg-1>",
    }

    def fake_fetch_messages(**_kwargs):
        return [msg]

    monkeypatch.setenv("GMAIL_USER", "test@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")
    monkeypatch.setattr("scripts.import_exchanger_emails.fetch_messages", fake_fetch_messages)
    monkeypatch.setattr(sys, "argv", ["import_exchanger_emails.py", "--db", str(db_path), "--limit", "10"])

    from scripts import import_exchanger_emails

    assert import_exchanger_emails.main() == 0

    orders = repository.list_exchanger_orders(db_path=db_path, limit=10)
    assert len(orders) == 1
    withdrawals = repository.list_withdrawals(db_path=db_path)
    assert withdrawals[0]["counterparty_label"] == "UAChanger"
    assert withdrawals[0]["exchanger_order_id"] == orders[0]["exchanger_order_id"]
