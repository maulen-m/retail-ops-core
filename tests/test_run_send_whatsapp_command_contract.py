from pathlib import Path


def test_run_send_whatsapp_command_forces_merged_source() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "--bundle-source merged" in text


def test_run_send_whatsapp_command_propagates_sender_exit_code() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "SENDER_RC=$?" in text
    assert 'exit "${SENDER_RC}"' in text


def test_run_send_whatsapp_command_does_not_bypass_stale_batch_guard() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "--allow-stale-batch" not in text


def test_run_send_whatsapp_command_runs_smoke_check_before_live_send() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "--smoke-check-only" in text
    assert "SMOKE_RC=$?" in text
    assert 'exit "${SMOKE_RC}"' in text
