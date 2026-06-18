from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.report_storefront_disposition import build_report


ROOT = Path(__file__).resolve().parents[1]


def test_current_storefront_disposition_contract_is_green() -> None:
    report = build_report()

    assert report["ok"] is True
    assert report["gate"] == "GREEN"
    assert set(report["archived_stores"]) == {"11KZ", "MELVIS"}
    assert set(report["sync_enabled_kaspi_stores"]) == {"UNIVERSAL", "ACMEWEAR", "STOREB"}
    assert set(report["active_daily_polling_stores"]) == {"UNIVERSAL", "ACMEWEAR", "STOREB"}
    assert report["no_external_writes_performed"] is True


def _write(path: Path, payload: object) -> Path:
    if path.suffix == ".json":
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _minimal_files(tmp_path: Path) -> dict[str, Path]:
    decision = {
        "decision_id": "OD-027",
        "action": "archive_both_stop_daily_polling",
        "archived_stores": ["11KZ", "MELVIS"],
        "active_daily_polling_stores_after": ["UNIVERSAL", "ACMEWEAR", "STOREB"],
        "preserve_history": True,
        "scope": "local_config_and_validation_only",
    }
    owner_recorded = {
        "decisions": [
            {
                "id": "OD-027",
                "answer": "RECOMMENDED",
                "params": {"action": "archive_both", "stop_daily_polling": True},
            }
        ]
    }
    policy = {
        "store_scope": {
            "active_positive_stock_stores": ["UNIVERSAL", "ACMEWEAR", "STOREB"],
            "inactive_stores": ["11KZ", "MELVIS"],
            "archived_stores": ["11KZ", "MELVIS"],
            "archived_store_decision_id": "OD-027",
        }
    }
    kaspi_stores = {
        "settings": {"required_fresh_stores": ["UNIVERSAL", "ACMEWEAR", "STOREB"]},
        "stores": {
            "UNIVERSAL": {"sync_enabled": True, "priority": 1},
            "ACMEWEAR": {"sync_enabled": True, "priority": 2},
            "STOREB": {"sync_enabled": True, "priority": 3},
            "11KZ": {
                "sync_enabled": False,
                "lifecycle_status": "ARCHIVED",
                "owner_decision_id": "OD-027",
                "token_env": "KASPI_TOKEN_11KZ",
                "merchant_uid": "30290083",
            },
            "MELVIS": {
                "sync_enabled": False,
                "lifecycle_status": "ARCHIVED",
                "owner_decision_id": "OD-027",
                "token_env": "KASPI_TOKEN_MELVIS",
                "merchant_uid": "30362323",
            },
        },
    }
    daily_stores = {
        "stores": {
            "UNIVERSAL": {"active": True},
            "ACMEWEAR": {"active": True},
            "STOREB": {"active": True},
            "11KZ": {
                "active": False,
                "lifecycle_status": "ARCHIVED",
                "owner_decision_id": "OD-027",
                "token_env": "KASPI_TOKEN_11KZ",
            },
            "MELVIS": {
                "active": False,
                "lifecycle_status": "ARCHIVED",
                "owner_decision_id": "OD-027",
                "token_env": "KASPI_TOKEN_MELVIS",
            },
        }
    }
    return {
        "decision_path": _write(tmp_path / "decision.json", decision),
        "owner_recorded_path": _write(tmp_path / "owner.yaml", owner_recorded),
        "policy_path": _write(tmp_path / "policy.yaml", policy),
        "kaspi_stores_path": _write(tmp_path / "kaspi_stores.yaml", kaspi_stores),
        "daily_stores_path": _write(tmp_path / "stores.yaml", daily_stores),
    }


def test_storefront_disposition_fails_when_archived_store_is_still_enabled(tmp_path: Path) -> None:
    paths = _minimal_files(tmp_path)
    kaspi_payload = yaml.safe_load(paths["kaspi_stores_path"].read_text(encoding="utf-8"))
    kaspi_payload["stores"]["MELVIS"]["sync_enabled"] = True
    paths["kaspi_stores_path"].write_text(yaml.safe_dump(kaspi_payload), encoding="utf-8")

    report = build_report(**paths)

    assert report["ok"] is False
    assert report["gate"] == "RED"
    assert any("MELVIS kaspi_stores sync_enabled must be false" in error for error in report["errors"])
