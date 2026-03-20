from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts.validate_webui_archive_pack_integrity import (
    WebuiPackIntegrityError,
    validate_webui_archive_pack_integrity,
)
from scripts.webui_archive_truth_utils import PACK_NORMALIZED_COLUMNS, compute_sha256, write_pack


def _write_stores(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "stores": {
                    "ACMEWEAR": {"enabled": True, "merchant_uid": "30137883"},
                    "UNIVERSAL": {"enabled": True, "merchant_uid": "30000001"},
                }
            }
        ),
        encoding="utf-8",
    )


def _write_pack(root: Path, *, status_change_missing: bool) -> Path:
    pack = root / "pack"
    pack.mkdir(parents=True, exist_ok=True)
    source_file = pack / "source.csv"
    source_file.write_text("id\n1\n", encoding="utf-8")

    manifest = {
        "pack_id": "pack",
        "source_file_count": 1,
        "missing_store_files": [],
        "files": [
            {
                "absolute_source_file": str(source_file.resolve()),
                "source_file_sha256": compute_sha256(source_file),
            }
        ],
    }
    (pack / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    row = {column: "" for column in PACK_NORMALIZED_COLUMNS}
    row.update(
        {
            "pack_id": "pack",
            "store_code": "ACMEWEAR",
            "source_file": "source.csv",
            "source_file_sha256": manifest["files"][0]["source_file_sha256"],
            "source_file_format": "csv",
            "source_row_number": 1,
            "order_id": "1",
            "created_at": "2026-01-01",
            "status_change_at": "" if status_change_missing else "2026-01-05",
            "status_raw": "Выдан",
            "status_internal": "DELIVERED",
            "quantity": "1",
            "net_rev_kzt": "1000",
            "status_change_required": "True",
            "status_change_missing": "True" if status_change_missing else "",
            "row_fingerprint": "row-1",
            "window_since": "2026-01-01",
            "window_until": "2026-01-31",
        }
    )
    pd.DataFrame([row], columns=PACK_NORMALIZED_COLUMNS).to_csv(
        pack / "normalized_rows.csv",
        index=False,
        encoding="utf-8",
    )
    return pack


def test_validate_webui_archive_pack_integrity_pass(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    pack = _write_pack(tmp_path, status_change_missing=False)

    report = validate_webui_archive_pack_integrity(
        pack_root=pack,
        stores_config=stores,
        strict=True,
    )

    assert report["status"] == "PASS"


def test_validate_webui_archive_pack_integrity_strict_fail(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    pack = _write_pack(tmp_path, status_change_missing=True)

    with pytest.raises(WebuiPackIntegrityError):
        validate_webui_archive_pack_integrity(
            pack_root=pack,
            stores_config=stores,
            strict=True,
        )


def test_write_pack_accepts_same_store_multiple_warehouse_suffixes(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    source_root = tmp_path / "source"
    raw_dir = source_root / "store_ACMEWEAR"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / "ArchiveOrders_ACMEWEAR_2025-11-28_to_2026-02-25.xlsx"
    pd.DataFrame(
        [
            {
                "№ заказа": "1",
                "Дата поступления заказа": "2025-11-28",
                "Дата изменения статуса": "2025-11-30",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30137883_PP1",
            },
            {
                "№ заказа": "2",
                "Дата поступления заказа": "2025-11-29",
                "Дата изменения статуса": "2025-12-01",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30137883_PP3",
            },
        ]
    ).to_excel(raw_file, index=False)

    report = write_pack(
        source_root=source_root,
        pack_id="pack",
        output_root=tmp_path / "packs",
        stores_config=stores,
    )

    assert report["manifest"]["stores_present"] == ["ACMEWEAR"]
    assert report["manifest"]["delivered_missing_status_change_date"] == 0


def test_write_pack_rejects_cross_store_warehouse_mix(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    source_root = tmp_path / "source"
    raw_dir = source_root / "store_ACMEWEAR"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / "ArchiveOrders_ACMEWEAR_2025-11-28_to_2026-02-25.xlsx"
    pd.DataFrame(
        [
            {
                "№ заказа": "1",
                "Дата поступления заказа": "2025-11-28",
                "Дата изменения статуса": "2025-11-30",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30137883_PP3",
            },
            {
                "№ заказа": "2",
                "Дата поступления заказа": "2025-11-29",
                "Дата изменения статуса": "2025-12-01",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30000001_PP1",
            },
        ]
    ).to_excel(raw_file, index=False)

    with pytest.raises(ValueError, match="multiple warehouse-to-store mappings found"):
        write_pack(
            source_root=source_root,
            pack_id="pack",
            output_root=tmp_path / "packs",
            stores_config=stores,
        )
