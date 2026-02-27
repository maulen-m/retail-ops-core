from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_ocean_drop_reference_snapshot import (
    SnapshotError,
    build_ocean_drop_snapshot_dataframe,
)


REQUIRED_BASE = {
    "№ заказа": "",
    "Статус": "ЗАВЕРШЕН",
    "Количество": "1",
    "Сумма": "1000",
    "Склад передачи КД": "30137883_PP1",
    "Дата поступления заказа": "24.02.2026",
    "Дата изменения статуса": "25.02.2026",
    "Артикул": "OF_ARTICLE",
    "Название в системе продавца": "Offer",
    "mapped_sku_key": "SKU_KEY",
    "mapped_size": "L",
}


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    payload: list[dict[str, str]] = []
    for row in rows:
        base = dict(REQUIRED_BASE)
        base.update(row)
        payload.append(base)
    pd.DataFrame(payload).to_csv(path, index=False, encoding="utf-8")


def test_ocean_drop_parser_uses_status_date_then_creation_fallback(tmp_path: Path) -> None:
    ocean_drop = tmp_path / "ocean_drop.csv"
    _write_csv(
        ocean_drop,
        [
            {
                "№ заказа": "1001",
                "Склад передачи КД": "30137883_PP1",
                "Дата изменения статуса": "25.02.2026",
            },
            {
                "№ заказа": "1002",
                "Склад передачи КД": "30000001_PP1",
                "Дата изменения статуса": "",
                "Дата поступления заказа": "26.02.2026",
            },
            {
                "№ заказа": "1003",
                "Статус": "ОТМЕНЕН",
                "Склад передачи КД": "30000002_PP1",
                "Дата изменения статуса": "26.02.2026",
            },
        ],
    )

    df, meta = build_ocean_drop_snapshot_dataframe(
        ocean_drop_path=ocean_drop,
        as_of=date(2026, 2, 26),
        include_as_of_day=True,
        strict=True,
    )

    assert len(df) == 3
    assert set(df["store_code"]) == {"ACMEWEAR", "UNIVERSAL", "STOREB"}
    assert meta["date_source_counter"]["status_change_date"] == 2
    assert meta["date_source_counter"]["creation_date"] == 1

    df_cutoff, _ = build_ocean_drop_snapshot_dataframe(
        ocean_drop_path=ocean_drop,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        strict=True,
    )
    assert set(df_cutoff["order_id"]) == {"1001"}


def test_ocean_drop_parser_fails_closed_on_unknown_warehouse_in_strict_mode(tmp_path: Path) -> None:
    ocean_drop = tmp_path / "ocean_drop_unknown.csv"
    _write_csv(
        ocean_drop,
        [
            {
                "№ заказа": "9991",
                "Склад передачи КД": "UNKNOWN_WAREHOUSE",
            }
        ],
    )

    with pytest.raises(SnapshotError, match="unknown warehouse"):
        build_ocean_drop_snapshot_dataframe(
            ocean_drop_path=ocean_drop,
            as_of=date(2026, 2, 26),
            include_as_of_day=True,
            strict=True,
        )
