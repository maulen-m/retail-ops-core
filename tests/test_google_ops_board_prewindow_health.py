from __future__ import annotations

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from scripts import run_google_ops_board_prewindow_health as health_mod
from core.integrations.google_ops_board import load_ops_board_contract


@pytest.fixture(autouse=True)
def _green_name_core_attribution_gate(monkeypatch, request):
    """Keep legacy fixtures focused on health orchestration, not DB identity setup."""

    monkeypatch.setattr(
        health_mod,
        "_build_name_core_attribution_report",
        lambda **_kwargs: {
            "schema_version": 1,
            "ok": True,
            "total_rows": 0,
            "safe_rows": 0,
            "blocked_rows": 0,
            "source_counts": {},
            "issue_counts": {},
            "findings": [],
        },
    )
    if request.node.name != "test_live_board_parity_requires_exact_rows_and_preserves_nonblank_size":
        monkeypatch.setattr(
            health_mod,
            "_build_live_board_parity_report",
            lambda **_kwargs: {
                "ok": True,
                "target_date": "fixture",
                "same_day_preserve": True,
                "tabs": {},
                "issues": [],
            },
        )


class _FakeClient:
    def __init__(self, contract) -> None:
        self.contract = contract

    def get_metadata(self):
        return {
            "sheets": [
                {"properties": {"title": name}}
                for name in self.contract.tabs
            ]
        }

    def get_tab_values(self, tab_name: str):
        return [self.contract.tabs[tab_name].headers]


def _matrix(headers: list[str], rows: list[dict]) -> list[list[object]]:
    return [headers, *[[row.get(header, "") for header in headers] for row in rows]]


def test_live_board_parity_requires_exact_rows_and_preserves_nonblank_size(
    monkeypatch,
) -> None:
    from scripts import sync_google_ops_board as sync_mod

    contract = load_ops_board_contract()
    target = health_mod.date(2026, 7, 16)
    sales_headers = contract.tabs["SalesRaw_Today"].headers
    control_headers = contract.tabs["Run_Control"].headers
    readme_headers = contract.tabs["README"].headers
    exception_headers = contract.tabs["Exceptions"].headers
    sales_row = {header: "" for header in sales_headers}
    sales_row.update(
        {
            "OrderID": "ORDER-1",
            "STORE_NAME": "Universal",
            "SKU_key": "CL_EXACT",
            "_db_row_id": "41",
            "_line_key": "UNIVERSAL|ORDER-1|41",
            "MY_SIZE": "L",
        }
    )
    control_row = {header: "" for header in control_headers}
    control_row.update({"target_date": target.isoformat(), "ready_for_closeout": "HOLD"})
    exception_row = {header: "" for header in exception_headers}
    exception_row.update(
        {
            "exception_key": "ORDER-1:MISSING_SIZE",
            "order_id": "ORDER-1",
            "store": "Universal",
            "planned_date": target.isoformat(),
            "exception_type": "MISSING_SIZE",
            "last_sync_at": "2026-07-16T14:00:00+05:00",
        }
    )
    snapshot = {
        "README": _matrix(
            readme_headers,
            [{"field": "target_date", "value": target.isoformat(), "notes": ""}],
        ),
        "SalesRaw_Today": _matrix(sales_headers, [sales_row]),
        "Run_Control": _matrix(control_headers, [control_row]),
        "Exceptions": _matrix(exception_headers, [exception_row]),
    }

    class Client:
        def snapshot_tabs(self, tab_names):
            return {name: snapshot[name] for name in tab_names}

    monkeypatch.setattr(sync_mod, "build_phase1_payload", lambda **kwargs: {})
    monkeypatch.setattr(
        health_mod,
        "audit_salesraw_name_core_attribution",
        lambda **kwargs: {"ok": True, "blocked_rows": 0, "findings": []},
    )
    monkeypatch.setattr(
        sync_mod,
        "build_publish_plan",
        lambda **kwargs: {
            "same_day_preserve": True,
            "previous_target_date": target.isoformat(),
            "tab_actions": {
                "SalesRaw_Today": {"final_rows": [dict(sales_row)]},
                "Run_Control": {"final_rows": [dict(control_row)]},
                "Exceptions": {
                    "final_rows": [
                        dict(
                            exception_row,
                            last_sync_at="2026-07-16T14:01:00+05:00",
                        )
                    ]
                },
            },
        },
    )

    green = health_mod._build_live_board_parity_report(
        client=Client(),
        db_path=Path("/tmp/app.db"),
        contract=contract,
        target_date=target,
    )
    assert green["ok"] is True
    assert green["tabs"]["SalesRaw_Today"]["live_row_count"] == 1
    assert green["tabs"]["Exceptions"]["ignored_volatile_columns"] == [
        "last_sync_at"
    ]

    snapshot["SalesRaw_Today"][1][sales_headers.index("MY_SIZE")] = "XL"
    red = health_mod._build_live_board_parity_report(
        client=Client(),
        db_path=Path("/tmp/app.db"),
        contract=contract,
        target_date=target,
    )
    assert red["ok"] is False
    codes = {issue["code"] for issue in red["issues"]}
    assert "LIVE_ROW_VALUE_MISMATCH" in codes
    assert "NONBLANK_SIZE_NOT_PRESERVED" in codes


