from pathlib import Path


def test_run_send_whatsapp_command_forces_merged_source() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "--bundle-source merged" in text


def test_run_send_whatsapp_command_propagates_sender_exit_code() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "SENDER_RC=$?" in text
    assert 'exit "${SENDER_RC}"' in text
