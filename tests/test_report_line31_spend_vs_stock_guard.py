from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

from scripts.report_line31_spend_vs_stock_guard import report_line31_spend_vs_stock_guard


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _create_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE ads_campaign_product_daily (
                date TEXT NOT NULL,
                store_code TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                campaign_name TEXT,
                sku_key TEXT NOT NULL DEFAULT '',
                cost_kzt REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE fact_inventory_snapshot_size (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                current_stock INTEGER NOT NULL DEFAULT 0,
                inbound_stock INTEGER NOT NULL DEFAULT 0
            );
            """
        )


def _seed_stock(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            )
            VALUES ('2026-06-16', ?, ?, ?, ?, 0)
            """,
            [
                ("LINE31_BLACK_S", "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK", "S", 0),
                ("LINE31_BLACK_M", "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK", "M", -1),
                ("LINE31_BLACK_L", "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK", "L", 4),
                ("LINE31_BLUE_L", "CL_OF_ARC_WM_LINE31_C-025_WHALE-BLUE", "L", 4),
            ],
        )


def test_zero_spend_with_zero_stock_is_green_and_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_schema(db_path)
    _seed_stock(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily (
                date, store_code, campaign_id, campaign_name, sku_key, cost_kzt
            )
            VALUES (
                '2026-06-16', 'ACMEWEAR', '2695637', 'LINE31_ST',
                'CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK', 0
            )
            """
        )

    before = _sha256(db_path)
    payload = report_line31_spend_vs_stock_guard(
        db_path=db_path,
        as_of=date(2026, 6, 17),
        start=date(2026, 6, 1),
        end=date(2026, 6, 16),
        output_root=tmp_path / "out",
        run_id="green",
    )
    after = _sha256(db_path)

    assert before == after
    assert payload["gate"] == "GREEN"
    assert payload["summary"]["positive_line31_ad_rows"] == 0
    assert payload["summary"]["zero_or_negative_stock_rows"] == 2
    assert payload["summary"]["violation_rows"] == 0
    assert Path(payload["output_files"]["report_json"]).exists()
    assert Path(payload["output_files"]["violations_csv"]).exists()


def test_positive_spend_against_zero_size_is_yellow(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_schema(db_path)
    _seed_stock(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily (
                date, store_code, campaign_id, campaign_name, sku_key, cost_kzt
            )
            VALUES (
                '2026-06-16', 'ACMEWEAR', '2695637', 'LINE31_ST',
                'CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK', 100
            )
            """
        )

    payload = report_line31_spend_vs_stock_guard(
        db_path=db_path,
        as_of=date(2026, 6, 17),
        start=date(2026, 6, 1),
        end=date(2026, 6, 16),
        output_root=tmp_path / "out",
        run_id="yellow",
    )

    assert payload["gate"] == "YELLOW"
    assert payload["summary"]["positive_line31_ad_rows"] == 1
    assert payload["summary"]["violation_rows"] == 1


def test_positive_spend_without_stock_evidence_is_yellow(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_schema(db_path)
    _seed_stock(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily (
                date, store_code, campaign_id, campaign_name, sku_key, cost_kzt
            )
            VALUES (
                '2026-06-16', 'ACMEWEAR', '999', 'LINE31_UNKNOWN',
                'CL_OF_ARC_WM_LINE31_UNKNOWN', 10
            )
            """
        )

    payload = report_line31_spend_vs_stock_guard(
        db_path=db_path,
        as_of=date(2026, 6, 17),
        start=date(2026, 6, 1),
        end=date(2026, 6, 16),
        output_root=tmp_path / "out",
        run_id="missing_stock",
    )

    assert payload["gate"] == "YELLOW"
    assert payload["summary"]["violation_rows"] == 1
