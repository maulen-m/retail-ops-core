from __future__ import annotations

import csv
from pathlib import Path
import sqlite3

from scripts.report_g_dark01_mapping_resolution import build_mapping_resolution_report


def _write_preflight(path: Path) -> None:
    fieldnames = [
        "family_id",
        "sku_key",
        "size",
        "desired_state",
        "current_stock",
        "store",
        "source_state",
        "SKU",
        "price",
        "PP1",
        "PP2",
        "PP3",
        "PP4",
        "PP5",
        "preorder",
        "row_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for size, stock in (("S", "14"), ("3XL", "16")):
            writer.writerow(
                {
                    "family_id": "RUSH_WHITE",
                    "sku_key": "CL_NEW-CLO_MEN_RUSH_WHITE",
                    "size": size,
                    "desired_state": "BUYABLE",
                    "current_stock": stock,
                    "row_status": "MISSING_FROM_ACTIVE_AND_ARCHIVE",
                }
            )


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_article TEXT,
                kaspi_offer_name TEXT,
                kaspi_name_core TEXT,
                sku_key TEXT,
                sku_id TEXT,
                source TEXT,
                active_flag INTEGER
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, kaspi_name_core, sku_key, sku_id, source, active_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "UNIVERSAL",
                    "CL_NEW-CLO_MEN_RUSH_WHITE_L_149066048",
                    "Rashguard white S",
                    "RUSH white",
                    "CL_NEW-CLO_MEN_RUSH_WHITE",
                    "CL_NEW-CLO_MEN_RUSH_WHITE_M",
                    "fixture",
                    1,
                ),
                (
                    "UNIVERSAL",
                    "CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE_3XL_150318674",
                    "Rashguard white 3XL",
                    "Berserk rush white",
                    "CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE",
                    "CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE_3XL",
                    "fixture",
                    1,
                ),
            ],
        )


def _create_repricer_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE repricer_items (
                fetched_at TEXT,
                store_id INTEGER,
                store_name TEXT,
                merchant_sku TEXT,
                kaspi_sku TEXT,
                merchant_title TEXT,
                link TEXT,
                price INTEGER,
                min_price INTEGER,
                max_price INTEGER,
                active INTEGER,
                is_available INTEGER,
                preorder INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO repricer_items
            (fetched_at, store_id, store_name, merchant_sku, kaspi_sku, merchant_title, link, price, min_price, max_price, active, is_available, preorder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-19T11:53:00+05:00",
                30000001,
                "UNIVERSAL",
                "CL_NEW-CLO_MEN_RUSH_WHITE_L_149066048",
                "149066048",
                "Rashguard white S",
                "https://example.invalid",
                14990,
                14990,
                14990,
                1,
                1,
                0,
            ),
        )


def test_mapping_resolution_separates_title_drift_from_missing_catalog(tmp_path: Path) -> None:
    preflight = tmp_path / "preflight.csv"
    db_path = tmp_path / "app.db"
    repricer_path = tmp_path / "repricer.sqlite"
    _write_preflight(preflight)
    _create_db(db_path)
    _create_repricer_db(repricer_path)

    report = build_mapping_resolution_report(
        preflight_target_csv=preflight,
        db_path=db_path,
        repricer_db_path=repricer_path,
        output_root=tmp_path / "out",
        generated_at="2026-06-19T12:20:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["target_missing_sizes"] == ["S", "3XL"]
    assert report["external_writes_performed"] is False
    assert report["production_db_written"] is False
    assert report["route_counts"]["ARTICLE_MAP_OR_PRODUCT_TITLE_MAPPING_REVIEW"] == 1
    assert report["route_counts"]["DIFFERENT_PRODUCT_TITLE_MAPPING_REVIEW"] == 1
    rows = list(csv.DictReader(Path(report["resolution_csv"]).open(encoding="utf-8")))
    by_size = {row["size"]: row for row in rows}
    assert by_size["S"]["article_map_title_size_rows"] == "1"
    assert by_size["3XL"]["other_family_title_size_rows"] == "1"


def test_mapping_resolution_marks_true_catalog_gap(tmp_path: Path) -> None:
    preflight = tmp_path / "preflight.csv"
    db_path = tmp_path / "app.db"
    repricer_path = tmp_path / "repricer.sqlite"
    _write_preflight(preflight)
    _create_db(db_path)
    _create_repricer_db(repricer_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM dim_kaspi_article_map WHERE sku_key != 'CL_NEW-CLO_MEN_RUSH_WHITE'")

    report = build_mapping_resolution_report(
        preflight_target_csv=preflight,
        db_path=db_path,
        repricer_db_path=repricer_path,
        output_root=tmp_path / "out",
        generated_at="2026-06-19T12:21:00+05:00",
    )

    assert report["route_counts"]["OFFER_CREATION_OR_CATALOG_MISSING_REVIEW"] == 1
    assert "at least one missing size has no reusable mapping evidence" in report["blockers"]
