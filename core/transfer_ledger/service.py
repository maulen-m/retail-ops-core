"""Business logic for transfer ledger."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .models import LedgerEntry
from .repository import (
    insert_entry,
    ensure_schema,
    ledger_entry_exists,
    get_entry,
    create_po_funding_allocation,
    list_pos_for_allocation,
    get_po_allocated_kzt,
    get_po_total_cny_from_lines,
)
from .fx import get_fx_snapshot


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
    account_label: str = "",
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

    note_parts = []
    if counterparty:
        note_parts.append(f"counterparty={counterparty}")
    if account_label:
        note_parts.append(f"account={account_label}")
    notes = "; ".join(note_parts)

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
            notes=notes,
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
            notes=notes,
        )
        entry_ids.append(insert_entry(entry_fiat, db_path=db_path))

    return entry_ids


def post_binance_withdrawal(
    withdraw_id: str,
    amount_usdt: float,
    network: str,
    address: str,
    apply_time: Optional[date | datetime | str] = None,
    fee_usdt: float = 0.0,
    source: str = "BINANCE_WITHDRAW",
    counterparty_label: str = "",
    exchanger_order_id: str = "",
    account_label: str = "",
    db_path=None,
) -> int:
    """
    Record a Binance USDT withdrawal as a ledger outflow.
    """
    ensure_schema(db_path)
    paid_date = _normalize_date(apply_time)
    fx = get_fx_snapshot(paid_date, db_path=db_path)
    if not fx or not fx.get("usdt_kzt"):
        raise ValueError("Missing usdt_kzt FX rate for withdrawal date")
    usdt_kzt = float(fx["usdt_kzt"])
    amount_kzt = -abs(amount_usdt) * usdt_kzt

    notes = f"network={network}; address={address}"
    if account_label:
        notes += f"; account={account_label}"
    if counterparty_label:
        notes += f"; label={counterparty_label}"
    if exchanger_order_id:
        notes += f"; exchanger_order_id={exchanger_order_id}"

    entry = LedgerEntry(
        entry_id=None,
        entry_date=paid_date,
        amount=-abs(amount_usdt),
        currency="USDT",
        amount_kzt=amount_kzt,
        fx_rate_to_kzt=usdt_kzt,
        fx_source=source,
        reference_type="BINANCE_WITHDRAWAL",
        reference_id=withdraw_id,
        from_account="binance_funding",
        to_account="external_wallet",
        notes=notes,
    )
    entry_id = insert_entry(entry, db_path=db_path)

    # Optional fee entry (kept simple for now)
    if fee_usdt and fee_usdt > 0:
        fee_entry = LedgerEntry(
            entry_id=None,
            entry_date=paid_date,
            amount=-abs(fee_usdt),
            currency="USDT",
            amount_kzt=-abs(fee_usdt) * usdt_kzt,
            fx_rate_to_kzt=usdt_kzt,
            fx_source=source,
            reference_type="BINANCE_WITHDRAWAL_FEE",
            reference_id=f"{withdraw_id}:fee",
            from_account="binance_funding",
            to_account="binance_fee",
            notes=notes,
        )
        insert_entry(fee_entry, db_path=db_path)
    return entry_id


def allocate_po_funding(
    po_id: str,
    entry_id: int,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    amount_kzt: Optional[float] = None,
    notes: str = "",
    db_path=None,
) -> int:
    ensure_schema(db_path)
    entry = get_entry(entry_id, db_path=db_path)
    if not entry:
        raise ValueError(f"Ledger entry not found: {entry_id}")

    base_amount = abs(entry.amount)
    base_amount_kzt = abs(entry.amount_kzt)
    alloc_amount = abs(amount) if amount is not None else base_amount
    alloc_currency = currency if currency is not None else entry.currency
    alloc_amount_kzt = abs(amount_kzt) if amount_kzt is not None else base_amount_kzt

    return create_po_funding_allocation(
        po_id=po_id,
        entry_id=entry_id,
        amount=alloc_amount,
        currency=alloc_currency,
        amount_kzt=alloc_amount_kzt,
        notes=notes,
        db_path=db_path,
    )


def _parse_po_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None


def _po_target_kzt(po_row: dict, db_path=None) -> Optional[float]:
    total_kzt = po_row.get("total_cost_kzt_supplier")
    if total_kzt is not None and float(total_kzt) > 0:
        return float(total_kzt)

    total_cny = po_row.get("total_cost_cny")
    if total_cny is None or float(total_cny) <= 0:
        total_cny = get_po_total_cny_from_lines(po_row.get("po_id"), db_path=db_path)

    if total_cny is None or float(total_cny) <= 0:
        return None

    fx_rate = po_row.get("fx_rate_cny_plan") or 75.0
    try:
        fx_rate = float(fx_rate)
    except (TypeError, ValueError):
        fx_rate = 75.0

    return float(total_cny) * fx_rate


def auto_allocate_entry_to_active_po(
    entry_id: int,
    db_path=None,
    notes: str = "auto-allocate",
) -> list[int]:
    """
    Allocate a funding entry to the active PO based on PO message_date.

    If allocation exceeds PO target, spill into the next PO(s).
    """
    ensure_schema(db_path)
    entry = get_entry(entry_id, db_path=db_path)
    if not entry:
        raise ValueError(f"Ledger entry not found: {entry_id}")

    total_kzt = abs(entry.amount_kzt)
    total_amount = abs(entry.amount)
    if total_kzt <= 0:
        return []

    pos = list_pos_for_allocation(db_path=db_path)
    parsed: list[tuple[date, dict]] = []
    for row in pos:
        po_date = _parse_po_date(row.get("message_date")) or _parse_po_date(row.get("created_at"))
        if po_date:
            parsed.append((po_date, row))

    if not parsed:
        raise ValueError("No PO dates available for auto-allocation")

    parsed.sort(key=lambda x: (x[0], str(x[1].get("po_id"))))

    entry_date = entry.entry_date
    idx = 0
    for i, (po_date, _) in enumerate(parsed):
        if entry_date >= po_date:
            idx = i
        else:
            break

    remaining_kzt = total_kzt
    allocation_ids: list[int] = []

    for _, po_row in parsed[idx:]:
        po_id = po_row.get("po_id")
        if not po_id:
            continue
        target_kzt = _po_target_kzt(po_row, db_path=db_path)
        if target_kzt is None or target_kzt <= 0:
            continue

        allocated_kzt = get_po_allocated_kzt(po_id, db_path=db_path)
        remaining_po_kzt = target_kzt - allocated_kzt
        if remaining_po_kzt <= 0:
            continue

        alloc_kzt = min(remaining_po_kzt, remaining_kzt)
        ratio = alloc_kzt / total_kzt if total_kzt else 0
        alloc_amount = total_amount * ratio

        allocation_ids.append(
            create_po_funding_allocation(
                po_id=po_id,
                entry_id=entry_id,
                amount=alloc_amount,
                currency=entry.currency,
                amount_kzt=alloc_kzt,
                notes=notes,
                db_path=db_path,
            )
        )
        remaining_kzt -= alloc_kzt
        if remaining_kzt <= 0:
            break

    return allocation_ids
