from pathlib import Path


def test_write_canary_plan_has_v5_no_apply_clause() -> None:
    path = Path("docs/ops/WRITE_CANARY_PLAN_V1.md")
    text = path.read_text(encoding="utf-8")
    assert "config/write_side_gating_manifest.yaml" in text
    assert "scripts/validate_write_side_gating.py" in text
    assert "No apply execution is allowed in board V5" in text
