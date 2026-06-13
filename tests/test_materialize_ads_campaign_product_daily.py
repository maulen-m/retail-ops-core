from __future__ import annotations

import sqlite3
from pathlib import Path
import csv

from scripts.materialize_ads_campaign_product_daily import materialize_ads_campaign_product_daily


def _app_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL,
            merchant_id TEXT,
            kaspi_article TEXT NOT NULL,
            sku_key TEXT,
            sku_id TEXT
        );
        CREATE TABLE ads_source_refresh_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            merchant_id TEXT,
            store_code TEXT NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            product_rows_total INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            notes_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE ads_campaign_product_daily (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT,
            sku_key TEXT NOT NULL DEFAULT '',
            cost_kzt REAL NOT NULL DEFAULT 0,
            impressions INTEGER,
            clicks INTEGER,
            source_run_id TEXT,
            coverage_status TEXT NOT NULL DEFAULT 'UNKNOWN',
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, store_code, campaign_id, sku_key)
        );
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date DATE NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            quantity INTEGER NOT NULL,
            status TEXT DEFAULT 'DELIVERED',
            return_flag INTEGER DEFAULT 0
        );
        INSERT INTO dim_kaspi_article_map (
            store_code, merchant_id, kaspi_article, sku_key, sku_id
        ) VALUES
          ('ACMEWEAR', '759051', 'ART-ACMEWEAR-1', 'SKU_ACMEWEAR', 'SKU_ACMEWEAR_M'),
          ('ACMEWEAR', '759051', 'ART-ZERO', 'SKU_ZERO', 'SKU_ZERO_M'),
          ('ACMEWEAR', '759051', 'ART-POSITIVE', 'SKU_POSITIVE', 'SKU_POSITIVE_M'),
          ('ACMEWEAR', '759051', 'ART-PARTIAL', 'SKU_PARTIAL', 'SKU_PARTIAL_M'),
          ('STOREB', '1065684', 'KASPI-PRODUCT-MAPPED', 'SKU_STOREB_MAPPED', 'SKU_STOREB_MAPPED_M');
        """
    )
    conn.commit()
    conn.close()


def _marketing_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_product_daily_current (
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            views INTEGER,
            clicks INTEGER,
            cost REAL,
            json_merchant_sku TEXT
        );
        INSERT INTO campaign_product_daily_current (
            date, merchant_id, store_code, campaign_id, campaign_name,
            sku_key, views, clicks, cost, json_merchant_sku
        ) VALUES
          ('2026-04-01', '759051', '30137883', 'C1', 'Campaign 1',
           'SRC1', 10, 1, 125.5, 'ART-ACMEWEAR-1'),
          ('2026-04-01', '759051', '30137883', 'C2', 'Campaign 2',
           'SRC2', 0, 0, 0.0, 'ART-ACMEWEAR-1'),
          ('2026-04-01', '759051', '30137883', 'C3', 'Campaign 3',
           'SRC3', 0, 0, 0.0, 'UNMAPPED-ARTICLE');
        """
    )
    conn.commit()
    conn.close()


