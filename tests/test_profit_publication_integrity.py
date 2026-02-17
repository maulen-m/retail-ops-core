from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from scripts.validate_profit_publication_integrity import (
    validate_profit_publication_integrity,
)


def _seed_sales_db(db_path: Path, *, include_unresolved: bool) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            cogs REAL,
            net_rev REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL
        );
        """
    )

    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU_OK', 100, 1.5)"
    )
    conn.execute(
        "INSERT INTO sales_fact_v2 (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag) "
        "VALUES ('ORD-1', '2026-02-08', 'SKU_OK', 'SKU_OK_XL', 1, 0, 20000, 'DELIVERED', 0)"
    )

    if include_unresolved:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU_BAD', 80, NULL)"
        )
        conn.execute(
            "INSERT INTO sales_fact_v2 (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag) "
            "VALUES ('ORD-2', '2026-02-08', 'SKU_BAD', 'SKU_BAD_L', 1, 0, 12000, 'DELIVERED', 0)"
        )

    conn.commit()
    conn.close()


def test_validator_fails_on_unresolved_rows_even_if_dashboard_locked(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_sales_db(db_path, include_unresolved=True)

    business_insides_path = tmp_path / "BUSINESS_INSIDES_2026-02-08.md"
    business_insides_path.write_text(
        "- Unresolved COGS rows: `1`.\n- Unresolved SKU count: `1`.\n",
        encoding="utf-8",
    )

    dashboard_path = tmp_path / "po_dashboard_data.json"
    dashboard_path.write_text(
        json.dumps(
            {
                "sku_level": [
                    {
                        "sku_key": "SKU_BAD",
                        "cogs_unresolved_rows": 1,
                        "profit_publishable": False,
                        "profit_unit": None,
                        "monthly_profit": None,
                        "roic_pct": None,
                        "profit_margin_pct": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = validate_profit_publication_integrity(
        db_path=db_path,
        as_of="2026-02-08",
        days=14,
        business_insides_path=business_insides_path,
        po_dashboard_path=dashboard_path,
    )

    assert report["ok"] is False
    assert any("unresolved COGS rows present" in err for err in report["errors"])
    assert report["leak_errors"] == []


def test_validator_flags_dashboard_profit_leak_for_unresolved_sku(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_sales_db(db_path, include_unresolved=True)

    business_insides_path = tmp_path / "BUSINESS_INSIDES_2026-02-08.md"
    business_insides_path.write_text(
        "- Unresolved COGS rows: `1`.\n- Unresolved SKU count: `1`.\n",
        encoding="utf-8",
    )

    dashboard_path = tmp_path / "po_dashboard_data.json"
    dashboard_path.write_text(
        json.dumps(
            {
                "sku_level": [
                    {
                        "sku_key": "SKU_BAD",
                        "cogs_unresolved_rows": 1,
                        "profit_publishable": True,
                        "profit_unit": 1500,
                        "monthly_profit": 12000,
                        "roic_pct": 18.5,
                        "profit_margin_pct": 20.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = validate_profit_publication_integrity(
        db_path=db_path,
        as_of="2026-02-08",
        days=14,
        business_insides_path=business_insides_path,
        po_dashboard_path=dashboard_path,
    )

    assert report["ok"] is False
    assert any("profit lock violated" in err for err in report["leak_errors"])


def test_validator_passes_when_no_unresolved_rows_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_sales_db(db_path, include_unresolved=False)

    business_insides_path = tmp_path / "BUSINESS_INSIDES_2026-02-08.md"
    business_insides_path.write_text(
        "- Unresolved COGS rows: `0`.\n- Unresolved SKU count: `0`.\n",
        encoding="utf-8",
    )

    dashboard_path = tmp_path / "po_dashboard_data.json"
    dashboard_path.write_text(json.dumps({"sku_level": []}), encoding="utf-8")

    report = validate_profit_publication_integrity(
        db_path=db_path,
        as_of="2026-02-08",
        days=14,
        business_insides_path=business_insides_path,
        po_dashboard_path=dashboard_path,
    )

    assert report["ok"] is True
    assert report["errors"] == []
