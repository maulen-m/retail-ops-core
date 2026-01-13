"""Import Binance deposit history into DB."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .repository import upsert_binance_deposit

LOCAL_TZ = ZoneInfo("Asia/Almaty")


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


def normalize_binance_deposit(raw: dict) -> dict:
    deposit_id = raw.get("id") or raw.get("insertId") or raw.get("depositId") or raw.get("tranId")
    if not deposit_id:
        raise ValueError("Missing deposit id in Binance payload")

    amount = _to_float(raw.get("amount"))
    if amount is None:
        raise ValueError(f"Invalid deposit amount for {deposit_id}")

    account_label = raw.get("account_label") or os.getenv("BINANCE_ACCOUNT_LABEL") or ""
    return {
        "deposit_id": str(deposit_id),
        "coin": (raw.get("coin") or "").upper(),
        "amount": amount,
        "address": raw.get("address"),
        "address_tag": raw.get("addressTag"),
        "tx_id": raw.get("txId"),
        "insert_time": _to_iso(raw.get("insertTime")),
        "complete_time": _to_iso(raw.get("successTime") or raw.get("completeTime")),
        "status": str(raw.get("status")) if raw.get("status") is not None else None,
        "network": raw.get("network"),
        "transfer_type": raw.get("transferType"),
        "wallet_type": raw.get("walletType"),
        "account_label": account_label,
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "source": "BINANCE_DEPOSIT",
    }


def import_binance_deposits(
    raw_deposits: list[dict],
    db_path=None,
) -> dict:
    inserted = 0
    errors: list[str] = []

    for raw in raw_deposits:
        try:
            deposit = normalize_binance_deposit(raw)
            is_new = upsert_binance_deposit(deposit, db_path=db_path)
            if is_new:
                inserted += 1
        except Exception as exc:
            errors.append(str(exc))

    return {
        "inserted": inserted,
        "errors": errors,
    }
