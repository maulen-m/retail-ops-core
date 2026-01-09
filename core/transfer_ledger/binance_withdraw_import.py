"""Import Binance withdrawals into DB and ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .repository import upsert_binance_withdrawal
from .service import post_binance_withdrawal, auto_allocate_entry_to_active_po


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _to_iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat()
    return str(value)


def normalize_binance_withdrawal(raw: dict) -> dict:
    withdraw_id = raw.get("id") or raw.get("withdrawOrderId") or raw.get("idStr")
    if not withdraw_id:
        raise ValueError("Missing withdrawal id in Binance payload")

    amount = _to_float(raw.get("amount"))
    fee = _to_float(raw.get("transactionFee"))
    if amount is None:
        raise ValueError(f"Invalid withdrawal amount for {withdraw_id}")

    return {
        "withdraw_id": str(withdraw_id),
        "tx_id": raw.get("txId"),
        "coin": (raw.get("coin") or "").upper(),
        "network": raw.get("network"),
        "amount": amount,
        "transaction_fee": fee,
        "address": raw.get("address"),
        "address_tag": raw.get("addressTag"),
        "apply_time": _to_iso(raw.get("applyTime") or raw.get("applyTimeStamp")),
        "success_time": _to_iso(raw.get("successTime")),
        "status": str(raw.get("status")) if raw.get("status") is not None else None,
        "wallet_type": str(raw.get("walletType")) if raw.get("walletType") is not None else None,
        "counterparty_label": raw.get("counterparty_label"),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "source": "BINANCE_WITHDRAW",
    }


def import_binance_withdrawals(
    raw_withdrawals: list[dict],
    db_path=None,
    ledger_coin: str = "USDT",
    write_ledger: bool = True,
    auto_allocate: bool = True,
) -> dict:
    inserted = 0
    ledger_entries = 0
    errors: list[str] = []

    for raw in raw_withdrawals:
        try:
            wd = normalize_binance_withdrawal(raw)
            is_new = upsert_binance_withdrawal(wd, db_path=db_path)
            if is_new:
                inserted += 1

            if write_ledger and wd["coin"] == ledger_coin:
                entry_id = post_binance_withdrawal(
                    withdraw_id=wd["withdraw_id"],
                    amount_usdt=wd["amount"],
                    network=wd.get("network") or "",
                    address=wd.get("address") or "",
                    apply_time=wd.get("apply_time"),
                    fee_usdt=wd.get("transaction_fee") or 0.0,
                    source=wd.get("source", "BINANCE_WITHDRAW"),
                    counterparty_label=wd.get("counterparty_label") or "",
                    db_path=db_path,
                )
                ledger_entries += 1
                if auto_allocate:
                    try:
                        auto_allocate_entry_to_active_po(entry_id, db_path=db_path)
                    except Exception as exc:
                        errors.append(f"auto-allocate failed for {wd['withdraw_id']}: {exc}")
        except Exception as exc:
            errors.append(str(exc))

    return {
        "inserted": inserted,
        "ledger_entries": ledger_entries,
        "errors": errors,
    }
