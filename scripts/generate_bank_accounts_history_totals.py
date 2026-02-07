#!/usr/bin/env python3
"""Generate a bank accounts history totals ASCII table from history YAML.

Reads append-only bank account history, composes sparse autosync rows over the
latest full snapshot, and renders a newest-to-oldest markdown table with:
  - leading totals across stores
  - per-store/per-account/per-currency columns
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from scripts import generate_bank_snapshot

HISTORY_PATH = PROJECT_ROOT / "config" / "bank_accounts_history.yaml"
OUTPUT_PATH = PROJECT_ROOT / "config" / "bank_accounts_history_totals.md"

BASE_COLUMNS = [
    "as_of",
    "source",
    "TOTAL_KZT",
    "TOTAL_USD",
    "TOTAL_RUB",
    "TOTAL_USDT",
    "TOTAL_KZT_EQ",
]

STORE_ORDER = ["UNIVERSAL", "11KZ", "STOREB", "ACMEWEAR", "MELVIS"]
ACCOUNT_ORDER = [
    "kaspi_gold",
    "kaspi_pay",
    "bcc",
    "freedom",
    "cash_kzt",
    "cash_usd",
    "cash_rub",
    "binance_usdt",
]


def _format_amount(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return f"{int(rounded):,}"

    fixed = f"{value:.6f}"
    whole, frac = fixed.split(".", 1)
    frac = frac.rstrip("0")
    if not frac:
        return f"{int(whole):,}"
    return f"{int(whole):,}.{frac}"


def _store_sort_key(store: str) -> tuple[int, str]:
    if store in STORE_ORDER:
        return (STORE_ORDER.index(store), store)
    return (len(STORE_ORDER), store)


def _account_sort_key(account: str) -> tuple[int, str]:
    if account in ACCOUNT_ORDER:
        return (ACCOUNT_ORDER.index(account), account)
    return (len(ACCOUNT_ORDER), account)


def _compose_sparse_entry(entry: dict[str, Any], base_entry: dict[str, Any]) -> dict[str, Any]:
    composed = deepcopy(base_entry)
    composed["as_of"] = entry.get("as_of", composed.get("as_of"))

    base_source = str(base_entry.get("source") or "").strip()
    sparse_source = str(entry.get("source") or "").strip()
    if base_source and sparse_source:
        composed["source"] = f"{base_source} + {sparse_source}"
    elif sparse_source:
        composed["source"] = sparse_source

    sparse_balances = entry.get("balances") or []
    sparse_amount = sparse_balances[0].get("amount") if sparse_balances else None
    if sparse_amount is not None:
        balances = composed.get("balances")
        if not isinstance(balances, list):
            balances = []
            composed["balances"] = balances
        generate_bank_snapshot._upsert_universal_usdt_balance(balances, float(sparse_amount))

    return composed


def build_effective_history_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compose sparse autosync rows over latest full snapshots and return newest->oldest."""
    ordered = sorted(entries, key=lambda e: generate_bank_snapshot._parse_as_of(e.get("as_of", "")))
    effective_asc: list[dict[str, Any]] = []
    latest_full: dict[str, Any] | None = None

    for entry in ordered:
        current = deepcopy(entry)
        if generate_bank_snapshot._is_sparse_auto_usdt_entry(current):
            if latest_full is not None:
                current = _compose_sparse_entry(entry, latest_full)
        else:
            latest_full = deepcopy(current)
        effective_asc.append(current)

    return sorted(
        effective_asc,
        key=lambda e: generate_bank_snapshot._parse_as_of(e.get("as_of", "")),
        reverse=True,
    )


def _balances_to_map(balances: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    mapped: dict[tuple[str, str, str], float] = {}
    for row in balances:
        store = str(row.get("store") or "")
        account = str(row.get("account") or "")
        currency = str(row.get("currency") or "").upper()
        amount = float(row.get("amount") or 0.0)
        key = (store, account, currency)
        mapped[key] = mapped.get(key, 0.0) + amount
    return mapped


def _collect_account_keys(entries: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for entry in entries:
        balances = entry.get("balances") or []
        for row in balances:
            key = (
                str(row.get("store") or ""),
                str(row.get("account") or ""),
                str(row.get("currency") or "").upper(),
            )
            keys.add(key)
    return sorted(keys, key=lambda k: (_store_sort_key(k[0]), _account_sort_key(k[1]), k[2], k[0], k[1]))


def _fx_summary(fx_rates: dict[str, tuple[float, str, str]]) -> str:
    pairs = ["USDT_KZT", "USD_KZT", "RUB_KZT", "CNY_KZT"]
    items: list[str] = []
    for pair in pairs:
        rate, source, eff_date = fx_rates.get(pair, (1.0, "default", "hardcoded"))
        items.append(f"{pair}={rate} ({source} {eff_date})")
    return "; ".join(items)


def generate_history_totals_markdown(
    entries: list[dict[str, Any]],
    fx_rates: dict[str, tuple[float, str, str]],
    history_label: str,
) -> str:
    effective_entries = build_effective_history_entries(entries)
    account_keys = _collect_account_keys(effective_entries)

    account_headers = [f"{store}/{account}/{currency}" for store, account, currency in account_keys]
    headers = BASE_COLUMNS + account_headers

    align = []
    for idx, _header in enumerate(headers):
        if idx < 2:
            align.append("---")
        else:
            align.append("---:")

    lines = [
        "# Bank Accounts History Totals",
        "",
        f"Source: `{history_label}`",
        "Order: newest to oldest",
        f"KZT conversion rates: {_fx_summary(fx_rates)}",
        "",
        f"| {' | '.join(headers)} |",
        f"| {' | '.join(align)} |",
    ]

    for entry in effective_entries:
        balances = entry.get("balances") or []
        by_currency, _, total_kzt = generate_bank_snapshot.compute_totals(balances, fx_rates)
        mapped = _balances_to_map(balances)

        row = [
            str(entry.get("as_of") or ""),
            str(entry.get("source") or ""),
            _format_amount(float(by_currency.get("KZT", 0.0))),
            _format_amount(float(by_currency.get("USD", 0.0))),
            _format_amount(float(by_currency.get("RUB", 0.0))),
            _format_amount(float(by_currency.get("USDT", 0.0))),
            _format_amount(float(total_kzt)),
        ]

        for key in account_keys:
            row.append(_format_amount(float(mapped.get(key, 0.0))))

        lines.append(f"| {' | '.join(row)} |")

    lines.append("")
    return "\n".join(lines)


def render_history_totals(
    history_path: Path = HISTORY_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    entries = generate_bank_snapshot.load_history(history_path)
    fx_rates = generate_bank_snapshot.get_fx_rates(db_path)
    return generate_history_totals_markdown(entries, fx_rates, str(history_path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate bank_accounts history totals markdown table",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--history", type=Path, default=HISTORY_PATH, help="Path to bank_accounts_history.yaml")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path for FX conversion rates")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output markdown table path")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing")
    args = parser.parse_args()

    try:
        content = render_history_totals(history_path=args.history, db_path=args.db)
        if args.dry_run:
            print(content)
            return 0

        args.output.write_text(content, encoding="utf-8")
        print(f"Wrote: {args.output}")
        return 0
    except Exception as exc:
        print(f"Failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
