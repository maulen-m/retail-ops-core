from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_archive_export_integrity import validate_archive_export_integrity


def _write_store_fixture(base: Path, store_code: str, *, completed_missing_status_change: bool) -> None:
    store_dir = base / f"store_{store_code}"
    store_dir.mkdir(parents=True, exist_ok=True)

    windows_csv = (
        "window_index,since,until,orders_fetched,status,error,duration_sec\n"
        "1,2026-02-20,2026-02-26,2,ok,,0.21\n"
    )
    (store_dir / "windows.csv").write_text(windows_csv, encoding="utf-8")

    status_change = "" if completed_missing_status_change else "25.02.2026"
    csv_data = (
        "№ заказа,Дата поступления заказа,Дата изменения статуса,Статус\n"
        f"835000001,24.02.2026,{status_change},Завершен\n"
        "835000002,24.02.2026,,Отменен\n"
    )
    (store_dir / f"ArchiveOrders_{store_code}.csv").write_text(csv_data, encoding="utf-8")


def test_validate_archive_export_integrity_pass(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    _write_store_fixture(export_root, "UNIVERSAL", completed_missing_status_change=False)
    _write_store_fixture(export_root, "ACMEWEAR", completed_missing_status_change=False)

    report = validate_archive_export_integrity(
        export_root=export_root,
        since="2026-02-20",
        until="2026-02-26",
        strict=False,
        require_status_change_date_for_completed=True,
    )

    assert report["status"] == "PASS"
    assert report["errors"] == []
    assert Path(report["artifacts"]["json"]).exists()
    payload = json.loads(Path(report["artifacts"]["json"]).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_validate_archive_export_integrity_strict_fails_missing_completed_status_change(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    _write_store_fixture(export_root, "UNIVERSAL", completed_missing_status_change=True)

    with pytest.raises(RuntimeError, match="archive export integrity validation failed"):
        validate_archive_export_integrity(
            export_root=export_root,
            since="2026-02-20",
            until="2026-02-26",
            strict=True,
            require_status_change_date_for_completed=True,
        )


def test_validate_archive_export_integrity_fails_when_status_mode_selects_zero_with_dedup(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    _write_store_fixture(export_root, "UNIVERSAL", completed_missing_status_change=False)
    # Replace CSV with headers only to emulate zero selected rows.
    (export_root / "store_UNIVERSAL" / "ArchiveOrders_UNIVERSAL.csv").write_text(
        "№ заказа,Дата поступления заказа,Дата изменения статуса,Статус\n",
        encoding="utf-8",
    )
    manifest = {
        "results": [
            {
                "store_code": "UNIVERSAL",
                "date_mode": "statusChangeDate",
                "orders_dedup": 100,
                "orders_selected": 0,
            }
        ]
    }
    (export_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(RuntimeError, match="archive export integrity validation failed"):
        validate_archive_export_integrity(
            export_root=export_root,
            since="2026-02-20",
            until="2026-02-26",
            strict=True,
            require_status_change_date_for_completed=True,
        )
