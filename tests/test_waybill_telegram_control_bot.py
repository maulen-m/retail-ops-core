from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import waybill_telegram_control_bot as bot_mod


def _green_readiness() -> dict[str, object]:
    return {
        "ready": False,
        "run_control_ready_ok": False,
        "run_control_target_match": True,
        "blank_size_count": 0,
        "blank_size_rows": [],
        "invalid_size_count": 0,
        "invalid_size_rows": [],
    }


def test_waybill_telegram_ready_reports_missing_sizes_without_starting_closeout(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []
    saved_offsets: list[int] = []
    calls: list[list[str]] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: saved_offsets.append(offset))
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 10,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/ready@of_waybill_bot",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod,
        "build_waybill_control_readiness",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": True,
            "run_control_target_match": True,
            "blank_size_count": 2,
            "blank_size_rows": [{"OrderID": "1001"}, {"OrderID": "1002"}],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})
    monkeypatch.setattr(bot_mod.subprocess, "run", lambda command, cwd, env: calls.append(command))

    rc = bot_mod.poll_once(now=datetime(2026, 4, 15, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert calls == []
    assert saved_offsets == [11]
    assert any("BLOCKED_MISSING_SIZES" in msg for msg in sent_messages)
    assert any("1001" in msg and "1002" in msg for msg in sent_messages)
    assert not bot_mod.STATE_FILE.exists()


def test_waybill_telegram_ready_denies_commands_without_allowed_user_gate(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []
    readiness_calls: list[object] = []

    monkeypatch.delenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", raising=False)
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 10,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/ready",
                },
            }
        ],
    )
    monkeypatch.setattr(bot_mod, "build_waybill_control_readiness", lambda **kwargs: readiness_calls.append(kwargs))
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 15, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert readiness_calls == []
    assert sent_messages == ["Waybill bot command denied."]
    assert not bot_mod.STATE_FILE.exists()


def test_waybill_telegram_ready_allows_users_from_runtime_allowlist_file(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.delenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", raising=False)
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    allowlist_path = tmp_path / "allowed_users.txt"
    allowlist_path.write_text("42\n# backup owner\n99\n", encoding="utf-8")
    monkeypatch.setattr(bot_mod, "ALLOWED_USERS_FILE", allowlist_path)
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 10,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/ready",
                },
            }
        ],
    )
    monkeypatch.setattr(bot_mod, "build_waybill_control_readiness", lambda **_kwargs: _green_readiness())
    monkeypatch.setattr(bot_mod, "set_run_control_ready", lambda **_kwargs: None)
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 15, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("accepted" in msg.lower() for msg in sent_messages)
    assert json.loads(bot_mod.STATE_FILE.read_text(encoding="utf-8"))["pending_ready"]["user_id"] == "42"


def test_waybill_telegram_ready_arms_debounce_without_google_ready_button(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 10,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/ready",
                },
            }
        ],
    )
    monkeypatch.setattr(bot_mod, "build_waybill_control_readiness", lambda **_kwargs: _green_readiness())
    monkeypatch.setattr(bot_mod, "set_run_control_ready", lambda **_kwargs: None)
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 15, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    state = json.loads(bot_mod.STATE_FILE.read_text(encoding="utf-8"))
    assert rc == 0
    assert state["pending_ready"]["chat_id"] == "-5102810505"
    assert state["pending_ready"]["user_id"] == "42"
    assert any("60" in msg and "accepted" in msg.lower() for msg in sent_messages)


