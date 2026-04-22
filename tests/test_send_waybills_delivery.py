from datetime import date
from pathlib import Path

from scripts import send_waybills_delivery as delivery_mod


def test_delivery_uses_telegram_success_without_whatsapp(monkeypatch, tmp_path: Path):
    whatsapp_calls: list[dict] = []

    monkeypatch.setattr(
        delivery_mod,
        "run_telegram_sender",
        lambda **_kwargs: {"ok": True, "sent": 2, "failed": 0, "fallback_allowed": False},
    )
    monkeypatch.setattr(
        delivery_mod,
        "delivery_completion_state",
        lambda **_kwargs: {"completed": True, "channel": "telegram", "status": "TELEGRAM_CONFIRMED"},
    )
    monkeypatch.setattr(
        delivery_mod,
        "run_whatsapp_fallback",
        lambda **kwargs: whatsapp_calls.append(kwargs) or {"ok": True, "returncode": 0},
    )

    report = delivery_mod.run_delivery(
        today_folder=tmp_path,
        expected_target_date=date(2026, 4, 21),
        telegram_token="token-1",
        telegram_chat_id="-1001",
    )

    assert report["ok"] is True
    assert report["primary_channel"] == "telegram"
    assert report["delivery_channel"] == "telegram"
    assert report["whatsapp_fallback_attempted"] is False
    assert whatsapp_calls == []


def test_delivery_blocks_telegram_ok_when_ledger_is_incomplete(monkeypatch, tmp_path: Path):
    whatsapp_calls: list[dict] = []

    monkeypatch.setattr(
        delivery_mod,
        "run_telegram_sender",
        lambda **_kwargs: {"ok": True, "sent": 2, "failed": 0, "fallback_allowed": False},
    )
    monkeypatch.setattr(
        delivery_mod,
        "delivery_completion_state",
        lambda **_kwargs: {"completed": False, "channel": "telegram", "status": "TELEGRAM_LEDGER_INCOMPLETE"},
    )
    monkeypatch.setattr(
        delivery_mod,
        "run_whatsapp_fallback",
        lambda **kwargs: whatsapp_calls.append(kwargs) or {"ok": True, "returncode": 0},
    )

    report = delivery_mod.run_delivery(
        today_folder=tmp_path,
        expected_target_date=date(2026, 4, 21),
        telegram_token="token-1",
        telegram_chat_id="-1001",
    )

    assert report["ok"] is False
    assert report["failure_stage"] == "telegram_primary"
    assert "TELEGRAM_LEDGER_INCOMPLETE" in report["failure_reason"]
    assert whatsapp_calls == []


def test_delivery_auto_falls_back_to_whatsapp_only_when_telegram_sent_zero(monkeypatch, tmp_path: Path):
    whatsapp_calls: list[dict] = []

    monkeypatch.setattr(
        delivery_mod,
        "run_telegram_sender",
        lambda **_kwargs: {
            "ok": False,
            "sent": 0,
            "failed": 1,
            "halted": True,
            "halt_reason": "TELEGRAM_CONFIG",
            "fallback_allowed": True,
        },
    )
    monkeypatch.setattr(
        delivery_mod,
        "run_whatsapp_fallback",
        lambda **kwargs: whatsapp_calls.append(kwargs) or {"ok": True, "returncode": 0},
    )
    monkeypatch.setattr(
        delivery_mod,
        "delivery_completion_state",
        lambda **_kwargs: {"completed": True, "channel": "whatsapp", "status": "WHATSAPP_CONFIRMED"},
    )

    report = delivery_mod.run_delivery(
        today_folder=tmp_path,
        expected_target_date=date(2026, 4, 21),
        telegram_token="",
        telegram_chat_id="",
    )

    assert report["ok"] is True
    assert report["delivery_channel"] == "whatsapp"
    assert report["whatsapp_fallback_attempted"] is True
    assert len(whatsapp_calls) == 1


def test_delivery_blocks_whatsapp_fallback_ok_when_ledger_is_incomplete(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        delivery_mod,
        "run_telegram_sender",
        lambda **_kwargs: {
            "ok": False,
            "sent": 0,
            "failed": 1,
            "halted": True,
            "halt_reason": "TELEGRAM_CONFIG",
            "fallback_allowed": True,
        },
    )
    monkeypatch.setattr(
        delivery_mod,
        "run_whatsapp_fallback",
        lambda **_kwargs: {"ok": True, "returncode": 0},
    )
    monkeypatch.setattr(
        delivery_mod,
        "delivery_completion_state",
        lambda **_kwargs: {"completed": False, "channel": "whatsapp", "status": "WHATSAPP_LEDGER_INCOMPLETE"},
    )

    report = delivery_mod.run_delivery(
        today_folder=tmp_path,
        expected_target_date=date(2026, 4, 21),
        telegram_token="",
        telegram_chat_id="",
    )

    assert report["ok"] is False
    assert report["delivery_channel"] == ""
    assert report["whatsapp_fallback_attempted"] is True
    assert report["failure_stage"] == "whatsapp_fallback"
    assert "WHATSAPP_LEDGER_INCOMPLETE" in report["failure_reason"]


def test_delivery_blocks_whatsapp_after_partial_telegram_send(monkeypatch, tmp_path: Path):
    whatsapp_calls: list[dict] = []

    monkeypatch.setattr(
        delivery_mod,
        "run_telegram_sender",
        lambda **_kwargs: {
            "ok": False,
            "sent": 1,
            "failed": 1,
            "halted": True,
            "halt_reason": "TELEGRAM_UNSURE",
            "fallback_allowed": False,
        },
    )
    monkeypatch.setattr(
        delivery_mod,
        "run_whatsapp_fallback",
        lambda **kwargs: whatsapp_calls.append(kwargs) or {"ok": True, "returncode": 0},
    )

    report = delivery_mod.run_delivery(
        today_folder=tmp_path,
        expected_target_date=date(2026, 4, 21),
        telegram_token="token-1",
        telegram_chat_id="-1001",
    )

    assert report["ok"] is False
    assert report["delivery_channel"] == ""
    assert report["whatsapp_fallback_attempted"] is False
    assert report["failure_stage"] == "telegram_primary"
    assert whatsapp_calls == []
