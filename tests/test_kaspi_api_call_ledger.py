from __future__ import annotations

from datetime import date
import json

from core.integrations.kaspi_api_client import KaspiAPIClient
from scripts import run_google_ops_board_closeout_scheduler as closeout_scheduler_mod
from scripts import run_google_ops_board_prewindow_health_scheduler as prewindow_scheduler_mod
from scripts import run_google_ops_board_publish_scheduler as publish_scheduler_mod
from scripts import run_kaspi_import_scheduler as import_scheduler_mod
from scripts.google_ops_board_automation_common import ensure_kaspi_api_call_ledger_env


class _FakeResponse:
    status_code = 200
    ok = True
    text = "{}"

    def json(self):
        return {"data": []}


class _Result:
    returncode = 0


def test_kaspi_api_client_writes_redacted_call_ledger(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "kaspi_api_calls.jsonl"
    monkeypatch.setenv("KASPI_API_CALL_LEDGER_PATH", str(ledger_path))
    monkeypatch.setattr("core.integrations.kaspi_api_client.time.sleep", lambda _seconds: None)

    client = KaspiAPIClient(store_code="UNIVERSAL", token="secret-token-1")
    monkeypatch.setattr(client._session, "request", lambda **_kwargs: _FakeResponse())

    response = client._request("GET", "orders/abc123/entries", params={"token": "secret-token-1"})

    assert response.success is True
    entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["store_code"] == "UNIVERSAL"
    assert entry["method"] == "GET"
    assert entry["endpoint_family"] == "orders/{id}/entries"
    assert entry["status_code"] == 200
    assert entry["success"] is True
    assert entry["duration_sec"] >= 0
    assert "secret-token-1" not in json.dumps(entry)


def test_google_ops_scheduler_sets_daily_kaspi_api_ledger_path(tmp_path) -> None:
    env: dict[str, str] = {}

    ensure_kaspi_api_call_ledger_env(env, target_date=date(2026, 4, 22), project_root=tmp_path)

    assert env["KASPI_API_CALL_LEDGER_PATH"] == str(tmp_path / "runtime" / "api_ledger" / "kaspi_api_2026-04-22.jsonl")


def test_google_ops_scheduler_preserves_explicit_kaspi_api_ledger(monkeypatch, tmp_path) -> None:
    env = {"KASPI_API_CALL_LEDGER_PATH": str(tmp_path / "custom.jsonl")}

    ensure_kaspi_api_call_ledger_env(env, target_date=date(2026, 4, 22), project_root=tmp_path)

    assert env["KASPI_API_CALL_LEDGER_PATH"] == str(tmp_path / "custom.jsonl")


def test_publish_scheduler_child_processes_receive_default_daily_ledger(monkeypatch, tmp_path) -> None:
    env: dict[str, str] = {}
    child_envs: list[dict[str, str]] = []

    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    monkeypatch.setattr(publish_scheduler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(publish_scheduler_mod, "today_almaty", lambda: date(2026, 4, 22))
    monkeypatch.setattr(publish_scheduler_mod, "is_source_refresh_slot", lambda now=None: False)
    monkeypatch.setattr(
        publish_scheduler_mod,
        "inspect_activeorders_source",
        lambda *_args, **_kwargs: {
            "fresh": True,
            "path": "ActiveOrders.xlsx",
            "mtime_date": "2026-04-22",
            "target_row_count": 1,
        },
    )
    monkeypatch.setattr(
        publish_scheduler_mod,
        "write_source_snapshot",
        lambda **_kwargs: {"path": str(tmp_path / "source_snapshot.json")},
    )
    monkeypatch.setattr(
        publish_scheduler_mod,
        "ensure_prewindow_health",
        lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "health.json")},
    )
    monkeypatch.setattr(
        publish_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: child_envs.append(dict(env)) or _Result(),
    )

    rc = publish_scheduler_mod.run_publish_cycle(
        env=env,
        service_account_json=str(tmp_path / "svc.json"),
        spreadsheet_id="sheet-id",
    )

    expected = str(tmp_path / "runtime" / "api_ledger" / "kaspi_api_2026-04-22.jsonl")
    assert rc == 0
    assert env["KASPI_API_CALL_LEDGER_PATH"] == expected
    assert child_envs
    assert all(child_env["KASPI_API_CALL_LEDGER_PATH"] == expected for child_env in child_envs)


