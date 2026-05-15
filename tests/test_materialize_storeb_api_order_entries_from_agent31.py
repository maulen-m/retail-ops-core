import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.materialize_storeb_api_order_entries_from_agent31 import (
    MaterializationError,
    materialize_storeb_api_order_entries,
)


def _make_db(path: Path) -> None:
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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_quarantine(path: Path, order_ids: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["order_id", "store_code", "reason"])
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
        "target_quantity": "5",
        "source_kind": "kaspi_api_readonly_order_entry",
        "source_name": "KASPI_API_READONLY_STOREB_EXACT_ORDER_IDS",
    }


def test_only_sku_id_size_mapped_rows_are_inserted_and_quarantine_remains(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "temp.sqlite"
    _make_db(db_path)
    preview_path = tmp_path / "safe.jsonl"
    api_path = tmp_path / "api.jsonl"
    quarantine_path = tmp_path / "quarantine.csv"
    _write_jsonl(
        preview_path,
        [
            _safe_preview("O-SAFE"),
            {
                **_safe_preview("O-BLOCKED", entry_ids="entry-blocked"),
                "evidence_status": "API_ITEM_ENTRY_FOUND_SIZE_REQUIRED",
                "recommended_temp_apply": False,
            },
        ],
    )
    _write_jsonl(api_path, [_api_entry("O-SAFE"), _api_entry("O-BLOCKED", entry_id="entry-blocked")])
    _write_quarantine(quarantine_path, ["O-BLOCKED"])

    monkeypatch.setenv("ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY", "1")
    summary = materialize_storeb_api_order_entries(
        db_path=db_path,
        safe_rows_path=preview_path,
        api_entries_path=api_path,
        quarantine_rows_path=quarantine_path,
        output_root=tmp_path / "out",
        apply=True,
        expected_safe_order_rows=1,
        expected_quarantine_rows=1,
    )

    assert summary["safe_order_rows"] == 1
    assert summary["quarantine_rows"] == 1
    assert summary["apply"]["inserted_entry_rows"] == 1
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT order_id FROM fact_order_entries_kaspi ORDER BY order_id").fetchall()
    assert rows == [("O-SAFE",)]


def test_header_only_target_identity_fields_are_not_materialized(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "temp.sqlite"
    _make_db(db_path)
    preview_path = tmp_path / "safe.jsonl"
    api_path = tmp_path / "api.jsonl"
    quarantine_path = tmp_path / "quarantine.csv"
    _write_jsonl(preview_path, [_safe_preview("O-SAFE")])
    _write_jsonl(api_path, [_api_entry("O-SAFE")])
    _write_quarantine(quarantine_path, [])

    monkeypatch.setenv("ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY", "1")
    materialize_storeb_api_order_entries(
        db_path=db_path,
        safe_rows_path=preview_path,
        api_entries_path=api_path,
        quarantine_rows_path=quarantine_path,
        output_root=tmp_path / "out",
        apply=True,
        expected_safe_order_rows=1,
        expected_quarantine_rows=0,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT offer_id, product_id, quantity, total_price_kzt, raw_json FROM fact_order_entries_kaspi"
        ).fetchone()

    assert row[0] == "API_ARTICLE_L"
    assert row[1] == "api-product"
    assert row[2] == 1
    assert row[3] == 9900
    raw_payload = json.loads(row[4])
    raw_text = json.dumps(raw_payload, sort_keys=True)
    assert raw_payload["article_map_sku_id"] == "ARTICLE_MAP_SKU_L"
    assert "HEADER_ONLY_WRONG" not in raw_text
    assert "target_sku_id" not in raw_text
    assert "target_sku_key" not in raw_text


def test_materializer_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "temp.sqlite"
    _make_db(db_path)
    preview_path = tmp_path / "safe.jsonl"
    api_path = tmp_path / "api.jsonl"
    quarantine_path = tmp_path / "quarantine.csv"
    _write_jsonl(preview_path, [_safe_preview("O-SAFE")])
    _write_jsonl(api_path, [_api_entry("O-SAFE")])
    _write_quarantine(quarantine_path, [])

    monkeypatch.setenv("ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY", "1")
    first = materialize_storeb_api_order_entries(
        db_path=db_path,
        safe_rows_path=preview_path,
        api_entries_path=api_path,
        quarantine_rows_path=quarantine_path,
        output_root=tmp_path / "out1",
        apply=True,
        expected_safe_order_rows=1,
        expected_quarantine_rows=0,
    )
    second = materialize_storeb_api_order_entries(
        db_path=db_path,
        safe_rows_path=preview_path,
        api_entries_path=api_path,
        quarantine_rows_path=quarantine_path,
        output_root=tmp_path / "out2",
        apply=True,
        expected_safe_order_rows=1,
        expected_quarantine_rows=0,
    )

    assert first["apply"]["inserted_entry_rows"] == 1
    assert second["apply"]["inserted_entry_rows"] == 0
    assert second["apply"]["skipped_existing_entry_rows"] == 1


def test_apply_requires_env_gate_and_apply_flag(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "temp.sqlite"
    _make_db(db_path)
    preview_path = tmp_path / "safe.jsonl"
    api_path = tmp_path / "api.jsonl"
    quarantine_path = tmp_path / "quarantine.csv"
    _write_jsonl(preview_path, [_safe_preview("O-SAFE")])
    _write_jsonl(api_path, [_api_entry("O-SAFE")])
    _write_quarantine(quarantine_path, [])

    dry_run = materialize_storeb_api_order_entries(
        db_path=db_path,
        safe_rows_path=preview_path,
        api_entries_path=api_path,
        quarantine_rows_path=quarantine_path,
        output_root=tmp_path / "dry",
        apply=False,
        expected_safe_order_rows=1,
        expected_quarantine_rows=0,
    )
    assert dry_run["apply"]["applied"] is False
    assert dry_run["apply"]["would_insert_entry_rows"] == 1

    monkeypatch.delenv("ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY", raising=False)
    with pytest.raises(MaterializationError, match="ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY=1"):
        materialize_storeb_api_order_entries(
            db_path=db_path,
            safe_rows_path=preview_path,
            api_entries_path=api_path,
            quarantine_rows_path=quarantine_path,
            output_root=tmp_path / "blocked",
            apply=True,
            expected_safe_order_rows=1,
            expected_quarantine_rows=0,
        )
