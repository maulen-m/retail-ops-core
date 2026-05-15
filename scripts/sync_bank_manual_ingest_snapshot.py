#!/usr/bin/env python3
"""Normalize a manual bank snapshot and sync derived bank config files.

Dry-run is the default. Apply writes only repo-local YAML/Markdown files and
requires ENABLE_BANK_MANUAL_INGEST_WRITE=1.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from scripts import generate_bank_accounts_history_totals
from scripts import generate_bank_snapshot

BANK_MANUAL_INGEST_ENV_GATE = "ENABLE_BANK_MANUAL_INGEST_WRITE"

DEFAULT_MANUAL_PATH = PROJECT_ROOT / "config" / "bank_accounts_manual_ingest_3.5.2026.yaml"
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "config" / "bank_accounts_history.yaml"
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "config" / "bank_accounts.yaml"
DEFAULT_TOTALS_PATH = PROJECT_ROOT / "config" / "bank_accounts_history_totals.md"

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
CURRENCY_ORDER = ["KZT", "USDT", "USD", "RUB", "CNY"]

_INLINE_ACCOUNT_RE = re.compile(r"^(\s*)([A-Za-z0-9_\"'-]+):([+-]?\d+(?:[,.]\d+)?)\s*$")
_COMMA_DECIMAL_RE = re.compile(r"^(\s*balance_[a-z]+:\s*)([+-]?\d+),(\d+)(\s*(?:#.*)?)$")


def _store_sort_key(store: str) -> tuple[int, str]:
    if store in STORE_ORDER:
        return (STORE_ORDER.index(store), store)
    return (len(STORE_ORDER), store)


def _account_sort_key(account: str) -> tuple[int, str]:
    if account in ACCOUNT_ORDER:
        return (ACCOUNT_ORDER.index(account), account)
    return (len(ACCOUNT_ORDER), account)


def _currency_sort_key(currency: str) -> tuple[int, str]:
    if currency in CURRENCY_ORDER:
        return (CURRENCY_ORDER.index(currency), currency)
    return (len(CURRENCY_ORDER), currency)


def _amount_for_yaml(amount: float) -> int | float:
    rounded = round(amount)
    if abs(amount - rounded) < 1e-9:
        return int(rounded)
    return amount


def normalize_manual_ingest_text(text: str) -> str:
    """Repair known operator-entry syntax issues without weakening validators."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fixed: list[str] = []
    pending_inline_balance: tuple[str, str] | None = None

    for line in lines:
        if pending_inline_balance is not None:
            indent, amount = pending_inline_balance
            balance_prefix = f"{indent}  balance_kzt:"
            if line.startswith(balance_prefix) and line.strip() == "balance_kzt:":
                fixed.append(f"{balance_prefix} {amount.replace(',', '.')}")
                pending_inline_balance = None
                continue
            fixed.append(f"{balance_prefix} {amount.replace(',', '.')}")
            pending_inline_balance = None

        inline_match = _INLINE_ACCOUNT_RE.match(line)
        if inline_match and len(inline_match.group(1)) >= 6:
            indent, account, amount = inline_match.groups()
            fixed.append(f"{indent}{account}:")
            pending_inline_balance = (indent, amount)
            continue

        comma_match = _COMMA_DECIMAL_RE.match(line)
        if comma_match:
            prefix, whole, frac, suffix = comma_match.groups()
            fixed.append(f"{prefix}{whole}.{frac}{suffix}")
            continue

        fixed.append(line)

    if pending_inline_balance is not None:
        indent, amount = pending_inline_balance
        fixed.append(f"{indent}  balance_kzt: {amount.replace(',', '.')}")

    return "\n".join(fixed)


def load_manual_ingest(path: Path) -> dict[str, Any]:
    normalized = normalize_manual_ingest_text(path.read_text(encoding="utf-8"))
    payload = yaml.safe_load(normalized)
    if not isinstance(payload, dict):
        raise ValueError("manual ingest YAML must be a mapping")
    return payload


