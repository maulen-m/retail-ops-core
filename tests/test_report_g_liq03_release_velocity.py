from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.report_g_liq03_release_velocity import build_release_velocity_report


TRANCHE_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "tier",
    "release_date",
    "initial_units",
    "released_units",
    "sold_units",
    "current_units",
    "floor_version",
    "stock_confidence",
    "rollback_price",
    "owner_decision_id",
    "stop_rule_status",
    "escalation_decision",
    "status",
    "notes",
]


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


def _write_tranche(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRANCHE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_lead_map(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "tranche_id",
        "sku_key",
        "size",
        "lead_store",
        "allowed_follower_stores",
        "effective_from",
        "source_artifact",
        "status",
        "owner_decision_id",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_config(path: Path, *, scoreboard: Path, tranche: Path, lead_map: Path) -> None:
    _write_json(
        path,
        {
            "contract_id": "LIQUIDATION_RELEASE_VELOCITY_V1",
            "gate_id": "G-LIQ-03",
            "scoreboard_path": str(scoreboard),
            "tranche_ledger_path": str(tranche),
            "lead_store_map_csv": str(lead_map),
            "liquidation_execution_gate": "G-LIQ-02",
            "required_row_fields": [
                "tranche_id",
                "sku_key",
                "tier",
                "release_date",
                "released_units",
                "sold_units",
                "floor_version",
                "stock_confidence",
                "rollback_price",
                "owner_decision_id",
            ],
            "tier_dwell_days": {"T1": 7, "T2": 10, "T3": 14},
            "min_sell_through_pct_for_escalation": 3.0,
            "parked_tiers": ["T4", "T5"],
        },
    )


def test_no_tranche_rows_is_armed(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    tranche = tmp_path / "tranche.csv"
    lead_map = tmp_path / "lead_map.csv"
    config = tmp_path / "config.json"
    _write_scoreboard(scoreboard, {"G-LIQ-02": "PENDING"})
    _write_tranche(tranche, [])
    _write_lead_map(lead_map, [])
    _write_config(config, scoreboard=scoreboard, tranche=tranche, lead_map=lead_map)

    report = build_release_velocity_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["active_tranche_rows"] == 0
    assert any("liquidation_gate_not_green:G-LIQ-02=PENDING" in blocker for blocker in report["blockers"])


def test_escalating_under_three_percent_sellthrough_is_red(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    tranche = tmp_path / "tranche.csv"
    lead_map = tmp_path / "lead_map.csv"
    config = tmp_path / "config.json"
    _write_scoreboard(scoreboard, {"G-LIQ-02": "GREEN"})
    _write_tranche(
        tranche,
        [
            {
                "tranche_id": "T1",
                "sku_key": "SKU",
                "size": "XL",
                "tier": "T1",
                "release_date": "2026-06-01",
                "initial_units": "100",
                "released_units": "100",
                "sold_units": "2",
                "current_units": "98",
                "floor_version": "v7",
                "stock_confidence": "GREEN",
                "rollback_price": "9990",
                "owner_decision_id": "OD-011",
                "stop_rule_status": "OPEN",
                "escalation_decision": "ADVANCE_TO_T2",
                "status": "ACTIVE",
                "notes": "fixture",
            }
        ],
    )
    _write_lead_map(
        lead_map,
        [
            {
                "tranche_id": "T1",
                "sku_key": "SKU",
                "size": "XL",
                "lead_store": "UNIVERSAL",
                "allowed_follower_stores": "",
                "effective_from": "2026-06-01",
                "source_artifact": "fixture",
                "status": "ACTIVE",
                "owner_decision_id": "OD-011",
                "notes": "fixture",
            }
        ],
    )
    _write_config(config, scoreboard=scoreboard, tranche=tranche, lead_map=lead_map)

    report = build_release_velocity_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["rule_violation_count"] == 1
    assert "under_min_sellthrough_escalated" in report["rule_violations"][0]["violation_reasons"]


def test_active_tranche_with_clean_rules_can_green(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    tranche = tmp_path / "tranche.csv"
    lead_map = tmp_path / "lead_map.csv"
    config = tmp_path / "config.json"
    _write_scoreboard(scoreboard, {"G-LIQ-02": "GREEN"})
    _write_tranche(
        tranche,
        [
            {
                "tranche_id": "T1",
                "sku_key": "SKU",
                "size": "XL",
                "tier": "T1",
                "release_date": "2026-06-01",
                "initial_units": "100",
                "released_units": "100",
                "sold_units": "12",
                "current_units": "88",
                "floor_version": "v7",
                "stock_confidence": "GREEN",
                "rollback_price": "9990",
                "owner_decision_id": "OD-011",
                "stop_rule_status": "OPEN",
                "escalation_decision": "HOLD",
                "status": "ACTIVE",
                "notes": "fixture",
            }
        ],
    )
    _write_lead_map(
        lead_map,
        [
            {
                "tranche_id": "T1",
                "sku_key": "SKU",
                "size": "XL",
                "lead_store": "UNIVERSAL",
                "allowed_follower_stores": "",
                "effective_from": "2026-06-01",
                "source_artifact": "fixture",
                "status": "ACTIVE",
                "owner_decision_id": "OD-011",
                "notes": "fixture",
            }
        ],
    )
    _write_config(config, scoreboard=scoreboard, tranche=tranche, lead_map=lead_map)

    report = build_release_velocity_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["active_tranche_rows"] == 1
    assert report["weighted_sell_through_pct"] == 12.0