def test_kaspi_import_scheduler_child_processes_receive_default_daily_ledger(monkeypatch, tmp_path) -> None:
    source_refresh_path = tmp_path / "run_google_ops_board_publish_scheduler.py"
    source_refresh_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    child_envs: list[dict[str, str]] = []
    child_commands: list[list[str]] = []

    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    monkeypatch.setattr(import_scheduler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(import_scheduler_mod, "SOURCE_REFRESH_PATH", source_refresh_path)
    monkeypatch.setattr(import_scheduler_mod, "today_almaty", lambda: date(2026, 4, 22))
    monkeypatch.setattr(
        import_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: (
            child_commands.append(list(command)),
            child_envs.append(dict(env)),
            _Result(),
        )[-1],
    )

    rc = import_scheduler_mod.main()

    expected = str(tmp_path / "runtime" / "api_ledger" / "kaspi_api_2026-04-22.jsonl")
    assert rc == 0
    assert child_commands == [
        [import_scheduler_mod.sys.executable, str(source_refresh_path), "--force-source-refresh"]
    ]
    assert len(child_envs) == 1
    assert all(child_env["KASPI_API_CALL_LEDGER_PATH"] == expected for child_env in child_envs)


def test_closeout_scheduler_child_processes_receive_default_daily_ledger(monkeypatch, tmp_path) -> None:
    script_path = tmp_path / "run_google_ops_board_closeout.py"
    db_check_path = tmp_path / "check_local_app_db.py"
    creds_path = tmp_path / "svc.json"
    script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    db_check_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    creds_path.write_text("{}", encoding="utf-8")
    child_envs: list[dict[str, str]] = []

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    monkeypatch.setattr(closeout_scheduler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(closeout_scheduler_mod, "SCRIPT_PATH", script_path)
    monkeypatch.setattr(closeout_scheduler_mod, "DB_CHECK_PATH", db_check_path)
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 22))
    monkeypatch.setattr(closeout_scheduler_mod, "load_ops_board_contract", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(closeout_scheduler_mod, "resolve_service_account_json", lambda **_kwargs: creds_path)
    monkeypatch.setattr(closeout_scheduler_mod, "resolve_spreadsheet_id", lambda *_args, **_kwargs: "sheet-id")
    monkeypatch.setattr(closeout_scheduler_mod, "_closeout_already_completed", lambda **_kwargs: False)
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_current_ready_identity",
        lambda **_kwargs: {
            "target_date": "2026-04-22",
            "ready_set_at": "2026-04-22T17:10:00+05:00",
            "ready_for_closeout": "READY",
        },
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: child_envs.append(dict(env)) or _Result(),
    )

    rc = closeout_scheduler_mod.main(
        [
            "--expected-target-date",
            "2026-04-22",
            "--expected-ready-set-at",
            "2026-04-22T17:10:00+05:00",
        ]
    )

    expected = str(tmp_path / "runtime" / "api_ledger" / "kaspi_api_2026-04-22.jsonl")
    assert rc == 0
    assert len(child_envs) == 2
    assert all(child_env["KASPI_API_CALL_LEDGER_PATH"] == expected for child_env in child_envs)


def test_prewindow_health_scheduler_child_process_receives_default_daily_ledger(monkeypatch, tmp_path) -> None:
    script_path = tmp_path / "run_google_ops_board_prewindow_health.py"
    creds_path = tmp_path / "svc.json"
    script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    creds_path.write_text("{}", encoding="utf-8")
    child_envs: list[dict[str, str]] = []

    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds_path))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(prewindow_scheduler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(prewindow_scheduler_mod, "SCRIPT_PATH", script_path)
    monkeypatch.setattr(prewindow_scheduler_mod, "today_almaty", lambda: date(2026, 4, 22))
    monkeypatch.setattr(
        prewindow_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: child_envs.append(dict(env)) or _Result(),
    )

    rc = prewindow_scheduler_mod.main()

    expected = str(tmp_path / "runtime" / "api_ledger" / "kaspi_api_2026-04-22.jsonl")
    assert rc == 0
    assert len(child_envs) == 1
    assert child_envs[0]["KASPI_API_CALL_LEDGER_PATH"] == expected
