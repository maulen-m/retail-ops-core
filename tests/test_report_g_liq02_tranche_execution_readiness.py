from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.report_g_liq02_tranche_execution_readiness import build_tranche_execution_readiness_report


SEGMENT_COLUMNS = [
    "sku_key",
    "segment_code",
    "segment",
    "segment_reason",
    "stock_units",
    "goods_basis_kzt_known_cogs",
    "delivered_30d_units",
    "june_non_cancelled_units",
    "days_cover_30d",
    "prior_canonical_tranche1",
    "tranche_sizing_allowed",
    "hold_reason",
]


LEDGER_COLUMNS = [
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


def _write_segment_map(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "sku_key": "SKU_ZERO",
            "segment_code": "B",
            "segment": "B_ZERO_VELOCITY",
            "segment_reason": "fixture",
            "stock_units": "10",
            "goods_basis_kzt_known_cogs": "1000.00",
            "delivered_30d_units": "0",
            "june_non_cancelled_units": "0",
            "days_cover_30d": "",
            "prior_canonical_tranche1": "True",
            "tranche_sizing_allowed": "True",
            "hold_reason": "",
        },
        {
            "sku_key": "SKU_HOLD",
            "segment_code": "A",
            "segment": "A_COUNT_GATED",
            "segment_reason": "fixture",
            "stock_units": "20",
            "goods_basis_kzt_known_cogs": "1000.00",
            "delivered_30d_units": "1",
            "june_non_cancelled_units": "1",
            "days_cover_30d": "600",
            "prior_canonical_tranche1": "False",
            "tranche_sizing_allowed": "False",
            "hold_reason": "count_gated",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SEGMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_ledger(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_config(
    path: Path,
    *,
    scoreboard: Path,
    summary: Path,
    segment_map: Path,
    ledger: Path,
    manifest: Path,
) -> None:
    _write_json(
        path,
        {
            "contract_id": "LIQUIDATION_TRANCHE1_EXECUTION_READINESS_V1",
            "gate_id": "G-LIQ-02",
            "scoreboard_path": str(scoreboard),
            "register_summary_path": str(summary),
            "segment_map_path": str(segment_map),
            "tranche_ledger_path": str(ledger),
            "apply_readback_manifest_path": str(manifest),
            "dependency_gates": ["G-LIQ-01", "G-PRICE-01", "G-PRICE-02", "G-WA-01"],
            "price_stopline_gates": ["G-PRICE-03", "G-PRICE-05"],
            "candidate_segments": ["B_ZERO_VELOCITY", "C_SLOW_HIGH_COVER", "D_SIZE_MISALLOCATED"],
            "require_prior_canonical_tranche1": True,
            "required_candidate_fields": [
                "tranche_id",
                "sku_key",
                "size",
                "tier",
                "planned_units",
                "segment",
                "floor_version",
                "stock_confidence",
                "owner_decision_id",
                "source_artifact",
                "status",
            ],
            "required_execution_fields": [
                "tranche_id",
                "sku_key",
                "size",
                "tier",
                "release_date",
                "released_units",
                "sold_units",
                "floor_version",
                "stock_confidence",
                "rollback_price",
                "owner_decision_id",
                "status",
            ],
            "tranche_id": "T1",
            "owner_decision_id": "OD-011",
            "floor_version": "v7",
            "default_tier": "T1",
        },
    )


def test_price_stoplines_keep_readiness_armed(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    summary = tmp_path / "summary.json"
    segment_map = tmp_path / "segment.csv"
    ledger = tmp_path / "ledger.csv"
    manifest = tmp_path / "manifest.csv"
    config = tmp_path / "config.json"
    _write_scoreboard(
        scoreboard,
        {
            "G-LIQ-01": "GREEN",
            "G-PRICE-01": "GREEN",
            "G-PRICE-02": "GREEN",
            "G-WA-01": "ARMED",
            "G-PRICE-03": "RED",
            "G-PRICE-05": "RED",
        },
    )
    _write_json(summary, {"gate": "GREEN"})
    _write_segment_map(segment_map)
    _write_ledger(ledger, [])
    manifest.write_text("store,upload_batch_id,applied_at,active_hash,archive_hash,status\n", encoding="utf-8")
    _write_config(config, scoreboard=scoreboard, summary=summary, segment_map=segment_map, ledger=ledger, manifest=manifest)

    report = build_tranche_execution_readiness_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "ARMED"
    assert report["candidate_row_count"] == 1
    assert report["executed_active_ledger_rows"] == 0
    assert any("price_stopline_red:G-PRICE-03=RED" in blocker for blocker in report["blockers"])
    assert any("dependency_gate_not_green:G-WA-01=ARMED" in blocker for blocker in report["blockers"])


def test_executed_clean_ledger_can_green(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    summary = tmp_path / "summary.json"
    segment_map = tmp_path / "segment.csv"
    ledger = tmp_path / "ledger.csv"
    manifest = tmp_path / "manifest.csv"
    config = tmp_path / "config.json"
    _write_scoreboard(
        scoreboard,
        {
            "G-LIQ-01": "GREEN",
            "G-PRICE-01": "GREEN",
            "G-PRICE-02": "GREEN",
            "G-WA-01": "GREEN",
            "G-PRICE-03": "GREEN",
            "G-PRICE-05": "GREEN",
        },
    )
    _write_json(summary, {"gate": "GREEN"})
    _write_segment_map(segment_map)
    _write_ledger(
        ledger,
        [
            {
                "tranche_id": "T1",
                "sku_key": "SKU_ZERO",
                "size": "ALL",
                "tier": "T1",
                "release_date": "2026-06-18",
                "initial_units": "10",
                "released_units": "10",
                "sold_units": "0",
                "current_units": "10",
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
    manifest.write_text(
        "store,upload_batch_id,applied_at,active_hash,archive_hash,status\nUNIVERSAL,b1,2026-06-18T19:00:00+05:00,h1,h2,APPLIED\n",
        encoding="utf-8",
    )
    _write_config(config, scoreboard=scoreboard, summary=summary, segment_map=segment_map, ledger=ledger, manifest=manifest)

    report = build_tranche_execution_readiness_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "GREEN"
    assert report["executed_active_ledger_rows"] == 1
    assert report["applied_readback_rows"] == 1


def test_missing_segment_map_is_red(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    summary = tmp_path / "summary.json"
    ledger = tmp_path / "ledger.csv"
    manifest = tmp_path / "manifest.csv"
    config = tmp_path / "config.json"
    _write_scoreboard(scoreboard, {"G-LIQ-01": "GREEN"})
    _write_json(summary, {"gate": "GREEN"})
    _write_ledger(ledger, [])
    manifest.write_text("store,upload_batch_id,applied_at,active_hash,archive_hash,status\n", encoding="utf-8")
    _write_config(
        config,
        scoreboard=scoreboard,
        summary=summary,
        segment_map=tmp_path / "missing.csv",
        ledger=ledger,
        manifest=manifest,
    )

    report = build_tranche_execution_readiness_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "RED"
    assert "missing_segment_map" in report["fatal_errors"]
