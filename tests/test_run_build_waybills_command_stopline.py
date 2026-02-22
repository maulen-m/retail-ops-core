from pathlib import Path


def test_waybill_command_tracks_hard_fail_and_exits_nonzero() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert 'HARD_FAIL=0' in text
    assert 'if [ "${HARD_FAIL}" -ne 0 ]; then' in text
    assert "exit 1" in text


def test_waybill_command_uses_strict_stopline_report_flag() -> None:
    text = Path("excel_ui/run_build_waybills.command").read_text(encoding="utf-8")
    assert "--strict-stopline" in text
