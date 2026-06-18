from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import yaml

from scripts.report_ads_campaign_crr_disposition import build_report, load_od019_rule


def _init_app_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
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
        CREATE TABLE fact_sales_daily (
            id INTEGER PRIMARY KEY,
            sale_date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            units INTEGER NOT NULL DEFAULT 0,
            revenue REAL NOT NULL DEFAULT 0,
            cogs REAL NOT NULL DEFAULT 0,
            profit REAL NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    rows = [
        ("2026-02-08", "ACMEWEAR", "C-KILL", "Bad", "SKU_BAD", 4000.0, "COVERED"),
        ("2026-02-08", "ACMEWEAR", "C-FIX", "Fix", "SKU_FIX", 250.0, "COVERED"),
        ("2026-02-08", "ACMEWEAR", "C-KEEP", "Keep", "SKU_KEEP", 100.0, "COVERED"),
        ("2026-02-08", "ACMEWEAR", "C-NOSPEND", "No Spend", "SKU_IDLE", 0.0, "NO_SPEND_VERIFIED"),
    ]
    conn.executemany(
        """
        INSERT INTO ads_campaign_product_daily
        (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, coverage_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.executemany(
        """
        INSERT INTO fact_sales_daily
        (sale_date, store_code, sku_key, units, revenue, cogs, profit)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-02-08", "ACMEWEAR", "SKU_BAD", 1, 1000.0, 900.0, 100.0),
            ("2026-02-08", "ACMEWEAR", "SKU_FIX", 1, 1000.0, 100.0, 900.0),
            ("2026-02-08", "ACMEWEAR", "SKU_KEEP", 1, 1000.0, 100.0, 900.0),
        ],
    )
    conn.commit()
    conn.close()


