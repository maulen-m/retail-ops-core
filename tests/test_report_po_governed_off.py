from __future__ import annotations

import json
from pathlib import Path
import plistlib
import sqlite3

from scripts.report_po_governed_off import build_po_governed_off_report


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "PO_GOVERNED_OFF_V1",
                "policy_id": "OD-009",
                "mode": "governed_off",
                "auto_po_restart_permitted": False,
                "auto_draft_creation_allowed": False,
                "manual_po_gate_mode": "advisory",
                "proposal_artifacts_are_advisory_only": True,
                "stop_buy_gates": [
                    {"id": "frozen_cover_gt_180d"},
                    {"id": "size_overstock"},
                    {"id": "return_qc_telemetry"},
                    {"id": "ppch_v1_gate"},
                    {"id": "cash_truth_gate"},
                    {"id": "ads_crr_gate"},
                ],
                "restart_requires": [
                    "cogs_green_30d",
                    "stock_green_30d",
                    "cash_green",
                    "fx_floor_vintage_green",
                    "priors_7of7_tests",
                    "forecast_backtest_pass_threshold_set_at_acceptance",
                    "owner_approval",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_owner_decisions(path: Path) -> None:
    path.write_text(
        """
decisions:
  - id: OD-009
    title: auto_po_governed_off
    answer: RECOMMENDED
    params: { restart_requires: [cogs_green_30d, stock_green_30d, cash_green, fx_floor_vintage_green, priors_7of7_tests, forecast_backtest_pass_threshold_set_at_acceptance, owner_approval], stop_buy_gates_advisory_on_manual_pos: true }
""".lstrip(),
        encoding="utf-8",
    )


def _init_db(path: Path, *, draft_rows: int = 0) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE fact_po_draft (draft_id INTEGER PRIMARY KEY);
            CREATE TABLE fact_po_draft_lines (line_id INTEGER PRIMARY KEY);
            CREATE TABLE fact_po_execution (execution_id INTEGER PRIMARY KEY);
            CREATE TABLE fact_sku_metrics (computed_at TEXT);
            INSERT INTO fact_sku_metrics VALUES ('2025-12-06 05:30:55');
            """
        )
        for i in range(draft_rows):
            conn.execute("INSERT INTO fact_po_draft (draft_id) VALUES (?)", (i + 1,))
        conn.commit()
    finally:
        conn.close()


def test_governed_off_report_passes_without_subvalidators(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    config_path = tmp_path / "config.json"
    decisions_path = tmp_path / "decisions.yaml"
    launchagents = tmp_path / "LaunchAgents"
    launchagents.mkdir()
    _init_db(db_path)
    _write_config(config_path)
    _write_owner_decisions(decisions_path)

    report = build_po_governed_off_report(
        as_of="2026-06-17",
        db_path=db_path,
        config_path=config_path,
        owner_decisions_path=decisions_path,
        output_root=tmp_path / "out",
        launchagent_dir=launchagents,
        run_subvalidators=False,
    )

    assert report["status"] == "GREEN"
    assert report["po_table_counts"] == {
        "fact_po_draft": 0,
        "fact_po_draft_lines": 0,
        "fact_po_execution": 0,
    }
    assert Path(report["json_path"]).exists()


def test_governed_off_report_fails_when_drafts_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    config_path = tmp_path / "config.json"
    decisions_path = tmp_path / "decisions.yaml"
    launchagents = tmp_path / "LaunchAgents"
    launchagents.mkdir()
    _init_db(db_path, draft_rows=1)
    _write_config(config_path)
    _write_owner_decisions(decisions_path)

    report = build_po_governed_off_report(
        as_of="2026-06-17",
        db_path=db_path,
        config_path=config_path,
        owner_decisions_path=decisions_path,
        output_root=tmp_path / "out",
        launchagent_dir=launchagents,
        run_subvalidators=False,
    )

    assert report["status"] == "RED"
    assert any(row["check"] == "po_draft_tables_empty" and not row["ok"] for row in report["checks"])


def test_governed_off_report_fails_on_auto_po_launchagent(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    config_path = tmp_path / "config.json"
    decisions_path = tmp_path / "decisions.yaml"
    launchagents = tmp_path / "LaunchAgents"
    launchagents.mkdir()
    _init_db(db_path)
    _write_config(config_path)
    _write_owner_decisions(decisions_path)
    plist_path = launchagents / "com.example.auto-po.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.example.auto-po",
                "ProgramArguments": ["python3", "scripts/run_auto_po.py"],
            }
        )
    )

    report = build_po_governed_off_report(
        as_of="2026-06-17",
        db_path=db_path,
        config_path=config_path,
        owner_decisions_path=decisions_path,
        output_root=tmp_path / "out",
        launchagent_dir=launchagents,
        run_subvalidators=False,
    )

    assert report["status"] == "RED"
    assert any(row["check"] == "auto_po_launchagent_absent" and not row["ok"] for row in report["checks"])
