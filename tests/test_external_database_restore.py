import json
from pathlib import Path

from scripts.external_database_restore import ensure_external_database_available


def _make_valid_snapshot(backup_root: Path, name: str = "20260206_211000") -> Path:
    snapshot_dir = backup_root / "snapshots" / name
    data_dir = snapshot_dir / "External_database" / "Kaspi_marketing"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sample.txt").write_text("restored", encoding="utf-8")
    manifest = {
        "snapshot_id": name,
        "status": "ok",
        "snapshot_data_dir": str(snapshot_dir / "External_database"),
    }
    (snapshot_dir / "backup_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return snapshot_dir


def test_restore_missing_subdir_from_latest_snapshot(tmp_path: Path) -> None:
    source_root = tmp_path / "External_database"
    source_root.mkdir(parents=True)
    (source_root / "Other").mkdir()

    backup_root = tmp_path / "backup_root"
    _make_valid_snapshot(backup_root)

    result = ensure_external_database_available(
        source_root=source_root,
        backup_root=backup_root,
        required_subdirs=["Kaspi_marketing"],
    )

    assert result["restored"] is True
    assert any(a.startswith("restored_subdir:Kaspi_marketing") for a in result["actions"])
    assert (source_root / "Kaspi_marketing" / "sample.txt").exists()


def test_restore_returns_already_available_when_paths_exist(tmp_path: Path) -> None:
    source_root = tmp_path / "External_database"
    (source_root / "Kaspi_marketing").mkdir(parents=True)
    backup_root = tmp_path / "backup_root"

    result = ensure_external_database_available(
        source_root=source_root,
        backup_root=backup_root,
        required_subdirs=["Kaspi_marketing"],
    )
    assert result["reason"] == "already_available"
    assert result["restored"] is False
