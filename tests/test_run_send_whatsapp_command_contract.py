from pathlib import Path


def test_run_send_whatsapp_command_forces_merged_source() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "--bundle-source merged" in text


def test_run_send_whatsapp_command_fails_closed_on_helper_bootstrap_errors() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


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


def test_run_send_whatsapp_command_uses_attach_mode_for_smoke_and_live_send() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert 'BROWSER_MODE="attach"' in text
    assert text.count('--browser-mode "${BROWSER_MODE}"') == 3
    assert 'CHROME_USER_DATA_DIR="${HOME}/Library/Application Support/Google/Chrome-WhatsAppDebug"' in text
    assert text.count('--chrome-user-data-dir "${CHROME_USER_DATA_DIR}"') == 3


def test_run_send_whatsapp_command_auto_starts_dedicated_debug_chrome() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert 'DEBUG_HELPER="~/Docs/Autonomous_business/excel_ui/start_whatsapp_debug_chrome.command"' in text
    assert '"${DEBUG_HELPER}"' in text


def test_run_send_whatsapp_command_waits_for_cdp_after_helper_bootstrap() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert 'CDP_ENDPOINT_IPV4="http://127.0.0.1:9222/json/version"' in text
    assert 'CDP_ENDPOINT_IPV6="http://[::1]:9222/json/version"' in text
    assert 'RESOLVED_CDP_ENDPOINT="http://127.0.0.1:9222"' in text
    assert "wait_for_cdp" in text
    assert "cdp_live" in text
    assert 'curl -fsS "${CDP_ENDPOINT_IPV4}"' in text
    assert 'curl -g -fsS "${CDP_ENDPOINT_IPV6}"' in text
    assert text.count('--cdp-endpoint "${RESOLVED_CDP_ENDPOINT}"') == 3


def test_run_send_whatsapp_command_points_to_one_time_profile_setup_on_smoke_failure() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "start_whatsapp_debug_chrome.command" in text
    assert "If the failure mentions QR/login screen, complete WhatsApp login once in the dedicated automation profile." in text
    assert "If the failure mentions DevTools/CDP unavailability, the browser session may still be logged in" in text


def test_run_send_whatsapp_command_prints_attach_mode_runtime_contract() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "Production mode: dedicated automation Chrome attach." in text
    assert "Auto-starting automation Chrome with:" in text


def test_run_send_whatsapp_command_keeps_browser_open_briefly_after_live_send() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert "--linger-seconds 120" in text
    assert "--linger-seconds 180" in text


def test_run_send_whatsapp_command_retries_pre_status_probe_stopline_without_status_messages() -> None:
    text = Path("excel_ui/run_send_whatsapp.command").read_text(encoding="utf-8")
    assert 'STOPLINE_PATH="excel_ui/Kaspi_orders/Today/whatsapp_send_stopline.json"' in text
    assert 'PRE_STATUS_PROBE_PATTERN="Pre-send delivery probe failed"' in text
    assert 'grep -q "${PRE_STATUS_PROBE_PATTERN}" "${STOPLINE_PATH}"' in text
    assert "WARNING: Pre-send status probe drifted. Retrying live send without status messages..." in text
    assert "--no-status-messages" in text


def test_start_whatsapp_debug_chrome_uses_dedicated_debug_profile_root() -> None:
    text = Path("excel_ui/start_whatsapp_debug_chrome.command").read_text(encoding="utf-8")
    assert 'DEBUG_USER_DATA_DIR="${HOME}/Library/Application Support/Google/Chrome-WhatsAppDebug"' in text
    assert '--user-data-dir="${DEBUG_USER_DATA_DIR}"' in text
    assert "SOURCE_USER_DATA_DIR" in text
    assert 'CDP_ENDPOINT_IPV4="http://127.0.0.1:9222/json/version"' in text
    assert 'CDP_ENDPOINT_IPV6="http://[::1]:9222/json/version"' in text


def test_start_whatsapp_debug_chrome_preserves_existing_dedicated_profile() -> None:
    text = Path("excel_ui/start_whatsapp_debug_chrome.command").read_text(encoding="utf-8")
    assert 'if [ ! -d "${DEBUG_USER_DATA_DIR}/${PROFILE_DIR}" ]; then' in text
    assert "Existing dedicated debug profile found; preserving it." in text


def test_start_whatsapp_debug_chrome_waits_for_stale_debug_session_to_fully_exit() -> None:
    text = Path("excel_ui/start_whatsapp_debug_chrome.command").read_text(encoding="utf-8")
    assert "wait_for_debug_shutdown" in text
    assert "pgrep -f -- '--remote-debugging-port=9222'" in text


def test_start_whatsapp_debug_chrome_uses_extended_cdp_bootstrap_wait() -> None:
    text = Path("excel_ui/start_whatsapp_debug_chrome.command").read_text(encoding="utf-8")
    assert "MAX_WAIT_SECONDS=60" in text
    assert "CDP bootstrap is still pending" in text
    assert 'curl -g -fsS "${CDP_ENDPOINT_IPV6}"' in text