def test_publish_profile_observes_mismatch_without_blocking_until_strict_readback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")
    workbook = tmp_path / "crm.xlsx"
    workbook.write_bytes(b"unused")
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(health_mod, "_build_google_layout_report", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        health_mod,
        "_build_live_board_parity_report",
        lambda **kwargs: {"ok": False, "issues": [{"code": "MISSING_LIVE_KEYS"}]},
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **kwargs: True)

    observed = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 7, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        profile=health_mod.HEALTH_PROFILE_PUBLISH,
    )
    strict = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 7, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        profile=health_mod.HEALTH_PROFILE_PUBLISH,
        require_live_board_parity=True,
    )

    assert observed["ok"] is True
    assert observed["checks"]["live_board_parity"]["blocking"] is False
    assert strict["ok"] is False
    assert strict["checks"]["live_board_parity"]["blocking"] is True


def test_attribution_red_allows_visibility_publish_but_blocks_closeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")
    workbook = tmp_path / "crm.xlsx"
    workbook.write_bytes(b"unused")
    red_attribution = {
        "schema_version": 1,
        "ok": False,
        "total_rows": 1,
        "safe_rows": 0,
        "blocked_rows": 1,
        "source_counts": {"raw_offer_extract": 1},
        "issue_counts": {"UNMAPPED_OR_UNSAFE_ATTRIBUTION": 1},
        "findings": [{"status": "BLOCKED"}],
    }
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "_build_google_layout_report",
        lambda **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_live_board_parity_report",
        lambda **kwargs: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_name_core_attribution_report",
        lambda **kwargs: dict(red_attribution),
    )
    monkeypatch.setattr(health_mod, "_load_active_store_codes", lambda _path: [])
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **kwargs: True)

    publish = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 7, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "publish_health",
        workbook_path=workbook,
        profile=health_mod.HEALTH_PROFILE_PUBLISH,
    )
    closeout = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 7, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "closeout_health",
        workbook_path=workbook,
        profile=health_mod.HEALTH_PROFILE_CLOSEOUT,
    )

    assert publish["ok"] is True
    assert publish["checks"]["name_core_attribution"]["blocking"] is False
    assert publish["checks"]["name_core_attribution"]["visibility_only"] is True
    assert publish["checks"]["name_core_attribution"]["closeout_ready"] is False
    assert closeout["ok"] is False
    assert closeout["checks"]["name_core_attribution"]["blocking"] is True
    assert closeout["checks"]["name_core_attribution"]["visibility_only"] is False


def _write_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Артикул", "SKU_key"])
    ws.append(["ART-1", "SKU-1"])
    ws2 = wb.create_sheet("M02_SKU_CATALOG_NC")
    ws2.append(["SKU_ID_KSP", "SKU_key", "SKU_ID", "MY_SIZE", "Kaspi_name_core"])
    ws2.append(["ART-1", "SKU-1", "SKU-1_L", "L", "Core"])
    wb.save(path)


