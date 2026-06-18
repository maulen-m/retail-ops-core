from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_g_dark02_recovery_slope import build_dark_recovery_slope_report


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
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            my_size TEXT,
            quantity INTEGER,
            status TEXT
        );
        """
    )
    conn.execute("INSERT INTO sales_fact_v2 VALUES ('o1', '2026-06-10', 'SKU', 'XL', 2, 'DELIVERED')")
    conn.commit()
    conn.close()


def _write_config(path: Path, *, db: Path, scoreboard: Path, relist_start: str | None = None) -> None:
    payload = {
        "contract_id": "DARK_RELIST_RECOVERY_SLOPE_V1",
        "gate_id": "G-DARK-02",
        "db_path": str(db),
        "scoreboard_path": str(scoreboard),
        "dependency_gates": ["G-DARK-01"],
        "families": [{"family_id": "TEST", "sku_key": "SKU"}],
        "baseline_start": "2026-06-01",
        "maturity_days": 30,
        "estimated_serviceable_flow_low_kzt_per_month": 198300,
        "estimated_serviceable_flow_high_kzt_per_month": 254200,
        "source_reference": "CN-054",
    }
    if relist_start:
        payload["relist_start"] = relist_start
    _write_json(path, payload)


def test_blocked_dependency_is_armed_with_baseline(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_scoreboard(scoreboard, {"G-DARK-01": "RED"})
    _write_config(config, db=db, scoreboard=scoreboard)

    report = build_dark_recovery_slope_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["baseline_units"] == 2
    assert any("dependency_gate_not_green:G-DARK-01=RED" in blocker for blocker in report["blockers"])


def test_mature_curve_can_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_scoreboard(scoreboard, {"G-DARK-01": "GREEN"})
    _write_config(config, db=db, scoreboard=scoreboard, relist_start="2026-05-01")

    report = build_dark_recovery_slope_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["mature_post_relist_days"] >= 30


def test_missing_sales_table_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    sqlite3.connect(db).close()
    _write_scoreboard(scoreboard, {"G-DARK-01": "GREEN"})
    _write_config(config, db=db, scoreboard=scoreboard)

    report = build_dark_recovery_slope_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "RED"
    assert "missing_table:sales_fact_v2" in report["fatal_errors"]
