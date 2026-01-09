"""Business logic for transfer ledger."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .models import LedgerEntry
from .repository import insert_entry, ensure_schema, ledger_entry_exists


def _normalize_date(value: Optional[date | datetime]) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return date.fromisoformat(value)
    return value


def post_po_payment_cny(
    po_id: str,
    amount_cny: float,
    fx_rate_cny_kzt: float,
    paid_at: Optional[date | datetime] = None,
    source: str = "MANUAL",
    notes: str = "",
    db_path=None,
) -> int:
    ensure_schema(db_path)
    paid_date = _normalize_date(paid_at)
    amount_kzt = amount_cny * fx_rate_cny_kzt
    entry = LedgerEntry(
        entry_id=None,
        entry_date=paid_date,
        amount=amount_cny,
        currency="CNY",
        amount_kzt=amount_kzt,
        fx_rate_to_kzt=fx_rate_cny_kzt,
        fx_source=source,
        reference_type="PO",
        reference_id=po_id,
        from_account="",
        to_account="",
        notes=notes,
    )
    return insert_entry(entry, db_path=db_path)


def post_cargo_payment_usd(
    po_id: str,
    amount_usd: float,
    fx_rate_usd_kzt: float,
    paid_at: Optional[date | datetime] = None,
    source: str = "MANUAL",
    notes: str = "",
    db_path=None,
) -> int:
    ensure_schema(db_path)
    paid_date = _normalize_date(paid_at)
    amount_kzt = amount_usd * fx_rate_usd_kzt
    entry = LedgerEntry(
        entry_id=None,
        entry_date=paid_date,
        amount=amount_usd,
        currency="USD",
        amount_kzt=amount_kzt,
        fx_rate_to_kzt=fx_rate_usd_kzt,
        fx_source=source,
        reference_type="CARGO",
        reference_id=po_id,
        from_account="",
        to_account="",
        notes=notes,
    )
    return insert_entry(entry, db_path=db_path)


def post_transfer(
    amount: float,
    currency: str,
    fx_rate_to_kzt: float,
    from_account: str,
    to_account: str,
    paid_at: Optional[date | datetime] = None,
    source: str = "MANUAL",
    notes: str = "",
    reference_id: Optional[str] = None,
    db_path=None,
) -> int:
    ensure_schema(db_path)
    paid_date = _normalize_date(paid_at)
    amount_kzt = amount * fx_rate_to_kzt
    if not reference_id:
        reference_id = f"{from_account}->{to_account}"
    entry = LedgerEntry(
        entry_id=None,
        entry_date=paid_date,
        amount=amount,
        currency=currency.upper(),
        amount_kzt=amount_kzt,
        fx_rate_to_kzt=fx_rate_to_kzt,
        fx_source=source,
        reference_type="TRANSFER",
        reference_id=reference_id,
        from_account=from_account,
        to_account=to_account,
        notes=notes,
    )
    return insert_entry(entry, db_path=db_path)


def post_binance_p2p_trade(
    order_number: str,
    trade_type: str,
    asset: str,
    fiat: str,
    crypto_amount: float,
    fiat_amount: float,
    unit_price: float,
    paid_at: Optional[date | datetime] = None,
    source: str = "BINANCE_P2P",
    counterparty: str = "",
    db_path=None,
) -> list[int]:
    """
    Record a Binance P2P trade as two ledger entries (asset + fiat).

    BUY: +asset, -fiat
    SELL: -asset, +fiat
    """
    ensure_schema(db_path)
    paid_date = _normalize_date(paid_at)
    trade = (trade_type or "").upper()
    asset = asset.upper()
    fiat = fiat.upper()

    if trade not in {"BUY", "SELL"}:
        raise ValueError(f"Unsupported trade_type: {trade_type}")

    asset_sign = 1 if trade == "BUY" else -1
    fiat_sign = -1 if trade == "BUY" else 1

    asset_amount = asset_sign * crypto_amount
    fiat_amount_signed = fiat_sign * fiat_amount

    entry_ids: list[int] = []

    asset_ref = f"{order_number}:{asset}"
    fiat_ref = f"{order_number}:{fiat}"

    if not ledger_entry_exists("BINANCE_P2P", asset_ref, currency=asset, db_path=db_path):
        entry_asset = LedgerEntry(
            entry_id=None,
            entry_date=paid_date,
            amount=asset_amount,
            currency=asset,
            amount_kzt=asset_amount * unit_price,
            fx_rate_to_kzt=unit_price,
            fx_source=source,
            reference_type="BINANCE_P2P",
            reference_id=asset_ref,
            from_account="",
            to_account="",
            notes=f"counterparty={counterparty}",
        )
        entry_ids.append(insert_entry(entry_asset, db_path=db_path))

    if not ledger_entry_exists("BINANCE_P2P", fiat_ref, currency=fiat, db_path=db_path):
        entry_fiat = LedgerEntry(
            entry_id=None,
            entry_date=paid_date,
            amount=fiat_amount_signed,
            currency=fiat,
            amount_kzt=fiat_amount_signed if fiat == "KZT" else fiat_amount_signed * unit_price,
            fx_rate_to_kzt=1.0 if fiat == "KZT" else unit_price,
            fx_source=source,
            reference_type="BINANCE_P2P",
            reference_id=fiat_ref,
            from_account="",
            to_account="",
            notes=f"counterparty={counterparty}",
        )
        entry_ids.append(insert_entry(entry_fiat, db_path=db_path))

    return entry_ids
