from core.transfer_ledger.exchanger_email_import import parse_exchanger_email


def test_parse_btcchange24_email():
    msg = {
        "subject": "BTCChange24 - New exchange #163665 [Tether TRC20 -> WeChat]",
        "from": "no-reply@btcchange24.com",
        "date": "2026-01-07T15:00:00+05:00",
        "body_text": (
            "Exchange amount: 779.41 USDT\n"
            "Rate: 1 USDT : 6.861500 CNY\n"
            "You get: 5313 CNY\n"
            "Deposit to wallet: TDUa2o74G3uN4SpHY2EML79aqfNujoP3Rg\n"
            "WeChat account: w18672678719\n"
        ),
        "body_html": "",
        "message_id": "<abc@btcchange24.com>",
    }

    order = parse_exchanger_email(msg)
    assert order is not None
    assert order["exchanger"] == "BTCChange24"
    assert order["order_id"] == "163665"
    assert order["status"] == "NEW"
    assert order["direction"] == "Tether TRC20 -> WeChat"
    assert order["amount_usdt"] == 779.41
    assert order["amount_cny"] == 5313.0
    assert abs(order["rate_usdt_cny"] - (5313.0 / 779.41)) < 1e-6
    assert order["deposit_address"].startswith("TDUa2o")


def test_parse_uachanger_email():
    msg = {
        "subject": "Order for exchange 1985118",
        "from": "uachanger2020@gmail.com",
        "date": "2026-01-07T18:52:00+05:00",
        "body_text": (
            "Exchange direction: Tether TRC20 -> WeChat\n"
            "Amount: 733.08387 Tether TRC20 -> 5000 WeChat\n"
            "Payment details: TVyWstV5RpadRd85Bfpn4Q1WBLb1a3PW1J\n"
        ),
        "body_html": "",
        "message_id": "<xyz@uachanger.com>",
    }

    order = parse_exchanger_email(msg)
    assert order is not None
    assert order["exchanger"] == "UAChanger"
    assert order["order_id"] == "1985118"
    assert order["status"] == "NEW"
    assert order["deposit_address"].startswith("TVyWst")
    assert abs(order["rate_usdt_cny"] - (5000.0 / 733.08387)) < 1e-6
