from pathlib import Path


def test_waybill_command_tracks_hard_fail_and_exits_nonzero() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert 'HARD_FAIL=0' in text
    assert 'if [ "${HARD_FAIL}" -ne 0 ]; then' in text
    assert "exit 1" in text


def test_waybill_command_uses_strict_stopline_report_flag() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert "--strict-stopline" in text


def test_waybill_command_clears_stale_output_when_build_is_skipped() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert 'SKIPPED: build step blocked by earlier hard failure.' in text
    assert 'Cleared stale output folder:' in text


def test_waybill_command_skips_build_after_hard_fail() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert 'if [ "${HARD_FAIL}" -ne 0 ]; then' in text
    assert "SKIPPED: build step blocked by earlier hard failure." in text


def test_waybill_command_supports_partial_health_override() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert "KASPI_ALLOW_PARTIAL_WAYBILL_HEALTH" in text
    assert "--allow-partial-health" in text
