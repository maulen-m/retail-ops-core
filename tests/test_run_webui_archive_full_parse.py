from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
import yaml

import scripts.run_webui_archive_full_parse as mod
from scripts.run_webui_archive_full_parse import plan_full_parse_blocks, run_webui_archive_full_parse


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


def _warehouse_for(store_code: str) -> str:
    return {
        "ACMEWEAR": "30137883_PP1",
        "UNIVERSAL": "30000001_PP1",
    }[store_code]


def _write_raw_block(path: Path, store_code: str, window_since: str, window_until: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "№ заказа": f"{store_code}-DEL-{window_since}",
                "Дата поступления заказа": window_since,
                "Дата изменения статуса": window_until,
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "10000",
                "Склад передачи КД": _warehouse_for(store_code),
            },
            {
                "№ заказа": f"{store_code}-CAN-{window_since}",
                "Дата поступления заказа": window_since,
                "Дата изменения статуса": window_since,
                "Статус": "Отменен",
                "Количество": "1",
                "Сумма": "10000",
                "Склад передачи КД": _warehouse_for(store_code),
            },
        ]
    )
    frame.to_excel(path, index=False)


def test_plan_full_parse_blocks_expands_stores_across_windows() -> None:
    blocks = plan_full_parse_blocks(
        stores=["ACMEWEAR", "UNIVERSAL"],
        since=date(2026, 1, 1),
        until=date(2026, 4, 5),
    )

    assert blocks == [
        {"store_code": "ACMEWEAR", "window_since": "2026-01-01", "window_until": "2026-03-31"},
        {"store_code": "ACMEWEAR", "window_since": "2026-04-01", "window_until": "2026-04-05"},
        {"store_code": "UNIVERSAL", "window_since": "2026-01-01", "window_until": "2026-03-31"},
        {"store_code": "UNIVERSAL", "window_since": "2026-04-01", "window_until": "2026-04-05"},
    ]