def _webautomation_evidence_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_product_rows (
            window_id TEXT,
            date TEXT,
            start_date TEXT,
            end_date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            json_merchant_sku TEXT,
            views INTEGER,
            clicks INTEGER,
            cost REAL
        );
        INSERT INTO campaign_product_rows (
            window_id, date, start_date, end_date, merchant_id, store_code,
            campaign_id, campaign_name, sku_key, json_merchant_sku, views,
            clicks, cost
        ) VALUES
          ('aggregate', '', '2026-04-01', '2026-04-10', '759051', '30137883',
           'C_AGG', 'Aggregate Campaign', 'SRC_AGG', 'ART-ACMEWEAR-1', 100, 10, 500),
          ('daily_2026-04-02', '2026-04-02', '2026-04-02', '2026-04-02',
           '759051', '30137883', 'C_DAILY', 'Daily Campaign', 'SRC_DAILY',
           'ART-ACMEWEAR-1', 5, 1, 0);
        """
    )
    conn.commit()
    conn.close()


def _webautomation_aggregate_evidence_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE window_completeness (
            window_id TEXT,
            start_date TEXT,
            end_date TEXT,
            window_type TEXT,
            campaign_list_status TEXT,
            product_fetch_expected INTEGER,
            product_fetch_success INTEGER,
            product_fetch_errors INTEGER,
            completeness_status TEXT,
            supports_absence_no_spend_verified TEXT,
            fetched_at TEXT
        );
        CREATE TABLE campaign_product_rows (
            window_id TEXT,
            window_type TEXT,
            date TEXT,
            start_date TEXT,
            end_date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            json_merchant_sku TEXT,
            views INTEGER,
            clicks INTEGER,
            cost REAL,
            raw_path TEXT
        );
        INSERT INTO window_completeness (
            window_id, start_date, end_date, window_type, campaign_list_status,
            product_fetch_expected, product_fetch_success, product_fetch_errors,
            completeness_status, supports_absence_no_spend_verified, fetched_at
        ) VALUES
          ('full_store_window', '2026-04-01', '2026-04-10', 'aggregate', 'success',
           2, 2, 0, 'full_store_product_rows_complete', 'yes_for_downstream_sku_compare',
           '2026-05-05T09:27:57+05:00'),
          ('partial_window', '2026-04-20', '2026-04-20', 'aggregate', 'success',
           2, 1, 1, 'partial_or_targeted_only', 'no',
           '2026-05-05T09:27:57+05:00');
        INSERT INTO campaign_product_rows (
            window_id, window_type, date, start_date, end_date, merchant_id,
            store_code, campaign_id, campaign_name, sku_key, json_merchant_sku,
            views, clicks, cost, raw_path
        ) VALUES
          ('full_store_window', 'aggregate', '', '2026-04-01', '2026-04-10',
           '759051', '30137883', 'C_ZERO', 'Zero Campaign', 'SRC_ZERO',
           'ART-ZERO', 0, 0, 0.0, 'raw/full/campaign_zero.json'),
          ('full_store_window', 'aggregate', '', '2026-04-01', '2026-04-10',
           '759051', '30137883', 'C_POS', 'Positive Campaign', 'SRC_POS',
           'ART-POSITIVE', 15, 2, 50.0, 'raw/full/campaign_positive.json'),
          ('partial_window', 'aggregate', '', '2026-04-20', '2026-04-20',
           '759051', '30137883', 'C_PARTIAL', 'Partial Campaign', 'SRC_PARTIAL',
           'ART-PARTIAL', 0, 0, 0.0, 'raw/partial/campaign_partial.json');
        """
    )
    conn.commit()
    conn.close()


