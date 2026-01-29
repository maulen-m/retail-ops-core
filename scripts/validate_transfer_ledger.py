#!/usr/bin/env python3
"""Validate transfer ledger correctness (matching, allocation, reconciliation)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db
from core.transfer_ledger.matching import (
    UNMATCHED_AGE_DAYS,
    amount_close,
    address_match,
    date_close,
    parse_dt,
    USDT_AMOUNT_TOLERANCE,
)
from core.transfer_ledger.money import to_decimal
from core.transfer_ledger.repository import (
    ensure_schema,
    list_exchanger_orders,
    list_withdrawals,
    list_funding_balance_snapshots,
)

UTC = timezone.utc
ALMATY_TZ = ZoneInfo("Asia/Almaty")


@dataclass
class CheckResult:
    name: str
    ok: bool
    errors: list[str]
    warnings: list[str]


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _age_days(dt: datetime | None, now: datetime) -> float | None:
    if not dt:
        return None
    return (now - dt).total_seconds() / 86400.0


def _parse_dt_utc(value: object) -> datetime | None:
    dt = parse_dt(value)
    if not dt:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_snapshot_dt(value: object) -> datetime | None:
    dt = parse_dt(value)
    if not dt:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ALMATY_TZ)


def _snapshot_balance(snapshot: dict) -> Decimal | None:
    total = to_decimal(snapshot.get("total"))
    if total is not None:
        return total
    free = to_decimal(snapshot.get("free")) or Decimal("0")
    locked = to_decimal(snapshot.get("locked")) or Decimal("0")
    return free + locked


def find_unmatched_withdrawals(
    withdrawals: list[dict],
    now: datetime,
    age_days: int = UNMATCHED_AGE_DAYS,
) -> list[dict]:
    stale = []
    for wd in withdrawals:
        if wd.get("exchanger_order_id"):
            continue
        dt = _parse_dt_utc(wd.get("apply_time") or wd.get("success_time"))
        age = _age_days(dt, now)
        if age is None:
            continue
        if age >= age_days:
            stale.append(wd)
    return stale


def find_unmatched_orders(
    orders: list[dict],
    withdrawals: list[dict],
    now: datetime,
    age_days: int = UNMATCHED_AGE_DAYS,
) -> list[dict]:
    matched_ids = {w.get("exchanger_order_id") for w in withdrawals if w.get("exchanger_order_id")}
    stale = []
    for order in orders:
        ex_id = order.get("exchanger_order_id")
        if not ex_id or ex_id in matched_ids:
            continue
        status = (order.get("status") or "").upper()
        if "CANCEL" in status:
            continue
        dt = _parse_dt_utc(order.get("message_date"))
        age = _age_days(dt, now)
        if age is None:
            continue
        if age >= age_days:
            stale.append(order)
    return stale


def validate_matching_invariants(
    orders: list[dict],
    withdrawals: list[dict],
    now: datetime,
) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []

    orders_by_id = {o.get("exchanger_order_id"): o for o in orders if o.get("exchanger_order_id")}
    withdrawals_by_order: dict[str, list[dict]] = {}

    for wd in withdrawals:
        ex_id = wd.get("exchanger_order_id")
        if not ex_id:
            continue
        withdrawals_by_order.setdefault(ex_id, []).append(wd)
        order = orders_by_id.get(ex_id)
        if not order:
            errors.append(f"Withdrawal {wd.get('withdraw_id')} links to missing order {ex_id}")
            continue
        if order.get("amount_usdt") is not None and wd.get("amount") is not None:
            if not amount_close(wd.get("amount"), order.get("amount_usdt")):
                errors.append(f"Amount mismatch for order {ex_id} vs withdrawal {wd.get('withdraw_id')}")
        if order.get("deposit_address") and wd.get("address"):
            if not address_match(order.get("deposit_address"), wd.get("address")):
                errors.append(f"Address mismatch for order {ex_id} vs withdrawal {wd.get('withdraw_id')}")
        if not date_close(
            _parse_dt_utc(order.get("message_date")),
            _parse_dt_utc(wd.get("apply_time") or wd.get("success_time")),
        ):
            errors.append(f"Date window exceeded for order {ex_id} vs withdrawal {wd.get('withdraw_id')}")

    for ex_id, wds in withdrawals_by_order.items():
        if len(wds) > 1:
            errors.append(f"Order {ex_id} matched to {len(wds)} withdrawals (split required)")

    stale_withdrawals = find_unmatched_withdrawals(withdrawals, now)
    for wd in stale_withdrawals:
        warnings.append(f"Unmatched withdrawal {wd.get('withdraw_id')} older than {UNMATCHED_AGE_DAYS}d")

    stale_orders = find_unmatched_orders(orders, withdrawals, now)
    for order in stale_orders:
        warnings.append(f"Unmatched exchanger order {order.get('exchanger_order_id')} older than {UNMATCHED_AGE_DAYS}d")

    return CheckResult(
        name="matching_invariants",
        ok=not errors,
        errors=errors,
        warnings=warnings,
    )


def validate_allocation_invariants(db_path: Path) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT a.allocation_id, a.entry_id, a.amount, a.currency, a.amount_kzt,
                   e.amount AS entry_amount, e.currency AS entry_currency
            FROM po_funding_allocations a
            LEFT JOIN transfer_ledger e ON e.entry_id = a.entry_id
            """
        ).fetchall()
    for row in rows:
        if row["entry_amount"] is None:
            errors.append(f"Allocation {row['allocation_id']} references missing entry_id {row['entry_id']}")
            continue
        if row["currency"] and row["entry_currency"] and row["currency"] != row["entry_currency"]:
            errors.append(
                f"Allocation {row['allocation_id']} currency {row['currency']} "
                f"!= entry currency {row['entry_currency']}"
            )
        if row["amount"] is not None and float(row["amount"]) <= 0:
            warnings.append(f"Allocation {row['allocation_id']} has non-positive amount")
        if row["amount_kzt"] is not None and float(row["amount_kzt"]) <= 0:
            warnings.append(f"Allocation {row['allocation_id']} has non-positive amount_kzt")
    return CheckResult(
        name="allocation_invariants",
        ok=not errors,
        errors=errors,
        warnings=warnings,
    )


