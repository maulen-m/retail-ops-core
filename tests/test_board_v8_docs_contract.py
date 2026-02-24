from pathlib import Path


PLAN_DOC = Path("docs/PLAN_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md")
EVIDENCE_DOC = Path("docs/OPS_ROLLOUT_EVIDENCE_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md")


def test_board_v8_plan_doc_exists_with_required_sections() -> None:
    assert PLAN_DOC.exists(), f"missing plan doc: {PLAN_DOC}"
    text = PLAN_DOC.read_text(encoding="utf-8")
    for required in [
        "## Purpose",
        "## Phase List",
        "## Global Gates",
        "## Rollback (board-level)",
        "## Stop-line criteria",
    ]:
        assert required in text, f"missing required section: {required}"
    assert "/Users/" not in text, "plan doc must not contain absolute personal paths"


def test_board_v8_evidence_doc_exists_with_required_fields() -> None:
    assert EVIDENCE_DOC.exists(), f"missing evidence doc: {EVIDENCE_DOC}"
    text = EVIDENCE_DOC.read_text(encoding="utf-8")
    for required in [
        "PR link",
        "Merge SHA",
        "Required Gates Checklist",
        "Rollback Commands",
        "No DB/network apply writes executed",
    ]:
        assert required in text, f"missing required evidence field: {required}"
    assert "TODO" not in text
    assert "TBD" not in text
    assert "/Users/" not in text, "evidence doc must not contain absolute personal paths"
