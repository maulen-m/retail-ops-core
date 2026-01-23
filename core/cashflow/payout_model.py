#!/usr/bin/env python3
"""
Payout lag model utilities.

Reads config/payout_model.yaml and provides base/conservative lag days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "payout_model.yaml"


@dataclass
class PayoutModel:
    base_lag_days: int
    conservative_lag_days: int
    updated_at: str | None = None
    sample_size: int | None = None
    source: str | None = None


def load_payout_model(config_path: Path = DEFAULT_CONFIG) -> PayoutModel:
    if not config_path.exists():
        return PayoutModel(base_lag_days=7, conservative_lag_days=10, source="DEFAULT")
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return PayoutModel(
        base_lag_days=int(data.get("payout_lag_days_base", 7)),
        conservative_lag_days=int(data.get("payout_lag_days_conservative", 10)),
        updated_at=data.get("updated_at"),
        sample_size=data.get("sample_size"),
        source=data.get("source"),
    )


def save_payout_model(model: PayoutModel, config_path: Path = DEFAULT_CONFIG) -> None:
    payload = {
        "payout_lag_days_base": int(model.base_lag_days),
        "payout_lag_days_conservative": int(model.conservative_lag_days),
        "updated_at": model.updated_at or datetime.now().isoformat(),
        "sample_size": model.sample_size,
        "source": model.source or "HISTORY",
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False)
