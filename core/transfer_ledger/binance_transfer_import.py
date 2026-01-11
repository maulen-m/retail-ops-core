"""Import Binance universal transfer history into DB."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .repository import upsert_binance_transfer

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


def normalize_binance_transfer(raw: dict) -> dict:
    transfer_id = raw.get("tranId") or raw.get("transferId") or raw.get("id")
    if not transfer_id:
        raise ValueError("Missing transfer id in Binance payload")

    amount = _to_float(raw.get("amount"))
    if amount is None:
        raise ValueError(f"Invalid transfer amount for {transfer_id}")

    transfer_type = raw.get("type") or raw.get("transferType") or ""

    return {
        "transfer_id": str(transfer_id),
        "asset": (raw.get("asset") or "").upper(),
        "amount": amount,
        "transfer_type": str(transfer_type),
        "status": str(raw.get("status")) if raw.get("status") is not None else None,
        "timestamp": _to_iso(raw.get("timestamp")),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "source": "BINANCE_TRANSFER",
    }


def import_binance_transfers(
    raw_transfers: list[dict],
    db_path=None,
) -> dict:
    inserted = 0
    errors: list[str] = []

    for raw in raw_transfers:
        try:
            transfer = normalize_binance_transfer(raw)
            is_new = upsert_binance_transfer(transfer, db_path=db_path)
            if is_new:
                inserted += 1
        except Exception as exc:
            errors.append(str(exc))

    return {
        "inserted": inserted,
        "errors": errors,
    }
