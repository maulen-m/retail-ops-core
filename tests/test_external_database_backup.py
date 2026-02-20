from pathlib import Path

from scripts.external_database_backup import create_snapshot


def test_create_snapshot_writes_manifest_and_cleans_old(tmp_path: Path) -> None:
    source_root = tmp_path / "External_database"
    kaspi_dir = source_root / "Kaspi_marketing"
    kaspi_dir.mkdir(parents=True)
    (kaspi_dir / "sample.txt").write_text("ok", encoding="utf-8")

    backup_root = tmp_path / "backup_root"
    old_snapshot = backup_root / "snapshots" / "20000101_000000"
    old_snapshot.mkdir(parents=True)

    manifest = create_snapshot(
        source_root=source_root,
        backup_root=backup_root,
        keep_days=30,
        critical_subdirs=["Kaspi_marketing"],
    )

    snapshot_id = manifest["snapshot_id"]
    snapshot_data = backup_root / "snapshots" / snapshot_id / "External_database"
    assert manifest["status"] == "ok"
    assert (snapshot_data / "Kaspi_marketing" / "sample.txt").exists()
    assert (backup_root / "latest_snapshot.txt").read_text(encoding="utf-8").strip() == snapshot_id
    assert "20000101_000000" in manifest.get("deleted_snapshots", [])


def test_create_snapshot_excludes_heavy_file_and_offer_uploads(tmp_path: Path) -> None:
    source_root = tmp_path / "External_database"
    source_root.mkdir(parents=True)
    (source_root / "Kaspi_marketing").mkdir(parents=True)
    (source_root / "Kaspi_marketing" / "sample.txt").write_text("ok", encoding="utf-8")

    heavy_file_name = "沪锦大客户报价表 （不含邮与税）.xlsx"
    (source_root / heavy_file_name).write_text("heavy", encoding="utf-8")

    offers_dir = source_root / "kaspi_offer_uploads"
    offers_dir.mkdir(parents=True)
    (offers_dir / "offer.zip").write_text("zip", encoding="utf-8")

    backup_root = tmp_path / "backup_root"
    manifest = create_snapshot(
        source_root=source_root,
        backup_root=backup_root,
        keep_days=30,
        critical_subdirs=["Kaspi_marketing"],
    )
    snapshot_data = backup_root / "snapshots" / manifest["snapshot_id"] / "External_database"

    assert not (snapshot_data / heavy_file_name).exists()
    assert not (snapshot_data / "kaspi_offer_uploads").exists()
    excluded_items = set(manifest.get("excluded_items", []))
    assert heavy_file_name in excluded_items
    assert "kaspi_offer_uploads" in excluded_items


def test_create_snapshot_excludes_by_order_dir_by_default(tmp_path: Path) -> None:
    source_root = tmp_path / "External_database"
    kaspi_dir = source_root / "Kaspi_marketing"
    kaspi_dir.mkdir(parents=True)
    (kaspi_dir / "sample.txt").write_text("ok", encoding="utf-8")

    by_order_dir = source_root / "Autonomous_business" / "kaspi_waybills" / "by_order"
    by_order_dir.mkdir(parents=True)
    (by_order_dir / "123.pdf").write_bytes(b"%PDF-1.4")

    backup_root = tmp_path / "backup_root"
    manifest = create_snapshot(
        source_root=source_root,
        backup_root=backup_root,
        keep_days=30,
        critical_subdirs=["Kaspi_marketing"],
    )
    snapshot_data = backup_root / "snapshots" / manifest["snapshot_id"] / "External_database"

    assert not (snapshot_data / "Autonomous_business" / "kaspi_waybills" / "by_order").exists()
    excluded_items = set(manifest.get("excluded_items", []))
    assert "Autonomous_business/kaspi_waybills/by_order" in excluded_items


def test_create_snapshot_always_excludes_by_order_even_with_custom_exclude_dirs(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "External_database"
    kaspi_dir = source_root / "Kaspi_marketing"
    kaspi_dir.mkdir(parents=True)
    (kaspi_dir / "sample.txt").write_text("ok", encoding="utf-8")

    by_order_dir = source_root / "Autonomous_business" / "kaspi_waybills" / "by_order"
    by_order_dir.mkdir(parents=True)
    (by_order_dir / "999.pdf").write_bytes(b"%PDF-1.4")

    backup_root = tmp_path / "backup_root"
    manifest = create_snapshot(
        source_root=source_root,
        backup_root=backup_root,
        keep_days=30,
        critical_subdirs=["Kaspi_marketing"],
        exclude_dirs=["kaspi_offer_uploads"],
    )
    snapshot_data = backup_root / "snapshots" / manifest["snapshot_id"] / "External_database"

    assert not (snapshot_data / "Autonomous_business" / "kaspi_waybills" / "by_order").exists()
