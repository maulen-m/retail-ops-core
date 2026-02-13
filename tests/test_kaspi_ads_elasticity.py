from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.kaspi_ads_elasticity import analyze_elasticity


def _seed_ads_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE campaign_product_daily_current (
                date TEXT,
                merchant_id TEXT,
                campaign_id TEXT,
                sku_key TEXT,
                bid_cpc REAL,
                clicks INTEGER,
                orders_total INTEGER,
                gmv REAL,
                cost REAL,
                PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO campaign_product_daily_current
            (date, merchant_id, campaign_id, sku_key, bid_cpc, clicks, orders_total, gmv, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-08", "759051", "2380614", "SKU-A", 30.0, 100, 10, 10000.0, 1000.0),
                ("2026-02-09", "759051", "2380614", "SKU-A", 30.0, 110, 9, 9800.0, 980.0),
                ("2026-02-10", "759051", "2380614", "SKU-A", 60.0, 150, 12, 12000.0, 2500.0),
                ("2026-02-11", "759051", "2380614", "SKU-A", 60.0, 155, 11, 11800.0, 2450.0),
            ],
        )


def _seed_ads_db_two_campaigns(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE campaign_product_daily_current (
                date TEXT,
                merchant_id TEXT,
                campaign_id TEXT,
                sku_key TEXT,
                bid_cpc REAL,
                clicks INTEGER,
                orders_total INTEGER,
                gmv REAL,
                cost REAL,
                PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO campaign_product_daily_current
            (date, merchant_id, campaign_id, sku_key, bid_cpc, clicks, orders_total, gmv, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-08", "759051", "2380614", "SKU-A", 30.0, 100, 10, 10000.0, 1000.0),
                ("2026-02-09", "759051", "2380614", "SKU-A", 60.0, 150, 12, 12000.0, 2500.0),
                ("2026-02-08", "759051", "2545773", "SKU-B", 40.0, 80, 8, 9000.0, 900.0),
                ("2026-02-09", "759051", "2545773", "SKU-B", 70.0, 95, 9, 10200.0, 1800.0),
            ],
        )


def _seed_app_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE fact_sales (
                order_date TEXT,
                sku_key TEXT,
                quantity INTEGER,
                sell_price_kzt REAL,
                profit_line REAL,
                cogs_line REAL
            )
            """
        )
        # Margin ~= 30%
        conn.executemany(
            """
            INSERT INTO fact_sales
            (order_date, sku_key, quantity, sell_price_kzt, profit_line, cogs_line)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-08", "SKU-A", 1, 1000.0, 300.0, 700.0),
                ("2026-02-09", "SKU-A", 1, 1000.0, 300.0, 700.0),
            ],
        )


def _write_cost_adjustments_config(
    path: Path,
    *,
    default_multiplier: float = 1.0,
    campaign_multiplier: float | None = None,
    campaign_multiplier_id: str = "2380614",
    discount_rule_multiplier: float | None = None,
    discount_campaign_id: str = "2380614",
) -> None:
    campaign_section = ""
    if campaign_multiplier is not None:
        campaign_section = f"""
campaign_multipliers:
  "{campaign_multiplier_id}":
    multiplier: {campaign_multiplier}
    reason: "campaign test adjustment"
"""
    rules_section = "rules: []"
    if discount_rule_multiplier is not None:
        rules_section = f"""
rules:
  - id: "TEST_DISCOUNT"
    enabled: true
    priority: 100
    start_date: "2026-02-01"
    end_date: "2026-02-28"
    multiplier: {discount_rule_multiplier}
    reason: "test discount rule"
    match:
      campaign_ids: ["{discount_campaign_id}"]
"""

    path.write_text(
        f"""version: 1
default_effective_cost_multiplier: {default_multiplier}
{campaign_section}
{rules_section}
""",
        encoding="utf-8",
    )


def test_analyze_elasticity_recommends_profit_best_bid(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    cost_cfg = tmp_path / "cost_adjustments.yaml"
    _seed_ads_db(ads_db)
    _seed_app_db(app_db)
    _write_cost_adjustments_config(cost_cfg)

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-10",
        min_days=1,
        default_margin_pct=0.25,
        cost_adjustments_config=cost_cfg,
    )

    assert result["level_rows"] == 2
    assert result["transition_rows"] == 1
    assert result["recommendation_rows"] == 1

    rec = result["recommendations"][0]
    assert rec["recommended_bid_cpc"] == 30.0
    assert rec["expected_profit_est_kzt"] > 0


