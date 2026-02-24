from pathlib import Path
import os

import pytest


EVIDENCE_DOC = Path("docs/OPS_ROLLOUT_EVIDENCE_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md")


def test_board_v8_evidence_must_be_stamped_for_promotion() -> None:
    if os.environ.get("AB_REQUIRE_V8_PROMOTION_STAMP") != "1":
        pytest.skip("promotion stamp enforcement disabled outside promotion gate")
    text = EVIDENCE_DOC.read_text(encoding="utf-8")
    assert "PR link: NOT_MERGED_YET" not in text
    assert "Merge SHA: NOT_MERGED_YET" not in text
    assert "CI gates job: NOT_AVAILABLE_YET" not in text
    assert "CI headless-gates job: NOT_AVAILABLE_YET" not in text
