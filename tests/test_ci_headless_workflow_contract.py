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

REQUIRED_HEADLESS_PYTEST_TARGETS = [
    "tests/test_ci_headless_workflow_contract.py",
    "tests/test_prepare_ci_headless_fixture.py",
    "tests/test_check_anchor_health.py",
    "tests/test_run_strict_daily_preflight.py",
    "tests/test_install_single_truth_ops_scheduler.py",
    "tests/test_ops_docs_anchor_contract.py",
    "tests/test_ops_status.py",
    "tests/test_validate_write_side_gating.py",
    "tests/test_write_side_gating_contract.py",
    "tests/test_validate_sales_vs_workbook_anchor.py",
    "tests/test_sales_workbook_anchor_parser.py",
    "tests/test_validate_sales_truth_consumers.py",
    "tests/test_promotion_minimum_standard_contract.py",
    "tests/test_import_orders_to_crm.py::test_load_sku_meta_for_keys_handles_missing_dim_sku_table",
]

REQUIRED_TOOLCHAIN_SNIPPETS = [
    "sudo apt-get update",
    "sudo apt-get install -y ripgrep",
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


def test_ci_headless_workflow_uses_curated_pytest_bucket() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'AB_HEADLESS_FIXTURE: "1"' in text
    for target in REQUIRED_HEADLESS_PYTEST_TARGETS:
        assert target in text, f"missing headless pytest target: {target}"


def test_ci_headless_workflow_installs_required_tooling() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for snippet in REQUIRED_TOOLCHAIN_SNIPPETS:
        assert snippet in text, f"missing tooling install command: {snippet}"
