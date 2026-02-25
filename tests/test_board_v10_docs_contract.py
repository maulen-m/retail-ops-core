from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_DOC = PROJECT_ROOT / "docs" / "PLAN_BOARD_V10_ENDGAME_E2E_AUTONOMY_2026-02-26.md"
EVIDENCE_DOC = PROJECT_ROOT / "docs" / "OPS_ROLLOUT_EVIDENCE_BOARD_V10_ENDGAME_E2E_AUTONOMY_2026-02-26.md"


def test_v10_plan_doc_exists_and_lists_all_phases() -> None:
    assert PLAN_DOC.exists(), f"missing plan doc: {PLAN_DOC}"
    text = PLAN_DOC.read_text(encoding="utf-8")
    required_tokens = [
        "Phase V10-T0",
        "Phase V10-C1",
        "Phase V10-C2",
        "Phase V10-C3",
        "Phase V10-H1",
        "Phase V10-H2",
        "Phase V10-A1",
        "Phase V10-O1",
        "Phase V10-S1",
        "Phase V10-PROMOTE",
    ]
    for token in required_tokens:
        assert token in text, f"plan doc missing phase token: {token}"


def test_v10_evidence_doc_exists_with_gate_checklist() -> None:
    assert EVIDENCE_DOC.exists(), f"missing evidence doc: {EVIDENCE_DOC}"
    text = EVIDENCE_DOC.read_text(encoding="utf-8")
    required_tokens = [
        "Gate Checklist",
        "python3 scripts/validate_params.py --strict",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q",
        "python3 scripts/run_contract_suite.py --fixture small",
        "python3 scripts/validate_single_truth_system.py",
        "bash scripts/lint_docs.sh",
        "bash scripts/check_no_db_tracked.sh",
        "bash scripts/install_single_truth_ops_scheduler.sh --validate-only",
        "python3 scripts/check_anchor_health.py --project-root <REPO_PATH>",
        "python3 scripts/ops_status.py --project-root <REPO_PATH>",
        "python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>",
    ]
    for token in required_tokens:
        assert token in text, f"evidence doc missing token: {token}"


def test_v10_docs_do_not_include_absolute_personal_paths() -> None:
    forbidden = "~/"
    assert forbidden not in PLAN_DOC.read_text(encoding="utf-8")
    if EVIDENCE_DOC.exists():
        assert forbidden not in EVIDENCE_DOC.read_text(encoding="utf-8")
