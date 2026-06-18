from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.report_g_met03_sku_contribution import build_sku_contribution_report


def _write_db(path: Path, *, with_sales: bool = True) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE view_sales_line_truth (
            order_id TEXT,
            sale_date TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            units REAL,
            net_rev_kzt REAL,
            cogs_kzt REAL,
            profit_kzt REAL
        );
        CREATE TABLE ads_spend_sidecar_daily_sku (
            date TEXT,
            store_code TEXT,
            sku_key TEXT,
            ads_cost_kzt REAL
        );
        """
    )
    if with_sales:
        conn.executemany(
            """
            INSERT INTO view_sales_line_truth(
                order_id, sale_date, store_code, sku_key, sku_id, my_size,
                units, net_rev_kzt, cogs_kzt, profit_kzt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "2026-06-16", "UNIVERSAL", "SKU_A", "SKU_A_S", "S", 2, 2000, 500, 700),
                ("2", "2026-06-16", "UNIVERSAL", "SKU_B", "SKU_B_M", "M", 1, 1000, 300, 250),
            ],
        )
        conn.execute(
            "INSERT INTO ads_spend_sidecar_daily_sku(date, store_code, sku_key, ads_cost_kzt) VALUES (?, ?, ?, ?)",
            ("2026-06-16", "UNIVERSAL", "SKU_A", 80),
        )
    conn.commit()
    conn.close()


def _write_config(path: Path, *, db_path: Path, require_full_inputs: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "SKU_CONTRIBUTION_DAILY_V1",
                "gate_id": "G-MET-03",
                "db_path": str(db_path),
                "max_latest_sales_lag_days": 2,
                "require_expected_return_loss_source": require_full_inputs,
                "require_handling_cost_source": require_full_inputs,
                "known_input_formula": "profit_kzt - mapped_ads_cost_kzt",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_known_input_contribution_is_armed_when_return_and_handling_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_config(config, db_path=db)

    report = build_sku_contribution_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:20:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["latest_sales_date"] == "2026-06-16"
    assert report["contribution_row_count"] == 2
    assert report["known_input_net_contribution_kzt"] == 870.0
    assert "expected_return_loss_source_missing" in report["measurement_blockers"]


def test_no_sales_rows_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db, with_sales=False)
    _write_config(config, db_path=db)

    report = build_sku_contribution_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("latest_sales_present" in blocker for blocker in report["blockers"])


def test_optional_full_inputs_can_green_for_fixture(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_config(config, db_path=db, require_full_inputs=False)

    report = build_sku_contribution_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:20:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["measurement_blockers"] == []
