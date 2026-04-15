from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.send_waybills_whatsapp import (
    ALMATY_TZ,
    DEFAULT_CHROME_USER_DATA_DIR,
    DEFAULT_WHATSAPP_AUTOMATION_USER_DATA_DIR,
    SOURCE_MERGED,
    _should_copy_browser_profile_to_temp,
    run_delivery_probe,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_PROBE_ENABLED = os.environ.get("KASPI_LIVE_WHATSAPP_PROBE") == "1"
LIVE_PROBE_CHAT = os.environ.get("KASPI_LIVE_WHATSAPP_CHAT", "Заказы")
LIVE_PROBE_USER_DATA_DIR = Path(
    os.environ.get(
        "KASPI_LIVE_WHATSAPP_USER_DATA_DIR",
        str(DEFAULT_WHATSAPP_AUTOMATION_USER_DATA_DIR),
    )
)
LIVE_PROBE_PROFILE_DIR = os.environ.get("KASPI_LIVE_WHATSAPP_PROFILE_DIR", "Profile 2")
LIVE_PROBE_PROFILE_NAME = os.environ.get("KASPI_LIVE_WHATSAPP_PROFILE_NAME", "Universal")
LIVE_PROBE_BROWSER_MODE = os.environ.get("KASPI_LIVE_WHATSAPP_BROWSER_MODE", "attach")
DEBUG_HELPER = PROJECT_ROOT / "excel_ui" / "start_whatsapp_debug_chrome.command"


def test_should_copy_browser_profile_to_temp_only_for_default_source_profile() -> None:
    assert _should_copy_browser_profile_to_temp(DEFAULT_CHROME_USER_DATA_DIR) is True
    assert _should_copy_browser_profile_to_temp(DEFAULT_WHATSAPP_AUTOMATION_USER_DATA_DIR) is False


def test_run_delivery_probe_sends_two_messages_and_verifies_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[str] = []
    sent_confirmations: list[tuple[str, int]] = []
    persisted_checks: list[tuple[list[str], int]] = []
    bind_calls: list[str] = []
    slept: list[float] = []

    class _FakeSender:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def assert_document_send_ready(self) -> None:
            return None

        def send_text_message(self, text: str) -> None:
            sent_messages.append(text)

        def confirm_text_message_sent(self, text: str, timeout_ms: int = 120_000) -> dict:
            sent_confirmations.append((text, timeout_ms))
            return {"sent": True, "delivered": False, "delivery_state": "sent"}

        def bind_active_chat_identity_if_missing(self) -> None:
            bind_calls.append("bind")

        def wait_for_outgoing_sync(self, timeout_ms: int = 90_000) -> None:
            return None

        def verify_recent_texts_persist(self, texts, timeout_ms: int = 120_000) -> None:
            persisted_checks.append((list(texts), timeout_ms))

    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.time.sleep", lambda seconds: slept.append(seconds))

    result = run_delivery_probe(
        chat_title="Заказы",
        browser_mode="launch-temp",
        probe_message_prefix="[probe-test]",
        probe_repeat_count=2,
        probe_interval_seconds=300.0,
        probe_timeout_seconds=120.0,
        chrome_user_data_dir=PROJECT_ROOT / "tmp-does-not-matter",
        chrome_profile_directory="Profile 2",
        chrome_profile_name="Universal",
        blocked_chat_titles=["order 2"],
        verbose=False,
    )

    assert result["ok"] is True
    assert result["probe_repeat_count"] == 2
    assert len(result["attempts"]) == 2
    assert all(attempt["sent"] for attempt in result["attempts"])
    assert all(attempt["delivery_state"] == "sent" for attempt in result["attempts"])
    assert not any(attempt["delivered"] for attempt in result["attempts"])
    assert all(attempt["persisted"] for attempt in result["attempts"])
    assert len(sent_messages) == 2
    assert len(sent_confirmations) == 2
    assert len(bind_calls) == 2
    assert persisted_checks == [
        ([sent_messages[0]], 120_000),
        ([sent_messages[0], sent_messages[1]], 120_000),
    ]
    assert slept == [300.0]


@pytest.mark.skipif(
    not LIVE_PROBE_ENABLED,
    reason="Set KASPI_LIVE_WHATSAPP_PROBE=1 to run the real WhatsApp two-probe / five-minute delivery test",
)
def test_send_waybills_whatsapp_real_delivery_probe_twice_over_five_minutes(tmp_path: Path) -> None:
    json_out = tmp_path / "live_probe.json"
    probe_prefix = f"[codex-live-probe {datetime.now(ALMATY_TZ).strftime('%Y-%m-%d %H:%M:%S')}]"
    helper_completed = subprocess.run(
        [str(DEBUG_HELPER)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert helper_completed.returncode == 0, (
        f"helper stdout:\n{helper_completed.stdout}\n\nhelper stderr:\n{helper_completed.stderr}"
    )
    command = [
        sys.executable,
        "scripts/send_waybills_whatsapp.py",
        "--chat-title",
        LIVE_PROBE_CHAT,
        "--bundle-source",
        SOURCE_MERGED,
        "--browser-mode",
        LIVE_PROBE_BROWSER_MODE,
        "--chrome-user-data-dir",
        str(LIVE_PROBE_USER_DATA_DIR),
        "--chrome-profile-directory",
        LIVE_PROBE_PROFILE_DIR,
        "--chrome-profile-name",
        LIVE_PROBE_PROFILE_NAME,
        "--delivery-probe-only",
        "--probe-message-prefix",
        probe_prefix,
        "--probe-repeat-count",
        "2",
        "--probe-interval-seconds",
        "300",
        "--probe-timeout-seconds",
        "120",
        "--json-out",
        str(json_out),
        "--verbose",
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=900,
    )
    assert completed.returncode == 0, (
        f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
    )

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["probe_repeat_count"] == 2
    assert len(payload["attempts"]) == 2
    assert all(attempt["sent"] for attempt in payload["attempts"])
    assert all(attempt["persisted"] for attempt in payload["attempts"])
    assert all(attempt["delivery_state"] in {"sent", "delivered"} for attempt in payload["attempts"])
