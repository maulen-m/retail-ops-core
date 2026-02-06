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
