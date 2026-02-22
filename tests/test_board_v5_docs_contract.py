from pathlib import Path


PHASES = [
    "V5-T0_PLAN_AUTHORITY",
    "V5-C1_PROD_DRY_RUN",
    "V5-H1_API_STATE_TRANSITION",
    "V5-O1_DRIFT_PACK_SLOS",
    "V5-A1_WRITE_CANARY_READINESS",
    "V5-S1_MULTI_STORE_SCALE",
]


def test_v5_plan_doc_exists_with_phase_map() -> None:
    path = Path("docs/PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V5_PROD_WRITE_SCALE_2026-02-22.md")
    assert path.exists(), "missing V5 plan doc"
    text = path.read_text(encoding="utf-8")
    for phase in PHASES:
        assert phase in text


def test_v5_evidence_doc_exists_and_has_required_sections() -> None:
    path = Path("docs/OPS_ROLLOUT_EVIDENCE_BOARD_V5_PROD_WRITE_SCALE_2026-02-22.md")
    assert path.exists(), "missing V5 evidence doc"
    text = path.read_text(encoding="utf-8")
    assert "PR link" in text
    assert "merge SHA" in text
    assert "No DB/network apply writes executed" in text
    assert "Rollback" in text