def test_waybill_telegram_pending_ready_starts_closeout_after_stable_delay(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "offset": 20,
                "pending_ready": {
                    "target_date": "2026-04-15",
                    "chat_id": "-5102810505",
                    "user_id": "42",
                    "requested_at": "2026-04-15T17:00:00+05:00",
                },
            }
        ),
        encoding="utf-8",
    )
    sent_messages: list[str] = []
    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", state_path)
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_get_updates", lambda token, offset: [])
    monkeypatch.setattr(bot_mod, "build_waybill_control_readiness", lambda **_kwargs: _green_readiness())
    monkeypatch.setattr(bot_mod, "set_run_control_ready", lambda **_kwargs: None)
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})
    monkeypatch.setattr(bot_mod.subprocess, "run", lambda command, cwd, env: calls.append(command) or _Result())

    rc = bot_mod.poll_once(now=datetime(2026, 4, 15, 17, 1, 1, tzinfo=ZoneInfo("Asia/Almaty")))

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert calls == [[str(bot_mod.sys.executable), str(bot_mod.CLOSEOUT_SCHEDULER_PATH), "--resume"]]
    assert "pending_ready" not in state
    assert any("starting closeout" in msg.lower() for msg in sent_messages)


def test_waybill_telegram_delivery_status_reports_ledger_counts(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 30,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/delivery_status",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod,
        "delivery_completion_state",
        lambda **_kwargs: {
            "completed": False,
            "status": "TELEGRAM_LEDGER_INCOMPLETE",
            "channel": "telegram",
            "manifest_count": 39,
            "confirmed_count": 38,
            "batch_label": "21.04.26_MERGED_qnt94_r2",
        },
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 21, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("TELEGRAM_LEDGER_INCOMPLETE" in msg for msg in sent_messages)
    assert any("38/39" in msg for msg in sent_messages)


def test_waybill_telegram_returns_pickup_reports_table(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 41,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/returns_pickup",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod.returns_pickup_report_mod,
        "build_pickup_ready_snapshot",
        lambda **_kwargs: {"total_orders": 2},
    )
    monkeypatch.setattr(
        bot_mod.returns_pickup_report_mod,
        "format_returns_pickup_message",
        lambda snapshot: "<b>Returns Pickup Ready</b>\n<pre>| STORE | FIRST_ORDER_ID |\n| AcmeWear | 1001 |\n</pre>\nAcmeWear: <code>1001</code>",
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 28, 15, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("Returns Pickup Ready" in msg for msg in sent_messages)
    assert any("1001" in msg for msg in sent_messages)


def test_waybill_telegram_returns_ack_store_marks_queue(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 42,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/returns_ack_store ACMEWEAR UNIVERSAL",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod.returns_pickup_report_mod,
        "ack_current_pickup_orders_for_stores",
        lambda **_kwargs: {
            "acked_orders": 3,
            "stores": [
                {"store_code": "ACMEWEAR", "display_name": "AcmeWear", "acked_orders": 2},
                {"store_code": "UNIVERSAL", "display_name": "Universal", "acked_orders": 1},
            ],
        },
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 28, 15, 5, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("3" in msg and "AcmeWear" in msg and "Universal" in msg for msg in sent_messages)


def test_waybill_telegram_short_returns_alias_reports_table(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 43,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/r",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod.returns_pickup_report_mod,
        "build_pickup_ready_snapshot",
        lambda **_kwargs: {"total_orders": 1},
    )
    monkeypatch.setattr(
        bot_mod.returns_pickup_report_mod,
        "format_returns_pickup_message",
        lambda snapshot: "<b>Returns Pickup Ready</b>\nAcmeWear: <code>1001</code>",
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 28, 16, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("Returns Pickup Ready" in msg for msg in sent_messages)


def test_waybill_telegram_button_text_acknowledges_store(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 44,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "Забрал OF",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod.returns_pickup_report_mod,
        "ack_current_pickup_orders_for_stores",
        lambda **_kwargs: {
            "acked_orders": 2,
            "stores": [{"store_code": "ACMEWEAR", "display_name": "AcmeWear", "acked_orders": 2}],
        },
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 28, 16, 5, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("acknowledged" in msg.lower() and "AcmeWear" in msg for msg in sent_messages)


def test_waybill_telegram_resume_delivery_runs_scheduler_when_incomplete(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []
    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 31,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/resume_delivery",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod,
        "delivery_completion_state",
        lambda **_kwargs: {
            "completed": False,
            "status": "TELEGRAM_LEDGER_INCOMPLETE",
            "channel": "telegram",
            "manifest_count": 39,
            "confirmed_count": 38,
        },
    )
    monkeypatch.setattr(bot_mod, "build_waybill_control_readiness", lambda **_kwargs: _green_readiness())
    monkeypatch.setattr(bot_mod.subprocess, "run", lambda command, cwd, env: calls.append(command) or _Result())
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 21, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert calls == [[str(bot_mod.sys.executable), str(bot_mod.CLOSEOUT_SCHEDULER_PATH), "--resume"]]
    assert any("resuming delivery" in msg.lower() for msg in sent_messages)


def test_waybill_telegram_ordered_resend_is_disabled_without_confirm(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 33,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/resend_today_ordered",
                },
            }
        ],
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 5, 7, 17, 30, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("permanently disabled" in msg.lower() for msg in sent_messages)


def test_waybill_telegram_ordered_resend_is_disabled_even_with_confirm(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 34,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/resend_today_ordered confirm",
                },
            }
        ],
    )

    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 5, 7, 17, 30, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("permanently disabled" in msg.lower() for msg in sent_messages)


