from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from core.alerts import ops_alert_outbox as outbox_mod
from core.alerts.google_ops_board_alerts import send_owner_ops_alert


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _isolate(monkeypatch, tmp_path: Path) -> Path:
    outbox_path = tmp_path / "runtime" / "state" / "ops_alert_outbox.jsonl"
    monkeypatch.setattr(outbox_mod, "DEFAULT_OUTBOX_PATH", outbox_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(outbox_mod.time, "sleep", lambda _seconds: None)
    return outbox_path


def test_send_owner_alert_is_queued_before_successful_delivery(monkeypatch, tmp_path: Path) -> None:
    outbox_path = _isolate(monkeypatch, tmp_path)
    post_calls: list[dict[str, object]] = []

    def _post(_url, *, json, timeout):
        post_calls.append({"payload": json, "timeout": timeout})
        assert _events(outbox_path)[0]["status"] == "queued"
        return _Response({"ok": True, "result": {"message_id": 321}})

    monkeypatch.setattr("core.alerts.telegram.requests.post", _post)

    assert send_owner_ops_alert(title="Queued first", lines=["line 1"]) is True
    events = _events(outbox_path)
    assert [event["status"] for event in events] == ["queued", "delivered"]
    assert events[-1]["telegram_message_id"] == "321"
    assert len(post_calls) == 1


def test_delivery_retries_three_times_with_one_and_five_second_backoff(
    monkeypatch,
    tmp_path: Path,
) -> None:
    outbox_path = _isolate(monkeypatch, tmp_path)
    sleeps: list[int] = []
    responses = iter(
        [
            {"ok": False, "description": "first"},
            {"ok": False, "description": "second"},
            {"ok": True, "result": {"message_id": 99}},
        ]
    )
    monkeypatch.setattr(
        "core.alerts.telegram.requests.post",
        lambda *_args, **_kwargs: _Response(next(responses)),
    )
    monkeypatch.setattr(outbox_mod.time, "sleep", sleeps.append)

    assert outbox_mod.enqueue_alert(title="Retry", lines=["detail"]) is True
    delivered = _events(outbox_path)[-1]
    assert delivered["status"] == "delivered"
    assert len(delivered["attempts"]) == 3
    assert sleeps == [1, 5]


def test_total_telegram_failure_uses_macos_fallback(monkeypatch, tmp_path: Path) -> None:
    outbox_path = _isolate(monkeypatch, tmp_path)
    fallback_calls: list[list[str]] = []
    monkeypatch.setattr(
        "core.alerts.telegram.requests.post",
        lambda *_args, **_kwargs: _Response(
            {
                "ok": False,
                "description": "https://api.telegram.org/bottest-token/sendMessage offline",
            }
        ),
    )

    def _run(command, **_kwargs):
        fallback_calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(outbox_mod.subprocess, "run", _run)

    assert outbox_mod.enqueue_alert(title="Fallback", lines=["detail"]) is False
    failed = _events(outbox_path)[-1]
    assert failed["status"] == "telegram_failed_notified"
    assert failed["macos_fallback_notified"] is True
    assert len(failed["attempts"]) == 3
    assert fallback_calls[0][:2] == ["osascript", "-e"]
    assert "test-token" not in outbox_path.read_text(encoding="utf-8")
    assert "bot<redacted>/sendMessage" in failed["last_error"]


def test_held_alert_is_not_sent_until_flush_held(monkeypatch, tmp_path: Path) -> None:
    outbox_path = _isolate(monkeypatch, tmp_path)
    post_calls: list[object] = []

    def _post(*_args, **_kwargs):
        post_calls.append(object())
        return _Response({"ok": True, "result": {"message_id": 55}})

    monkeypatch.setattr("core.alerts.telegram.requests.post", _post)

    assert outbox_mod.enqueue_alert(title="Held", lines=["detail"], held=True) is False
    assert post_calls == []
    assert _events(outbox_path)[-1]["held"] is True

    result = outbox_mod.flush_held("barrier superseded")
    assert result == {"attempted": 1, "delivered": 1}
    assert len(post_calls) == 1
    events = _events(outbox_path)
    assert [event["status"] for event in events] == ["queued", "queued", "delivered"]
    assert events[-2]["held_release_reason"] == "barrier superseded"


def test_jsonl_remains_parseable_across_failed_flush_and_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    outbox_path = _isolate(monkeypatch, tmp_path)
    post_ok = {"value": False}

    def _post(*_args, **_kwargs):
        if post_ok["value"]:
            return _Response({"ok": True, "result": {"message_id": 88}})
        return _Response({"ok": False, "description": "offline"})

    monkeypatch.setattr("core.alerts.telegram.requests.post", _post)
    monkeypatch.setattr(
        outbox_mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    assert outbox_mod.enqueue_alert(title="Flush me", lines=["detail"]) is False
    post_ok["value"] = True
    assert outbox_mod.flush_undelivered() == {"attempted": 1, "delivered": 1}

    events = _events(outbox_path)
    assert [event["status"] for event in events] == ["queued", "failed", "delivered"]
    assert len({event["alert_id"] for event in events}) == 1
    assert outbox_path.read_bytes().endswith(b"\n")


def test_dedup_key_suppresses_repeats_for_one_hour(monkeypatch, tmp_path: Path) -> None:
    outbox_path = _isolate(monkeypatch, tmp_path)
    post_calls: list[object] = []
    clock = {"now": datetime(2026, 7, 18, 5, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(outbox_mod, "_now", lambda: clock["now"])

    def _post(*_args, **_kwargs):
        post_calls.append(object())
        return _Response({"ok": True, "result": {"message_id": len(post_calls)}})

    monkeypatch.setattr("core.alerts.telegram.requests.post", _post)

    assert outbox_mod.enqueue_alert(title="Dedup", lines=["detail"], dedup_key="same") is True
    clock["now"] += timedelta(minutes=59)
    assert outbox_mod.enqueue_alert(title="Dedup", lines=["detail"], dedup_key="same") is True
    assert len(post_calls) == 1

    clock["now"] += timedelta(minutes=2)
    assert outbox_mod.enqueue_alert(title="Dedup", lines=["detail"], dedup_key="same") is True
    assert len(post_calls) == 2
    assert len({event["alert_id"] for event in _events(outbox_path)}) == 2
