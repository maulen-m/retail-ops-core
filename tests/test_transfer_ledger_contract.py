from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.transfer_ledger.matching import (
    UNMATCHED_AGE_DAYS,
    address_match,
    effective_usdt,
    match_withdrawal_for_order,
)
from scripts.validate_transfer_ledger import (
    find_unmatched_withdrawals,
    validate_matching_invariants,
)

UTC = timezone.utc


def test_address_match_partial_tokens() -> None:
    order_addr = "TSoJR...H4tdC"
    withdrawal_addr = "TSoJR8WrmKTgSw3TCxLfWJ26962MiH4tdC"
    assert address_match(order_addr, withdrawal_addr)


def test_match_withdrawal_exact() -> None:
    order = {
        "deposit_address": "TSoJR8WrmKTgSw3TCxLfWJ26962MiH4tdC",
        "amount_usdt": 734.91,
        "message_date": "2026-01-07T16:39:07+00:00",
    }
    withdrawals = [
        {
            "withdraw_id": "wd_1",
            "amount": 734.91,
            "address": "TSoJR8WrmKTgSw3TCxLfWJ26962MiH4tdC",
            "apply_time": "2026-01-07T16:40:00+00:00",
        }
    ]
    result = match_withdrawal_for_order(order, withdrawals, used_ids=set())
    assert result.match is not None
    assert result.match["withdraw_id"] == "wd_1"


def test_fee_inclusive_effective_usdt() -> None:
    assert float(effective_usdt(734.91, 1.00)) == 735.91


def test_unmatched_withdrawal_age() -> None:
    now = datetime(2026, 1, 14, tzinfo=UTC)
    old_dt = (now - timedelta(days=UNMATCHED_AGE_DAYS + 1)).isoformat()
    withdrawals = [
        {
            "withdraw_id": "wd_old",
            "apply_time": old_dt,
            "exchanger_order_id": "",
        }
    ]
    stale = find_unmatched_withdrawals(withdrawals, now)
    assert len(stale) == 1
    assert stale[0]["withdraw_id"] == "wd_old"


def test_split_required_detection() -> None:
    now = datetime(2026, 1, 14, tzinfo=UTC)
    orders = [
        {
            "exchanger_order_id": "BTC:123",
            "amount_usdt": 100.0,
            "message_date": "2026-01-10T10:00:00+00:00",
            "deposit_address": "ADDR1",
        }
    ]
    withdrawals = [
        {
            "withdraw_id": "wd_1",
            "exchanger_order_id": "BTC:123",
            "amount": 100.0,
            "address": "ADDR1",
            "apply_time": "2026-01-10T10:10:00+00:00",
        },
        {
            "withdraw_id": "wd_2",
            "exchanger_order_id": "BTC:123",
            "amount": 100.0,
            "address": "ADDR1",
            "apply_time": "2026-01-10T10:15:00+00:00",
        },
    ]
    result = validate_matching_invariants(orders, withdrawals, now)
    assert any("split required" in err for err in result.errors)
