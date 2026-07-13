from __future__ import annotations

import os
from pathlib import Path

from openpyxl import Workbook

from scripts import run_google_ops_board_prewindow_health as health_mod
from core.integrations.google_ops_board import load_ops_board_contract


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
        lambda **_kwargs: calls.__setitem__("import", calls["import"] + 1) or {"status": "APPLIED"},
    )
    monkeypatch.setattr(
        health_mod,
        "rebuild_identity_map",
        lambda **_kwargs: calls.__setitem__("rebuild", calls["rebuild"] + 1) or {"status": "APPLIED"},
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
