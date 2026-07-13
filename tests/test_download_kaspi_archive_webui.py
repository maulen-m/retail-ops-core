from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest
import yaml

import scripts.playwright.download_kaspi_archive_webui as mod
from scripts.playwright.download_kaspi_archive_webui import (
    WebuiArchiveDownloadError,
    _plan_archive_windows,
    _resolve_store_credentials,
    download_kaspi_archive_webui,
)


def _write_stores(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "stores": {
                    "ACMEWEAR": {"sync_enabled": True},
                    "UNIVERSAL": {"sync_enabled": True},
                }
            }
        ),
        encoding="utf-8",
    )


def test_resolve_store_credentials_reads_store_specific_keys() -> None:
    credentials = _resolve_store_credentials(
        "ACMEWEAR",
        {
            "ACMEWEAR_ACCOUNT_EMAIL": "seller@example.com",
            "ACMEWEAR_ACCOUNT_PASSWORD": "secret",
            "Kaspi_marketing_login_ACMEWEAR": "7000123456",
            "Kaspi_marketing_Password_ACMEWEAR": "phone-pass",
        },
    )

    assert credentials["email"] == "seller@example.com"
    assert credentials["email_password"] == "secret"
    assert credentials["phone"] == "7000123456"
    assert credentials["phone_password"] == "phone-pass"


def test_plan_archive_windows_supports_current_view_and_90_day_blocks() -> None:
    assert _plan_archive_windows(None, None) == [(None, None)]

    windows = _plan_archive_windows(date(2026, 1, 1), date(2026, 4, 5))
    assert windows == [
        (date(2026, 1, 1), date(2026, 3, 31)),
        (date(2026, 4, 1), date(2026, 4, 5)),
    ]


def test_plan_archive_windows_requires_both_bounds() -> None:
    with pytest.raises(WebuiArchiveDownloadError):
        _plan_archive_windows(date(2026, 1, 1), None)


def test_download_kaspi_archive_webui_live_mode_writes_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)

    def fake_run_live_download(**kwargs):
        copied = tmp_path / "exports" / "run1" / "downloads" / "store_ACMEWEAR" / "ArchiveOrders_ACMEWEAR.xlsx"
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_text("xlsx", encoding="utf-8")
        return {
            "mode": "live-download",
            "archive_url": "https://kaspi.kz/mc/#/orders-new?status=ARCHIVE",
            "session_state_path": str(tmp_path / "session.json"),
            "headful": True,
            "manual_login": True,
            "allow_manual_download": False,
            "login_timeout": 300.0,
            "download_timeout": 120.0,
            "requested_since": "2026-01-01",
            "requested_until": "2026-02-28",
            "window_days": 90,
            "planned_windows": [{"window_since": "2026-01-01", "window_until": "2026-02-28"}],
            "target_stores": ["ACMEWEAR"],
            "status": "PASS",
            "ok": True,
            "store_results": [
                {
                    "store_code": "ACMEWEAR",
                    "window_since": "2026-01-01",
                    "window_until": "2026-02-28",
                    "status": "PASS",
                    "copied_file": str(copied),
                    "sha256": "sha",
                    "auth_method": "manual_login",
                    "download_trigger": "button:has-text('Скачать')",
                }
            ],
        }

    monkeypatch.setattr(mod, "_run_live_download", fake_run_live_download)

    report = download_kaspi_archive_webui(
        mode="live-download",
        run_id="run1",
        output_root=tmp_path / "exports",
        stores_config=stores,
        session_state=tmp_path / "session.json",
        source_root=None,
        strict=True,
        store_codes=["ACMEWEAR"],
        headful=True,
        manual_login=True,
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        write_anchor=False,
    )

    assert report["status"] == "PASS"
    manifest = json.loads((tmp_path / "exports" / "run1" / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_stores"] == ["ACMEWEAR"]
    assert manifest["mode"] == "live-download"
    assert manifest["requested_since"] == "2026-01-01"
    assert manifest["requested_until"] == "2026-02-28"


def test_download_kaspi_archive_webui_rejects_unknown_store(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)

    with pytest.raises(WebuiArchiveDownloadError):
        download_kaspi_archive_webui(
            mode="session-check",
            run_id="run1",
            output_root=tmp_path / "exports",
            stores_config=stores,
            session_state=tmp_path / "session.json",
            source_root=None,
            strict=False,
            store_codes=["MISSING"],
        )


def test_download_kaspi_archive_webui_strict_failure_still_writes_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)

    monkeypatch.setattr(
        mod,
        "_run_live_download",
        lambda **kwargs: {
            "mode": "live-download",
            "archive_url": "https://kaspi.kz/mc/#/orders-new?status=ARCHIVE",
            "session_state_path": str(tmp_path / "session.json"),
            "headful": True,
            "manual_login": True,
            "allow_manual_download": False,
            "login_timeout": 300.0,
            "download_timeout": 120.0,
            "target_stores": ["ACMEWEAR"],
            "status": "FAIL",
            "ok": False,
            "store_results": [
                {
                    "store_code": "ACMEWEAR",
                    "status": "FAIL",
                    "error": "MANUAL_LOGIN_TIMEOUT",
                }
            ],
        },
    )

    with pytest.raises(WebuiArchiveDownloadError):
        download_kaspi_archive_webui(
            mode="live-download",
            run_id="run_fail",
            output_root=tmp_path / "exports",
            stores_config=stores,
            session_state=tmp_path / "session.json",
            source_root=None,
            strict=True,
            store_codes=["ACMEWEAR"],
            headful=True,
            manual_login=True,
            write_anchor=False,
        )

    manifest_path = tmp_path / "exports" / "run_fail" / "run_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "FAIL"