def test_analyze_elasticity_falls_back_to_default_margin(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    cost_cfg = tmp_path / "cost_adjustments.yaml"
    _seed_ads_db(ads_db)
    # App DB without fact_sales table -> fallback margin
    with sqlite3.connect(app_db):
        pass
    _write_cost_adjustments_config(cost_cfg)

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-10",
        min_days=1,
        default_margin_pct=0.2,
        cost_adjustments_config=cost_cfg,
    )

    assert result["level_rows"] == 2
    assert result["economics_rows"] == 0
    assert result["recommendation_rows"] == 1


def test_analyze_elasticity_filters_campaign_ids(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    cost_cfg = tmp_path / "cost_adjustments.yaml"
    _seed_ads_db_two_campaigns(ads_db)
    _seed_app_db(app_db)
    _write_cost_adjustments_config(cost_cfg)

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-10",
        min_days=1,
        default_margin_pct=0.25,
        campaign_ids=["2545773"],
        cost_adjustments_config=cost_cfg,
    )

    assert result["recommendation_rows"] == 1
    rec = result["recommendations"][0]
    assert rec["campaign_id"] == "2545773"


def test_discount_policy_outputs_raw_and_effective_roic(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    cost_cfg = tmp_path / "cost_adjustments.yaml"
    _seed_ads_db(ads_db)
    _seed_app_db(app_db)
    _write_cost_adjustments_config(
        cost_cfg,
        default_multiplier=1.0,
        discount_rule_multiplier=0.7,
        discount_campaign_id="2380614",
    )

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-11",
        min_days=1,
        default_margin_pct=0.25,
        cost_adjustments_config=cost_cfg,
    )

    levels = pd.read_csv(out_dir / "kaspi_ads_elasticity_levels.csv")
    assert "ads_roic" in levels.columns
    assert "effective_ads_roic" in levels.columns
    assert "effective_cost_total" in levels.columns
    assert (levels["effective_cost_total"] < levels["cost_total"]).all()
    assert (levels["effective_ads_roic"] > levels["ads_roic"]).all()

    totals = result["totals"]
    assert totals["effective_cost_kzt"] < totals["raw_cost_kzt"]
    assert totals["effective_ads_roic"] > totals["raw_ads_roic"]


def test_report_transparency_logs_overrides(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    cost_cfg = tmp_path / "cost_adjustments.yaml"
    _seed_ads_db_two_campaigns(ads_db)
    _seed_app_db(app_db)
    _write_cost_adjustments_config(
        cost_cfg,
        campaign_multiplier=0.9,
        campaign_multiplier_id="2545773",
        discount_rule_multiplier=0.8,
        discount_campaign_id="2545773",
    )

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-10",
        min_days=1,
        default_margin_pct=0.25,
        cost_adjustments_config=cost_cfg,
    )

    report = result["cost_adjustments_report"]
    assert report["rows_total"] > 0
    assert report["rows_with_campaign_multiplier"] > 0
    assert report["rows_with_discount_rule"] > 0
    assert report["rows_with_any_adjustment"] > 0
    assert report["applied_rule_counts"].get("TEST_DISCOUNT", 0) > 0
    assert len(report["rules_defined"]) == 1
    assert result["outputs"]["cost_adjustments_audit_csv"].endswith("kaspi_ads_cost_adjustments_audit.csv")
    assert Path(result["outputs"]["cost_adjustments_audit_csv"]).exists()

    audit_df = pd.read_csv(result["outputs"]["cost_adjustments_audit_csv"])
    assert {"effective_cost_multiplier", "discount_rule_id", "campaign_cost_reason"}.issubset(set(audit_df.columns))
    assert "TEST_DISCOUNT" in set(audit_df["discount_rule_id"].astype(str))


def test_missing_cost_adjustments_config_fails_explicitly(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    _seed_ads_db(ads_db)
    _seed_app_db(app_db)

    missing_cfg = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError, match="Missing cost adjustments config"):
        analyze_elasticity(
            ads_db=ads_db,
            app_db=app_db,
            out_dir=out_dir,
            since="2026-02-01",
            until="2026-02-10",
            min_days=1,
            default_margin_pct=0.25,
            cost_adjustments_config=missing_cfg,
        )
