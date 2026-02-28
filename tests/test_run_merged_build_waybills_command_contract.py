from pathlib import Path


def test_merged_waybill_command_uses_dual_output_layout() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--output-layout per-store-and-merged" in text
    assert "PER_STORE/" in text
    assert "MERGED/" in text


def test_merged_waybill_command_keeps_stopline_report() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--strict-stopline" in text


def test_merged_waybill_command_clears_stale_output_when_build_is_skipped() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert 'SKIPPED: build step blocked by earlier hard failure.' in text
    assert 'Cleared stale output folder:' in text


def test_merged_waybill_command_supports_partial_health_override() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "KASPI_ALLOW_PARTIAL_WAYBILL_HEALTH" in text
    assert "--allow-partial-health" in text
