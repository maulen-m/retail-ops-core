from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.integrations.google_ops_board import load_ops_board_contract
from scripts import run_google_ops_board_closeout_scheduler as closeout_scheduler_mod
from scripts import run_google_ops_board_closeout_watch_scheduler as watch_mod
from scripts import run_google_ops_board_size_writeback_scheduler as writeback_scheduler_mod


class _FakeClient:
    def __init__(self, tab_values: dict[str, list[list[str]]]) -> None:
        self._tab_values = tab_values
        self.update_calls: list[dict[str, object]] = []

    def get_tab_values(self, tab_name: str):
        return self._tab_values.get(tab_name, [])

    def update_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, object]]) -> None:
        if rows:
            self.update_calls.append({"tab_name": tab_name, "headers": headers, "rows": rows})
        matrix = self._tab_values.setdefault(tab_name, [headers])
        for update in rows:
            sheet_row = int(update["sheet_row"])
            while len(matrix) < sheet_row:
                matrix.append([""] * len(headers))
            matrix[sheet_row - 1] = [str(update["row"].get(header, "")) for header in headers]


def _write_creds(tmp_path: Path) -> Path:
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    return creds


def _stub_closeout_health_green(monkeypatch, tmp_path: Path) -> None:
    return None


def test_early_closeout_watch_arms_debounce_when_board_first_becomes_ready(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", "BLOCKED"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    now = datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty"))

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(watch_mod, "now_almaty", lambda: now)
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["target_date"] == "2026-04-15"
    assert state["armed_at"] == now.isoformat()


def test_early_closeout_watch_triggers_scheduler_only_after_debounce_elapsed(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", "BLOCKED"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    child_envs: list[dict[str, str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or child_envs.append(dict(env)) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[str(watch_mod.sys.executable), str(watch_mod.SCRIPT_PATH), "--resume"]]
    assert child_envs[0]["KASPI_API_CALL_LEDGER_PATH"].endswith("runtime/api_ledger/kaspi_api_2026-04-15.jsonl")
    assert not state_path.exists()


def test_early_closeout_watch_delegates_health_gate_to_closeout_runner(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", "BLOCKED"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )
    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or type("Result", (), {"returncode": 0})(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[str(watch_mod.sys.executable), str(watch_mod.SCRIPT_PATH), "--resume"]]
    assert not state_path.exists()


def test_early_closeout_watch_auto_fills_blank_sizes_after_1857_and_triggers_without_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "2XL",
                    "Комплект ACMEWEAR OF_LINE51_BLK_2XL_58",
                    "CL_OC_MEN_LINE51_WHITE",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "HIGH",
                ],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", tmp_path / "ready_watch_state.json")
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "product_type": "CL",
            }
        },
    )

    readiness_calls = {"count": 0}

    def _fake_readiness(**_kwargs):
        readiness_calls["count"] += 1
        if readiness_calls["count"] == 1:
            return {
                "ready": False,
                "run_control_ready_ok": False,
                "blank_size_count": 1,
                "invalid_size_count": 0,
            }
        return {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        }

    monkeypatch.setattr(watch_mod, "build_readiness_report", _fake_readiness)

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[str(watch_mod.sys.executable), str(watch_mod.SCRIPT_PATH), "--resume"]]


def test_early_closeout_watch_writes_auto_fill_audit_after_1857(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "2XL",
                    "Комплект ACMEWEAR",
                    "CL_OC_MEN_LINE52_BLACK",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "HIGH",
                ],
            ],
        }
    )
    audit_root = tmp_path / "audit"

    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", audit_root, raising=False)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE52_BLACK",
                "product_type": "CL",
            }
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["salesraw_updates_applied"] == 1
    audit_files = list((audit_root / "2026-04-15").glob("auto_probable_closeout_*.json"))
    assert len(audit_files) == 1
    payload = json.loads(audit_files[0].read_text(encoding="utf-8"))
    assert payload["target_date"] == "2026-04-15"
    assert payload["applied_rows"][0]["OrderID"] == "1001"
    assert payload["applied_rows"][0]["MY_SIZE"] == "2XL"
    assert client.get_tab_values("SalesRaw_Today")[1][8] == "2XL"
    assert client.get_tab_values("Run_Control")[1][1] == "READY"
    assert client.get_tab_values("Run_Control")[1][2] == watch_mod.AUTO_READY_SET_BY
    assert "AUTO_1857 probable backfill: 1 row(s)" in client.get_tab_values("Run_Control")[1][4]


def test_early_closeout_watch_requires_visible_probable_size_after_1857(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "",
                    "Комплект ACMEWEAR OF_LINE51_BLK_2XL_58",
                    "CL_OC_MEN_LINE51_WHITE",
                    "1",
                    "line-1",
                    "",
                    "",
                ],
            ],
        }
    )
    audit_root = tmp_path / "audit"

    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", audit_root, raising=False)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "product_type": "CL",
            }
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["salesraw_updates_applied"] == 0
    assert report["run_control_updated"] is False
    assert report["blank_rows_remaining"][0]["OrderID"] == "1001"
    assert report["blank_rows_remaining"][0]["reason"] == "MISSING_PROBABLE_SIZE"
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


