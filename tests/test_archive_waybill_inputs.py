import json
import os
import time
from pathlib import Path

from scripts import archive_waybill_inputs


def _set_mtime(path: Path, age_days: int) -> None:
    ts = time.time() - (age_days * 24 * 60 * 60)
    os.utime(path, (ts, ts))


def test_archive_waybill_inputs_selection_only_and_retention(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    waybill_dir = data_root / "excel_ui" / "ActiveOrders" / "waybills"
    active_orders_dir = data_root / "excel_ui" / "ActiveOrders"
    archive_root = data_root / "excel_ui" / "Archive"
    crm_file = data_root / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    selection_cache = waybill_dir / "_waybill_selection_orders.json"
    gdrive_root = tmp_path / "gdrive" / "Kaspi_waybills"
    external_db_root = tmp_path / "External_database"

    waybill_dir.mkdir(parents=True, exist_ok=True)
    active_orders_dir.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)
    crm_file.write_text("dummy workbook", encoding="utf-8")

    selection_cache.write_text(
        json.dumps(
            {
                "target_date": "2026-02-06",
                "stores": {"UNIVERSAL": ["1001"], "MELVIS": ["1002"]},
            }
        ),
        encoding="utf-8",
    )

    (waybill_dir / "1001.pdf").write_bytes(b"%PDF-1.4")
    (waybill_dir / "1002.pdf").write_bytes(b"%PDF-1.4")
    (waybill_dir / "1003.pdf").write_bytes(b"%PDF-1.4")
    (waybill_dir / "9999.pdf").write_bytes(b"%PDF-1.4")
    _set_mtime(waybill_dir / "9999.pdf", age_days=40)

    (active_orders_dir / "waybill_sample.zip").write_bytes(b"zip-bytes")

    old_archive = archive_root / "input_2025-01-01_000000"
    old_archive.mkdir(parents=True, exist_ok=True)
    _set_mtime(old_archive, age_days=40)

    argv = [
        "archive_waybill_inputs.py",
        "--data-root",
        str(data_root),
        "--selection-cache",
        str(selection_cache),
        "--crm-file",
        str(crm_file),
        "--waybill-dir",
        str(waybill_dir),
        "--active-orders-dir",
        str(active_orders_dir),
        "--archive-root",
        str(archive_root),
        "--gdrive-archive-root",
        str(gdrive_root),
        "--external-db-root",
        str(external_db_root),
        "--repo-label",
        "Autonomous_business",
        "--cache-retention-days",
        "30",
        "--archive-retention-days",
        "14",
    ]
    monkeypatch.setattr("sys.argv", argv)

    rc = archive_waybill_inputs.main()
    assert rc == 0

    archive_dirs = sorted(archive_root.glob("input_*"))
    assert len(archive_dirs) == 1
    run_dir = archive_dirs[0]

    # Selection-only archive: selected IDs copied, unrelated IDs not copied.
    assert (run_dir / "waybills" / "1001.pdf").exists()
    assert (run_dir / "waybills" / "1002.pdf").exists()
    assert not (run_dir / "waybills" / "1003.pdf").exists()

    # Workbook backup written to local + gdrive + external db.
    assert (run_dir / "SALES_KSP_CRM_V3.xlsx").exists()
    gdrive_runs = sorted(gdrive_root.glob("input_*"))
    assert len(gdrive_runs) == 1
    assert (gdrive_runs[0] / "SALES_KSP_CRM_V3.xlsx").exists()
    external_workbooks = list(
        (external_db_root / "Autonomous_business" / "kaspi_waybills" / "workbooks").glob(
            "SALES_KSP_CRM_V3_*.xlsx"
        )
    )
    assert external_workbooks

    # Old cache migrated and removed locally.
    assert (
        external_db_root
        / "Autonomous_business"
        / "kaspi_waybills"
        / "by_order"
        / "9999.pdf"
    ).exists()
    assert not (waybill_dir / "9999.pdf").exists()

    # Old archive removed by retention.
    assert not old_archive.exists()

    # Manifest files exist.
    assert (run_dir / "archive_manifest.json").exists()
    assert (run_dir / "archive_manifest.csv").exists()
