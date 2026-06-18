from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_g_dark01_relist_state import build_dark_relist_state_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_scoreboard(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gate_id", "state", "evidence", "dated"])
        for gate_id, state in rows.items():
            writer.writerow([gate_id, state, "fixture", "20260618_1900"])


def _write_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL,
            inbound_stock INTEGER NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO fact_inventory_snapshot_size VALUES ('2026-06-17', ?, 'SKU', ?, ?, 0)",
        [
            ("SKU_S", "S", 5),
            ("SKU_L", "L", 0),
        ],
    )
    conn.commit()
    conn.close()


def _write_repricer(path: Path, *, include_s: bool = True, include_l: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE repricer_items (
            fetched_at TEXT,
            store_id INTEGER,
            store_name TEXT,
            row_id INTEGER,
            merchant_sku TEXT,
            kaspi_sku TEXT,
            merchant_title TEXT,
            link TEXT,
            price INTEGER,
            min_price INTEGER,
            max_price INTEGER,
            active INTEGER,
            is_available INTEGER,
            raw_json TEXT
        )
        """
    )
    rows = []
    if include_s:
        rows.append(("2026-06-18T19:00:00+05:00", 1, "STORE", 1, "SKU_S_1", "K1", "SKU S", "url-s", 100, 100, 200, 1, 1, "{}"))
    if include_l:
        rows.append(("2026-06-18T19:00:00+05:00", 1, "STORE", 2, "SKU_L_1", "K2", "SKU L", "url-l", 100, 100, 200, 1, 1, "{}"))
    conn.executemany("INSERT INTO repricer_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def _write_config(path: Path, *, db: Path, repricer: Path, scoreboard: Path) -> None:
    _write_json(
        path,
        {
            "contract_id": "DARK_FAMILY_RELIST_STATE_V1",
            "gate_id": "G-DARK-01",
            "db_path": str(db),
            "repricer_sqlite_path": str(repricer),
            "scoreboard_path": str(scoreboard),
            "dependency_gates": ["G-STOCK-03"],
            "max_repricer_age_days": 1,
            "families": [
                {
                    "family_id": "TEST",
                    "sku_key": "SKU",
                    "exclude_sizes": ["L"],
                    "owner_decision_id": "OD-033",
                }
            ],
        },
    )


def test_aligned_offer_state_can_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    repricer = tmp_path / "repricer.sqlite"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_repricer(repricer, include_s=True, include_l=False)
    _write_scoreboard(scoreboard, {"G-STOCK-03": "GREEN"})
    _write_config(config, db=db, repricer=repricer, scoreboard=scoreboard)

    report = build_dark_relist_state_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["missing_buyable_count"] == 0
    assert report["excluded_or_zero_stock_buyable_count"] == 0


def test_excluded_live_offer_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    repricer = tmp_path / "repricer.sqlite"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_repricer(repricer, include_s=True, include_l=True)
    _write_scoreboard(scoreboard, {"G-STOCK-03": "GREEN"})
    _write_config(config, db=db, repricer=repricer, scoreboard=scoreboard)

    report = build_dark_relist_state_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["excluded_or_zero_stock_buyable_count"] == 1


def test_missing_positive_stock_offer_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    repricer = tmp_path / "repricer.sqlite"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_repricer(repricer, include_s=False, include_l=False)
    _write_scoreboard(scoreboard, {"G-STOCK-03": "GREEN"})
    _write_config(config, db=db, repricer=repricer, scoreboard=scoreboard)

    report = build_dark_relist_state_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["missing_buyable_count"] == 1
