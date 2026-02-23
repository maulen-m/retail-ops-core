from pathlib import Path


PLAN_DOC = Path("docs/PLAN_BOARD_V6_AUTONOMOUS_SCALE_2026-02-22.md")
EVIDENCE_DOC = Path("docs/OPS_ROLLOUT_EVIDENCE_BOARD_V6_AUTONOMOUS_SCALE_2026-02-22.md")


def test_board_v6_plan_doc_exists_with_required_sections() -> None:
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


def test_board_v6_evidence_doc_exists_with_promotion_minimum_content() -> None:
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
    assert "TBD" not in text
    assert "TODO" not in text