def _acmewear_gap_fill_evidence_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_product_daily (
            date TEXT,
            required_window TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            json_sku TEXT,
            json_merchant_sku TEXT,
            views TEXT,
            clicks TEXT,
            cost TEXT,
            source_completeness_class TEXT,
            evidence_source TEXT,
            raw_path TEXT,
            fetched_at TEXT
        );
        CREATE TABLE sku_daily_evidence_classification (
            date TEXT,
            required_window TEXT,
            target_sku_key TEXT,
            target_group TEXT,
            classification TEXT,
            supports_clear TEXT,
            evidence_source TEXT,
            matched_rows TEXT,
            matched_campaign_ids TEXT,
            matched_json_merchant_skus TEXT,
            cost_sum TEXT,
            views_sum TEXT,
            clicks_sum TEXT,
            raw_paths TEXT,
            notes TEXT
        );
        INSERT INTO campaign_product_daily (
            date, required_window, merchant_id, store_code, campaign_id,
            campaign_name, sku_key, json_sku, json_merchant_sku, views,
            clicks, cost, source_completeness_class, evidence_source,
            raw_path, fetched_at
        ) VALUES (
            '2026-05-04', 'post_0415', '759051', '30137883', 'C_POS',
            'Daily Campaign', '19796919b', '19796919b', 'ART-POSITIVE',
            '7', '2', '42.25', 'COVERED', 'kaspi_marketing_directapi_live',
            'raw/directapi/2026-05-04/campaign_C_POS_products.json',
            '2026-05-05T12:25:24+05:00'
        );
        INSERT INTO sku_daily_evidence_classification (
            date, required_window, target_sku_key, target_group,
            classification, supports_clear, evidence_source, matched_rows,
            matched_campaign_ids, matched_json_merchant_skus, cost_sum,
            views_sum, clicks_sum, raw_paths, notes
        ) VALUES (
            '2026-05-04', 'post_0415', 'SKU_ABSENT', 'line31',
            'ABSENT_FROM_FULL_STORE_DAILY_PRODUCT_UNIVERSE', 'yes',
            'kaspi_marketing_directapi_live', '0', '', '', '0', '0', '0',
            '[]', 'full-store product universe supports absence'
        );
        """
    )
    conn.commit()
    conn.close()


def _storeb_campaign_list_only_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_list_window (
            business_store_code TEXT,
            access_store_code TEXT,
            api_merchant_id TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            cost REAL
        );
        CREATE TABLE product_fetch_status (
            date TEXT,
            business_store_code TEXT,
            access_store_code TEXT,
            api_merchant_id TEXT,
            campaign_id TEXT,
            endpoint_status TEXT,
            product_rows INTEGER,
            blocker TEXT
        );
        INSERT INTO campaign_list_window VALUES (
            'STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', '1065684',
            '2609342', 'Line52_storeb_26.2.2026', 214671.0
        );
        INSERT INTO product_fetch_status VALUES (
            '2026-04-15', 'STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB',
            '1065684', '2609342', '429', 0, 'rate_limited'
        );
        """
    )
    conn.commit()
    conn.close()


def _storeb_campaign_daily_refresh_only_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_daily_current (
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            cost REAL
        );
        INSERT INTO campaign_daily_current VALUES (
            '2026-05-15', '1065684', 'STOREB',
            '2609342', 'Line52_storeb_26.2.2026', 1107.63
        );
        """
    )
    conn.commit()
    conn.close()


def _storeb_live_chrome_product_report_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_product_report_daily_live_chrome (
            business_store_code TEXT,
            access_store_code TEXT,
            selected_store_label TEXT,
            api_merchant_id TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            campaign_state TEXT,
            source_report_start_date TEXT,
            source_report_end_date TEXT,
            date TEXT,
            kaspi_product_code TEXT,
            product_name TEXT,
            product_status TEXT,
            merchant_article TEXT,
            merchant_sku TEXT,
            merchant_article_available TEXT,
            views TEXT,
            clicks TEXT,
            ad_cost_kzt TEXT,
            raw_payload_path TEXT,
            normalized_csv_path TEXT,
            source_captured_at TEXT,
            coverage_classification_source_grain TEXT
        );
        INSERT INTO campaign_product_report_daily_live_chrome (
            business_store_code, access_store_code, selected_store_label,
            api_merchant_id, campaign_id, campaign_name, campaign_state,
            source_report_start_date, source_report_end_date, date,
            kaspi_product_code, product_name, product_status, merchant_article,
            merchant_sku, merchant_article_available, views, clicks,
            ad_cost_kzt, raw_payload_path, normalized_csv_path,
            source_captured_at, coverage_classification_source_grain
        ) VALUES
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'ИП STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'KASPI-PRODUCT-MAPPED', 'Mapped Product', 'Активный', '',
           '', 'false', '10', '2', '25.50', 'raw/daily.csv',
           'campaign_product_daily_live_chrome.csv', '2026-05-05T10:20:59+05:00',
           'COVERED'),
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'ИП STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'KASPI-PRODUCT-UNMAPPED', 'Unmapped Product', 'Активный', '',
           '', 'false', '0', '0', '0.00', 'raw/daily.csv',
           'campaign_product_daily_live_chrome.csv', '2026-05-05T10:20:59+05:00',
           'NO_SPEND_VERIFIED');
        """
    )
    conn.commit()
    conn.close()


