import json
import sys
from pathlib import Path

import pandas as pd

from scripts import evaluate_import_run_result as eval_mod


def _write_health(
    path: Path,
    *,
    miss_crm: int,
    stale_crm: int = 0,
    miss_seller_fee: int = 0,
    partial_api: bool = False,
    warnings: list[str] | None = None,
) -> None:
    payload = {
        "target_date": "2026-02-16",
        "partial_api": partial_api,
        "totals": {
            "api_today": 71,
            "crm_today": 71 - miss_crm + stale_crm,
            "miss_crm": miss_crm,
            "stale_crm": stale_crm,
            "seller_fee_expected": 71,
            "seller_fee_filled": 71 - miss_seller_fee,
            "miss_seller_fee": miss_seller_fee,
        },
        "warnings": warnings or [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluator_passes_when_step2_ok_and_no_miss(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0, warnings=["soft warning"])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
        ],
    )

    assert eval_mod.main() == 0


def test_evaluator_fails_when_step2_failed(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "124",
            "--health-json",
            str(health),
        ],
    )

    assert eval_mod.main() != 0


def test_evaluator_fails_when_miss_crm_nonzero(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=3)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
        ],
    )

    assert eval_mod.main() != 0


def test_evaluator_fails_when_stale_crm_nonzero(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0, stale_crm=2)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
        ],
    )

    assert eval_mod.main() != 0


def test_evaluator_fails_when_seller_fee_coverage_incomplete(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0, miss_seller_fee=2)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
        ],
    )

    assert eval_mod.main() != 0


def test_evaluator_requires_live_parity_even_when_snapshot_matches(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=5)

    activeorders = tmp_path / "ActiveOrders.xlsx"
    pd.DataFrame(
        {
            "№ заказа": ["9001", "9002"],
            "Плановая дата передачи курьеру": ["17.02.2026", "17.02.2026"],
        }
    ).to_excel(activeorders, index=False)

    crm = tmp_path / "crm.xlsx"
    pd.DataFrame(
        {
            "Date": ["2026-02-17", "2026-02-17"],
            "OrderID": ["9001", "9002"],
        }
    ).to_excel(crm, index=False, sheet_name="SALES_KSP_CRM_1")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
            "--activeorders-file",
            str(activeorders),
            "--crm-file",
            str(crm),
            "--target-date",
            "2026-02-17",
        ],
    )

    assert eval_mod.main() != 0


def test_evaluator_passes_when_snapshot_matches_and_live_parity_holds(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0)

    activeorders = tmp_path / "ActiveOrders.xlsx"
    pd.DataFrame(
        {
            "№ заказа": ["9001", "9002"],
            "Плановая дата передачи курьеру": ["17.02.2026", "17.02.2026"],
        }
    ).to_excel(activeorders, index=False)

    crm = tmp_path / "crm.xlsx"
    pd.DataFrame(
        {
            "Date": ["2026-02-17", "2026-02-17"],
            "OrderID": ["9001", "9002"],
        }
    ).to_excel(crm, index=False, sheet_name="SALES_KSP_CRM_1")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
            "--activeorders-file",
            str(activeorders),
            "--crm-file",
            str(crm),
            "--target-date",
            "2026-02-17",
        ],
    )

    assert eval_mod.main() == 0


def test_evaluator_fails_when_activeorders_snapshot_missing_in_crm(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0)

    activeorders = tmp_path / "ActiveOrders.xlsx"
    pd.DataFrame(
        {
            "№ заказа": ["9101", "9102"],
            "Плановая дата передачи курьеру": ["17.02.2026", "17.02.2026"],
        }
    ).to_excel(activeorders, index=False)

    crm = tmp_path / "crm.xlsx"
    pd.DataFrame(
        {
            "Date": ["2026-02-17"],
            "OrderID": ["9101"],
        }
    ).to_excel(crm, index=False, sheet_name="SALES_KSP_CRM_1")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
            "--activeorders-file",
            str(activeorders),
            "--crm-file",
            str(crm),
            "--target-date",
            "2026-02-17",
        ],
    )

    assert eval_mod.main() != 0


def test_evaluator_prefers_populated_order_id_column_for_snapshot_gate(tmp_path, monkeypatch):
    health = tmp_path / "health.json"
    _write_health(health, miss_crm=0)

    activeorders = tmp_path / "ActiveOrders.xlsx"
    pd.DataFrame(
        {
            "№ заказа": ["9201", "9202"],
            "Плановая дата передачи курьеру": ["17.02.2026", "17.02.2026"],
        }
    ).to_excel(activeorders, index=False)

    crm = tmp_path / "crm.xlsx"
    pd.DataFrame(
        {
            "Date": ["2026-02-17", "2026-02-17"],
            "OrderID": ["", ""],
            "№ заказа": ["9201", "9202"],
        }
    ).to_excel(crm, index=False, sheet_name="SALES_KSP_CRM_1")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_import_run_result.py",
            "--step2-rc",
            "0",
            "--health-json",
            str(health),
            "--activeorders-file",
            str(activeorders),
            "--crm-file",
            str(crm),
            "--target-date",
            "2026-02-17",
        ],
    )

    assert eval_mod.main() == 0
