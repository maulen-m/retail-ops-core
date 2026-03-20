from pathlib import Path


def test_assemble_daily_defaults_to_status_first_mode():
    text = Path("excel_ui/run_assemble_daily.command").read_text(encoding="utf-8")
    assert "KASPI_ASSEMBLE_SINCE_DAYS" in text
    assert "Running in status-first mode (no creation-date lookback filter)." in text
    assert '--since-days "${LOOKBACK_DAYS}"' not in text


def test_assemble_daily_supports_optional_since_override():
    text = Path("excel_ui/run_assemble_daily.command").read_text(encoding="utf-8")
    assert 'if [ -n "${KASPI_ASSEMBLE_SINCE_DAYS:-}" ]; then' in text
    assert 'ASSEMBLE_EXTRA_ARGS+=(--since-days "${KASPI_ASSEMBLE_SINCE_DAYS}")' in text


def test_assemble_daily_enables_overdue_carry_forward_mode():
    text = Path("excel_ui/run_assemble_daily.command").read_text(encoding="utf-8")
    assert "KASPI_ASSEMBLE_OVERDUE_LOOKBACK_DAYS" in text
    assert 'ASSEMBLE_EXTRA_ARGS+=(--include-overdue --overdue-lookback-days "${ASSEMBLE_OVERDUE_LOOKBACK_DAYS}")' in text
