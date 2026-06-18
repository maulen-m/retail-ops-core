from __future__ import annotations

import csv
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from report_under_floor_leak import build_under_floor_leak_report


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE sales_fact_v2 (
                order_id TEXT NOT NULL,
                order_date DATE NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL,
                store_code TEXT DEFAULT 'UNIVERSAL',
                quantity INTEGER NOT NULL,
                sell_price_kzt REAL,
                status TEXT DEFAULT 'DELIVERED'
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, sell_price_kzt, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "2026-06-18", "LINE52", "LINE52_M", "M", "print", "UNIVERSAL", 1, 8000, "DELIVERED"),
                ("2", "2026-06-18", "LINE52", "LINE52_L", "L", "print", "UNIVERSAL", 1, 9000, "DELIVERED"),
                ("3", "2026-06-18", "LINE52", "LINE52_XL", "XL", "print", "UNIVERSAL", 1, 1, "CANCELLED"),
                ("4", "2026-06-18", "MISSING", "MISSING_M", "M", "missing", "STOREB", 2, 10000, "RETURNED"),
                ("5", "2026-06-18", "SUIT-31-TS", "SUIT-31-TS_XL", "XL", "suit", "ACMEWEAR", 1, 9490, "DELIVERED"),
            ],
        )


def _write_floor_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["SKU_key", "COGS", "Wt_kg", "AvgPrc_v7", "Min_price_35pct", "floor_source"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "SKU_key": "LINE52",
                "COGS": "5006",
                "Wt_kg": "0.95",
                "AvgPrc_v7": "9000",
                "Min_price_35pct": "8845",
                "floor_source": "fixture",
            }
        )
        writer.writerow(
            {
                "SKU_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "COGS": "5919",
                "Wt_kg": "1.1",
                "AvgPrc_v7": "15990",
                "Min_price_35pct": "10769",
                "floor_source": "fixture",
            }
        )


def _write_config(path: Path, db_path: Path, floor_path: Path) -> None:
    path.write_text(
        """
{
  "db_path": "%s",
  "floor_csv_path": "%s",
  "floor_version": "fixture",
  "window_days": 7,
  "max_sales_data_lag_days": 2,
  "excluded_status_tokens": ["CANCEL"],
  "floor_aliases": {
    "SUIT-31-TS": {
      "floor_sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
      "source": "fixture_alias"
    }
  },
  "strict_missing_floor_blocks_green": true,
  "strict_missing_price_blocks_green": true
}
"""
        % (db_path, floor_path),
        encoding="utf-8",
    )


def test_under_floor_report_detects_leaks_missing_floor_and_aliases(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    _write_floor_csv(floor_path)
    _write_config(config_path, db_path, floor_path)

    report = build_under_floor_leak_report(
        config_path=config_path,
        output_root=output_dir,
        as_of="2026-06-18",
    )

    assert report["gate"] == "RED"
    assert report["sales_source_table"] == "sales_fact_v2"
    assert report["sales_row_count_total"] == 5
    assert report["non_cancelled_row_count"] == 4
    assert report["under_floor_units"] == 2
    assert report["missing_floor_row_count"] == 1
    assert report["under_floor_gap_kzt"] == "2124.00"
    assert Path(report["artifacts"]["under_floor_sales_csv"]).exists()
    assert Path(report["artifacts"]["missing_floor_sales_csv"]).exists()


def test_under_floor_report_green_when_no_leaks_and_full_floor_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sales_fact_v2 SET sell_price_kzt = 12000 WHERE status <> 'CANCELLED'")
        conn.execute("UPDATE sales_fact_v2 SET sku_key = 'LINE52', sku_id = 'LINE52_M' WHERE sku_key = 'MISSING'")
    _write_floor_csv(floor_path)
    _write_config(config_path, db_path, floor_path)

    report = build_under_floor_leak_report(
        config_path=config_path,
        output_root=output_dir,
        as_of="2026-06-18",
    )

    assert report["gate"] == "GREEN"
    assert report["under_floor_units"] == 0
    assert report["missing_floor_row_count"] == 0
    assert all(check["ok"] for check in report["checks"])