def _extract_balances(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stores = payload.get("stores")
    if not isinstance(stores, dict):
        raise ValueError("manual ingest missing stores mapping")

    balances: list[dict[str, Any]] = []
    for store, store_payload in sorted(stores.items(), key=lambda item: _store_sort_key(str(item[0]))):
        accounts = store_payload.get("accounts") if isinstance(store_payload, dict) else None
        if not isinstance(accounts, dict):
            raise ValueError(f"{store}: accounts must be a mapping")
        for account, account_payload in sorted(accounts.items(), key=lambda item: _account_sort_key(str(item[0]))):
            if not isinstance(account_payload, dict):
                raise ValueError(f"{store}.{account}: account must be a mapping")
            balance_items = [
                (key, value)
                for key, value in account_payload.items()
                if str(key).startswith("balance_")
            ]
            if not balance_items:
                raise ValueError(f"{store}.{account}: no balance_* field")
            for key, value in sorted(
                balance_items,
                key=lambda item: _currency_sort_key(str(item[0]).replace("balance_", "").upper()),
            ):
                if value is None or str(value).strip() == "":
                    raise ValueError(f"{store}.{account}.{key}: missing balance")
                currency = str(key).replace("balance_", "").upper()
                amount = float(value)
                balances.append(
                    {
                        "store": str(store),
                        "account": str(account),
                        "amount": amount,
                        "currency": currency,
                    }
                )
    return balances


def entry_from_manual_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    as_of = str(payload.get("as_of") or "").strip()
    if not as_of:
        raise ValueError("manual ingest missing as_of")
    return {
        "as_of": as_of,
        "source": "manual snapshot (bank_accounts_manual_ingest_3.5.2026)",
        "balances": _extract_balances(payload),
    }


def _same_balances(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    def _keyed(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
        return {
            (
                str(row.get("store") or ""),
                str(row.get("account") or ""),
                str(row.get("currency") or "").upper(),
            ): float(row.get("amount") or 0.0)
            for row in rows
        }

    left_map = _keyed(left)
    right_map = _keyed(right)
    if left_map.keys() != right_map.keys():
        return False
    return all(abs(left_map[key] - right_map[key]) < 1e-9 for key in left_map)


def _format_history_amount(amount: float) -> str:
    value = _amount_for_yaml(amount)
    return str(value)


def _entry_to_history_block(entry: dict[str, Any]) -> str:
    lines = [
        f"- as_of: {entry['as_of']}",
        f"  source: {entry['source']}",
        "  balances:",
    ]
    for row in entry["balances"]:
        lines.extend(
            [
                f"  - store: {row['store']}",
                f"    account: {row['account']}",
                f"    amount: {_format_history_amount(float(row['amount']))}",
                f"    currency: {row['currency']}",
            ]
        )
    return "\n".join(lines) + "\n"


def _load_history_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError("history entries must be a list")
    return entries


def _history_text_with_entry(path: Path, entry: dict[str, Any]) -> tuple[str, bool]:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else "entries:\n"
    entries = _load_history_entries(path)
    for existing in entries:
        if str(existing.get("as_of") or "") != entry["as_of"]:
            continue
        if _same_balances(existing.get("balances") or [], entry["balances"]):
            return existing_text, False
        raise ValueError(f"history already has a different entry for as_of={entry['as_of']}")

    base = existing_text.rstrip() if existing_text.strip() else "entries:"
    if base != "entries:" and not base.startswith("entries:"):
        raise ValueError("history file must start with entries:")
    return base + "\n" + _entry_to_history_block(entry), True


def _report_without_large_strings(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.endswith("_yaml") and not key.endswith("_markdown")}


def sync_manual_ingest_snapshot(
    *,
    manual_path: Path,
    history_path: Path,
    snapshot_path: Path,
    totals_path: Path,
    fx_rates: dict[str, tuple[float, str, str]],
    apply: bool,
) -> dict[str, Any]:
    if apply and os.environ.get(BANK_MANUAL_INGEST_ENV_GATE) != "1":
        raise RuntimeError(f"{BANK_MANUAL_INGEST_ENV_GATE}=1 is required for bank manual ingest apply")

    raw_text = manual_path.read_text(encoding="utf-8")
    normalized_text = normalize_manual_ingest_text(raw_text)
    payload = yaml.safe_load(normalized_text)
    if not isinstance(payload, dict):
        raise ValueError("manual ingest YAML must be a mapping")

    entry = entry_from_manual_ingest(payload)
    by_currency, _by_store, total_kzt = generate_bank_snapshot.compute_totals(entry["balances"], fx_rates)
    normalized_manual_yaml = generate_bank_snapshot.generate_snapshot(entry, fx_rates)
    history_yaml, history_appended = _history_text_with_entry(history_path, entry)
    entries_after = _load_history_entries(history_path)
    if history_appended:
        entries_after = entries_after + [entry]
    snapshot_yaml = generate_bank_snapshot.generate_snapshot(
        generate_bank_snapshot.get_effective_latest_entry(entries_after),
        fx_rates,
    )
    totals_markdown = generate_bank_accounts_history_totals.generate_history_totals_markdown(
        entries_after,
        fx_rates,
        str(history_path),
    )

    report: dict[str, Any] = {
        "applied": False,
        "manual_path": str(manual_path),
        "history_path": str(history_path),
        "snapshot_path": str(snapshot_path),
        "totals_path": str(totals_path),
        "as_of": entry["as_of"],
        "balance_row_count": len(entry["balances"]),
        "totals_by_currency": {key: float(value) for key, value in sorted(by_currency.items())},
        "total_kzt_equivalent": float(total_kzt),
        "history_appended": history_appended,
        "normalized_manual_yaml": normalized_manual_yaml,
        "history_yaml": history_yaml,
        "snapshot_yaml": snapshot_yaml,
        "totals_markdown": totals_markdown,
    }

    if not apply:
        return report
    manual_path.write_text(normalized_manual_yaml, encoding="utf-8")
    history_path.write_text(history_yaml, encoding="utf-8")
    snapshot_path.write_text(snapshot_yaml, encoding="utf-8")
    totals_path.write_text(totals_markdown, encoding="utf-8")
    report["applied"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize and sync manual bank ingest snapshot")
    parser.add_argument("--manual", type=Path, default=DEFAULT_MANUAL_PATH)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--totals", type=Path, default=DEFAULT_TOTALS_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    fx_rates = generate_bank_snapshot.get_fx_rates(args.db)
    report = sync_manual_ingest_snapshot(
        manual_path=args.manual,
        history_path=args.history,
        snapshot_path=args.snapshot,
        totals_path=args.totals,
        fx_rates=fx_rates,
        apply=args.apply,
    )
    if args.json:
        print(json.dumps(_report_without_large_strings(report), indent=2, sort_keys=True))
    else:
        public = _report_without_large_strings(report)
        for key in sorted(public):
            print(f"{key}={public[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