def test_waybill_telegram_final_table_resends_summary(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 32,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/final_table",
                },
            }
        ],
    )
    monkeypatch.setattr(
        bot_mod,
        "send_final_status_table",
        lambda **_kwargs: {
            "ok": True,
            "final_status_sent": True,
            "final_status_message_id": "55",
            "confirmed_total": 39,
            "total": 39,
        },
    )
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 21, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert any("final table sent" in msg.lower() for msg in sent_messages)
    assert any("55" in msg for msg in sent_messages)


def test_waybill_telegram_handover_done_waits_60_seconds_then_reports_pending(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "HANDOVER_MANUAL_DELAY_SECONDS", 60)
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    updates = [
        {
            "update_id": 45,
            "message": {
                "chat": {"id": -5102810505},
                "from": {"id": 42},
                "text": "Передал курьеру",
            },
        }
    ]
    monkeypatch.setattr(bot_mod, "_get_updates", lambda token, offset: updates)
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    first_rc = bot_mod.poll_once(now=datetime(2026, 5, 7, 18, 30, tzinfo=ZoneInfo("Asia/Almaty")))

    state = json.loads(bot_mod.STATE_FILE.read_text(encoding="utf-8"))
    assert first_rc == 0
    assert state["pending_handover_check"]["mode"] == "manual"
    assert state["pending_handover_check"]["target_date"] == "2026-05-07"
    assert any("60" in msg and "handover" in msg.lower() for msg in sent_messages)

    updates.clear()
    monkeypatch.setattr(
        bot_mod,
        "build_waybill_handover_report",
        lambda **_kwargs: {
            "ok": False,
            "status": "PHYSICAL_HANDOVER_PENDING",
            "pending_count": 1,
            "pending_orders": [{"order_id": "914180723", "store": "AcmeWear"}],
        },
    )
    monkeypatch.setattr(
        bot_mod,
        "format_handover_compact_status_message",
        lambda report: f"{report['status']} {report['pending_orders'][0]['order_id']}",
    )

    second_rc = bot_mod.poll_once(now=datetime(2026, 5, 7, 18, 31, 1, tzinfo=ZoneInfo("Asia/Almaty")))

    state_after = json.loads(bot_mod.STATE_FILE.read_text(encoding="utf-8")) if bot_mod.STATE_FILE.exists() else {}
    assert second_rc == 0
    assert "pending_handover_check" not in state_after
    assert any("PHYSICAL_HANDOVER_PENDING 914180723" in msg for msg in sent_messages)


def test_waybill_telegram_handover_status_uses_compact_by_default_and_full_on_request(monkeypatch, tmp_path: Path):
    sent_messages: list[str] = []
    reports = [
        {"ok": False, "status": "PHYSICAL_HANDOVER_PENDING", "pending_count": 70},
        {"ok": False, "status": "PHYSICAL_HANDOVER_PENDING", "pending_count": 70},
    ]

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 90,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "Передача",
                },
            },
            {
                "update_id": 91,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/hfull",
                },
            },
        ],
    )
    monkeypatch.setattr(bot_mod, "build_waybill_handover_report", lambda **_kwargs: reports.pop(0))
    monkeypatch.setattr(bot_mod, "format_handover_compact_status_message", lambda report: f"COMPACT {report['pending_count']}")
    monkeypatch.setattr(bot_mod, "format_handover_status_message", lambda report: f"FULL {report['pending_count']}")
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 5, 8, 18, 30, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert sent_messages == ["COMPACT 70", "FULL 70"]