def test_ensure_prewindow_health_runs_full_green_gate(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")
    calls = {"import": 0, "rebuild": 0}
    call_order: list[str] = []

    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")
    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    monkeypatch.setattr(
        health_mod,
        "validate_local_db",
        lambda _path: [],
    )
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: (
            call_order.append("import"),
            calls.__setitem__("import", calls["import"] + 1),
            {"status": "APPLIED"},
        )[-1],
    )
    monkeypatch.setattr(
        health_mod,
        "rebuild_identity_map",
        lambda **_kwargs: (
            call_order.append("rebuild"),
            calls.__setitem__("rebuild", calls["rebuild"] + 1),
            {"status": "APPLIED"},
        )[-1],
    )
    monkeypatch.setattr(
        health_mod,
        "_build_name_core_attribution_report",
        lambda **_kwargs: call_order.append("attribution")
        or {
            "ok": True,
            "total_rows": 0,
            "safe_rows": 0,
            "blocked_rows": 0,
            "findings": [],
        },
    )
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: (_ for _ in ()).throw(
            AssertionError("canonical health must stay browser-free")
        ),
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    report = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="test",
    )

    assert report["ok"] is True
    assert calls == {"import": 1, "rebuild": 1}
    assert Path(report["report_path"]).exists()
    assert report["checks"]["google_layout"]["ok"] is True
    assert report["checks"]["name_core_attribution"]["ok"] is True
    assert report["runtime_code_fingerprints"][
        "core/ops/google_ops_board_attribution.py"
    ]["sha256"]
    assert report["runtime_code_fingerprints"][
        "scripts/validate_google_closeout_expected_orders.py"
    ]["sha256"]
    assert call_order == ["import", "rebuild", "attribution"]
    assert report["checks"]["whatsapp_smoke"]["skipped"] is True
    assert os.environ["KASPI_API_CALL_LEDGER_PATH"].endswith(
        "runtime/api_ledger/kaspi_api_2026-04-16.jsonl"
    )


def test_ensure_prewindow_health_reuses_current_green_state(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")
    calls = {"import": 0, "smoke": 0}

    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: calls.__setitem__("import", calls["import"] + 1) or {"status": "APPLIED"},
    )
    monkeypatch.setattr(health_mod, "rebuild_identity_map", lambda **_kwargs: {"status": "APPLIED"})
    monkeypatch.setattr(health_mod, "_build_store_context_report", lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []})
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: (_ for _ in ()).throw(
            AssertionError("canonical health must stay browser-free")
        ),
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    first = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        apply=True,
        reason="test",
    )
    second = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        apply=True,
        reason="test-repeat",
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert calls["import"] == 1
    assert calls["smoke"] == 0
    assert second["identity_sync_reused"] is True
    assert second["checks"]["identity_sync"]["reused"] is True


def test_closeout_profile_skips_workbook_identity_sync(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    workbook.write_bytes(b"PK\x03\x04truncated")
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")

    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("closeout must not import CRM maps")),
    )
    monkeypatch.setattr(
        health_mod,
        "rebuild_identity_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("closeout must not rebuild CRM identity")),
    )
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: (_ for _ in ()).throw(
            AssertionError("canonical health must stay browser-free")
        ),
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    report = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=False,
        reason="closeout-test",
        profile=health_mod.HEALTH_PROFILE_CLOSEOUT,
    )

    assert report["ok"] is True
    assert report["identity_sync_reused"] is False
    assert report["checks"]["identity_sync"]["ok"] is True
    assert report["checks"]["identity_sync"]["skipped"] is True
    assert report["checks"]["identity_sync"]["reason"] == "profile=closeout excludes identity_sync"


def test_closeout_profile_apply_does_not_require_workbook_sync_gate(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    workbook.write_bytes(b"not-an-xlsx")
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")

    monkeypatch.delenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", raising=False)
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("closeout must not import CRM maps")),
    )
    monkeypatch.setattr(
        health_mod,
        "rebuild_identity_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("closeout must not rebuild CRM identity")),
    )
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: {"ok": True, "issues": [], "active_chat_title": "Заказы"},
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    report = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 6, 30),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="closeout-apply-test",
        profile=health_mod.HEALTH_PROFILE_CLOSEOUT,
    )

    assert report["ok"] is True
    assert report["checks"]["identity_sync"]["ok"] is True
    assert report["checks"]["identity_sync"]["skipped"] is True


