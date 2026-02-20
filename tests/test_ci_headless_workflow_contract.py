from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/single_truth_headless.yml")


REQUIRED_SNIPPETS = [
    "DIM_SKU_LIGHT_WORKBOOK_PATH: config/anchors/fixtures/DIM_SKU_LIGHT_V5.fixture.xlsx",
    "python3 scripts/validate_params.py --strict",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q",
    "python3 scripts/run_contract_suite.py --fixture small",
    "python3 scripts/validate_single_truth_system.py",
    "scripts/lint_docs.sh",
    "scripts/check_no_db_tracked.sh",
    "bash scripts/install_single_truth_ops_scheduler.sh --validate-only",
    "python3 scripts/check_anchor_health.py --project-root",
    "python3 scripts/ops_status.py --project-root",
]


def test_ci_headless_workflow_exists() -> None:
    assert WORKFLOW.exists(), "missing .github/workflows/single_truth_headless.yml"


def test_ci_headless_workflow_runs_required_jobs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for snippet in REQUIRED_SNIPPETS:
        assert snippet in text, f"missing required gate in workflow: {snippet}"


def test_ci_headless_workflow_bootstraps_fixture_before_gates() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/prepare_ci_headless_fixture.py" in text
    assert "ls -l db/app.db" in text