def test_run_webui_archive_full_parse_builds_backups_and_final_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)

    def fake_download_kaspi_archive_webui(**kwargs):
        run_id = str(kwargs["run_id"])
        store_code = list(kwargs["store_codes"])[0]
        window_since = kwargs["since"].isoformat()
        window_until = kwargs["until"].isoformat()
        child_root = kwargs["output_root"] / run_id
        copied = child_root / "downloads" / f"store_{store_code}" / f"ArchiveOrders_{store_code}_{window_since}_to_{window_until}.xlsx"
        _write_raw_block(copied, store_code, window_since, window_until)
        manifest = {
            "run_id": run_id,
            "status": "PASS",
            "ok": True,
            "target_stores": [store_code],
            "store_results": [
                {
                    "store_code": store_code,
                    "status": "PASS",
                    "copied_file": str(copied.resolve()),
                    "sha256": "sha",
                    "window_since": window_since,
                    "window_until": window_until,
                }
            ],
        }
        child_root.mkdir(parents=True, exist_ok=True)
        (child_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {
            **manifest,
            "run_root": str(child_root.resolve()),
            "run_manifest_json": str((child_root / "run_manifest.json").resolve()),
            "download_log_md": str((child_root / "download_log.md").resolve()),
        }

    monkeypatch.setattr(mod, "download_kaspi_archive_webui", fake_download_kaspi_archive_webui)

    report = run_webui_archive_full_parse(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        run_id="full_parse_run",
        output_root=tmp_path / "full_runs",
        download_runs_root=tmp_path / "download_runs",
        stores_config=stores,
        session_state=tmp_path / "session.json",
        strict=True,
        store_codes=None,
    )

    run_root = Path(report["run_root"])
    assert (run_root / "raw_backups" / "store_ACMEWEAR" / "ArchiveOrders_ACMEWEAR_2026-01-01_to_2026-02-28.xlsx").exists()
    assert (run_root / "raw_backups" / "store_UNIVERSAL" / "ArchiveOrders_UNIVERSAL_2026-01-01_to_2026-02-28.xlsx").exists()
    assert Path(report["pack_root"]).exists()
    assert Path(report["final_merged_csv"]).exists()
    assert Path(report["final_merged_xlsx"]).exists()
    assert Path(report["per_store_outputs"]["ACMEWEAR"]["merged_csv"]).exists()
    assert Path(report["per_store_outputs"]["UNIVERSAL"]["merged_csv"]).exists()

    merged = pd.read_csv(Path(report["final_merged_csv"]), dtype=str)
    assert sorted(merged["store_code"].unique().tolist()) == ["ACMEWEAR", "UNIVERSAL"]
    assert int((merged["status_internal"] == "DELIVERED").sum()) == 2

    wb = openpyxl.load_workbook(Path(report["final_merged_xlsx"]), read_only=True, data_only=True)
    ws = wb.active
    assert ws.max_row >= 3


def test_run_webui_archive_full_parse_is_idempotent_for_completed_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    calls: list[tuple[str, str, str]] = []

    def fake_download_kaspi_archive_webui(**kwargs):
        run_id = str(kwargs["run_id"])
        store_code = list(kwargs["store_codes"])[0]
        window_since = kwargs["since"].isoformat()
        window_until = kwargs["until"].isoformat()
        calls.append((store_code, window_since, window_until))
        child_root = kwargs["output_root"] / run_id
        copied = child_root / "downloads" / f"store_{store_code}" / f"ArchiveOrders_{store_code}_{window_since}_to_{window_until}.xlsx"
        _write_raw_block(copied, store_code, window_since, window_until)
        manifest = {
            "run_id": run_id,
            "status": "PASS",
            "ok": True,
            "target_stores": [store_code],
            "store_results": [
                {
                    "store_code": store_code,
                    "status": "PASS",
                    "copied_file": str(copied.resolve()),
                    "sha256": "sha",
                    "window_since": window_since,
                    "window_until": window_until,
                }
            ],
        }
        child_root.mkdir(parents=True, exist_ok=True)
        (child_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {
            **manifest,
            "run_root": str(child_root.resolve()),
            "run_manifest_json": str((child_root / "run_manifest.json").resolve()),
            "download_log_md": str((child_root / "download_log.md").resolve()),
        }

    monkeypatch.setattr(mod, "download_kaspi_archive_webui", fake_download_kaspi_archive_webui)

    kwargs = dict(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        run_id="full_parse_run",
        output_root=tmp_path / "full_runs",
        download_runs_root=tmp_path / "download_runs",
        stores_config=stores,
        session_state=tmp_path / "session.json",
        strict=True,
        store_codes=None,
    )

    first = run_webui_archive_full_parse(**kwargs)
    call_count = len(calls)
    second = run_webui_archive_full_parse(**kwargs)

    assert len(calls) == call_count
    assert first["final_merged_csv"] == second["final_merged_csv"]


def test_run_webui_archive_full_parse_uses_store_specific_session_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    session_paths: list[Path] = []

    def fake_download_kaspi_archive_webui(**kwargs):
        session_paths.append(Path(kwargs["session_state"]))
        run_id = str(kwargs["run_id"])
        store_code = list(kwargs["store_codes"])[0]
        window_since = kwargs["since"].isoformat()
        window_until = kwargs["until"].isoformat()
        child_root = kwargs["output_root"] / run_id
        copied = child_root / "downloads" / f"store_{store_code}" / f"ArchiveOrders_{store_code}_{window_since}_to_{window_until}.xlsx"
        _write_raw_block(copied, store_code, window_since, window_until)
        manifest = {
            "run_id": run_id,
            "status": "PASS",
            "ok": True,
            "target_stores": [store_code],
            "store_results": [
                {
                    "store_code": store_code,
                    "status": "PASS",
                    "copied_file": str(copied.resolve()),
                    "sha256": "sha",
                    "window_since": window_since,
                    "window_until": window_until,
                }
            ],
        }
        child_root.mkdir(parents=True, exist_ok=True)
        (child_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {
            **manifest,
            "run_root": str(child_root.resolve()),
            "run_manifest_json": str((child_root / "run_manifest.json").resolve()),
            "download_log_md": str((child_root / "download_log.md").resolve()),
        }

    monkeypatch.setattr(mod, "download_kaspi_archive_webui", fake_download_kaspi_archive_webui)

    run_webui_archive_full_parse(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        run_id="full_parse_run",
        output_root=tmp_path / "full_runs",
        download_runs_root=tmp_path / "download_runs",
        stores_config=stores,
        session_state=tmp_path / "shared_session.json",
        strict=False,
        store_codes=None,
    )

    assert sorted(path.name for path in session_paths) == [
        "shared_session_ACMEWEAR.json",
        "shared_session_UNIVERSAL.json",
    ]


def test_run_webui_archive_full_parse_marks_missing_credentials_without_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    called = False

    def fake_download_kaspi_archive_webui(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("download should not run when credentials are missing")

    monkeypatch.setattr(mod, "download_kaspi_archive_webui", fake_download_kaspi_archive_webui)

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("", encoding="utf-8")

    report = run_webui_archive_full_parse(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        run_id="missing_creds_run",
        output_root=tmp_path / "full_runs",
        download_runs_root=tmp_path / "download_runs",
        stores_config=stores,
        session_state=tmp_path / "shared_session.json",
        strict=False,
        store_codes=None,
        dotenv_path=dotenv_path,
    )

    assert called is False
    assert report["status"] == "FAIL"
    assert {row["error"] for row in report["blocks"]} == {"CREDENTIALS_MISSING"}


def test_run_webui_archive_full_parse_records_download_exceptions_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "ACMEWEAR_ACCOUNT_EMAIL=acmewear@example.com",
                "ACMEWEAR_ACCOUNT_PASSWORD=secret",
                "UNIVERSAL_ACCOUNT_EMAIL=universal@example.com",
                "UNIVERSAL_ACCOUNT_PASSWORD=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_download_kaspi_archive_webui(**kwargs):
        run_id = str(kwargs["run_id"])
        store_code = list(kwargs["store_codes"])[0]
        window_since = kwargs["since"].isoformat()
        window_until = kwargs["until"].isoformat()
        if store_code == "UNIVERSAL":
            raise RuntimeError("LOGIN_FAILED")
        child_root = kwargs["output_root"] / run_id
        copied = child_root / "downloads" / f"store_{store_code}" / f"ArchiveOrders_{store_code}_{window_since}_to_{window_until}.xlsx"
        _write_raw_block(copied, store_code, window_since, window_until)
        manifest = {
            "run_id": run_id,
            "status": "PASS",
            "ok": True,
            "target_stores": [store_code],
            "store_results": [
                {
                    "store_code": store_code,
                    "status": "PASS",
                    "copied_file": str(copied.resolve()),
                    "sha256": "sha",
                    "window_since": window_since,
                    "window_until": window_until,
                }
            ],
        }
        child_root.mkdir(parents=True, exist_ok=True)
        (child_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {
            **manifest,
            "run_root": str(child_root.resolve()),
            "run_manifest_json": str((child_root / "run_manifest.json").resolve()),
            "download_log_md": str((child_root / "download_log.md").resolve()),
        }

    monkeypatch.setattr(mod, "download_kaspi_archive_webui", fake_download_kaspi_archive_webui)

    report = run_webui_archive_full_parse(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        run_id="exception_run",
        output_root=tmp_path / "full_runs",
        download_runs_root=tmp_path / "download_runs",
        stores_config=stores,
        session_state=tmp_path / "shared_session.json",
        strict=False,
        store_codes=None,
        dotenv_path=dotenv_path,
    )

    assert report["status"] == "FAIL"
    assert any(row["store_code"] == "ACMEWEAR" and row["status"] == "PASS" for row in report["blocks"])
    assert any(row["store_code"] == "UNIVERSAL" and row["error"] == "DOWNLOAD_EXCEPTION" for row in report["blocks"])