def test_run_whatsapp_smoke_check_uses_temp_launch_mode(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class _FakeSender:
        def __init__(self, **kwargs) -> None:
            seen.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def assert_document_send_ready(self) -> None:
            return None

        def _active_chat_title(self) -> str:
            return "Заказы"

    monkeypatch.setattr(health_mod, "check_playwright", lambda: True)
    monkeypatch.setattr(health_mod, "WhatsAppSender", _FakeSender)

    report = health_mod._run_whatsapp_smoke_check(verbose=False)

    assert report["ok"] is True
    assert seen["browser_mode"] == health_mod.BROWSER_MODE_LAUNCH


def test_telegram_delivery_config_warns_when_control_allowlist_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(health_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", raising=False)
    monkeypatch.setattr(
        health_mod,
        "get_waybill_telegram_config",
        lambda: {"token": "token", "chat_id": "-100123"},
    )

    report = health_mod._build_telegram_delivery_config_report()

    assert report["ok"] is True
    assert report["token_configured"] is True
    assert report["chat_id_configured"] is True
    assert report["allowed_user_gate_configured"] is False
    assert report["warnings"][0]["code"] == "telegram_control_allowlist_missing"
    assert report["warnings"][0]["blocking"] is False


def test_telegram_delivery_config_missing_token_or_chat_is_blocking(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(health_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_WAYBILL_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN_WAYBILL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(
        health_mod,
        "get_waybill_telegram_config",
        lambda: (_ for _ in ()).throw(ValueError("missing telegram token/chat")),
    )

    report = health_mod._build_telegram_delivery_config_report()

    assert report["ok"] is False
    assert report["token_configured"] is False
    assert report["chat_id_configured"] is False
    assert report["allowed_user_gate_configured"] is False
    assert report["issues"][0]["code"] == "telegram_delivery_config_missing"


def test_ensure_prewindow_health_loads_repo_dotenv(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")
    seen: dict[str, object] = {}

    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")
    monkeypatch.setattr(
        health_mod,
        "load_dotenv",
        lambda path, override=False: seen.update({"path": Path(path), "override": override}),
    )
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(health_mod, "import_map", lambda **_kwargs: {"status": "APPLIED"})
    monkeypatch.setattr(health_mod, "rebuild_identity_map", lambda **_kwargs: {"status": "APPLIED"})
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: (_ for _ in ()).throw(
            AssertionError("canonical health must stay browser-free")
        ),
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    report = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="test-dotenv",
    )

    assert report["ok"] is True
    assert seen["path"] == health_mod.DEFAULT_DOTENV_PATH
    assert seen["override"] is False


def test_ensure_prewindow_health_publish_profile_skips_whatsapp_and_store_context(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    workbook.write_bytes(b"PK\x03\x04truncated")
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")

    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("publish must not import CRM maps")),
    )
    monkeypatch.setattr(
        health_mod,
        "rebuild_identity_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("publish must not rebuild CRM identity")),
    )
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: (_ for _ in ()).throw(AssertionError("store_context should be skipped")),
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: (_ for _ in ()).throw(AssertionError("whatsapp smoke should be skipped")),
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    report = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 16),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="test-publish",
        profile=health_mod.HEALTH_PROFILE_PUBLISH,
    )

    assert report["ok"] is True
    assert report["profile"] == health_mod.HEALTH_PROFILE_PUBLISH
    assert report["report_path"].endswith("publish_health.json")
    assert report["identity_sync_reused"] is False
    assert report["checks"]["identity_sync"]["skipped"] is True
    assert report["checks"]["identity_sync"]["reason"] == "profile=publish excludes identity_sync"
    assert report["checks"]["store_context"]["skipped"] is True
    assert report["checks"]["whatsapp_smoke"]["skipped"] is True


def test_ensure_prewindow_health_closeout_profile_skips_whatsapp_when_telegram_is_green(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")

    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(health_mod, "import_map", lambda **_kwargs: {"status": "APPLIED"})
    monkeypatch.setattr(health_mod, "rebuild_identity_map", lambda **_kwargs: {"status": "APPLIED"})
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "token_configured": True, "chat_id_configured": True},
        raising=False,
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: (_ for _ in ()).throw(
            AssertionError("canonical closeout health must not open WhatsApp")
        ),
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    report = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 4, 22),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="test-closeout",
        profile=health_mod.HEALTH_PROFILE_CLOSEOUT,
    )

    assert report["ok"] is True
    assert report["checks"]["telegram_delivery_config"]["ok"] is True
    assert report["checks"]["whatsapp_smoke"]["ok"] is True
    assert report["checks"]["whatsapp_smoke"]["skipped"] is True


