from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.kaspi_ads_bid_manager import execute_bid_manager, execute_bid_rollback, ensure_bid_schema


def _seed_current_bids(conn: sqlite3.Connection, *, bid: float = 70.0) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_product_daily_current (
            date TEXT,
            merchant_id TEXT,
            campaign_id TEXT,
            sku_key TEXT,
            bid_cpc REAL,
            PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO campaign_product_daily_current
        (date, merchant_id, campaign_id, sku_key, bid_cpc)
        VALUES ('2026-02-10', '759051', '2380614', '19796919b', ?)
        """,
        (bid,),
    )


def _seed_hourly_snapshot(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    sku_key: str,
    bid_cpc: float,
    snapshot_at: str,
    merchant_id: str = "759051",
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_at TEXT NOT NULL,
            snapshot_hour INTEGER NOT NULL,
            date TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            bid_cpc REAL
        )
        """
    )
    dt = datetime.fromisoformat(snapshot_at)
    conn.execute(
        """
        INSERT INTO hourly_snapshot (snapshot_at, snapshot_hour, date, merchant_id, campaign_id, sku_key, bid_cpc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_at,
            dt.hour,
            dt.date().isoformat(),
            merchant_id,
            campaign_id,
            sku_key,
            float(bid_cpc),
        ),
    )


def _rules(
    *,
    dry_run: bool = True,
    base_bid: float = 70.0,
    max_daily_changes: int = 2,
    max_step_change_kzt: float = 30.0,
) -> dict:
    return {
        "version": 1,
        "safety": {
            "dry_run": dry_run,
            "min_bid_kzt": 10,
            "max_bid_kzt": 200,
            "max_step_change_kzt": max_step_change_kzt,
            "max_daily_changes": max_daily_changes,
            "cooldown_minutes": 60,
            "require_env": "ENABLE_KASPI_ADS_WRITE",
        },
        "allowlist": [{"campaign_id": "2380614", "sku_key": "19796919b"}],
        "schedules": [
            {"name": "night_reduction", "start_hour": 2, "end_hour": 7, "multiplier": 0.5}
        ],
        "campaigns": {
            "2380614": {"base_bid": base_bid}
        },
    }


def test_bid_manager_dry_run_writes_audit_log(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=70.0)

        result = execute_bid_manager(
            conn,
            rules=_rules(dry_run=True, base_bid=70.0, max_step_change_kzt=100.0),
            now_local=datetime(2026, 2, 10, 3, 0, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )

        assert result["exit_code"] == 0
        assert result["proposed_changes"] == 1
        assert result["executed_changes"] == 0

        row = conn.execute(
            """
            SELECT old_bid, new_bid, dry_run, success, reason
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == 70.0
        assert row[1] == 35.0
        assert row[2] == 1
        assert row[3] == 1
        assert row[4] == "would_change"


def test_bid_manager_apply_requires_enable_env(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=70.0)

        result = execute_bid_manager(
            conn,
            rules=_rules(dry_run=False, base_bid=70.0),
            now_local=datetime(2026, 2, 10, 3, 0, 0),
            apply=True,
            env={},
            discovery_payload={"method": "PUT", "url": "https://example.test/bid"},
        )

        assert result["exit_code"] == 1
        assert "ENABLE_KASPI_ADS_WRITE=1" in result["error"]


def test_bid_manager_respects_max_step_and_caps(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=70.0)

        result = execute_bid_manager(
            conn,
            rules=_rules(dry_run=True, base_bid=400.0, max_step_change_kzt=30.0),
            now_local=datetime(2026, 2, 10, 12, 0, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )

        assert result["exit_code"] == 0

        row = conn.execute(
            """
            SELECT new_bid
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        # 400 -> clamp to max 200 -> max step +30 from current 70 => 100
        assert row[0] == 100.0


def test_bid_manager_respects_max_daily_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=70.0)

        conn.executemany(
            """
            INSERT INTO bid_change_log (
                executed_at, campaign_id, sku_key, old_bid, new_bid,
                rule_name, dry_run, success, method, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-10T02:00:00+05:00", "2380614", "19796919b", 70.0, 35.0, "night_reduction", 1, 1, "none", "would_change"),
                ("2026-02-10T03:00:00+05:00", "2380614", "19796919b", 35.0, 70.0, "restore", 1, 1, "none", "would_change"),
            ],
        )

        result = execute_bid_manager(
            conn,
            rules=_rules(dry_run=True, base_bid=70.0, max_daily_changes=2),
            now_local=datetime(2026, 2, 10, 4, 0, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )

        assert result["exit_code"] == 0
        assert result["skipped_daily_limit"] == 1


def test_bid_manager_rollback_uses_last_successful_old_bid(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=35.0)

        conn.execute(
            """
            INSERT INTO bid_change_log (
                executed_at, campaign_id, sku_key, old_bid, new_bid,
                rule_name, dry_run, success, method, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-10T02:00:00+05:00",
                "2380614",
                "19796919b",
                70.0,
                35.0,
                "night_reduction",
                1,
                1,
                "none",
                "would_change",
            ),
        )

        result = execute_bid_rollback(
            conn,
            rules=_rules(dry_run=True),
            now_local=datetime(2026, 2, 10, 8, 0, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )

        assert result["exit_code"] == 0
        assert result["rollback_candidates"] == 1
        assert result["rollback_applied"] == 1
        row = conn.execute(
            """
            SELECT old_bid, new_bid, reason
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == 35.0
        assert row[1] == 70.0
        assert row[2] == "would_rollback"


def test_bid_manager_restore_prefers_hourly_snapshot_bid_and_restores_pre_canary(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        # Stale daily source says 300, but latest hourly snapshot says 200 after reduction.
        _seed_current_bids(conn, bid=300.0)
        _seed_hourly_snapshot(
            conn,
            campaign_id="2380614",
            sku_key="19796919b",
            bid_cpc=200.0,
            snapshot_at="2026-02-14T03:05:00+05:00",
        )
        # Night reduction already happened: pre-canary bid was 300 -> reduced to 200.
        conn.execute(
            """
            INSERT INTO bid_change_log (
                executed_at, campaign_id, sku_key, old_bid, new_bid,
                rule_name, dry_run, success, method, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-14T03:00:00+05:00",
                "2380614",
                "19796919b",
                300.0,
                200.0,
                "night_reduction",
                0,
                1,
                "api",
                "applied",
            ),
        )

        restore_rules = {
            "version": 1,
            "safety": {
                "dry_run": True,
                "min_bid_kzt": 10,
                "max_bid_kzt": 200,
                "max_step_change_kzt": 30,
                "max_daily_changes": 3,
                "cooldown_minutes": 0,
                "require_env": "ENABLE_KASPI_ADS_WRITE",
            },
            "allowlist": [{"campaign_id": "2380614", "sku_key": "19796919b"}],
            "schedules": [
                {"name": "night_reduction", "start_hour": 2, "end_hour": 7, "multiplier": 0.5},
                {"name": "day_restore", "start_hour": 7, "end_hour": 24, "multiplier": 1.0},
            ],
            "campaigns": {"2380614": {"base_bid": 70.0}},
        }

        result = execute_bid_manager(
            conn,
            rules=restore_rules,
            now_local=datetime(2026, 2, 14, 7, 0, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )

        assert result["exit_code"] == 0
        assert result["proposed_changes"] == 1
        row = conn.execute(
            """
            SELECT old_bid, new_bid, rule_name, reason
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        # Current bid source must be hourly snapshot (200), not stale daily_current (300).
        assert row[0] == 200.0
        # Restore target must be the intended pre-canary bid from reduction history.
        assert row[1] == 300.0
        assert row[2] == "day_restore"
        assert row[3] == "would_change"


def test_bid_manager_falls_back_to_bid_change_log_then_daily_current(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=300.0)
        # No hourly_snapshot rows: current bid should come from last successful bid_change_log new_bid.
        conn.execute(
            """
            INSERT INTO bid_change_log (
                executed_at, campaign_id, sku_key, old_bid, new_bid,
                rule_name, dry_run, success, method, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-14T03:00:00+05:00",
                "2380614",
                "19796919b",
                300.0,
                200.0,
                "night_reduction",
                0,
                1,
                "api",
                "applied",
            ),
        )

        result = execute_bid_manager(
            conn,
            rules=_rules(dry_run=True, base_bid=70.0, max_step_change_kzt=1000.0),
            now_local=datetime(2026, 2, 14, 12, 0, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )
        assert result["exit_code"] == 0
        row = conn.execute(
            """
            SELECT old_bid
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == 200.0

        # Remove history too: should now fall back to daily_current.
        conn.execute("DELETE FROM bid_change_log")
        result2 = execute_bid_manager(
            conn,
            rules=_rules(dry_run=True, base_bid=70.0, max_step_change_kzt=1000.0),
            now_local=datetime(2026, 2, 14, 12, 30, 0),
            apply=False,
            env={},
            discovery_payload=None,
        )
        assert result2["exit_code"] == 0
        row2 = conn.execute(
            """
            SELECT old_bid
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row2 is not None
        assert row2[0] == 300.0


def test_bid_manager_live_apply_executes_with_injected_writer(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    captured: list[tuple[str, str, float]] = []

    def _writer(*, campaign_id: str, sku_key: str, new_bid: float, discovery_payload: dict) -> tuple[bool, str]:
        captured.append((campaign_id, sku_key, new_bid))
        assert discovery_payload["method"] == "PATCH"
        return True, ""

    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=70.0)

        result = execute_bid_manager(
            conn,
            rules=_rules(dry_run=False, base_bid=70.0, max_step_change_kzt=100.0),
            now_local=datetime(2026, 2, 10, 3, 0, 0),
            apply=True,
            env={"ENABLE_KASPI_ADS_WRITE": "1"},
            discovery_payload={"method": "PATCH", "url": "https://example.test/bid"},
            write_bid_fn=_writer,
        )

        assert result["exit_code"] == 0
        assert result["proposed_changes"] == 1
        assert result["executed_changes"] == 1
        assert len(captured) == 1
        assert captured[0][2] == 35.0

        row = conn.execute(
            """
            SELECT dry_run, success, reason, method
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[1] == 1
        assert row[2] == "applied"
        assert row[3] == "api"


def test_bid_manager_rollback_live_apply_executes_with_injected_writer(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    captured: list[tuple[str, str, float]] = []

    def _writer(*, campaign_id: str, sku_key: str, new_bid: float, discovery_payload: dict) -> tuple[bool, str]:
        captured.append((campaign_id, sku_key, new_bid))
        assert discovery_payload["method"] == "PATCH"
        return True, ""

    with sqlite3.connect(db_path) as conn:
        ensure_bid_schema(conn)
        _seed_current_bids(conn, bid=35.0)
        conn.execute(
            """
            INSERT INTO bid_change_log (
                executed_at, campaign_id, sku_key, old_bid, new_bid,
                rule_name, dry_run, success, method, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-10T02:00:00+05:00",
                "2380614",
                "19796919b",
                70.0,
                35.0,
                "night_reduction",
                1,
                1,
                "none",
                "would_change",
            ),
        )

        result = execute_bid_rollback(
            conn,
            rules=_rules(dry_run=False),
            now_local=datetime(2026, 2, 10, 8, 0, 0),
            apply=True,
            env={"ENABLE_KASPI_ADS_WRITE": "1"},
            discovery_payload={"method": "PATCH", "url": "https://example.test/bid"},
            write_bid_fn=_writer,
        )

        assert result["exit_code"] == 0
        assert result["rollback_candidates"] == 1
        assert result["rollback_applied"] == 1
        assert len(captured) == 1
        assert captured[0][2] == 70.0

        row = conn.execute(
            """
            SELECT dry_run, success, reason, method
            FROM bid_change_log
            ORDER BY change_id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[1] == 1
        assert row[2] == "rollback_applied"
        assert row[3] == "api"
