from pathlib import Path

from scripts import generate_bank_accounts_history_totals as history_totals
from scripts import generate_bank_snapshot


def _parse_markdown_table(content: str) -> tuple[list[str], list[dict[str, str]]]:
    table_lines = [line.strip() for line in content.splitlines() if line.startswith("|")]
    headers = [part.strip() for part in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        values = [part.strip() for part in line.strip("|").split("|")]
        rows.append(dict(zip(headers, values)))
    return headers, rows


def _write_history(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "entries:",
                '  - as_of: "2026-02-04 10:00:00 GMT+5"',
                '    source: "manual snapshot"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: kaspi_gold",
                "        amount: 900",
                "        currency: KZT",
                "      - store: UNIVERSAL",
                "        account: binance_usdt",
                "        amount: 800",
                "        currency: USDT",
                '  - as_of: "2026-02-05 18:19:13 GMT+5"',
                '    source: "manual snapshot"',
                "    balances:",
                "      - store: UNIVERSAL",
                "        account: kaspi_gold",
                "        amount: 1000",
                "        currency: KZT",
                "      - store: UNIVERSAL",
                "        account: kaspi_pay",
                "        amount: 200",
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


def test_generate_history_totals_newest_first_with_sparse_composition(tmp_path):
    history = tmp_path / "bank_accounts_history.yaml"
    _write_history(history)
    entries = generate_bank_snapshot.load_history(history)
    fx_rates = {
        "USDT_KZT": (500.0, "binance_p2p", "2026-02-06"),
        "USD_KZT": (514.0, "dim_fx_rates", "2026-02-06"),
        "RUB_KZT": (6.6, "default", "hardcoded"),
        "CNY_KZT": (75.0, "dim_fx_rates", "2026-02-06"),
    }

    content = history_totals.generate_history_totals_markdown(entries, fx_rates, str(history))
    headers, rows = _parse_markdown_table(content)

    assert headers[:7] == [
        "as_of",
        "source",
        "TOTAL_KZT",
        "TOTAL_USD",
        "TOTAL_RUB",
        "TOTAL_USDT",
        "TOTAL_KZT_EQ",
    ]
    assert rows[0]["as_of"] == "2026-02-06 16:59:03 GMT+5"
    assert rows[1]["as_of"] == "2026-02-05 18:19:13 GMT+5"

    # Default mode is compact store/currency rollups.
    assert "UNIVERSAL_KZT" in headers
    assert "UNIVERSAL_USDT" in headers
    assert "11KZ_KZT" in headers

    # TOTAL columns are across stores for each snapshot row.
    assert rows[0]["TOTAL_KZT"] == "4,200"
    assert rows[0]["TOTAL_USDT"] == "160.362615"
    assert rows[0]["UNIVERSAL_KZT"] == "1,200"
    assert rows[0]["11KZ_KZT"] == "3,000"
    assert rows[0]["UNIVERSAL_USDT"] == "160.362615"


def test_generate_history_totals_column_order_is_deterministic(tmp_path):
    history = tmp_path / "bank_accounts_history.yaml"
    _write_history(history)
    entries = generate_bank_snapshot.load_history(history)
    fx_rates = {
        "USDT_KZT": (500.0, "binance_p2p", "2026-02-06"),
        "USD_KZT": (514.0, "dim_fx_rates", "2026-02-06"),
        "RUB_KZT": (6.6, "default", "hardcoded"),
        "CNY_KZT": (75.0, "dim_fx_rates", "2026-02-06"),
    }

    content = history_totals.generate_history_totals_markdown(entries, fx_rates, str(history), mode="detail")
    headers, _rows = _parse_markdown_table(content)

    assert headers.index("UNIVERSAL/kaspi_gold/KZT") < headers.index("UNIVERSAL/kaspi_pay/KZT")
    assert headers.index("UNIVERSAL/kaspi_pay/KZT") < headers.index("UNIVERSAL/binance_usdt/USDT")
    assert headers.index("UNIVERSAL/binance_usdt/USDT") < headers.index("11KZ/kaspi_gold/KZT")
