from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.export_kaspi_archive_ui_history import (
    DEFAULT_STORES,
    export_kaspi_archive_ui_history,
    plan_windows,
)


def test_plan_windows_uses_90_day_blocks() -> None:
    windows = plan_windows(
        since=pd.Timestamp("2026-01-01").date(),
        until=pd.Timestamp("2026-04-15").date(),
    )
    assert windows[0][0].isoformat() == "2026-01-01"
    assert windows[0][1].isoformat() == "2026-03-31"
    assert windows[1][0].isoformat() == "2026-04-01"
    assert windows[1][1].isoformat() == "2026-04-15"


def test_resume_manifest_short_circuits_when_outputs_exist(tmp_path: Path) -> None:
    out_dir = tmp_path / "ui_pack"
    out_dir.mkdir(parents=True)
    manifest = {
        "since": "2026-01-01",
        "until": "2026-02-26",
        "results": [{"store_code": s, "rows_exported": 0} for s in DEFAULT_STORES],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (out_dir / "run_summary.md").write_text("# summary\n", encoding="utf-8")
    for store in DEFAULT_STORES:
        store_dir = out_dir / f"store_{store}"
        store_dir.mkdir(parents=True)
        (store_dir / f"ArchiveOrders_{store}.csv").write_text("№ заказа\n", encoding="utf-8")

    report = export_kaspi_archive_ui_history(
        since=pd.Timestamp("2026-01-01").date(),
        until=pd.Timestamp("2026-02-26").date(),
        output_root=tmp_path,
        strict=True,
        stores=DEFAULT_STORES,
        seed_xlsx_files=[],
        resume_manifest=manifest_path,
    )
    assert report["resumed"] is True
    assert report["manifest_path"] == str(manifest_path.resolve())


def test_export_from_seed_files_writes_store_outputs(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "universal.xlsx"
    pd.DataFrame(
        [
            {
                "№ заказа": "123",
                "Дата поступления заказа": "26.02.2026",
                "Дата изменения статуса": "26.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30000001_PP1",
            }
        ]
    ).to_excel(xlsx_path, index=False)

    report = export_kaspi_archive_ui_history(
        since=pd.Timestamp("2026-02-01").date(),
        until=pd.Timestamp("2026-02-26").date(),
        output_root=tmp_path,
        strict=True,
        stores=["UNIVERSAL"],
        seed_xlsx_files=[xlsx_path],
        resume_manifest=None,
    )
    pack = Path(report["output_dir"])
    assert (pack / "store_UNIVERSAL" / "ArchiveOrders_UNIVERSAL.csv").exists()
    assert (pack / "manifest.json").exists()