def test_early_closeout_watch_rejects_invalid_probable_size_after_1857(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "NOT_A_SIZE",
                    "Комплект ACMEWEAR",
                    "CL_OC_MEN_LINE52_BLACK",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "LOW",
                ],
            ],
        }
    )
    audit_root = tmp_path / "audit"

    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", audit_root, raising=False)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE52_BLACK",
                "product_type": "CL",
            }
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["salesraw_updates_applied"] == 0
    assert report["run_control_updated"] is False
    assert report["blank_rows_remaining"][0]["OrderID"] == "1001"
    assert report["blank_rows_remaining"][0]["reason"] == "INVALID_PROBABLE_SIZE"
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


def test_early_closeout_watch_blank_probable_size_after_1857_blocks_closeout(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Line51", "1001", "", "", "Offer", "CL_TEST", "1", "line", "", ""],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", tmp_path / "ready_watch_state.json")
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {"1": {"assigned_size": "", "store_code": "UNIVERSAL", "sku_key": "CL_TEST", "product_type": "CL"}},
    )
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": False,
            "blank_size_count": 1,
            "blank_size_rows": [{"OrderID": "1001", "_db_row_id": "1"}],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )
    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command))

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


def test_early_closeout_watch_skips_when_board_is_not_ready(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "adil", "", "", "", "", ""],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": False,
            "blank_size_count": 3,
            "invalid_size_count": 0,
        },
    )
    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    assert not state_path.exists()


def test_early_closeout_watch_marks_ready_with_missing_sizes_as_recoverable_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
                ["TODAY", "2026-04-15", "AcmeWear", "", "", "1", "Line51", "1002", "", "2XL", "Offer", "SKU-2", "2", "line", "DEFAULT", "LOW"],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text('{"target_date":"2026-04-15","armed_at":"2026-04-15T17:10:00+05:00"}', encoding="utf-8")

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": True,
            "blank_size_count": 2,
            "blank_size_rows": [
                {"OrderID": "1001", "STORE_NAME": "Universal", "_db_row_id": "1"},
                {"OrderID": "1002", "STORE_NAME": "AcmeWear", "_db_row_id": "2"},
            ],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )
    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command))

    rc = watch_mod.main()

    run_control = client.get_tab_values("Run_Control")[1]
    assert rc == 0
    assert calls == []
    assert run_control[1] == "READY"
    assert run_control[7] == "BLOCKED_MISSING_SIZES"
    assert "1001" in run_control[4]
    assert "1002" in run_control[4]
    assert not state_path.exists()


def test_early_closeout_watch_ready_block_marker_is_idempotent(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    note = "BLOCKED_MISSING_SIZES: fill MY_SIZE for orders 1001, 1002"
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", note, "2026-04-15T17:11:00+05:00", "", "BLOCKED_MISSING_SIZES"],
            ]
        }
    )

    watch_mod._mark_recoverable_ready_block(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 15),
        readiness={
            "ready": False,
            "run_control_ready_ok": True,
            "blank_size_count": 2,
            "blank_size_rows": [
                {"OrderID": "1001", "STORE_NAME": "Universal", "_db_row_id": "1"},
                {"OrderID": "1002", "STORE_NAME": "AcmeWear", "_db_row_id": "2"},
            ],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
        now=datetime(2026, 4, 15, 17, 11, 15, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert client.update_calls == []


def test_early_closeout_watch_recovers_after_missing_sizes_are_fixed_while_ready_remains_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "BLOCKED_MISSING_SIZES: 1001", "", "", "BLOCKED_MISSING_SIZES"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "blank_size_rows": [],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command) or _Result())

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[str(watch_mod.sys.executable), str(watch_mod.SCRIPT_PATH), "--resume"]]
    assert not state_path.exists()


def test_closeout_scheduler_skips_when_closeout_already_completed(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main()

    assert rc == 0
    assert calls == []


def test_closeout_scheduler_runs_when_run_control_ok_but_delivery_incomplete(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = closeout_scheduler_mod.main()

    assert rc == 0
    assert calls == [
        [
            closeout_scheduler_mod.sys.executable,
            str(closeout_scheduler_mod.DB_CHECK_PATH),
            "--db-path",
            str(closeout_scheduler_mod.PROJECT_ROOT / "db" / "app.db"),
        ],
        [
            closeout_scheduler_mod.sys.executable,
            str(closeout_scheduler_mod.SCRIPT_PATH),
            "--apply",
            "--resume",
            "--spreadsheet-id",
            "sheet-id",
            "--service-account-json",
            str(creds),
        ],
    ]


def test_closeout_scheduler_returns_zero_when_lock_is_busy(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    class _BusyLock:
        def __enter__(self):
            raise RuntimeError("busy")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _BusyLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main()

    assert rc == 0
    assert calls == []


def test_size_writeback_scheduler_skips_after_successful_closeout(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        writeback_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        writeback_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = writeback_scheduler_mod.main()

    assert rc == 0
    assert calls == []