def _balance_from_binance(db_path: Path) -> Decimal:
    with get_db(db_path) as conn:
        p2p = conn.execute(
            """
            SELECT crypto_amount FROM binance_c2c_orders
            WHERE trade_type='BUY' AND asset='USDT' AND order_status='COMPLETED'
            """
        ).fetchall()
        withdrawals = conn.execute(
            "SELECT amount, transaction_fee FROM binance_withdrawals WHERE coin='USDT'"
        ).fetchall()
        deposits = conn.execute(
            "SELECT amount FROM binance_deposits WHERE coin='USDT'"
        ).fetchall()
        transfers = conn.execute(
            "SELECT amount, transfer_type FROM binance_transfers WHERE asset='USDT'"
        ).fetchall()

    total = to_decimal("0") or Decimal("0")
    for row in p2p:
        amt = to_decimal(row["crypto_amount"])
        if amt is not None:
            total += amt
    for row in withdrawals:
        amt = to_decimal(row["amount"]) or Decimal("0")
        fee = to_decimal(row["transaction_fee"]) or Decimal("0")
        total -= (amt + fee)
    for row in deposits:
        amt = to_decimal(row["amount"])
        if amt is not None:
            total += amt
    for row in transfers:
        amt = to_decimal(row["amount"]) or Decimal("0")
        ttype = (row["transfer_type"] or "").upper()
        if ttype.startswith("FUNDING_"):
            total -= amt
        elif ttype.endswith("_FUNDING"):
            total += amt
    return total


def _in_window(value: object, start_dt: datetime, end_dt: datetime) -> bool:
    dt = _parse_dt_utc(value)
    if not dt:
        return False
    return start_dt < dt <= end_dt


def _balance_delta_from_binance(db_path: Path, start_dt: datetime, end_dt: datetime) -> Decimal:
    with get_db(db_path) as conn:
        p2p = conn.execute(
            """
            SELECT crypto_amount, create_time FROM binance_c2c_orders
            WHERE trade_type='BUY' AND asset='USDT'
            """
        ).fetchall()
        withdrawals = conn.execute(
            "SELECT amount, transaction_fee, apply_time, success_time FROM binance_withdrawals WHERE coin='USDT'"
        ).fetchall()
        deposits = conn.execute(
            "SELECT amount, insert_time FROM binance_deposits WHERE coin='USDT'"
        ).fetchall()
        transfers = conn.execute(
            "SELECT amount, transfer_type, timestamp FROM binance_transfers WHERE asset='USDT'"
        ).fetchall()

    delta = to_decimal("0") or Decimal("0")
    for row in p2p:
        if _in_window(row["create_time"], start_dt, end_dt):
            amt = to_decimal(row["crypto_amount"])
            if amt is not None:
                delta += amt
    for row in withdrawals:
        ts = row["apply_time"] or row["success_time"]
        if _in_window(ts, start_dt, end_dt):
            amt = to_decimal(row["amount"]) or Decimal("0")
            fee = to_decimal(row["transaction_fee"]) or Decimal("0")
            delta -= (amt + fee)
    for row in deposits:
        if _in_window(row["insert_time"], start_dt, end_dt):
            amt = to_decimal(row["amount"])
            if amt is not None:
                delta += amt
    for row in transfers:
        if _in_window(row["timestamp"], start_dt, end_dt):
            amt = to_decimal(row["amount"]) or Decimal("0")
            ttype = (row["transfer_type"] or "").upper()
            if ttype.startswith("FUNDING_"):
                delta -= amt
            elif ttype.endswith("_FUNDING"):
                delta += amt
    return delta


