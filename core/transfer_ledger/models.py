"""Datatypes for transfer ledger entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: Optional[int]
    entry_date: date
    amount: float
    currency: str
    amount_kzt: float
    fx_rate_to_kzt: float
    fx_source: str
    reference_type: str
    reference_id: str
    from_account: str = ""
    to_account: str = ""
    notes: str = ""
