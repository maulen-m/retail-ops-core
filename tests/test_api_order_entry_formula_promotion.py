from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import scripts.apply_api_order_entry_formula_promotion_manifest as apply_mod
from scripts.apply_api_order_entry_formula_promotion_manifest import (
    ApiEntryPromotionApplyError,
    apply_manifest,
)
from scripts.build_api_order_entry_formula_promotion_manifest import (
    ApiEntryPromotionManifestError,
    build_promotion_manifest,
    validate_promotion_manifest,
)
from scripts.build_api_order_entry_formula_provenance_sidecar import build_sidecar


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw(entry_id: str, offer: str, total: int) -> str:
    pos = base64.b64encode(b"30000001_PP1").decode().rstrip("=")
    return json.dumps(
        {
            "entry": {
                "id": entry_id,
                "attributes": {
                    "offer": {"code": offer},
                    "quantity": 1,
                    "totalPrice": total,
                },
                "relationships": {
                    "deliveryPointOfService": {"data": {"id": pos}}
                },
            },
            "recovery_source": {"kind": "fixture"},
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _source_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_order_entries_kaspi (
              entry_id TEXT PRIMARY KEY, order_id TEXT, store_code TEXT,
              product_id TEXT, offer_id TEXT, quantity REAL,
              unit_price_kzt REAL, total_price_kzt REAL, raw_json TEXT,
              entry_number INTEGER);
            CREATE TABLE fact_orders_kaspi (
              id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
              quantity REAL, unit_price_kzt REAL, delivery_cost_for_seller REAL,
              created_at TEXT, status_updated_at TEXT, kaspi_status TEXT,
              internal_status TEXT, source TEXT, source_file TEXT,
              line_identity_key TEXT);
            CREATE TABLE order_status_event (
              event_id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
              stage_code TEXT, event_ts TEXT, source TEXT,
              source_status_change_at TEXT, source_run_id TEXT,
              source_row_hash TEXT);
            CREATE TABLE dim_kaspi_article_map (
              id INTEGER PRIMARY KEY, store_code TEXT, merchant_id TEXT,
              kaspi_article TEXT, sku_key TEXT, sku_id TEXT,
              active_flag INTEGER, source TEXT);
            CREATE TABLE dim_sku_size (
              sku_key TEXT, sku_id TEXT, my_size TEXT, active_flag INTEGER);
            """
        )
        rows = [
            ("E0", "P0", "A0", 7990, 0, "ROM", "ROM_24", "24"),
            ("E1", "P1", "A1", 9500, 1, "PRINT", "PRINT_S", "S"),
        ]
        for entry, product, offer, total, ordinal, key, sku, size in rows:
            conn.execute(
                "INSERT INTO fact_order_entries_kaspi VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entry, "978", "UNIVERSAL", product, offer, 1, total, total, _raw(entry, offer, total), ordinal),
            )
            conn.execute(
                "INSERT INTO dim_kaspi_article_map VALUES (?,?,?,?,?,?,1,'FIXTURE')",
                (ordinal + 1, "UNIVERSAL", "30000001", offer, key, sku),
            )
            conn.execute("INSERT INTO dim_sku_size VALUES (?,?,?,1)", (key, sku, size))
        conn.execute(
            "INSERT INTO fact_orders_kaspi VALUES (1,'978','UNIVERSAL',1,17490,1507,'2026-06-27','2026-06-30','ARCHIVE','COMPLETED','API','SOURCE','HEADER')"
        )
        conn.execute(
            "INSERT INTO fact_orders_kaspi VALUES (2,'978','UNIVERSAL',1,9500,NULL,'2026-06-27',NULL,'KASPI_DELIVERY','ACCEPTED','API','SOURCE','LINE')"
        )
        conn.execute(
            "INSERT INTO order_status_event VALUES (1,'978','UNIVERSAL','COMPLETED','2026-06-30','WEBUI_STATUS_LEDGER_SCOPED','2026-06-30','run','hash')"
        )


def _copied_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
              sale_id INTEGER PRIMARY KEY, order_id TEXT, order_date TEXT,
              store_code TEXT, sku_key TEXT, sku_id TEXT, my_size TEXT,
              quantity REAL, sell_price_kzt REAL, delivery_fee REAL,
              net_rev REAL, cogs REAL, profit REAL, status TEXT,
              return_flag INTEGER, source_file TEXT, source_entry_id TEXT,
              kaspi_article TEXT, line_identity_key TEXT);
            CREATE TABLE unrelated (id INTEGER PRIMARY KEY, value TEXT);
            INSERT INTO unrelated VALUES (1,'preserve');
            INSERT INTO sales_fact_v2 VALUES
              (1,'978','2026-06-28','UNIVERSAL','ROM','ROM_24','24',1,7990,NULL,NULL,NULL,NULL,'DELIVERED',0,'repair','E0','A0','ENTRY:E0');
            INSERT INTO sales_fact_v2 VALUES
              (2,'978','2026-06-28','UNIVERSAL','PRINT','PRINT_S','S',1,9500,0,8063.125,NULL,NULL,'DELIVERED',0,'crm','E1','A1','ENTRY:E1');
            INSERT INTO sales_fact_v2 VALUES
              (3,'OTHER','2026-06-28','ACMEWEAR','OTHER','OTHER_M','M',1,5000,100,4000,2000,2000,'DELIVERED',0,'other','EO','AO','ENTRY:EO');
            CREATE VIEW view_sales_line_truth AS
            SELECT order_id,date(order_date) sale_date,store_code,sku_key,sku_id,
              my_size,quantity units,COALESCE(net_rev,0) net_rev_kzt,
              'sales_fact_v2' source_table,sku_key source_sku_key,
              sku_id source_sku_id,quantity source_units,
              COALESCE(net_rev,0) source_net_rev_kzt
            FROM sales_fact_v2 WHERE status='DELIVERED' AND COALESCE(return_flag,0)=0;
            """
        )


def _packet(tmp_path: Path) -> tuple[Path, Path, Path, Path, dict]:
    source = tmp_path / "source.db"
    baseline = tmp_path / "baseline.db"
    sidecar_dir = tmp_path / "sidecar"
    promotion_path = tmp_path / "promotion.json"
    _source_db(source)
    _copied_db(baseline)
    sidecar = build_sidecar(
        source_db_path=source,
        copied_db_path=baseline,
        order_id="978",
        store_code="UNIVERSAL",
        merchant_id="30000001",
        expected_entry_count=2,
        expected_source_db_sha256=_sha(source),
        expected_copied_db_sha256=_sha(baseline),
        output_dir=sidecar_dir,
    )
    promotion = build_promotion_manifest(
        source_manifest_path=sidecar_dir / "manifest.json",
        copied_db_path=baseline,
        expected_source_manifest_sha256=sidecar["manifest_sha256"],
        expected_copied_db_sha256=_sha(baseline),
        output_path=promotion_path,
    )
    return source, baseline, sidecar_dir, promotion_path, promotion


def test_manifest_is_exact_deterministic_and_valid(tmp_path: Path) -> None:
    _, baseline, sidecar_dir, promotion_path, first = _packet(tmp_path)
    first_bytes = promotion_path.read_bytes()
    second = build_promotion_manifest(
        source_manifest_path=sidecar_dir / "manifest.json",
        copied_db_path=baseline,
        expected_source_manifest_sha256=json.loads((sidecar_dir / "manifest.json").read_text())["manifest_sha256"],
        expected_copied_db_sha256=_sha(baseline),
        output_path=promotion_path,
    )
    assert first == second
    assert first_bytes == promotion_path.read_bytes()
    assert first["target_count"] == 2
    assert first["target_sale_ids"] == [1, 2]
    assert first["production_apply_authorized"] is False
    assert first["copied_apply_ready"] is True
    assert first["provisional_economic_date"] is False
    assert first["blocked_reasons"] == []
    assert validate_promotion_manifest(promotion_path)["ok"] is True


def test_manifest_rejects_target_preimage_drift(tmp_path: Path) -> None:
    _, baseline, sidecar_dir, _, _ = _packet(tmp_path)
    with sqlite3.connect(baseline) as conn:
        conn.execute("UPDATE sales_fact_v2 SET my_size='XL' WHERE sale_id=2")
    with pytest.raises(ApiEntryPromotionManifestError, match="validation failed|different copied DB"):
        build_promotion_manifest(
            source_manifest_path=sidecar_dir / "manifest.json",
            copied_db_path=baseline,
            expected_source_manifest_sha256=json.loads((sidecar_dir / "manifest.json").read_text())["manifest_sha256"],
            expected_copied_db_sha256=_sha(baseline),
            output_path=tmp_path / "drift.json",
        )


def test_manifest_output_cannot_overwrite_or_hardlink_a_protected_file(tmp_path: Path) -> None:
    _, baseline, sidecar_dir, _, _ = _packet(tmp_path)
    sidecar_manifest = sidecar_dir / "manifest.json"
    internal = json.loads(sidecar_manifest.read_text())["manifest_sha256"]
    with pytest.raises(ApiEntryPromotionManifestError, match="collides"):
        build_promotion_manifest(
            source_manifest_path=sidecar_manifest,
            copied_db_path=baseline,
            expected_source_manifest_sha256=internal,
            expected_copied_db_sha256=_sha(baseline),
            output_path=baseline,
        )
    hardlink = tmp_path / "manifest-hardlink.json"
    hardlink.hardlink_to(sidecar_manifest)
    before = _sha(sidecar_manifest)
    with pytest.raises(ApiEntryPromotionManifestError, match="collides"):
        build_promotion_manifest(
            source_manifest_path=sidecar_manifest,
            copied_db_path=baseline,
            expected_source_manifest_sha256=internal,
            expected_copied_db_sha256=_sha(baseline),
            output_path=hardlink,
        )
    assert _sha(sidecar_manifest) == before


def test_dry_run_is_noop_and_refuses_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, baseline, _, promotion_path, promotion = _packet(tmp_path)
    target = tmp_path / "target.db"
    shutil.copy2(baseline, target)
    monkeypatch.setattr(apply_mod, "RUNS_ROOT", tmp_path.resolve())
    before = _sha(target)
    report = apply_manifest(
        manifest_path=promotion_path,
        db_path=target,
        expected_manifest_sha256=promotion["manifest_sha256"],
        expected_db_sha256=before,
        apply=False,
    )
    assert report["status"] == "PASS"
    assert _sha(target) == before
    with pytest.raises(ApiEntryPromotionApplyError, match="baseline DB"):
        apply_manifest(
            manifest_path=promotion_path,
            db_path=baseline,
            expected_manifest_sha256=promotion["manifest_sha256"],
            expected_db_sha256=_sha(baseline),
            apply=False,
        )


def test_apply_is_gated_backup_first_target_only_and_read_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, baseline, _, promotion_path, promotion = _packet(tmp_path)
    target = tmp_path / "target.db"
    shutil.copy2(baseline, target)
    monkeypatch.setattr(apply_mod, "RUNS_ROOT", tmp_path.resolve())
    pre_sha = _sha(target)
    with pytest.raises(ApiEntryPromotionApplyError, match="requires ENABLE"):
        apply_manifest(
            manifest_path=promotion_path,
            db_path=target,
            expected_manifest_sha256=promotion["manifest_sha256"],
            expected_db_sha256=pre_sha,
            apply=True,
            backup_dir=tmp_path / "backups",
        )
    monkeypatch.setenv("ENABLE_COPIED_API_ENTRY_FORMULA_REPAIR", "1")
    report_path = tmp_path / "apply_report.json"
    report = apply_manifest(
        manifest_path=promotion_path,
        db_path=target,
        expected_manifest_sha256=promotion["manifest_sha256"],
        expected_db_sha256=pre_sha,
        apply=True,
        backup_dir=tmp_path / "backups",
        report_path=report_path,
    )
    assert report["status"] == "PASS"
    assert report["target_count"] == 2
    assert report["db_integrity"] == "ok"
    assert report["non_target_sales_fact_v2_sha256_before"] == report["non_target_sales_fact_v2_sha256_after"]
    assert Path(report["backup_path"]).exists()
    assert _sha(Path(report["backup_path"])) == pre_sha
    assert report["idempotent_replay"] is True
    rollback = json.loads(Path(report["rollback_artifact_path"]).read_text(encoding="utf-8"))
    assert rollback["status"] == "READY"
    assert rollback["backup_sha256"] == pre_sha
    with sqlite3.connect(target) as conn:
        rows = conn.execute(
            "SELECT sale_id,delivery_fee,net_rev,profit FROM sales_fact_v2 ORDER BY sale_id"
        ).fetchall()
        assert rows[0][1:] == (688.45, 6050.69, None)
        assert rows[1][1:] == (818.55, 7194.19, None)
        assert rows[2][1:] == (100.0, 4000.0, 2000.0)
        assert conn.execute("SELECT value FROM unrelated").fetchone()[0] == "preserve"


def test_report_collision_is_rejected_before_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, baseline, _, promotion_path, promotion = _packet(tmp_path)
    target = tmp_path / "target.db"
    shutil.copy2(baseline, target)
    occupied = tmp_path / "occupied.json"
    occupied.write_text("keep")
    monkeypatch.setattr(apply_mod, "RUNS_ROOT", tmp_path.resolve())
    monkeypatch.setenv("ENABLE_COPIED_API_ENTRY_FORMULA_REPAIR", "1")
    backup_dir = tmp_path / "backups"
    with pytest.raises(ApiEntryPromotionApplyError, match="already exists"):
        apply_manifest(
            manifest_path=promotion_path,
            db_path=target,
            expected_manifest_sha256=promotion["manifest_sha256"],
            expected_db_sha256=_sha(target),
            apply=True,
            backup_dir=backup_dir,
            report_path=occupied,
        )
    assert occupied.read_text() == "keep"
    assert not backup_dir.exists()


def test_second_apply_fails_closed_on_preimage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, baseline, _, promotion_path, promotion = _packet(tmp_path)
    target = tmp_path / "target.db"
    shutil.copy2(baseline, target)
    monkeypatch.setattr(apply_mod, "RUNS_ROOT", tmp_path.resolve())
    monkeypatch.setenv("ENABLE_COPIED_API_ENTRY_FORMULA_REPAIR", "1")
    pre_sha = _sha(target)
    apply_manifest(
        manifest_path=promotion_path,
        db_path=target,
        expected_manifest_sha256=promotion["manifest_sha256"],
        expected_db_sha256=pre_sha,
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    with pytest.raises(ApiEntryPromotionApplyError, match="SHA-256 mismatch|preimage"):
        apply_manifest(
            manifest_path=promotion_path,
            db_path=target,
            expected_manifest_sha256=promotion["manifest_sha256"],
            expected_db_sha256=_sha(target),
            apply=True,
            backup_dir=tmp_path / "backups2",
        )


def test_post_commit_failure_restores_exact_copied_preimage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, baseline, _, promotion_path, promotion = _packet(tmp_path)
    target = tmp_path / "target.db"
    shutil.copy2(baseline, target)
    monkeypatch.setattr(apply_mod, "RUNS_ROOT", tmp_path.resolve())
    monkeypatch.setenv("ENABLE_COPIED_API_ENTRY_FORMULA_REPAIR", "1")
    pre_sha = _sha(target)
    report_path = tmp_path / "apply_report.json"
    backup_dir = tmp_path / "backups"

    def fail_post_commit(_path: Path) -> None:
        raise ApiEntryPromotionApplyError("injected post-commit failure")

    monkeypatch.setattr(apply_mod, "_post_commit_barrier", fail_post_commit)
    with pytest.raises(ApiEntryPromotionApplyError, match="restored"):
        apply_manifest(
            manifest_path=promotion_path,
            db_path=target,
            expected_manifest_sha256=promotion["manifest_sha256"],
            expected_db_sha256=pre_sha,
            apply=True,
            backup_dir=backup_dir,
            report_path=report_path,
        )

    assert _sha(target) == pre_sha
    assert not report_path.exists()
    rollback_paths = list(backup_dir.glob("ROLLBACK_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "RESTORED_AFTER_POST_COMMIT_FAILURE"
    assert rollback["restore_verified"] is True
    assert rollback["restored_sha256"] == pre_sha


def test_idempotent_replay_failure_restores_exact_copied_preimage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, baseline, _, promotion_path, promotion = _packet(tmp_path)
    target = tmp_path / "target.db"
    shutil.copy2(baseline, target)
    monkeypatch.setattr(apply_mod, "RUNS_ROOT", tmp_path.resolve())
    monkeypatch.setenv("ENABLE_COPIED_API_ENTRY_FORMULA_REPAIR", "1")
    pre_sha = _sha(target)
    backup_dir = tmp_path / "backups"

    def fail_replay(*args, **kwargs) -> None:
        raise ApiEntryPromotionApplyError("injected idempotent replay failure")

    monkeypatch.setattr(apply_mod, "_verify_idempotent_replay_in_transaction", fail_replay)
    with pytest.raises(ApiEntryPromotionApplyError, match="idempotent replay"):
        apply_manifest(
            manifest_path=promotion_path,
            db_path=target,
            expected_manifest_sha256=promotion["manifest_sha256"],
            expected_db_sha256=pre_sha,
            apply=True,
            backup_dir=backup_dir,
        )

    assert _sha(target) == pre_sha
    rollback_paths = list(backup_dir.glob("ROLLBACK_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "TRANSACTION_ROLLED_BACK_AND_PREIMAGE_RESTORED"
    assert rollback["restore_verified"] is True
    assert rollback["restored_sha256"] == pre_sha
