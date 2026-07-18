from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.apply_exact_kaspi_article_map_manifest import (
    ENV_GATE,
    ExactArticleMapManifestError,
    run,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE dim_store (
            store_code TEXT PRIMARY KEY,
            active_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL REFERENCES dim_sku(sku_key),
            active_flag INTEGER
        );
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL REFERENCES dim_store(store_code),
            merchant_id TEXT,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            kaspi_name_core TEXT,
            sku_key TEXT REFERENCES dim_sku(sku_key),
            sku_id TEXT REFERENCES dim_sku_size(sku_id),
            model TEXT,
            brand TEXT,
            source TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(store_code, kaspi_article)
        );
        INSERT INTO dim_store VALUES ('ACMEWEAR', 1);
        INSERT INTO dim_sku VALUES ('LINE31_IVORY', 1);
        INSERT INTO dim_sku_size VALUES ('LINE31_IVORY_L', 'LINE31_IVORY', 1);
        INSERT INTO dim_kaspi_article_map
        (store_code, merchant_id, kaspi_article, kaspi_offer_name, kaspi_name_core,
         sku_key, sku_id, model, brand, source, active_flag, created_at, updated_at)
        VALUES
        ('ACMEWEAR', '30137883', 'EXISTING', 'Existing', 'Existing_Core',
         'LINE31_IVORY', 'LINE31_IVORY_L', 'LINE31', 'ACMEWEAR', 'fixture', 1, 'a', 'a');
        """
    )
    conn.commit()
    conn.close()
    return path


def _manifest(path: Path, evidence_path: Path) -> Path:
    evidence_path.write_text("evidence\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "operation": "EXACT_DIM_KASPI_ARTICLE_MAP_UPSERT",
        "rows": [
            {
                "old_row": None,
                "new_row": {
                    "store_code": "ACMEWEAR",
                    "merchant_id": "30137883",
                    "kaspi_article": "OF_LINE31_ST_IV_L",
                    "kaspi_offer_name": "LINE31 Ivory L",
                    "kaspi_name_core": "Ivory_Core",
                    "sku_key": "LINE31_IVORY",
                    "sku_id": "LINE31_IVORY_L",
                    "model": "LINE31",
                    "brand": "ACMEWEAR",
                    "source": "exact_manifest_fixture",
                    "active_flag": 1,
                },
                "evidence": [
                    {
                        "source": "fixture-a",
                        "path": str(evidence_path),
                        "sha256": _sha(evidence_path),
                    },
                    {"source": "fixture-b", "path": "", "sha256": ""},
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_dry_run_validates_without_writing(tmp_path: Path) -> None:
    db = _db(tmp_path / "app.db")
    manifest = _manifest(tmp_path / "manifest.json", tmp_path / "evidence.txt")
    pre_sha = _sha(db)

    report = run(
        db_path=db,
        manifest_path=manifest,
        expected_manifest_sha256=_sha(manifest),
        output_path=tmp_path / "dry-run.json",
        apply=False,
    )

    assert report["status"] == "DRY_RUN_VALID"
    assert report["target_count"] == 1
    assert report["before_rows"] == [None]
    assert report["after_rows"] == [None]
    assert report["foreign_key_check_status"] == "PASS"
    assert _sha(db) == pre_sha


def test_apply_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path / "app.db")
    manifest = _manifest(tmp_path / "manifest.json", tmp_path / "evidence.txt")
    monkeypatch.delenv(ENV_GATE, raising=False)

    with pytest.raises(ExactArticleMapManifestError, match=ENV_GATE):
        run(
            db_path=db,
            manifest_path=manifest,
            expected_manifest_sha256=_sha(manifest),
            output_path=tmp_path / "apply.json",
            apply=True,
            expected_pre_sha256=_sha(db),
            backup_dir=tmp_path / "backups",
        )


def test_apply_inserts_only_manifest_row_and_creates_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _db(tmp_path / "app.db")
    manifest = _manifest(tmp_path / "manifest.json", tmp_path / "evidence.txt")
    monkeypatch.setenv(ENV_GATE, "1")

    report = run(
        db_path=db,
        manifest_path=manifest,
        expected_manifest_sha256=_sha(manifest),
        output_path=tmp_path / "apply.json",
        apply=True,
        expected_pre_sha256=_sha(db),
        backup_dir=tmp_path / "backups",
    )

    assert report["status"] == "APPLIED"
    assert report["changes"] == [
        {
            "action": "INSERT",
            "store_code": "ACMEWEAR",
            "kaspi_article": "OF_LINE31_ST_IV_L",
        }
    ]
    assert Path(report["backup_path"]).is_file()
    assert report["before_non_target_hash"] == report["after_non_target_hash"]
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT kaspi_article, kaspi_name_core FROM dim_kaspi_article_map ORDER BY kaspi_article"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("EXISTING", "Existing_Core"), ("OF_LINE31_ST_IV_L", "Ivory_Core")]


def test_rejects_old_row_or_manifest_hash_mismatch(tmp_path: Path) -> None:
    db = _db(tmp_path / "app.db")
    manifest = _manifest(tmp_path / "manifest.json", tmp_path / "evidence.txt")
    with pytest.raises(ExactArticleMapManifestError, match="manifest SHA mismatch"):
        run(
            db_path=db,
            manifest_path=manifest,
            expected_manifest_sha256="0" * 64,
            output_path=tmp_path / "bad.json",
            apply=False,
        )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["rows"][0]["old_row"] = {"store_code": "ACMEWEAR"}
    manifest.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ExactArticleMapManifestError, match="old_row mismatch"):
        run(
            db_path=db,
            manifest_path=manifest,
            expected_manifest_sha256=_sha(manifest),
            output_path=tmp_path / "bad-old.json",
            apply=False,
        )
