from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_ocean_drop_anchor_dataset import build_ocean_drop_anchor_dataset


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _prepare_base_and_registry(tmp_path: Path) -> tuple[Path, Path]:
    base_csv = tmp_path / "base.csv"
    pd.DataFrame(
        [
            {
                "№ заказа": "1001",
                "Склад передачи КД": "30000001_PP1",
                "Дата поступления заказа": "26.02.2026",
                "Дата изменения статуса": "",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
            }
        ]
    ).to_csv(base_csv, index=False, encoding="utf-8")
    registry = tmp_path / "anchor.json"
    registry.write_text(
        json.dumps(
            {
                "ocean_drop_path": str(base_csv),
                "as_of_end": "2026-02-26",
                "sha256": _sha256(base_csv),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return base_csv, registry


def _prepare_ui_pack(tmp_path: Path, *, with_status_date: bool) -> Path:
    pack = tmp_path / "ui_pack"
    (pack / "store_UNIVERSAL").mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(
        json.dumps({"since": "2026-01-01", "until": "2026-02-26"}, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "№ заказа": "1001",
                "Дата поступления заказа": "26.02.2026",
                "Дата изменения статуса": "26.02.2026" if with_status_date else "",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30000001_PP1",
            }
        ]
    ).to_csv(pack / "store_UNIVERSAL" / "ArchiveOrders_UNIVERSAL.csv", index=False, encoding="utf-8")
    return pack


def test_merge_fills_status_change_date_without_row_drift(tmp_path: Path) -> None:
    _base, registry = _prepare_base_and_registry(tmp_path)
    ui_pack = _prepare_ui_pack(tmp_path, with_status_date=True)
    report = build_ocean_drop_anchor_dataset(
        as_of=pd.Timestamp("2026-02-26").date(),
        ui_pack_root=ui_pack,
        anchor_registry=registry,
        output_root=tmp_path / "out",
        validation_root=tmp_path / "validation",
        strict=True,
        update_registry=False,
        apply=False,
    )
    assert report["status"] == "PASS"
    assert report["before_rows"] == report["after_rows"] == 1
    merged = pd.read_csv(report["output_csv"], dtype=str, keep_default_na=False)
    assert merged.loc[0, "Дата изменения статуса"] == "26.02.2026"


def test_merge_strict_fails_when_ui_coverage_still_missing(tmp_path: Path) -> None:
    _base, registry = _prepare_base_and_registry(tmp_path)
    ui_pack = _prepare_ui_pack(tmp_path, with_status_date=False)
    with pytest.raises(RuntimeError, match="missing status-change date rows inside ui coverage window"):
        build_ocean_drop_anchor_dataset(
            as_of=pd.Timestamp("2026-02-26").date(),
            ui_pack_root=ui_pack,
            anchor_registry=registry,
            output_root=tmp_path / "out",
            validation_root=tmp_path / "validation",
            strict=True,
            update_registry=False,
            apply=False,
        )
