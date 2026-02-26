from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.validate_sales_vs_waybill_parity import validate_sales_vs_waybill_parity


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _init_orders_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            quantity REAL
        );
        """
    )
    conn.executemany(
        "INSERT INTO fact_orders_kaspi (order_id, quantity) VALUES (?, ?)",
        [
            ("A1", 2),
            ("A2", 1),
            ("B1", 3),
        ],
    )
    conn.commit()
    conn.close()


def test_sales_vs_waybill_parity_passes_on_matching_snapshot(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    db_path = tmp_path / "db" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _init_orders_db(db_path)

    selection = tmp_path / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
    _write_json(
        selection,
        {
            "target_date": as_of,
            "include_overdue": True,
            "all_dates": False,
            "stores": {
                "ACMEWEAR": ["A1", "A2"],
                "UNIVERSAL": ["B1"],
            },
        },
    )

    business_snapshot = tmp_path / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.json"
    _write_json(
        business_snapshot,
        {
            "as_of": as_of,
            "waybill_snapshot": {
                "status": "available",
                "target_date": as_of,
                "stores": {
                    "ACMEWEAR": {"orders": 2, "units": 3},
                    "UNIVERSAL": {"orders": 1, "units": 3},
                },
            },
        },
    )

    report = validate_sales_vs_waybill_parity(
        project_root=tmp_path,
        as_of=as_of,
        db_path=db_path,
        selection_cache_path=selection,
        output_root=tmp_path / "exports" / "daily",
        business_snapshot_json=business_snapshot,
        strict=True,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_sales_vs_waybill_parity_fails_when_business_units_exceed_source(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    db_path = tmp_path / "db" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _init_orders_db(db_path)

    selection = tmp_path / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
    _write_json(
        selection,
        {
            "target_date": as_of,
            "include_overdue": True,
            "all_dates": False,
            "stores": {"ACMEWEAR": ["A1", "A2"]},
        },
    )
    business_snapshot = tmp_path / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.json"
    _write_json(
        business_snapshot,
        {
            "as_of": as_of,
            "waybill_snapshot": {
                "status": "available",
                "target_date": as_of,
                "stores": {"ACMEWEAR": {"orders": 3, "units": 10}},
            },
        },
    )

    with pytest.raises(RuntimeError, match="sales vs waybill parity validation failed"):
        validate_sales_vs_waybill_parity(
            project_root=tmp_path,
            as_of=as_of,
            db_path=db_path,
            selection_cache_path=selection,
            output_root=tmp_path / "exports" / "daily",
            business_snapshot_json=business_snapshot,
            strict=True,
        )
