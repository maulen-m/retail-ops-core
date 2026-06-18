from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.report_g_liq04_line51_markdown_guard import (
    build_line51_markdown_guard_report,
)


LEAD_COLUMNS = [
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


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_liquidation_dir(path: Path, *, beli_s_stock: int = 82) -> None:
    _write_csv(
        path / "liquidation_register.csv",
        [
            "sku_key",
            "segment",
            "stock_units",
            "goods_basis_kzt_known_cogs",
            "tranche_sizing_allowed",
            "hold_reason",
        ],
        [
            {
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "segment": "A_COUNT_GATED",
                "stock_units": 834,
                "goods_basis_kzt_known_cogs": "3903120.00",
                "tranche_sizing_allowed": "False",
                "hold_reason": "count_gated",
            }
        ],
    )
    _write_csv(
        path / "liquidation_segment_map.csv",
        [
            "sku_key",
            "segment",
            "stock_units",
            "goods_basis_kzt_known_cogs",
            "tranche_sizing_allowed",
            "hold_reason",
        ],
        [
            {
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "segment": "A_COUNT_GATED",
                "stock_units": 834,
                "goods_basis_kzt_known_cogs": "3903120.00",
                "tranche_sizing_allowed": "False",
                "hold_reason": "count_gated",
            }
        ],
    )
    _write_csv(
        path / "liquidation_size_detail.csv",
        [
            "snapshot_date",
            "sku_id",
            "sku_key",
            "my_size",
            "current_stock",
            "cogs_kzt",
            "stock_value_kzt_known_cogs",
        ],
        [
            {
                "snapshot_date": "2026-06-17",
                "sku_id": "CL_OC_MEN_LINE51_WHITE_S",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "my_size": "S",
                "current_stock": beli_s_stock,
                "cogs_kzt": 4680,
                "stock_value_kzt_known_cogs": beli_s_stock * 4680,
            }
        ],
    )


def _write_lead_map(path: Path, rows: list[dict[str, object]] | None = None) -> None:
    _write_csv(path, LEAD_COLUMNS, rows or [])


def _write_count_evidence(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "| LINE51 S | **82** FULL | leading digit under ink blot | 3/3 read 82; high stakes |\n",
        encoding="utf-8",
    )


def _owner_decision(*, repricer_policy: str = "never enable dumping or automated min/current/max writes") -> dict[str, object]:
    return {
        "schema_version": "autonomous_business.owner_decision.line51_ko_clearance.v1",
        "decision_id": "owner_line51_ko_clearance_universal_storeb_2026_06_18",
        "owner_approval": {
            "approval_scope": "temporary fixed-price LINE51 lower-size clearance offers for Universal and STORE-B",
            "temporary_override_only": True,
        },
        "source_family": {
            "sku_key": "CL_OC_MEN_LINE51_WHITE",
            "canonical_cogs_kzt": 4680,
        },
        "target_stores": [
            {"store_code": "UNIVERSAL", "merchant_id": 30000001},
            {"store_code": "STOREB", "merchant_id": 30000002},
        ],
        "strategy": {
            "pricing": "fixed manual prices only",
            "repricer_policy": repricer_policy,
        },
        "economics_assumptions": {
            "initial_prices_by_size": {"S": 9990, "M": 10990, "L": 11990},
        },
        "target_variants": [
            {"size": "S", "sku_id": "CL_OC_MEN_LINE51_WHITE_S", "planned_price_kzt": 9990},
            {"size": "M", "sku_id": "CL_OC_MEN_LINE51_WHITE_M", "planned_price_kzt": 10990},
            {"size": "L", "sku_id": "CL_OC_MEN_LINE51_WHITE_L", "planned_price_kzt": 11990},
        ],
        "mapping_policy": {
            "ab_db_mutation_status": "not_applied_by_this_decision_file",
        },
        "stoplines": [
            "Do not enable Repricer dumping for these rows.",
            "Do not allow automated Repricer price writes for these rows.",
        ],
    }


def _write_owner_decision(path: Path, payload: dict[str, object] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or _owner_decision(), indent=2) + "\n", encoding="utf-8")


def _write_config(
    path: Path,
    *,
    liquidation_dir: Path,
    lead_map: Path,
    count_evidence: Path,
    owner_decision: Path,
) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "LINE51_MARKDOWN_GUARD_V1",
                "gate_id": "G-LIQ-04",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "required_size_stock": {"CL_OC_MEN_LINE51_WHITE_S": 82},
                "liquidation_register_dir": str(liquidation_dir),
                "lead_store_map_csv": str(lead_map),
                "count_evidence_path": str(count_evidence),
                "owner_decision_path": str(owner_decision),
                "active_map_statuses": ["ACTIVE"],
                "allowed_clearance_schema_version": "autonomous_business.owner_decision.line51_ko_clearance.v1",
                "allowed_clearance_target_stores": ["UNIVERSAL", "STOREB"],
                "allowed_clearance_sizes": ["S", "M", "L"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    liquidation_dir = tmp_path / "liq"
    lead_map = tmp_path / "lead.csv"
    count_evidence = tmp_path / "count.md"
    owner_decision = tmp_path / "owner.json"
    config = tmp_path / "config.json"
    _write_liquidation_dir(liquidation_dir)
    _write_lead_map(lead_map)
    _write_count_evidence(count_evidence)
    _write_owner_decision(owner_decision)
    _write_config(
        config,
        liquidation_dir=liquidation_dir,
        lead_map=lead_map,
        count_evidence=count_evidence,
        owner_decision=owner_decision,
    )
    return config, lead_map


def test_count_gated_line51_without_generic_markdown_is_green(tmp_path: Path) -> None:
    config, _lead_map = _fixture(tmp_path)

    report = build_line51_markdown_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:05:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["generic_line51_markdown_row_count"] == 0
    assert report["count_extension_executed"] is True
    assert report["owner_decision_status"] == "separate_fixed_manual_clearance_only"
    assert report["external_writes_performed"] is False


def test_active_generic_line51_lead_map_row_is_red(tmp_path: Path) -> None:
    config, lead_map = _fixture(tmp_path)
    _write_lead_map(
        lead_map,
        [
            {
                "tranche_id": "T1",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "size": "S",
                "lead_store": "UNIVERSAL",
                "allowed_follower_stores": "",
                "effective_from": "2026-06-18T18:00:00+05:00",
                "source_artifact": "exports/validation/example.csv",
                "status": "ACTIVE",
                "owner_decision_id": "OD-011",
                "notes": "generic liquidation row",
            }
        ],
    )

    report = build_line51_markdown_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:05:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["generic_line51_markdown_row_count"] == 1
    assert any("generic LINE51 markdown" in blocker for blocker in report["blockers"])


def test_owner_decision_with_automated_repricer_policy_is_red(tmp_path: Path) -> None:
    config, _lead_map = _fixture(tmp_path)
    owner_path = tmp_path / "owner.json"
    _write_owner_decision(owner_path, _owner_decision(repricer_policy="automated dumping allowed"))

    report = build_line51_markdown_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:05:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("repricer_policy" in blocker for blocker in report["blockers"])


def test_s_count_mismatch_is_red(tmp_path: Path) -> None:
    config, _lead_map = _fixture(tmp_path)
    _write_liquidation_dir(tmp_path / "liq", beli_s_stock=81)

    report = build_line51_markdown_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:05:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("CL_OC_MEN_LINE51_WHITE_S" in blocker for blocker in report["blockers"])
