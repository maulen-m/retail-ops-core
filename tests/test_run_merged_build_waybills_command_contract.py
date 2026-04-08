from pathlib import Path


def test_merged_waybill_command_uses_dual_output_layout() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--output-layout per-store-and-merged" in text
    assert "PER_STORE/" in text
    assert "MERGED/" in text
    assert "MERGED send bundles (WhatsApp source):" in text


def test_merged_waybill_command_keeps_stopline_report() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--strict-stopline" in text


def test_merged_waybill_command_runs_whatsapp_before_final_hard_fail_exit() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    step4_idx = text.index('Step 4: Sending bundles to WhatsApp...')
    stopline_idx = text.rindex('STOP-LINE: workflow completed with hard failures. See warnings above.')
    assert step4_idx < stopline_idx


def test_merged_waybill_command_runs_whatsapp_preflight_before_auto_send() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--preflight-only" in text
    assert "send_batch_manifest.json" in text


def test_merged_waybill_command_records_machine_readable_sender_stopline() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "whatsapp_send_stopline.json" in text


def test_merged_waybill_command_clears_stale_output_when_build_is_skipped() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert 'SKIPPED: build step blocked by earlier hard failure.' in text
    assert 'Cleared stale output folder:' in text


def test_merged_waybill_command_supports_partial_health_override() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "KASPI_ALLOW_PARTIAL_WAYBILL_HEALTH" in text
    assert "--allow-partial-health" in text


def test_merged_waybill_command_blocks_auto_send_when_waybill_health_is_red() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert 'WARNING: Waybill health reported mismatches, but ready merged bundles will still be sent.' not in text
    assert 'WARNING: WhatsApp auto-send blocked by strict waybill health mismatches.' in text


def test_merged_waybill_command_ships_with_overdue_carry_forward() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--include-overdue" in text
    assert "--overdue-lookback-days \"${LOOKBACK_DAYS}\"" in text


def test_merged_waybill_command_skips_non_shell_env_keys() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "SHELL_KEY_RE = re.compile" in text
    assert "if not SHELL_KEY_RE.match(key):" in text