def _init_ads_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE campaign_daily_current (
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            state TEXT,
            daily_budget REAL,
            default_bid REAL,
            views INTEGER,
            clicks INTEGER,
            favorites INTEGER,
            carts INTEGER,
            ctr REAL,
            gmv REAL,
            transactions INTEGER,
            cost REAL,
            crr REAL,
            report_state TEXT,
            record_timestamp TEXT,
            ingested_at TEXT,
            PRIMARY KEY (date, merchant_id, campaign_id)
        );
        """
    )
    rows = [
        ("2026-02-08", "759051", "30137883", "C-KILL", "Bad", "Enabled", 1000.0, 0, 100, 10, 0, 0, 0, 1000.0, 1, 4000.0, 400.0),
        ("2026-02-08", "759051", "30137883", "C-FIX", "Fix", "Enabled", 1000.0, 0, 100, 10, 0, 0, 0, 1000.0, 1, 250.0, 25.0),
        ("2026-02-08", "759051", "30137883", "C-KEEP", "Keep", "Enabled", 1000.0, 0, 100, 10, 0, 0, 0, 1000.0, 1, 100.0, 10.0),
        ("2026-02-08", "759051", "30137883", "C-NOSPEND", "No Spend", "Paused", 1000.0, 0, 0, 0, 0, 0, 0, 0.0, 0, 0.0, 0.0),
    ]
    conn.executemany(
        """
        INSERT INTO campaign_daily_current
        (date, merchant_id, store_code, campaign_id, campaign_name, state, daily_budget, default_bid,
         views, clicks, favorites, carts, ctr, gmv, transactions, cost, crr, report_state, record_timestamp, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OK', '2026-02-09T00:00:00', '2026-02-09T00:00:00')
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _owner_decisions(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "owner_decisions": [
                    {
                        "id": "OD-019",
                        "params": {
                            "kill_crr_pct_14d": 35,
                            "kill_requires_negative_contribution": True,
                            "fix_band_crr_pct": [20, 35],
                        },
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _scope(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "default_active": False,
                "stores": {
                    "ACMEWEAR": {
                        "windows": [
                            {"start": "2026-01-01", "active": True, "coverage_mode": "advertised_products_only"}
                        ]
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_report_dispositions_and_outputs_are_read_only_report_mode(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.sqlite"
    owner = tmp_path / "owner.yaml"
    scope = tmp_path / "scope.yaml"
    out = tmp_path / "out"
    _init_app_db(app_db)
    _init_ads_db(ads_db)
    _owner_decisions(owner)
    _scope(scope)

    before_app = app_db.read_bytes()
    before_ads = ads_db.read_bytes()
    payload = build_report(
        app_db=app_db,
        ads_db=ads_db,
        as_of="2026-02-08",
        window_days=1,
        output_dir=out,
        owner_decisions=owner,
        scope_config=scope,
        report_only=True,
    )

    assert app_db.read_bytes() == before_app
    assert ads_db.read_bytes() == before_ads
    assert payload["summary"]["campaign_count"] == 4
    assert payload["summary"]["kill_recommended_count"] == 1
    assert payload["summary"]["fix_review_count"] == 1
    assert payload["summary"]["external_actions_required_count"] == 1
    assert (out / "daily_crr_report.csv").exists()
    assert (out / "campaign_disposition_log.csv").exists()
    assert (out / "ads_campaign_crr_report.json").exists()
    assert (out / "ads_campaign_crr_report.md").exists()

    by_campaign = {row["campaign_id"]: row for row in _rows(out / "daily_crr_report.csv")}
    assert by_campaign["C-KILL"]["disposition"] == "KILL_RECOMMENDED_REPORT_ONLY"
    assert by_campaign["C-KILL"]["action_status"] == "REPORT_ONLY_PENDING_EXTERNAL_APPLY"
    assert by_campaign["C-FIX"]["disposition"] == "FIX_REVIEW"
    assert by_campaign["C-KEEP"]["disposition"] == "KEEP"
    assert by_campaign["C-NOSPEND"]["disposition"] == "PAUSED_NO_SPEND"


def test_default_as_of_uses_min_of_app_and_source_max_dates(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.sqlite"
    owner = tmp_path / "owner.yaml"
    scope = tmp_path / "scope.yaml"
    out = tmp_path / "out"
    _init_app_db(app_db)
    _init_ads_db(ads_db)
    _owner_decisions(owner)
    _scope(scope)
    conn = sqlite3.connect(ads_db)
    conn.execute(
        """
        INSERT INTO campaign_daily_current
        (date, merchant_id, store_code, campaign_id, campaign_name, state, daily_budget, default_bid,
         views, clicks, favorites, carts, ctr, gmv, transactions, cost, crr, report_state, record_timestamp, ingested_at)
        VALUES ('2026-02-09', '759051', '30137883', 'C-KEEP', 'Keep', 'Enabled', 1000, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 'OK', '2026-02-09T01:00:00', '2026-02-09T01:00:00')
        """
    )
    conn.commit()
    conn.close()

    payload = build_report(
        app_db=app_db,
        ads_db=ads_db,
        as_of=None,
        window_days=1,
        output_dir=out,
        owner_decisions=owner,
        scope_config=scope,
        report_only=True,
    )

    assert payload["as_of"] == "2026-02-08"


def test_owner_decision_loader_extracts_od019_from_malformed_decision_file(tmp_path: Path) -> None:
    path = tmp_path / "owner.yaml"
    path.write_text(
        """
owner_decisions:
  - id: OD-020
    params: { cap_kzt_per_day: 10000 }
  - id: OD-019
    title: campaign_kill_fix_thresholds
    answer: RECOMMENDED
    params: { kill_crr_pct_14d: 35, kill_requires_negative_contribution: true, fix_band_crr_pct: [20, 35] }
broken:
  file: DEFERRED_QUEUE.md
  - id: BAD
""",
        encoding="utf-8",
    )

    rule = load_od019_rule(path)

    assert rule.kill_crr_pct_14d == 35
    assert rule.kill_requires_negative_contribution is True
    assert rule.fix_band_min_pct == 20
    assert rule.fix_band_max_pct == 35
