from pathlib import Path

from scripts import generate_bank_snapshot
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


def test_effective_latest_entry_preserves_full_snapshot_with_auto_usdt_override(tmp_path):
    history = tmp_path / "bank_accounts_history.yaml"
    history.write_text(
        "\n".join(
            [
                "entries:",
                '  - as_of: "2026-02-05 18:19:13 GMT+5"',
                '    source: "manual snapshot"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: kaspi_gold",
                "        amount: 1589573",
                "        currency: KZT",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 948.19",
                "        currency: USDT",
                "      - store: 11KZ",
                "        account: kaspi_pay",
                "        amount: 0",
                "        currency: KZT",
                '  - as_of: "2026-02-06 16:59:03 GMT+5"',
                '    source: "binance api autosync"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 160.362615",
                "        currency: USDT",
            ]
        ),
        encoding="utf-8",
    )

    entries = generate_bank_snapshot.load_history(history)
    effective = generate_bank_snapshot.get_effective_latest_entry(entries)

    assert effective["as_of"] == "2026-02-06 16:59:03 GMT+5"
    balances = effective["balances"]
    by_key = {
        (row["store"], row["account"], row["currency"]): row["amount"]
        for row in balances
    }
    assert by_key[("UNIVERSAL", "kaspi_gold", "KZT")] == 1589573
    assert float(by_key[("UNIVERSAL", "binance_usdt", "USDT")]) == 160.362615
    assert by_key[("11KZ", "kaspi_pay", "KZT")] == 0


def test_generate_snapshot_from_effective_entry_contains_all_stores(tmp_path):
    history = tmp_path / "bank_accounts_history.yaml"
    history.write_text(
        "\n".join(
            [
                "entries:",
                '  - as_of: "2026-02-05 18:19:13 GMT+5"',
                '    source: "manual snapshot"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: kaspi_gold",
                "        amount: 1000",
                "        currency: KZT",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 900",
                "        currency: USDT",
                "      - store: 11KZ",
                "        account: kaspi_gold",
                "        amount: 3000",
                "        currency: KZT",
                '  - as_of: "2026-02-06 16:59:03 GMT+5"',
                '    source: "binance api autosync"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 160.362615",
                "        currency: USDT",
            ]
        ),
        encoding="utf-8",
    )

    entries = generate_bank_snapshot.load_history(history)
    effective = generate_bank_snapshot.get_effective_latest_entry(entries)
    fx_rates = {
        "USDT_KZT": (502.0, "binance_p2p", "2026-02-06"),
        "USD_KZT": (514.0, "dim_fx_rates", "2026-02-06"),
        "RUB_KZT": (6.6, "default", "hardcoded"),
        "CNY_KZT": (75.0, "dim_fx_rates", "2026-02-06"),
    }
    content = generate_bank_snapshot.generate_snapshot(effective, fx_rates)

    assert '  "11KZ":' in content
    assert "      kaspi_gold:" in content
    assert "        balance_kzt: 3000" in content
    assert "      binance_usdt:" in content
    assert "        balance_usdt: 160.362615" in content