def _storeb_live_chrome_related_order_products_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE campaign_product_report_daily_live_chrome (
            business_store_code TEXT,
            access_store_code TEXT,
            selected_store_label TEXT,
            api_merchant_id TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            campaign_state TEXT,
            source_report_start_date TEXT,
            source_report_end_date TEXT,
            date TEXT,
            kaspi_product_code TEXT,
            product_name TEXT,
            product_status TEXT,
            merchant_article TEXT,
            merchant_sku TEXT,
            merchant_article_available TEXT,
            views TEXT,
            clicks TEXT,
            ad_cost_kzt TEXT,
            related_order_products TEXT,
            raw_payload_path TEXT,
            normalized_csv_path TEXT,
            source_captured_at TEXT,
            coverage_classification_source_grain TEXT
        );
        INSERT INTO campaign_product_report_daily_live_chrome (
            business_store_code, access_store_code, selected_store_label,
            api_merchant_id, campaign_id, campaign_name, campaign_state,
            source_report_start_date, source_report_end_date, date,
            kaspi_product_code, product_name, product_status, merchant_article,
            merchant_sku, merchant_article_available, views, clicks,
            ad_cost_kzt, related_order_products, raw_payload_path,
            normalized_csv_path, source_captured_at,
            coverage_classification_source_grain
        ) VALUES
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'IP STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'P_DIRECT_PRINT', 'Mapped Print Product A', 'Active', '',
           '', 'false', '10', '1', '10.00', 'ARTICLE_PRINT_A',
           'raw/daily.csv', 'campaign_product_daily_live_chrome.csv',
           '2026-05-05T10:20:59+05:00', 'COVERED'),
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'IP STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'P_ORDERENTRY_PRINT', 'Mapped Print Product B', 'Active', '',
           '', 'false', '7', '2', '20.00', 'ORDERENTRY_PRINT',
           'raw/daily.csv', 'campaign_product_daily_live_chrome.csv',
           '2026-05-05T10:20:59+05:00', 'COVERED'),
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'IP STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'P_HUS_ZERO', 'Mapped HUS Product', 'Active', '',
           '', 'false', '0', '0', '0.00', 'ARTICLE_HUS',
           'raw/daily.csv', 'campaign_product_daily_live_chrome.csv',
           '2026-05-05T10:20:59+05:00', 'NO_SPEND_VERIFIED'),
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'IP STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'P_CONFLICT', 'Conflicting Related Products', 'Active', '',
           '', 'false', '3', '1', '5.00', 'ARTICLE_PRINT_A, ARTICLE_HUS',
           'raw/daily.csv', 'campaign_product_daily_live_chrome.csv',
           '2026-05-05T10:20:59+05:00', 'COVERED'),
          ('STOREB', 'UNIVERSAL_SWITCHER_FOR_STOREB', 'IP STORE-B',
           '1065684', '2609342', 'Line52_storeb_26.2.2026', 'Enabled',
           '2026-04-15', '2026-04-15', '2026-04-15',
           'P_NO_TOKENS', 'No Related Products', 'Active', '',
           '', 'false', '0', '0', '0.00', '',
           'raw/daily.csv', 'campaign_product_daily_live_chrome.csv',
           '2026-05-05T10:20:59+05:00', 'NO_SPEND_VERIFIED');
        """
    )
    conn.commit()
    conn.close()


def _insert_sale(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    order_date: str,
    store_code: str,
    sku_key: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES (?, ?, ?, ?, 'M', ?, ?, 1, 'DELIVERED', 0)
        """,
        (order_id, order_date, sku_key, f"{sku_key}_M", sku_key, store_code),
    )


