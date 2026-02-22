from pathlib import Path


PROMOTION_STANDARD = Path("docs/ops/PROMOTION_MINIMUM_STANDARD.md")
V5_EVIDENCE = Path("docs/OPS_ROLLOUT_EVIDENCE_BOARD_V5_PROD_WRITE_SCALE_2026-02-22.md")


def test_promotion_minimum_standard_doc_exists_and_is_fail_closed() -> None:
    assert PROMOTION_STANDARD.exists(), "missing promotion minimum standard doc"
    text = PROMOTION_STANDARD.read_text(encoding="utf-8")
    assert "fail-closed" in text.lower()
    assert "full_gates_green_final.md" in text
    assert "No merge" in text


def test_daily_sop_and_write_apply_runbook_reference_promotion_minimum_standard() -> None:
    sop = Path("docs/DAILY_SOP.md").read_text(encoding="utf-8")
    runbook = Path("docs/WRITE_APPLY_RUNBOOK.md").read_text(encoding="utf-8")
    assert "docs/ops/PROMOTION_MINIMUM_STANDARD.md" in sop
    assert "docs/ops/PROMOTION_MINIMUM_STANDARD.md" in runbook


def test_v5_evidence_doc_has_no_open_placeholders_and_has_final_gate_pointer() -> None:
    text = V5_EVIDENCE.read_text(encoding="utf-8")
    assert "TBD" not in text
    assert "TODO" not in text
    assert "full_gates_green_final.md" in text
