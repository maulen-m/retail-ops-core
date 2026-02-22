from pathlib import Path


def test_write_canary_v6_plan_exists_and_is_reversible() -> None:
    path = Path("docs/ops/WRITE_CANARY_V6_APPLY_BOARD.md")
    assert path.exists(), "missing V6 write canary apply board plan"
    text = path.read_text(encoding="utf-8")
    assert "single store" in text.lower()
    assert "DB backup" in text
    assert "--apply" in text
    assert "ENABLE_" in text
    assert "rollback" in text.lower()
    assert "validate_write_side_gating.py" in text
    assert "full_gates_green_final.md" in text
