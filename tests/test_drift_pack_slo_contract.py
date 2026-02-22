from pathlib import Path


def test_drift_pack_slo_policy_exists_with_stopline_thresholds() -> None:
    path = Path("docs/ops/DRIFT_PACK_SLO_POLICY.md")
    assert path.exists(), "missing drift pack SLO policy doc"
    text = path.read_text(encoding="utf-8")
    assert "single_truth_drift_pack" in text
    assert "Critical" in text
    assert "Warning" in text
    assert "Stop-line" in text
    assert "fail-closed" in text.lower()
