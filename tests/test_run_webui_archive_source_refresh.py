from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import yaml

import scripts.run_webui_archive_source_refresh as mod
from scripts.run_webui_archive_source_refresh import (
    WebuiArchiveSourceRefreshError,
    run_webui_archive_source_refresh,
)
from scripts.webui_archive_truth_utils import build_status_ledger


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


def _write_archive_xlsx(path: Path, store_code: str, since: str, until: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "№ заказа": f"{store_code}-DEL-{since}",
                "Дата поступления заказа": since,
                "Дата изменения статуса": until,
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "10000",
                "Склад передачи КД": _warehouse_for(store_code),
            },
            {
                "№ заказа": f"{store_code}-CAN-{since}",
                "Дата поступления заказа": since,
                "Дата изменения статуса": since,
                "Статус": "Отменен",
                "Количество": "1",
                "Сумма": "5000",
                "Склад передачи КД": _warehouse_for(store_code),
            },
        ]
    )
    frame.to_excel(path, index=False)


def test_import_existing_builds_read_only_pack_and_merged_outputs(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    source_root = tmp_path / "manual_source"
    for store_code in ["ACMEWEAR", "UNIVERSAL"]:
        _write_archive_xlsx(
            source_root / f"store_{store_code}" / f"ArchiveOrders_{store_code}_2026-01-01_to_2026-02-28.xlsx",
            store_code,
            "2026-01-01",
            "2026-02-28",
        )

    report = run_webui_archive_source_refresh(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        requested_mode="import-existing",
        run_id="source_refresh",
        output_root=tmp_path / "source_refresh_runs",
        source_root=source_root,
        stores_config=stores,
        session_state=tmp_path / "session.json",
        full_parse_root=tmp_path / "full_parse_runs",
        download_runs_root=tmp_path / "download_runs",
        dotenv_path=tmp_path / ".env",
        archive_url="https://example.invalid/archive",
        strict=True,
        store_codes=None,
        manual_login=False,
        login_timeout=1,
        download_timeout=1,
        allow_manual_download=False,
    )

    assert report["status"] == "PASS"
    assert report["effective_mode"] == "import-existing"
    assert report["all_enabled_stores"] == ["ACMEWEAR", "UNIVERSAL"]
    assert report["target_stores"] == ["ACMEWEAR", "UNIVERSAL"]
    assert report["omitted_enabled_stores"] == []
    assert report["planned_windows"] == [
        {"window_since": "2026-01-01", "window_until": "2026-02-28"}
    ]
    assert report["expected_block_count"] == 2
    assert report["read_only"] is True
    assert report["production_db_modified"] is False
    assert Path(report["run_manifest_json"]).exists()
    assert Path(report["source_refresh_summary_md"]).exists()
    assert Path(report["pack_root"]).exists()
    assert Path(report["pack_integrity_json"]).exists()
    assert Path(report["final_merged_csv"]).exists()
    assert Path(report["final_merged_xlsx"]).exists()

    merged = pd.read_csv(Path(report["final_merged_csv"]), dtype=str)
    assert sorted(merged["store_code"].unique().tolist()) == ["ACMEWEAR", "UNIVERSAL"]
    assert int((merged["status_internal"] == "DELIVERED").sum()) == 2


def test_auto_prefers_existing_source_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    source_root = tmp_path / "manual_source"
    for store_code in ["ACMEWEAR", "UNIVERSAL"]:
        _write_archive_xlsx(
            source_root / f"store_{store_code}" / f"ArchiveOrders_{store_code}_2026-01-01_to_2026-02-28.xlsx",
            store_code,
            "2026-01-01",
            "2026-02-28",
        )

    def fail_full_parse(**kwargs):
        raise AssertionError("auto mode should not use live full parse when source_root exists")

    monkeypatch.setattr(mod, "run_webui_archive_full_parse", fail_full_parse)

    report = run_webui_archive_source_refresh(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        requested_mode="auto",
        run_id="auto_refresh",
        output_root=tmp_path / "source_refresh_runs",
        source_root=source_root,
        stores_config=stores,
        session_state=tmp_path / "session.json",
        full_parse_root=tmp_path / "full_parse_runs",
        download_runs_root=tmp_path / "download_runs",
        dotenv_path=tmp_path / ".env",
        archive_url="https://example.invalid/archive",
        strict=True,
        store_codes=None,
        manual_login=False,
        login_timeout=1,
        download_timeout=1,
        allow_manual_download=False,
    )

    assert report["requested_mode"] == "auto"
    assert report["effective_mode"] == "import-existing"
    assert report["status"] == "PASS"


def test_import_existing_accepts_manual_download_folder_names(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    source_root = tmp_path / "manual_source"
    _write_archive_xlsx(
        source_root / "Acmewear" / "ArchiveOrders.xlsx",
        "ACMEWEAR",
        "2026-01-01",
        "2026-02-28",
    )
    _write_archive_xlsx(
        source_root / "universal" / "ArchiveOrders (2).xlsx",
        "UNIVERSAL",
        "2026-01-01",
        "2026-02-28",
    )

    report = run_webui_archive_source_refresh(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        requested_mode="import-existing",
        run_id="manual_names_refresh",
        output_root=tmp_path / "source_refresh_runs",
        source_root=source_root,
        stores_config=stores,
        session_state=tmp_path / "session.json",
        full_parse_root=tmp_path / "full_parse_runs",
        download_runs_root=tmp_path / "download_runs",
        dotenv_path=tmp_path / ".env",
        archive_url="https://example.invalid/archive",
        strict=True,
        store_codes=None,
        manual_login=False,
        login_timeout=1,
        download_timeout=1,
        allow_manual_download=False,
    )

    assert report["status"] == "PASS"
    child_manifest = json.loads(Path(report["child_run_manifest_json"]).read_text(encoding="utf-8"))
    assert child_manifest["anchor_written"] is False
    assert child_manifest["requested_since"] == "2026-01-01"
    assert child_manifest["requested_until"] == "2026-02-28"
    for row in child_manifest["store_results"]:
        assert row["window_since"] == "2026-01-01"
        assert row["window_until"] == "2026-02-28"
        assert row["window_provenance"] == "requested_cli_with_source_file_hash"
        assert len(row["source_file_sha256"]) == 64
        assert len(row["copied_file_sha256"]) == 64

    source_manifest = json.loads((Path(report["pack_root"]) / "source_manifest.json").read_text(encoding="utf-8"))
    for item in source_manifest["files"]:
        assert item["window_since"] == "2026-01-01"
        assert item["window_until"] == "2026-02-28"
        assert item["window_provenance"] == "requested_cli_with_source_file_hash"
        assert len(item["source_file_sha256"]) == 64

    ledger_report = build_status_ledger(
        pack_roots=[Path(report["pack_root"])],
        run_id="manual_names_ledger",
        output_root=tmp_path / "ledgers",
    )
    for item in ledger_report["manifest"]["pack_windows"]:
        assert item["window_since"] == "2026-01-01"
        assert item["window_until"] == "2026-02-28"
        assert item["window_provenance"] == "requested_cli_with_source_file_hash"
        assert len(item["source_file_sha256"]) == 64

    merged = pd.read_csv(Path(report["final_merged_csv"]), dtype=str)
    assert sorted(merged["store_code"].unique().tolist()) == ["ACMEWEAR", "UNIVERSAL"]


def test_live_headless_delegates_to_full_parse(tmp_path: Path, monkeypatch) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    captured: dict[str, object] = {}

    def fake_full_parse(**kwargs):
        captured.update(kwargs)
        child_root = kwargs["output_root"] / str(kwargs["run_id"])
        child_root.mkdir(parents=True, exist_ok=True)
        manifest = child_root / "run_manifest.json"
        summary = child_root / "run_summary.md"
        final_csv = child_root / "final_merged" / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv"
        final_xlsx = child_root / "final_merged" / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.xlsx"
        final_csv.parent.mkdir(parents=True, exist_ok=True)
        final_csv.write_text("store_code,order_id\nACMEWEAR,1\n", encoding="utf-8")
        final_xlsx.write_bytes(b"placeholder")
        manifest.write_text(json.dumps({"ok": True}), encoding="utf-8")
        summary.write_text("# summary\n", encoding="utf-8")
        return {
            "status": "PASS",
            "ok": True,
            "run_manifest_json": str(manifest),
            "run_summary_md": str(summary),
            "blocks": [{"store_code": "ACMEWEAR", "window_since": "2026-01-01", "window_until": "2026-02-28", "status": "PASS"}],
            "pack_root": str(child_root / "pack_outputs" / "pack"),
            "pack_integrity_json": str(child_root / "pack_outputs" / "pack" / "integrity_report.json"),
            "pack_integrity_ok": True,
            "pack_integrity_errors": [],
            "per_store_outputs": {},
            "final_merged_csv": str(final_csv),
            "final_merged_xlsx": str(final_xlsx),
        }

    monkeypatch.setattr(mod, "run_webui_archive_full_parse", fake_full_parse)

    report = run_webui_archive_source_refresh(
        since=date(2026, 1, 1),
        until=date(2026, 2, 28),
        requested_mode="live-headless",
        run_id="live_refresh",
        output_root=tmp_path / "source_refresh_runs",
        source_root=None,
        stores_config=stores,
        session_state=tmp_path / "session.json",
        full_parse_root=tmp_path / "full_parse_runs",
        download_runs_root=tmp_path / "download_runs",
        dotenv_path=tmp_path / ".env",
        archive_url="https://example.invalid/archive",
        strict=True,
        store_codes=["ACMEWEAR"],
        manual_login=False,
        login_timeout=1,
        download_timeout=1,
        allow_manual_download=False,
    )

    assert report["status"] == "PASS"
    assert captured["headful"] is False
    assert captured["manual_login"] is False
    assert captured["store_codes"] == ["ACMEWEAR"]
    assert captured["write_child_anchors"] is False
    assert report["all_enabled_stores"] == ["ACMEWEAR", "UNIVERSAL"]
    assert report["target_stores"] == ["ACMEWEAR"]
    assert report["omitted_enabled_stores"] == ["UNIVERSAL"]
    assert report["expected_block_count"] == 1
    assert Path(report["run_manifest_json"]).exists()


def test_chrome_cdp_attach_fails_closed(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)

    try:
        run_webui_archive_source_refresh(
            since=date(2026, 1, 1),
            until=date(2026, 2, 28),
            requested_mode="chrome-cdp-attach",
            run_id="cdp_refresh",
            output_root=tmp_path / "source_refresh_runs",
            source_root=None,
            stores_config=stores,
            session_state=tmp_path / "session.json",
            full_parse_root=tmp_path / "full_parse_runs",
            download_runs_root=tmp_path / "download_runs",
            dotenv_path=tmp_path / ".env",
            archive_url="https://example.invalid/archive",
            strict=True,
            store_codes=None,
            manual_login=False,
            login_timeout=1,
            download_timeout=1,
            allow_manual_download=False,
        )
    except WebuiArchiveSourceRefreshError as exc:
        assert "not yet supported" in str(exc)
    else:
        raise AssertionError("chrome-cdp-attach must fail closed until implemented")