def test_ads_materializer_maps_source_rows_and_keeps_unmapped_blocked(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    marketing_db = tmp_path / "marketing.db"
    _app_db(app_db)
    _marketing_db(marketing_db)

    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[marketing_db],
        child_registry=None,
        stores=["ACMEWEAR", "STOREB"],
        start="2026-04-01",
        end="2026-04-01",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    rows = conn.execute(
        """
        SELECT campaign_id, sku_key, cost_kzt, coverage_status
        FROM ads_campaign_product_daily
        ORDER BY campaign_id
        """
    ).fetchall()
    refresh = conn.execute(
        "SELECT store_code, date_start, date_end, product_rows_total, status FROM ads_source_refresh_runs"
    ).fetchone()

    assert result["summary"]["mapped_rows"] == 2
    assert result["summary"]["unmapped_rows"] == 1
    assert rows == [
        ("C1", "SKU_ACMEWEAR", 125.5, "COVERED"),
        ("C2", "SKU_ACMEWEAR", 0.0, "NO_SPEND_VERIFIED"),
    ]
    assert refresh == ("ACMEWEAR", "2026-04-01", "2026-04-01", 3, "SUCCESS")


def test_ads_materializer_imports_webautomation_daily_rows_only(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "wa.sqlite"
    _app_db(app_db)
    _webautomation_evidence_db(evidence_db)

    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["ACMEWEAR"],
        start="2026-04-01",
        end="2026-04-10",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    rows = conn.execute(
        "SELECT date, campaign_id, cost_kzt, coverage_status FROM ads_campaign_product_daily"
    ).fetchall()

    assert result["summary"]["source_rows"] == 1
    assert rows == [("2026-04-02", "C_DAILY", 0.0, "NO_SPEND_VERIFIED")]


def test_ads_materializer_uses_completed_aggregate_window_for_no_spend_only(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "wa_aggregate.sqlite"
    _app_db(app_db)
    _webautomation_aggregate_evidence_db(evidence_db)

    conn = sqlite3.connect(str(app_db))
    _insert_sale(conn, order_id="ABSENT", order_date="2026-04-03", store_code="ACMEWEAR", sku_key="SKU_ABSENT")
    _insert_sale(conn, order_id="ZERO", order_date="2026-04-03", store_code="ACMEWEAR", sku_key="SKU_ZERO")
    _insert_sale(conn, order_id="POSITIVE", order_date="2026-04-03", store_code="ACMEWEAR", sku_key="SKU_POSITIVE")
    _insert_sale(conn, order_id="PARTIAL", order_date="2026-04-20", store_code="ACMEWEAR", sku_key="SKU_PARTIAL")
    conn.commit()
    conn.close()

    output_root = tmp_path / "evidence"
    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["ACMEWEAR"],
        start="2026-04-01",
        end="2026-04-20",
        output_root=output_root,
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    rows = conn.execute(
        """
        SELECT date, store_code, campaign_id, sku_key, cost_kzt, coverage_status, source_run_id
        FROM ads_campaign_product_daily
        ORDER BY sku_key
        """
    ).fetchall()
    refresh = conn.execute(
        """
        SELECT run_id, store_code, date_start, date_end, product_rows_total, status, notes_json
        FROM ads_source_refresh_runs
        """
    ).fetchone()
    conn.close()

    assert result["summary"]["aggregate_no_spend_rows"] == 2
    assert result["summary"]["aggregate_positive_spend_blocked"] == 1
    assert rows == [
        (
            "2026-04-03",
            "ACMEWEAR",
            "AGGREGATE_ABSENCE:full_store_window",
            "SKU_ABSENT",
            0.0,
            "NO_SPEND_VERIFIED",
            "agent20-ads-source-acmewear-full_store_window",
        ),
        (
            "2026-04-03",
            "ACMEWEAR",
            "AGGREGATE_ZERO:full_store_window",
            "SKU_ZERO",
            0.0,
            "NO_SPEND_VERIFIED",
            "agent20-ads-source-acmewear-full_store_window",
        ),
    ]
    assert refresh[:6] == (
        "agent20-ads-source-acmewear-full_store_window",
        "ACMEWEAR",
        "2026-04-01",
        "2026-04-10",
        2,
        "SUCCESS",
    )
    assert '"source_window_id": "full_store_window"' in refresh[6]
    assert '"raw/full/campaign_zero.json"' in refresh[6]

    with (output_root / "ads_campaign_product_daily_mapped.csv").open(newline="", encoding="utf-8") as handle:
        ledger_rows = list(csv.DictReader(handle))
    assert {row["source_window_id"] for row in ledger_rows} == {"full_store_window"}
    assert {row["aggregate_evidence_type"] for row in ledger_rows} == {
        "ABSENT_FROM_FULL_STORE_PRODUCT_UNIVERSE",
        "AGGREGATE_ZERO_PRODUCT_ROWS",
    }
    assert all(row["source_path"] == str(evidence_db) for row in ledger_rows)


def test_ads_materializer_imports_acmewear_gap_fill_daily_and_classification_rows(
    tmp_path: Path,
) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "acmewear_gap_fill.sqlite"
    _app_db(app_db)
    _acmewear_gap_fill_evidence_db(evidence_db)

    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["ACMEWEAR"],
        start="2026-05-04",
        end="2026-05-04",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    rows = conn.execute(
        """
        SELECT date, campaign_id, sku_key, cost_kzt, impressions, clicks, coverage_status
        FROM ads_campaign_product_daily
        ORDER BY sku_key
        """
    ).fetchall()
    refresh = conn.execute(
        """
        SELECT store_code, date_start, date_end, product_rows_total, status
        FROM ads_source_refresh_runs
        """
    ).fetchone()
    conn.close()

    assert result["summary"]["source_rows"] == 2
    assert result["summary"]["mapped_rows"] == 2
    assert result["summary"]["unmapped_rows"] == 0
    assert rows == [
        (
            "2026-05-04",
            "CLASSIFICATION:ABSENT_FROM_FULL_STORE_DAILY_PRODUCT_UNIVERSE:post_0415",
            "SKU_ABSENT",
            0.0,
            0,
            0,
            "NO_SPEND_VERIFIED",
        ),
        ("2026-05-04", "C_POS", "SKU_POSITIVE", 42.25, 7, 2, "COVERED"),
    ]
    assert refresh == ("ACMEWEAR", "2026-05-04", "2026-05-04", 2, "SUCCESS")


def test_ads_materializer_keeps_storeb_campaign_list_only_evidence_blocked(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "storeb.sqlite"
    _app_db(app_db)
    _storeb_campaign_list_only_db(evidence_db)

    conn = sqlite3.connect(str(app_db))
    _insert_sale(conn, order_id="STOREB-1", order_date="2026-04-15", store_code="STOREB", sku_key="SKU_STOREB")
    conn.commit()
    conn.close()

    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["STOREB"],
        start="2026-04-15",
        end="2026-04-15",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    product_count = conn.execute("SELECT COUNT(*) FROM ads_campaign_product_daily").fetchone()[0]
    refresh_count = conn.execute("SELECT COUNT(*) FROM ads_source_refresh_runs").fetchone()[0]
    conn.close()

    assert result["summary"]["mapped_rows"] == 0
    assert result["summary"]["aggregate_no_spend_rows"] == 0
    assert product_count == 0
    assert refresh_count == 0


def test_ads_materializer_imports_campaign_daily_refresh_only_when_explicitly_allowed(
    tmp_path: Path,
) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "storeb_campaign_daily.sqlite"
    _app_db(app_db)
    _storeb_campaign_daily_refresh_only_db(evidence_db)

    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["STOREB"],
        start="2026-05-15",
        end="2026-05-15",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
        allow_campaign_daily_refresh_only=True,
    )

    conn = sqlite3.connect(str(app_db))
    product_count = conn.execute("SELECT COUNT(*) FROM ads_campaign_product_daily").fetchone()[0]
    refresh = conn.execute(
        """
        SELECT run_id, store_code, date_start, date_end, product_rows_total, status
        FROM ads_source_refresh_runs
        """
    ).fetchone()
    conn.close()

    assert result["summary"]["refresh_only_rows"] == 1
    assert result["summary"]["mapped_rows"] == 0
    assert product_count == 0
    assert refresh == (
        "agent12-ads-source-storeb-2026-05-15",
        "STOREB",
        "2026-05-15",
        "2026-05-15",
        1,
        "SUCCESS",
    )


def test_ads_materializer_reads_live_chrome_rows_with_stable_product_code_mapping(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "storeb_live.sqlite"
    _app_db(app_db)
    _storeb_live_chrome_product_report_db(evidence_db)

    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["STOREB"],
        start="2026-04-15",
        end="2026-04-15",
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    product_rows = conn.execute(
        """
        SELECT date, store_code, campaign_id, sku_key, cost_kzt, coverage_status, source_run_id
        FROM ads_campaign_product_daily
        """
    ).fetchall()
    refresh = conn.execute(
        """
        SELECT run_id, store_code, date_start, date_end, product_rows_total, status
        FROM ads_source_refresh_runs
        """
    ).fetchone()
    conn.close()

    assert result["summary"]["source_rows"] == 2
    assert result["summary"]["mapped_rows"] == 1
    assert result["summary"]["unmapped_rows"] == 1
    assert product_rows == [
        (
            "2026-04-15",
            "STOREB",
            "2609342",
            "SKU_STOREB_MAPPED",
            25.5,
            "COVERED",
            "agent12-ads-source-storeb-2026-04-15",
        )
    ]
    assert refresh == (
        "agent12-ads-source-storeb-2026-04-15",
        "STOREB",
        "2026-04-15",
        "2026-04-15",
        2,
        "SUCCESS",
    )


def test_ads_materializer_uses_owner_product_code_sidecar_for_storeb_blockers(
    tmp_path: Path,
) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "storeb_live.sqlite"
    owner_map = tmp_path / "owner_product_code_map.csv"
    _app_db(app_db)
    _storeb_live_chrome_product_report_db(evidence_db)
    owner_map.write_text(
        "\n".join(
            [
                "business_store_code,kaspi_product_code,owner_selected_sku_key,decision_token,owner_response_quote",
                "STOREB,KASPI-PRODUCT-UNMAPPED,SKU_OWNER_LINE52,OWNER_CONFIRMED_TEST,all are Line52",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "evidence"
    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["STOREB"],
        start="2026-04-15",
        end="2026-04-15",
        output_root=output_root,
        apply=True,
        env_gate_value="1",
        owner_product_code_map_path=owner_map,
    )

    conn = sqlite3.connect(str(app_db))
    product_rows = conn.execute(
        """
        SELECT campaign_id, sku_key, cost_kzt, coverage_status
        FROM ads_campaign_product_daily
        ORDER BY sku_key
        """
    ).fetchall()
    conn.close()

    with (output_root / "storeb_product_code_mapping.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        mapping_rows = {
            row["kaspi_product_code"]: row
            for row in csv.DictReader(handle)
        }

    assert result["summary"]["owner_product_code_mappings_loaded"] == 1
    assert result["summary"]["mapped_rows"] == 2
    assert result["summary"]["unmapped_rows"] == 0
    assert product_rows == [
        ("2609342", "SKU_STOREB_MAPPED", 25.5, "COVERED"),
        ("2609342", "SKU_OWNER_LINE52", 0.0, "NO_SPEND_VERIFIED"),
    ]
    assert mapping_rows["KASPI-PRODUCT-UNMAPPED"]["mapping_status"] == "MAPPED"
    assert mapping_rows["KASPI-PRODUCT-UNMAPPED"]["mapping_method"] == (
        "OWNER_CONFIRMED_PRODUCT_CODE_MAP"
    )
    assert mapping_rows["KASPI-PRODUCT-UNMAPPED"]["sku_key"] == "SKU_OWNER_LINE52"


def test_ads_materializer_enriches_storeb_product_codes_from_exact_related_order_products(
    tmp_path: Path,
) -> None:
    app_db = tmp_path / "app.db"
    evidence_db = tmp_path / "storeb_related.sqlite"
    _app_db(app_db)
    _storeb_live_chrome_related_order_products_db(evidence_db)

    conn = sqlite3.connect(str(app_db))
    conn.executescript(
        """
        INSERT INTO dim_kaspi_article_map (
            store_code, merchant_id, kaspi_article, sku_key, sku_id
        ) VALUES
          ('STOREB', '30000002', 'ARTICLE_PRINT_A', 'SKU_PRINT', 'SKU_PRINT_M'),
          ('STOREB', '30000002', 'ARTICLE_HUS', 'SKU_HUS', 'SKU_HUS_M');
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            product_id TEXT,
            offer_id TEXT
        );
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT,
            sku_id TEXT
        );
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, product_id, offer_id
        ) VALUES (
            'E1', 'O1', 'STOREB', 'PRODUCT-ORDERENTRY-PRINT',
            'ORDERENTRY_PRINT'
        );
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, sku_key, sku_id
        ) VALUES (
            'O1', 'STOREB', 'SKU_PRINT', 'SKU_PRINT_L'
        );
        """
    )
    conn.commit()
    conn.close()

    output_root = tmp_path / "evidence"
    result = materialize_ads_campaign_product_daily(
        app_db=app_db,
        source_dbs=[evidence_db],
        child_registry=None,
        stores=["STOREB"],
        start="2026-04-15",
        end="2026-04-15",
        output_root=output_root,
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(app_db))
    product_rows = conn.execute(
        """
        SELECT date, store_code, campaign_id, sku_key, cost_kzt, impressions,
               clicks, coverage_status
        FROM ads_campaign_product_daily
        ORDER BY sku_key
        """
    ).fetchall()
    conn.close()

    with (output_root / "storeb_product_code_mapping.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        mapping_rows = {
            row["kaspi_product_code"]: row
            for row in csv.DictReader(handle)
        }
    with (output_root / "ads_campaign_product_daily_unmapped.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        unmapped_rows = list(csv.DictReader(handle))

    assert result["summary"]["source_rows"] == 5
    assert result["summary"]["mapped_rows"] == 2
    assert result["summary"]["mapped_source_rows"] == 3
    assert result["summary"]["unmapped_rows"] == 2
    assert product_rows == [
        (
            "2026-04-15",
            "STOREB",
            "2609342",
            "SKU_HUS",
            0.0,
            0,
            0,
            "NO_SPEND_VERIFIED",
        ),
        (
            "2026-04-15",
            "STOREB",
            "2609342",
            "SKU_PRINT",
            30.0,
            17,
            3,
            "COVERED",
        ),
    ]
    assert mapping_rows["P_DIRECT_PRINT"]["mapping_status"] == "MAPPED"
    assert mapping_rows["P_DIRECT_PRINT"]["sku_key"] == "SKU_PRINT"
    assert mapping_rows["P_ORDERENTRY_PRINT"]["mapping_method"] == "EXACT_ORDER_ENTRY_SALES_JOIN"
    assert mapping_rows["P_CONFLICT"]["mapping_status"] == "BLOCKED_CONFLICT"
    assert mapping_rows["P_NO_TOKENS"]["mapping_status"] == "BLOCKED_NO_RELATED_PRODUCTS"
    assert {row["reason"] for row in unmapped_rows} == {
        "ADS_MAPPING_CONFLICT",
        "ADS_MAPPING_MISSING",
    }
