"""Import Binance withdrawals into DB and ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .repository import upsert_binance_withdrawal, has_entry
from .service import post_binance_withdrawal, auto_allocate_entry_to_active_po
from .exchanger_matching import match_exchanger_order_for_withdrawal


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


LOCAL_TZ = ZoneInfo("Asia/Almaty")


def _to_iso(value) -> Optional[str]:
    if value is None:
        return None
    dt: Optional[datetime] = None
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    else:
        try:
            dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        except Exception:
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except Exception:
                return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).isoformat()


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
        "exchanger_order_id": raw.get("exchanger_order_id"),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "source": "BINANCE_WITHDRAW",
    }


def import_binance_withdrawals(
    raw_withdrawals: list[dict],
    db_path=None,
    ledger_coin: str = "USDT",
    write_ledger: bool = True,
    auto_allocate: bool = True,
    auto_label: bool = True,
) -> dict:
    inserted = 0
    ledger_entries = 0
    errors: list[str] = []

    for raw in raw_withdrawals:
        try:
            wd = normalize_binance_withdrawal(raw)
            if auto_label:
                label, order_id = match_exchanger_order_for_withdrawal(wd, db_path=db_path)
                if label:
                    wd["counterparty_label"] = label
                if order_id:
                    wd["exchanger_order_id"] = order_id
            is_new = upsert_binance_withdrawal(wd, db_path=db_path)
            if is_new:
                inserted += 1

            if write_ledger and wd["coin"] == ledger_coin:
                if not has_entry("BINANCE_WITHDRAWAL", wd["withdraw_id"], db_path=db_path):
                    entry_id = post_binance_withdrawal(
                        withdraw_id=wd["withdraw_id"],
                        amount_usdt=wd["amount"],
                        network=wd.get("network") or "",
                        address=wd.get("address") or "",
                        apply_time=wd.get("apply_time"),
                        fee_usdt=wd.get("transaction_fee") or 0.0,
                        source=wd.get("source", "BINANCE_WITHDRAW"),
                        counterparty_label=wd.get("counterparty_label") or "",
                        exchanger_order_id=wd.get("exchanger_order_id") or "",
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
