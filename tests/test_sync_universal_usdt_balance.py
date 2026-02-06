from pathlib import Path

from scripts import sync_universal_usdt_balance as syncer


def _write_history(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "entries:",
                '  - as_of: "2026-02-06 12:00:00 GMT+5"',
                '    source: "manual snapshot"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 100.0",
                "        currency: USDT",
            ]
        ),
        encoding="utf-8",
    )


def test_append_universal_usdt_snapshot(tmp_path):
    history = tmp_path / "bank_accounts_history.yaml"
    _write_history(history)

    changed = syncer.append_or_update_universal_usdt_history(
        history_path=history,
        balance_usdt=222.222,
        as_of="2026-02-07 10:11:12 GMT+5",
    )
    assert changed is True

    entries = syncer.load_history_entries(history)
    latest = entries[-1]
    assert latest["source"] == "binance api autosync"
    assert latest["balances"][0]["store"] == "UNIVERSAL"
    assert latest["balances"][0]["account"] == "binance_usdt"
    assert latest["balances"][0]["currency"] == "USDT"
    assert float(latest["balances"][0]["amount"]) == 222.222


def test_skip_when_latest_auto_balance_same(tmp_path):
    history = tmp_path / "bank_accounts_history.yaml"
    history.write_text(
        "\n".join(
            [
                "entries:",
                '  - as_of: "2026-02-07 10:11:12 GMT+5"',
                '    source: "binance api autosync"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 333.333",
                "        currency: USDT",
            ]
        ),
        encoding="utf-8",
    )

    changed = syncer.append_or_update_universal_usdt_history(
        history_path=history,
        balance_usdt=333.333,
        as_of="2026-02-07 11:00:00 GMT+5",
    )
    assert changed is False

    entries = syncer.load_history_entries(history)
    assert len(entries) == 1
