from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from scripts.validate_webui_archive_vs_current_db import validate_webui_archive_vs_current_db


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                order_date TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                kaspi_offer_name TEXT,
                store_code TEXT,
                quantity REAL,
                net_rev REAL,
                cogs REAL,
                profit REAL,
                status TEXT,
                return_flag INTEGER,
                return_date TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT,
                store_code TEXT,
                sale_date TEXT,
                quantity REAL,
                net_rev_kzt REAL
            )
            """
        )
        conn.execute(
            """
            CREATE VIEW view_sales_line_truth AS
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                date(order_date) AS sale_date,
                UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                COALESCE(sku_key, '') AS sku_key,
                COALESCE(sku_id, '') AS sku_id,
                COALESCE(my_size, '') AS my_size,
                CAST(COALESCE(quantity, 0) AS REAL) AS units,
                CAST(COALESCE(net_rev, 0) AS REAL) AS net_rev_kzt,
                CAST(COALESCE(cogs, 0) AS REAL) AS cogs_kzt,
                CAST(COALESCE(profit, 0) AS REAL) AS profit_kzt,
                'unresolved' AS cogs_source
            FROM sales_fact_v2
            WHERE UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_ledger(root: Path, *, order_id: str, store_code: str, delivered_at: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ledger_manifest.json").write_text(
        json.dumps({"run_id": "test_ledger"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "webui_status_ledger.csv").write_text(
        "\n".join(
            [
                "store_code,order_id,status_internal,status_change_at,created_at,delivered_at,returned_at,first_seen_pack,last_seen_pack",
                f"{store_code},{order_id},DELIVERED,{delivered_at},{delivered_at},{delivered_at},,pack,pack",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_validate_webui_vs_current_db_treats_returned_workbook_lineage_as_not_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, net_rev, cogs, profit, status, return_flag, return_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "832677455",
                "2026-03-07",
                "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "CL_NEW-CLO2_MEN_SUIT-61_BLACK_2XL",
                "2XL",
                "OF_SUIT-61_BLK_2XL",
                "ACMEWEAR",
                1,
                13483.0,
                0.0,
                13483.0,
                "RETURNED",
                1,
                "2026-03-07",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_sales_workbook_anchor(order_id, store_code, sale_date, quantity, net_rev_kzt)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("832677455", "ACMEWEAR", "2026-02-23", 1.0, 11963.25),
        )
        conn.commit()
    finally:
        conn.close()

    ledger_root = tmp_path / "ledger"
    _write_ledger(ledger_root, order_id="832677455", store_code="ACMEWEAR", delivered_at="2026-02-26")
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-02-28",
        db_path=db,
        ledger_root=ledger_root,
        output_dir=output_dir,
        strict=False,
    )

    assert report["status"] == "PASS"
    assert report["missing_in_db_orders"] == 0
    assert report["original_missing_in_db_orders"] == 1


def test_validate_webui_vs_current_db_keeps_true_missing_as_hard_failure(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    ledger_root = tmp_path / "ledger"
    _write_ledger(ledger_root, order_id="832677455", store_code="ACMEWEAR", delivered_at="2026-02-26")
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-02-28",
        db_path=db,
        ledger_root=ledger_root,
        output_dir=output_dir,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["missing_in_db_orders"] == 1


def test_validate_webui_vs_current_db_treats_explicit_db_only_quarantine_as_not_blocking(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, net_rev, cogs, profit, status, return_flag, return_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "829586572",
                "2026-02-20",
                "SKU",
                "SKU_ID",
                "M",
                "Offer",
                "UNIVERSAL",
                1,
                1000.0,
                500.0,
                500.0,
                "DELIVERED",
                0,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    ledger_root = tmp_path / "ledger"
    (ledger_root / "ledger_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps({"run_id": "test_ledger"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (ledger_root / "webui_status_ledger.csv").write_text(
        "store_code,order_id,status_internal,status_change_at,created_at,delivered_at,returned_at,first_seen_pack,last_seen_pack\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "db_quarantine_candidates.csv").write_text(
        "\n".join(
            [
                "order_id,store_code,quarantine_bucket,reason",
                "829586572,UNIVERSAL,DB_ONLY_NO_WEBUI_LINEAGE,explicit contract-backed quarantine",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-02-28",
        db_path=db,
        ledger_root=ledger_root,
        output_dir=output_dir,
        strict=False,
    )

    assert report["status"] == "PASS"
    assert report["db_only_orders"] == 0
    assert report["quarantined_orders"] == 1


def test_validate_webui_vs_current_db_full_range_policy_treats_historical_and_returned_cases_as_diagnostic(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, net_rev, cogs, profit, status, return_flag, return_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "900000001",
                "2026-03-07",
                "SKU",
                "SKU_ID",
                "M",
                "Offer",
                "UNIVERSAL",
                1,
                1200.0,
                500.0,
                700.0,
                "RETURNED",
                1,
                "2026-03-07",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_sales_workbook_anchor(order_id, store_code, sale_date, quantity, net_rev_kzt)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("900000001", "UNIVERSAL", "2026-03-01", 1.0, 1200.0),
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2(
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, net_rev, cogs, profit, status, return_flag, return_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "900000777",
                "2026-03-03",
                "SKU",
                "SKU_ID",
                "L",
                "Offer",
                "STOREB",
                1,
                2200.0,
                1000.0,
                1200.0,
                "DELIVERED",
                0,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    ledger_root = tmp_path / "ledger"
    ledger_root.mkdir(parents=True, exist_ok=True)
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps({"run_id": "test_ledger"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (ledger_root / "webui_status_ledger.csv").write_text(
        "\n".join(
            [
                "store_code,order_id,status_internal,status_change_at,created_at,delivered_at,returned_at,first_seen_pack,last_seen_pack",
                "UNIVERSAL,900000001,DELIVERED,2026-03-01,2026-02-28,2026-03-01,,pack,pack",
                "ACMEWEAR,900000123,DELIVERED,2025-07-01,2025-06-29,2025-07-01,,pack,pack",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = validate_webui_archive_vs_current_db(
        start="2025-06-06",
        end="2026-03-09",
        db_path=db,
        ledger_root=ledger_root,
        output_dir=output_dir,
        strict=False,
        range_policy="full_range_owner_truth",
        statusdate_cutover="2026-02-27",
    )

    assert report["status"] == "PASS"
    assert report["missing_in_db_orders"] == 0
    assert report["historical_diagnostic_missing_orders"] == 1
    assert report["current_state_surface_mismatch_orders"] == 1
    assert report["db_only_orders"] == 0
    assert report["diagnostic_db_only_orders"] == 1


def test_validate_webui_vs_current_db_full_range_policy_keeps_true_post_cutover_missing_hard(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    ledger_root = tmp_path / "ledger"
    _write_ledger(ledger_root, order_id="900000888", store_code="ACMEWEAR", delivered_at="2026-03-01")
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = validate_webui_archive_vs_current_db(
        start="2025-06-06",
        end="2026-03-09",
        db_path=db,
        ledger_root=ledger_root,
        output_dir=output_dir,
        strict=False,
        range_policy="full_range_owner_truth",
        statusdate_cutover="2026-02-27",
    )

    assert report["status"] == "FAIL"
    assert report["missing_in_db_orders"] == 1
    assert report["post_cutover_hard_missing_orders"] == 1