def test_waybill_telegram_passive_handover_watch_waits_until_20_and_posts_once(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "passive_handover_watch": {
                    "target_date": "2026-05-08",
                    "chat_id": "-5102810505",
                    "armed_at": "2026-05-08T18:20:00+05:00",
                    "next_check_at": "2026-05-08T18:21:00+05:00",
                    "attempts": 0,
                    "max_checks": 5,
                    "interval_seconds": 60,
                }
            }
        ),
        encoding="utf-8",
    )
    sent_messages: list[str] = []
    reports = [
        {
            "ok": False,
            "status": "PHYSICAL_HANDOVER_PENDING",
            "pending_count": 1,
            "pending_orders": [{"order_id": "914180723", "store": "AcmeWear"}],
        }
    ]

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", state_path)
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_get_updates", lambda token, offset: [])
    monkeypatch.setattr(bot_mod, "build_waybill_handover_report", lambda **_kwargs: reports.pop(0))
    monkeypatch.setattr(bot_mod, "format_handover_compact_status_message", lambda report: report["status"])
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    first_rc = bot_mod.poll_once(now=datetime(2026, 5, 8, 18, 22, 0, tzinfo=ZoneInfo("Asia/Almaty")))
    state_after_first = json.loads(state_path.read_text(encoding="utf-8"))
    second_rc = bot_mod.poll_once(now=datetime(2026, 5, 8, 20, 0, 1, tzinfo=ZoneInfo("Asia/Almaty")))
    state_after_second = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    assert first_rc == 0
    assert second_rc == 0
    assert state_after_first["passive_handover_watch"]["attempts"] == 0
    assert state_after_first["passive_handover_watch"]["next_check_at"] == "2026-05-08T20:00:00+05:00"
    assert "passive_handover_watch" not in state_after_second
    assert sent_messages == ["PHYSICAL_HANDOVER_PENDING"]


def test_waybill_telegram_halt_clears_pending_and_sets_run_control_hold(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "pending_ready": {
                    "target_date": "2026-04-15",
                    "chat_id": "-5102810505",
                    "user_id": "42",
                    "requested_at": "2026-04-15T17:00:00+05:00",
                }
            }
        ),
        encoding="utf-8",
    )
    sent_messages: list[str] = []
    hold_calls: list[dict[str, object]] = []

    monkeypatch.setenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(bot_mod, "STATE_FILE", state_path)
    monkeypatch.setattr(bot_mod, "get_waybill_telegram_config", lambda: {"token": "token", "chat_id": "-5102810505"})
    monkeypatch.setattr(bot_mod, "_load_offset", lambda: None)
    monkeypatch.setattr(bot_mod, "_save_offset", lambda offset: None)
    monkeypatch.setattr(
        bot_mod,
        "_get_updates",
        lambda token, offset: [
            {
                "update_id": 22,
                "message": {
                    "chat": {"id": -5102810505},
                    "from": {"id": 42},
                    "text": "/halt",
                },
            }
        ],
    )
    monkeypatch.setattr(bot_mod, "set_run_control_hold", lambda **kwargs: hold_calls.append(kwargs))
    monkeypatch.setattr(bot_mod, "send_message", lambda **kwargs: sent_messages.append(kwargs["text"]) or {"success": True})

    rc = bot_mod.poll_once(now=datetime(2026, 4, 15, 17, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    assert rc == 0
    assert not state_path.exists() or "pending_ready" not in json.loads(state_path.read_text(encoding="utf-8"))
    assert hold_calls
    assert any("halted" in msg.lower() for msg in sent_messages)
