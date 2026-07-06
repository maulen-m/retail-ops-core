import types

from core.alerts import error_alerts


def test_alert_from_run_tracker_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(
        error_alerts,
        "send_message",
        lambda *args, **kwargs: {"success": True},
    )

    tracker = types.SimpleNamespace(
        run_id=123,
        run_type="END_OF_DAY",
        status="SUCCESS",
        steps=[types.SimpleNamespace(name="step_one", status="SUCCESS")],
        error_summary=[],
    )

    tracker.to_summary = lambda: {
        "run_id": 123,
        "run_type": "END_OF_DAY",
        "status": "SUCCESS",
        "duration_seconds": 12.0,
        "steps_total": 1,
        "steps_completed": 1,
        "errors_count": 0,
        "error_summary": [],
    }

    assert error_alerts.alert_from_run_tracker(tracker) is True


def test_alert_from_run_tracker_marks_only_cashfloor_failure_as_accepted(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    sent = {}

    def _fake_error_alert(**kwargs):
        sent.update(kwargs)
        return True

    monkeypatch.setattr(error_alerts, "send_error_alert", _fake_error_alert)

    tracker = types.SimpleNamespace(
        run_id=124,
        run_type="END_OF_DAY",
        status="FAILED",
        steps=[
            types.SimpleNamespace(name="0. Validate Parameters", status="SUCCESS"),
            types.SimpleNamespace(name="5a2. Cashflow PO Preflight", status="FAILED"),
        ],
        error_summary=[
            "5a2. Cashflow PO Preflight: min_cash below conservative floor"
        ],
    )
    tracker.to_summary = lambda: {
        "run_id": 124,
        "run_type": "END_OF_DAY",
        "status": "FAILED",
        "duration_seconds": 12.0,
        "steps_total": 2,
        "steps_completed": 1,
        "errors_count": 1,
        "error_summary": tracker.error_summary,
    }

    assert error_alerts.alert_from_run_tracker(tracker) is True
    assert error_alerts.ACCEPTED_FLOOR_RED_STATUS in sent["error_message"]
    assert "Status: FAILED" not in sent["error_message"]


def test_alert_from_run_tracker_keeps_failed_when_anything_else_fails(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    sent = {}

    def _fake_error_alert(**kwargs):
        sent.update(kwargs)
        return True

    monkeypatch.setattr(error_alerts, "send_error_alert", _fake_error_alert)

    tracker = types.SimpleNamespace(
        run_id=125,
        run_type="END_OF_DAY",
        status="FAILED",
        steps=[
            types.SimpleNamespace(name="0. Validate Parameters", status="SUCCESS"),
            types.SimpleNamespace(name="5a2. Cashflow PO Preflight", status="FAILED"),
            types.SimpleNamespace(name="6. Audit Dashboard Output", status="FAILED"),
        ],
        error_summary=[
            "5a2. Cashflow PO Preflight: min_cash below conservative floor",
            "6. Audit Dashboard Output: export missing",
        ],
    )
    tracker.to_summary = lambda: {
        "run_id": 125,
        "run_type": "END_OF_DAY",
        "status": "FAILED",
        "duration_seconds": 12.0,
        "steps_total": 3,
        "steps_completed": 1,
        "errors_count": 2,
        "error_summary": tracker.error_summary,
    }

    assert error_alerts.alert_from_run_tracker(tracker) is True
    assert "Status: FAILED" in sent["error_message"]
    assert error_alerts.ACCEPTED_FLOOR_RED_STATUS not in sent["error_message"]


def test_send_shadow_mode_digest_success(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(
        error_alerts,
        "send_message",
        lambda *args, **kwargs: {"success": True},
    )

    db_path = tmp_path / "db" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.touch()

    assert error_alerts.send_shadow_mode_digest(1, 10.0, str(db_path)) is True


def test_send_run_success_alert_guarded(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(
        error_alerts,
        "send_message",
        lambda *args, **kwargs: {"success": True},
    )

    assert error_alerts.send_run_success_alert("ok", "shadow") is True


def test_send_run_failure_alert_guarded(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(
        error_alerts,
        "send_message",
        lambda *args, **kwargs: {"success": True},
    )

    assert error_alerts.send_run_failure_alert("boom", "shadow") is True