def validate_reconciliation_invariants(db_path: Path) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []

    # Ensure each withdrawal has a ledger entry
    with get_db(db_path) as conn:
        missing = conn.execute(
            """
            SELECT w.withdraw_id
            FROM binance_withdrawals w
            LEFT JOIN transfer_ledger t
              ON t.reference_type='BINANCE_WITHDRAWAL' AND t.reference_id = w.withdraw_id
            WHERE t.entry_id IS NULL
            """
        ).fetchall()
        missing_fee = conn.execute(
            """
            SELECT w.withdraw_id
            FROM binance_withdrawals w
            LEFT JOIN transfer_ledger t
              ON t.reference_type='BINANCE_WITHDRAWAL_FEE' AND t.reference_id = w.withdraw_id || ':fee'
            WHERE w.transaction_fee IS NOT NULL AND w.transaction_fee > 0 AND t.entry_id IS NULL
            """
        ).fetchall()

    for row in missing:
        errors.append(f"Missing BINANCE_WITHDRAWAL ledger entry for {row['withdraw_id']}")
    for row in missing_fee:
        warnings.append(f"Missing BINANCE_WITHDRAWAL_FEE ledger entry for {row['withdraw_id']}")

    # Compare funding snapshot deltas vs derived deltas (require >=2 snapshots)
    snapshots = list_funding_balance_snapshots(db_path=db_path, asset="USDT", limit=2)
    if len(snapshots) < 2:
        warnings.append("Need at least 2 funding balance snapshots for USDT drift check")
    else:
        latest, previous = snapshots[0], snapshots[1]
        latest_time = _parse_snapshot_dt(latest.get("snapshot_time"))
        prev_time = _parse_snapshot_dt(previous.get("snapshot_time"))
        if not latest_time or not prev_time:
            warnings.append("Funding snapshot times are invalid")
        else:
            latest_bal = _snapshot_balance(latest)
            prev_bal = _snapshot_balance(previous)
            if latest_bal is None or prev_bal is None:
                warnings.append("Funding snapshot has no balance totals")
            else:
                derived_delta = _balance_delta_from_binance(db_path, prev_time, latest_time)
                snapshot_delta = latest_bal - prev_bal
                diff = abs(derived_delta - snapshot_delta)
                if diff > USDT_AMOUNT_TOLERANCE:
                    warnings.append(
                        "Funding balance delta drift > tolerance: "
                        f"snapshot_delta={snapshot_delta} derived_delta={derived_delta}"
                    )

    return CheckResult(
        name="reconciliation_invariants",
        ok=not errors,
        errors=errors,
        warnings=warnings,
    )


def validate_freshness_invariants(db_path: Path, now: datetime) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    sources = [
        ("exchanger_orders", "exchanger_orders", "message_date", True),
        ("binance_p2p", "binance_c2c_orders", "create_time", True),
        ("binance_withdrawals", "binance_withdrawals", "apply_time", True),
        ("binance_transfers", "binance_transfers", "timestamp", False),
        ("binance_deposits", "binance_deposits", "insert_time", False),
    ]

    with get_db(db_path) as conn:
        for name, table, col, required in sources:
            row = conn.execute(
                f"SELECT MAX({col}) AS last_ts, COUNT(1) AS cnt FROM {table}"
            ).fetchone()
            last_ts = row["last_ts"] if row else None
            count = row["cnt"] if row else 0
            if not count:
                msg = f"{name} has no rows"
                if required:
                    warnings.append(msg)
                continue
            last_dt = _parse_dt_utc(last_ts)
            age = _age_days(last_dt, now)
            if age is None:
                if required:
                    warnings.append(f"{name} last timestamp is invalid")
                continue
            if age > 30:
                if required:
                    warnings.append(f"{name} last updated {age:.1f} days ago")

    return CheckResult(
        name="freshness_invariants",
        ok=not errors,
        errors=errors,
        warnings=warnings,
    )


def _print_result(result: CheckResult) -> None:
    status = "OK" if result.ok and not result.warnings else "WARN" if not result.errors else "FAIL"
    print(f"[{status}] {result.name}")
    for err in result.errors:
        print(f"  - ERROR: {err}")
    for warn in result.warnings:
        print(f"  - WARN: {warn}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate transfer ledger correctness")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")
    args = parser.parse_args()

    ensure_schema(args.db)

    now = _now_utc()
    orders = list_exchanger_orders(db_path=args.db)
    withdrawals = list_withdrawals(db_path=args.db)

    results: list[CheckResult] = []
    results.append(validate_matching_invariants(orders, withdrawals, now))
    results.append(validate_allocation_invariants(args.db))
    results.append(validate_reconciliation_invariants(args.db))
    results.append(validate_freshness_invariants(args.db, now))

    errors = []
    warnings = []
    for res in results:
        _print_result(res)
        errors.extend(res.errors)
        warnings.extend(res.warnings)

    if errors:
        return 2
    if warnings and args.strict:
        return 2
    if warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
