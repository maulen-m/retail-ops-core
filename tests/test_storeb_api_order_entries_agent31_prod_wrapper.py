from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.apply_storeb_api_order_entries_from_agent31_production_safe import (
    PRODUCTION_ENV_GATE,
    ProductionAgent31ApplyError,
    apply_storeb_api_order_entries_from_agent31_production_safe,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_db(path: Path, *, existing_safe_entry: bool = False) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                product_id TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                raw_json TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                entry_number INTEGER,
                category_code TEXT,
                category_title TEXT,
                base_price_kzt REAL
            );
            """
        )
        if existing_safe_entry:
            conn.execute(
                """
                INSERT INTO fact_order_entries_kaspi (
                    entry_id, order_id, store_code, product_id, offer_id,
                    quantity, unit_price_kzt, total_price_kzt, raw_json
                ) VALUES ('entry-safe', 'O-SAFE', 'STOREB', 'api-product',
                          'API_ARTICLE_L', 1, 9900, 9900, '{}')
                """
            )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_quarantine(path: Path, order_ids: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["order_id", "store_code", "reason"])
        writer.writeheader()
        for order_id in order_ids:
            writer.writerow({"order_id": order_id, "store_code": "STOREB", "reason": "map_required"})


def _safe_preview(order_id: str, *, entry_ids: str = "entry-safe") -> dict:
    return {
        "order_id": order_id,
        "store_code": "STOREB",
        "evidence_status": "API_ITEM_ENTRY_SKU_ID_SIZE_MAPPED",
        "recommended_temp_apply": True,
        "entry_ids": entry_ids,
        "target_sku_id": "HEADER_ONLY_WRONG_SIZE",
        "target_sku_key": "HEADER_ONLY_WRONG_KEY",
        "source_sku_ids": "ARTICLE_MAP_SKU_L",
        "source_sku_keys": "ARTICLE_MAP_SKU",
    }


def _api_entry(order_id: str, *, entry_id: str = "entry-safe") -> dict:
    return {
        "target_order_id": order_id,
        "target_store_code": "STOREB",
        "entry_id": entry_id,
        "product_id": "api-product",
        "offer_code": "API_ARTICLE_L",
        "offer_name": "API Offer L",
        "quantity": 1,
        "total_price_kzt": 9900,
        "unit_price_kzt": None,
        "base_price_kzt": 9900,
        "entry_number": 0,
        "category_code": "category",
        "category_title": "Category",
        "real_item_entry_evidence": True,
        "sku_rebuild_mappable": True,
        "article_map_sku_id": "ARTICLE_MAP_SKU_L",
        "article_map_sku_key": "ARTICLE_MAP_SKU",
        "target_sku_id": "HEADER_ONLY_WRONG_SIZE",
        "target_sku_key": "HEADER_ONLY_WRONG_KEY",
        "source_kind": "kaspi_api_readonly_order_entry",
        "source_name": "KASPI_API_READONLY_STOREB_EXACT_ORDER_IDS",
    }


def _write_agent31_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    safe_rows = tmp_path / "safe.jsonl"
    api_entries = tmp_path / "api.jsonl"
    quarantine_rows = tmp_path / "quarantine.csv"
    _write_jsonl(safe_rows, [_safe_preview("O-SAFE")])
    _write_jsonl(api_entries, [_api_entry("O-SAFE"), _api_entry("O-QUAR", entry_id="entry-quar")])
    _write_quarantine(quarantine_rows, ["O-QUAR"])
    return safe_rows, api_entries, quarantine_rows


def test_agent31_prod_wrapper_requires_apply_env_and_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    safe_rows, api_entries, quarantine_rows = _write_agent31_inputs(tmp_path)
    original_sha = _sha256(db_path)

    summary = apply_storeb_api_order_entries_from_agent31_production_safe(
        db_path=db_path,
        safe_rows_path=safe_rows,
        api_entries_path=api_entries,
        quarantine_rows_path=quarantine_rows,
        output_root=tmp_path / "dry",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_safe_order_rows=1,
        expected_candidate_entry_rows=1,
        expected_inserted_entry_rows=1,
        expected_quarantine_rows=1,
        apply=False,
    )
    assert summary["apply"]["applied"] is False
    assert summary["backup_path"] is None
    assert _sha256(db_path) == original_sha

    monkeypatch.delenv(PRODUCTION_ENV_GATE, raising=False)
    with pytest.raises(ProductionAgent31ApplyError, match=f"{PRODUCTION_ENV_GATE}=1"):
        apply_storeb_api_order_entries_from_agent31_production_safe(
            db_path=db_path,
            safe_rows_path=safe_rows,
            api_entries_path=api_entries,
            quarantine_rows_path=quarantine_rows,
            output_root=tmp_path / "blocked_env",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_safe_order_rows=1,
            expected_candidate_entry_rows=1,
            expected_inserted_entry_rows=1,
            expected_quarantine_rows=1,
            apply=True,
        )

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionAgent31ApplyError, match="pre-write SHA mismatch"):
        apply_storeb_api_order_entries_from_agent31_production_safe(
            db_path=db_path,
            safe_rows_path=safe_rows,
            api_entries_path=api_entries,
            quarantine_rows_path=quarantine_rows,
            output_root=tmp_path / "blocked_sha",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256="0" * 64,
            expected_safe_order_rows=1,
            expected_candidate_entry_rows=1,
            expected_inserted_entry_rows=1,
            expected_quarantine_rows=1,
            apply=True,
        )
    assert _sha256(db_path) == original_sha


def test_agent31_prod_wrapper_applies_via_staging_and_blocks_quarantine_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    safe_rows, api_entries, quarantine_rows = _write_agent31_inputs(tmp_path)
    original_sha = _sha256(db_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    summary = apply_storeb_api_order_entries_from_agent31_production_safe(
        db_path=db_path,
        safe_rows_path=safe_rows,
        api_entries_path=api_entries,
        quarantine_rows_path=quarantine_rows,
        output_root=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_safe_order_rows=1,
        expected_candidate_entry_rows=1,
        expected_inserted_entry_rows=1,
        expected_quarantine_rows=1,
        apply=True,
    )

    assert summary["apply"]["applied"] is True
    assert summary["apply"]["target_replaced"] is True
    assert summary["materializer_summary"]["apply"]["inserted_entry_rows"] == 1
    assert summary["materializer_summary"]["apply"]["skipped_existing_entry_rows"] == 0
    assert summary["quarantine_product_truth_probe"]["after_count"] == 0
    assert summary["quarantine_product_truth_probe"]["passed"] is True
    assert summary["integrity_check"]["before"] == "ok"
    assert summary["integrity_check"]["after"] == "ok"
    assert Path(summary["backup_path"]).exists()
    assert "cp " in summary["rollback"]["restore_command"]
    assert Path(summary["summary_json"]).exists()

    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert persisted["rollback"]["backup_path"] == summary["backup_path"]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT order_id FROM fact_order_entries_kaspi ORDER BY order_id").fetchall()
    assert rows == [("O-SAFE",)]


def test_agent31_prod_wrapper_rejects_delta_mismatch_before_replacing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    safe_rows, api_entries, quarantine_rows = _write_agent31_inputs(tmp_path)
    original_sha = _sha256(db_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionAgent31ApplyError, match="inserted_entry_rows mismatch"):
        apply_storeb_api_order_entries_from_agent31_production_safe(
            db_path=db_path,
            safe_rows_path=safe_rows,
            api_entries_path=api_entries,
            quarantine_rows_path=quarantine_rows,
            output_root=tmp_path / "mismatch",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_safe_order_rows=1,
            expected_candidate_entry_rows=1,
            expected_inserted_entry_rows=2,
            expected_quarantine_rows=1,
            apply=True,
        )

    assert _sha256(db_path) == original_sha


def test_agent31_prod_wrapper_requires_reviewed_proof_for_existing_entry_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path, existing_safe_entry=True)
    safe_rows, api_entries, quarantine_rows = _write_agent31_inputs(tmp_path)
    original_sha = _sha256(db_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionAgent31ApplyError, match="reviewed drift proof"):
        apply_storeb_api_order_entries_from_agent31_production_safe(
            db_path=db_path,
            safe_rows_path=safe_rows,
            api_entries_path=api_entries,
            quarantine_rows_path=quarantine_rows,
            output_root=tmp_path / "blocked_existing",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_safe_order_rows=1,
            expected_candidate_entry_rows=1,
            expected_inserted_entry_rows=0,
            expected_quarantine_rows=1,
            apply=True,
        )

    proof = tmp_path / "reviewed_drift_proof.md"
    proof.write_text("reviewed: entry-safe already exists before Agent 31 wrapper apply\n", encoding="utf-8")
    summary = apply_storeb_api_order_entries_from_agent31_production_safe(
        db_path=db_path,
        safe_rows_path=safe_rows,
        api_entries_path=api_entries,
        quarantine_rows_path=quarantine_rows,
        output_root=tmp_path / "allowed_existing",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_safe_order_rows=1,
        expected_candidate_entry_rows=1,
        expected_inserted_entry_rows=0,
        expected_quarantine_rows=1,
        reviewed_drift_proof=proof,
        apply=True,
    )

    assert summary["apply"]["applied"] is True
    assert summary["materializer_summary"]["apply"]["inserted_entry_rows"] == 0
    assert summary["materializer_summary"]["apply"]["skipped_existing_entry_rows"] == 1
    assert summary["reviewed_drift_proof"] == str(proof.resolve())
