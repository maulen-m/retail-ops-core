from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_phase2_june15_production_apply as runner


def test_build_step_specs_orders_guarded_production_sequence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    steps = runner.build_step_specs(run_root=run_root, backup_root=run_root / "backups")

    assert [step.name for step in steps[:7]] == [
        "verify_daily_ops_paused",
        "check_local_app_db_before",
        "reconcile_on_delivery_settlement",
        "translate_on_delivery_cashflow",
        "rebuild_cashflow_calendar",
        "rebuild_sales_fact_v2",
        "apply_fact_sales_derived_replay",
    ]
    assert steps[0].assert_daily_ops_paused_report is True
    assert steps[2].needs_pre_sha is True
    assert steps[2].env == {"ENABLE_CASHFLOW_WRITE": "1", "ENABLE_CASHFLOW_PROD_WRITE": "1"}
    assert "--expected-pre-sha256" in steps[2].command
    assert runner.PRE_SHA_TOKEN in steps[2].command
    assert steps[5].needs_pre_sha is True
    assert "--expected-pre-sha256" in steps[5].command
    assert runner.PRE_SHA_TOKEN in steps[5].command
    assert steps[6].env == {"ENABLE_FACT_SALES_DERIVED_REPLAY_WRITE": "1"}
    validate_params = next(step for step in steps if step.name == "validate_params_strict")
    assert "--db" in validate_params.command
    assert "--business-insides-output-dir" in validate_params.command
    assert "--json" in validate_params.command
    assert "--json-out" not in validate_params.command
    assert validate_params.output_path.endswith("validate_params_prod_after.json")
    assert steps[-1].name == "check_local_app_db_after"


def test_plan_only_writes_plan_without_apply(tmp_path: Path) -> None:
    run_root = tmp_path / "run"

    rc = runner.main(["--run-root", str(run_root)])

    assert rc == 0
    plan = json.loads((run_root / "production_apply_plan.json").read_text(encoding="utf-8"))
    assert plan["apply"] is False
    assert plan["env_gate"] == runner.ENV_GATE
    assert plan["steps"][0]["name"] == "verify_daily_ops_paused"


def test_apply_requires_top_level_env_gate(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    steps = runner.build_step_specs(run_root=run_root, backup_root=run_root / "backups")

    with pytest.raises(RuntimeError, match=f"{runner.ENV_GATE}=1"):
        runner.run_apply(
            run_root=run_root,
            backup_root=run_root / "backups",
            db_path=runner.DEFAULT_DB,
            steps=steps,
            environ={},
        )