def test_closeout_profile_skips_same_day_identity_artifact_reuse(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(workbook)
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"sqlite")
    calls = {"import": 0}

    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")
    monkeypatch.setattr(health_mod, "validate_local_db", lambda _path: [])
    monkeypatch.setattr(
        health_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(contract),
    )
    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: calls.__setitem__("import", calls["import"] + 1) or {"status": "APPLIED"},
    )
    monkeypatch.setattr(health_mod, "rebuild_identity_map", lambda **_kwargs: {"status": "APPLIED"})
    monkeypatch.setattr(
        health_mod,
        "_build_store_context_report",
        lambda _stores: {"ok": True, "stores": [], "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(
        health_mod,
        "_build_telegram_delivery_config_report",
        lambda: {"ok": True, "token_configured": True, "chat_id_configured": True},
        raising=False,
    )
    monkeypatch.setattr(
        health_mod,
        "_run_whatsapp_smoke_check",
        lambda *, verbose: {"ok": False, "issues": [{"code": "qr_visible"}]},
    )
    monkeypatch.setattr(health_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    first = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 6, 29),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="prewindow",
        profile=health_mod.HEALTH_PROFILE_FULL,
    )

    monkeypatch.setattr(
        health_mod,
        "import_map",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("closeout must skip identity sync")),
    )
    second = health_mod.ensure_prewindow_health(
        target_date=health_mod.date(2026, 6, 29),
        db_path=db_path,
        contract_path=health_mod.DEFAULT_CONTRACT_PATH,
        service_account_json=tmp_path / "svc.json",
        spreadsheet_id="sheet-id",
        output_root=tmp_path / "health",
        workbook_path=workbook,
        stores_config_path=health_mod.DEFAULT_KASPI_STORES_CONFIG,
        apply=True,
        reason="closeout",
        profile=health_mod.HEALTH_PROFILE_CLOSEOUT,
    )

    assert first["checks"]["identity_sync"]["ok"] is True
    assert second["ok"] is True
    assert calls["import"] == 1
    assert second["identity_sync_reused"] is False
    assert second["checks"]["identity_sync"]["skipped"] is True
    assert second["checks"]["identity_sync"]["reason"] == "profile=closeout excludes identity_sync"


def test_identical_prewindow_red_realerts_on_third_sixth_and_twelfth(monkeypatch) -> None:
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(
        health_mod,
        "send_owner_ops_alert",
        lambda **kwargs: alerts.append(kwargs) or True,
    )
    previous: dict[str, object] | None = None
    for occurrence in range(1, 13):
        report: dict[str, object] = {
            "ok": False,
            "target_date": "2026-07-18",
            "reason": "scheduled_prewindow",
            "report_path": "/tmp/prewindow.json",
            "workbook_fingerprint": {"sha256": "same-workbook"},
            "checks": {"google_layout": {"ok": False}},
        }
        health_mod._update_health_alert_state(report, previous)
        assert report["alert_state"]["consecutive_identical_reds"] == occurrence
        health_mod._send_health_alert(report, previous)
        previous = report

    assert [alert["title"] for alert in alerts] == [
        "Google Ops Board Prewindow Red",
        "Google Ops Board Prewindow STILL RED (3rd consecutive)",
        "Google Ops Board Prewindow STILL RED (6th consecutive)",
        "Google Ops Board Prewindow STILL RED (12th consecutive)",
    ]
