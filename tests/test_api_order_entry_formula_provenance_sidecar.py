from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.build_api_order_entry_formula_provenance_sidecar import (
    ApiEntryFormulaProofError,
    build_sidecar,
    validate_manifest,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_entry(
    *,
    entry_id: str,
    offer: str,
    quantity: int,
    total: int,
    merchant_id: str,
    wrapped: bool,
) -> str:
    pos = base64.b64encode(f"{merchant_id}_PP1".encode()).decode().rstrip("=")
    entry = {
            "id": entry_id,
            "attributes": {
                "offer": {"code": offer},
                "quantity": quantity,
                "totalPrice": total,
            },
            "relationships": {"deliveryPointOfService": {"data": {"id": pos}}},
        }
    return json.dumps(
        {"entry": entry, "recovery_source": {"kind": "fixture"}} if wrapped else entry,
        separators=(",", ":"),
        sort_keys=True,
    )


def _init_source(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY, order_id TEXT, store_code TEXT,
                product_id TEXT, offer_id TEXT, quantity REAL,
                unit_price_kzt REAL, total_price_kzt REAL, raw_json TEXT,
                entry_number INTEGER
            );
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                quantity REAL, unit_price_kzt REAL,
                delivery_cost_for_seller REAL, created_at TEXT,
                status_updated_at TEXT, kaspi_status TEXT, internal_status TEXT,
                source TEXT, source_file TEXT, line_identity_key TEXT
            );
            CREATE TABLE order_status_event (
                event_id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                stage_code TEXT, event_ts TEXT, source TEXT,
                source_status_change_at TEXT, source_run_id TEXT,
                source_row_hash TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                id INTEGER PRIMARY KEY, store_code TEXT, merchant_id TEXT,
                kaspi_article TEXT, sku_key TEXT, sku_id TEXT,
                active_flag INTEGER, source TEXT
            );
            CREATE TABLE dim_sku_size (
                sku_key TEXT, sku_id TEXT, my_size TEXT, active_flag INTEGER
            );
            """
        )
        entries = [
            ("ENTRY0", "PRODUCT0", "OFFER0", 7990, 0, "SKU_ROM", "SKU_ROM_24", "24"),
            ("ENTRY1", "PRODUCT1", "OFFER1", 9500, 1, "SKU_PRINT", "SKU_PRINT_S", "S"),
        ]
        for entry_id, product, offer, total, ordinal, sku_key, sku_id, size in entries:
            conn.execute(
                """
                INSERT INTO fact_order_entries_kaspi VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    entry_id,
                    "978080963",
                    "UNIVERSAL",
                    product,
                    offer,
                    1,
                    total,
                    total,
                    _raw_entry(
                        entry_id=entry_id,
                        offer=offer,
                        quantity=1,
                        total=total,
                        merchant_id="30000001",
                        wrapped=ordinal == 0,
                    ),
                    ordinal,
                ),
            )
            conn.execute(
                "INSERT INTO dim_kaspi_article_map VALUES (?,?,?,?,?,?,?,?)",
                (ordinal + 1, "UNIVERSAL", "30000001", offer, sku_key, sku_id, 1, "FIXTURE"),
            )
            conn.execute(
                "INSERT INTO dim_sku_size VALUES (?,?,?,1)",
                (sku_key, sku_id, size),
            )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi VALUES
            (10,'978080963','UNIVERSAL',1,17490,1507,'2026-06-27',
             '2026-06-30','ARCHIVE','COMPLETED','API','ACTIVE_ORDERS','LEGACY_HEADER')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi VALUES
            (11,'978080963','UNIVERSAL',1,9500,NULL,'2026-06-27',
             NULL,'KASPI_DELIVERY','ACCEPTED','API','ACTIVE_ORDERS','LEGACY_LINE')
            """
        )
        conn.execute(
            """
            INSERT INTO order_status_event VALUES
            (20,'978080963','UNIVERSAL','COMPLETED','2026-06-30',
             'WEBUI_STATUS_LEDGER_SCOPED','2026-06-30','run','source-hash')
            """
        )


def _init_copied(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY, order_id TEXT, order_date TEXT,
                store_code TEXT, sku_key TEXT, sku_id TEXT, my_size TEXT,
                quantity REAL, sell_price_kzt REAL, delivery_fee REAL,
                net_rev REAL, cogs REAL, profit REAL, status TEXT,
                return_flag INTEGER, source_file TEXT, source_entry_id TEXT,
                kaspi_article TEXT, line_identity_key TEXT
            );
            INSERT INTO sales_fact_v2 VALUES
            (1,'978080963','2026-06-28','UNIVERSAL','SKU_ROM','SKU_ROM_24','24',
             1,7990,NULL,NULL,NULL,NULL,'DELIVERED',0,'repair','ENTRY0','OFFER0','ENTRY:ENTRY0');
            INSERT INTO sales_fact_v2 VALUES
            (2,'978080963','2026-06-28','UNIVERSAL','SKU_PRINT','SKU_PRINT_S','S',
             1,9500,0,8063.125,NULL,NULL,'DELIVERED',0,'crm','ENTRY1','OFFER1','ENTRY:ENTRY1');
            CREATE VIEW view_sales_line_truth AS
            SELECT order_id, date(order_date) AS sale_date, store_code,
                   sku_key, sku_id, my_size, quantity AS units,
                   COALESCE(net_rev,0) AS net_rev_kzt,
                   'sales_fact_v2' AS source_table,
                   sku_key AS source_sku_key, sku_id AS source_sku_id,
                   quantity AS source_units, COALESCE(net_rev,0) AS source_net_rev_kzt
            FROM sales_fact_v2
            WHERE status='DELIVERED' AND COALESCE(return_flag,0)=0;
            """
        )


def _build(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    out = tmp_path / "out"
    _init_source(source)
    _init_copied(copied)
    manifest = build_sidecar(
        source_db_path=source,
        copied_db_path=copied,
        order_id="978080963",
        store_code="UNIVERSAL",
        merchant_id="30000001",
        expected_entry_count=2,
        expected_source_db_sha256=_sha(source),
        expected_copied_db_sha256=_sha(copied),
        output_dir=out,
    )
    return source, copied, out, manifest


def _safe_api_header(path: Path, *, creation_date: str = "2026-01-12") -> str:
    creation_ms = int(
        datetime.fromisoformat(creation_date)
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )
    payload = {
        "schema_version": "kaspi_api_order_header_safe_evidence_v1",
        "source_kind": "FIRST_PARTY_KASPI_ORDER_API_GET",
        "captured_at": "2026-07-16T09:50:00+05:00",
        "store_code": "UNIVERSAL",
        "merchant_id": "30000001",
        "order_id": "978080963",
        "entry_count": 2,
        "raw_order_json_sha256": "a" * 64,
        "raw_entries_json_sha256": "b" * 64,
        "customer_fields_excluded": True,
        "attributes": {
            "code": "978080963",
            "completionDate": creation_ms + 86_400_000,
            "creationDate": creation_ms,
            "deliveryCost": 0,
            "deliveryCostForSeller": 1507,
            "deliveryMode": "DELIVERY_LOCAL",
            "paymentMode": "PREPAID",
            "preOrder": False,
            "state": "ARCHIVE",
            "status": "COMPLETED",
            "totalPrice": 17490,
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return _sha(path)


def test_build_is_deterministic_complete_and_conserves_fee(tmp_path: Path) -> None:
    source, copied, out, first = _build(tmp_path)
    before = {name: (out / name).read_bytes() for name in ("manifest.json", "formula_provenance.jsonl", "excluded.jsonl")}
    second = build_sidecar(
        source_db_path=source,
        copied_db_path=copied,
        order_id="978080963",
        store_code="UNIVERSAL",
        merchant_id="30000001",
        expected_entry_count=2,
        expected_source_db_sha256=_sha(source),
        expected_copied_db_sha256=_sha(copied),
        output_dir=out,
    )
    assert first == second
    assert before == {name: (out / name).read_bytes() for name in before}
    proof = json.loads((out / "formula_provenance.jsonl").read_text())
    assert proof["source_entry_count"] == 2
    assert proof["terminal_effective_date"] == "2026-06-30"
    assert proof["gross_order_total_kzt"] == "17490.00"
    assert proof["seller_delivery_fee_order_total_kzt"] == "1507.00"
    assert sum(float(row["seller_delivery_fee_line_kzt"]) for row in proof["line_proofs"]) == 1507.0
    assert {row["selected_row_preimage"]["sale_id"] for row in proof["line_proofs"]} == {1, 2}
    assert proof["cash_evidence_used_as_formula_proof"] is False
    assert proof["production_apply_authorized"] is False
    assert validate_manifest(out / "manifest.json")["ok"] is True


def test_output_does_not_expose_raw_json_or_customer_fields(tmp_path: Path) -> None:
    _, _, out, _ = _build(tmp_path)
    combined = b"".join(path.read_bytes() for path in out.iterdir())
    assert b"raw_json\"" not in combined
    assert b"customer" not in combined.lower()
    assert b"phone" not in combined.lower()


def test_safe_api_header_supports_explicit_precutover_provisional_formula_proof(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    out = tmp_path / "out"
    header = tmp_path / "safe_header.json"
    _init_source(source)
    _init_copied(copied)
    with sqlite3.connect(source) as conn:
        conn.execute(
            "UPDATE fact_order_entries_kaspi SET unit_price_kzt=0 WHERE entry_id='ENTRY0'"
        )
        conn.execute("UPDATE fact_orders_kaspi SET delivery_cost_for_seller=NULL")
    header_sha = _safe_api_header(header)
    manifest = build_sidecar(
        source_db_path=source,
        copied_db_path=copied,
        order_id="978080963",
        store_code="UNIVERSAL",
        merchant_id="30000001",
        expected_entry_count=2,
        expected_source_db_sha256=_sha(source),
        expected_copied_db_sha256=_sha(copied),
        api_order_header_evidence_path=header,
        expected_api_order_header_evidence_sha256=header_sha,
        allow_precutover_creation_date_fallback=True,
        output_dir=out,
    )
    proof = json.loads((out / "formula_provenance.jsonl").read_text())
    assert manifest["provisional_economic_date"] is True
    assert manifest["decision_grade_date_authorized"] is False
    assert proof["terminal_date_semantics"] == "PROVISIONAL_SOURCE_DATE_NOT_STATUS_CHANGE"
    assert proof["publication_binding_authorized"] is False
    assert proof["order_header_evidence"]["customer_fields_excluded"] is True
    assert proof["line_proofs"][0]["unit_sell_price_kzt"] == "7990.00"
    assert validate_manifest(out / "manifest.json")["ok"] is True


def test_safe_api_header_uses_first_party_completion_date_as_terminal_proof(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    out = tmp_path / "out"
    header = tmp_path / "safe_header.json"
    _init_source(source)
    _init_copied(copied)
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE fact_orders_kaspi SET delivery_cost_for_seller=NULL")
    header_sha = _safe_api_header(header)
    manifest = build_sidecar(
        source_db_path=source,
        copied_db_path=copied,
        order_id="978080963",
        store_code="UNIVERSAL",
        merchant_id="30000001",
        expected_entry_count=2,
        api_order_header_evidence_path=header,
        expected_api_order_header_evidence_sha256=header_sha,
        output_dir=out,
    )
    proof = json.loads((out / "formula_provenance.jsonl").read_text())
    assert manifest["provisional_economic_date"] is False
    assert manifest["decision_grade_date_authorized"] is True
    assert proof["terminal_effective_date"] == "2026-01-13"
    assert proof["terminal_evidence"]["evidence_kind"] == "FIRST_PARTY_API_COMPLETION_DATE"
    assert proof["terminal_date_semantics"] == "STATUS_CHANGE_TIMESTAMP_PROVEN"
    assert validate_manifest(out / "manifest.json")["ok"] is True


def test_safe_api_header_hash_and_postcutover_fallback_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    header = tmp_path / "safe_header.json"
    _init_source(source)
    _init_copied(copied)
    header_sha = _safe_api_header(header, creation_date="2026-03-01")
    with pytest.raises(ApiEntryFormulaProofError, match="forbidden after"):
        build_sidecar(
            source_db_path=source,
            copied_db_path=copied,
            order_id="978080963",
            store_code="UNIVERSAL",
            merchant_id="30000001",
            expected_entry_count=2,
            api_order_header_evidence_path=header,
            expected_api_order_header_evidence_sha256=header_sha,
            allow_precutover_creation_date_fallback=True,
            output_dir=tmp_path / "out",
        )
    with pytest.raises(ApiEntryFormulaProofError, match="file/hash mismatch"):
        build_sidecar(
            source_db_path=source,
            copied_db_path=copied,
            order_id="978080963",
            store_code="UNIVERSAL",
            merchant_id="30000001",
            expected_entry_count=2,
            api_order_header_evidence_path=header,
            expected_api_order_header_evidence_sha256="0" * 64,
            allow_precutover_creation_date_fallback=True,
            output_dir=tmp_path / "out2",
        )


def test_missing_or_duplicate_seller_fee_fails_complete_order(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    _init_source(source)
    _init_copied(copied)
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE fact_orders_kaspi SET delivery_cost_for_seller=NULL")
    with pytest.raises(ApiEntryFormulaProofError, match="seller fee row count"):
        build_sidecar(
            source_db_path=source,
            copied_db_path=copied,
            order_id="978080963",
            store_code="UNIVERSAL",
            merchant_id="30000001",
            expected_entry_count=2,
            output_dir=tmp_path / "out",
        )


def test_selected_line_or_entry_count_mismatch_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    _init_source(source)
    _init_copied(copied)
    with sqlite3.connect(copied) as conn:
        conn.execute("DELETE FROM sales_fact_v2 WHERE source_entry_id='ENTRY1'")
    with pytest.raises(ApiEntryFormulaProofError, match="selected view line count"):
        build_sidecar(
            source_db_path=source,
            copied_db_path=copied,
            order_id="978080963",
            store_code="UNIVERSAL",
            merchant_id="30000001",
            expected_entry_count=2,
            output_dir=tmp_path / "out",
        )


def test_ambiguous_terminal_dates_and_later_negative_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    copied = tmp_path / "copied.db"
    _init_source(source)
    _init_copied(copied)
    with sqlite3.connect(source) as conn:
        conn.execute(
            "INSERT INTO order_status_event VALUES (21,'978080963','UNIVERSAL','COMPLETED','2026-07-01','WEBUI_STATUS_LEDGER_SCOPED','2026-07-01','run2','hash2')"
        )
    with pytest.raises(ApiEntryFormulaProofError, match="missing or ambiguous"):
        build_sidecar(
            source_db_path=source,
            copied_db_path=copied,
            order_id="978080963",
            store_code="UNIVERSAL",
            merchant_id="30000001",
            expected_entry_count=2,
            output_dir=tmp_path / "out1",
        )
    with sqlite3.connect(source) as conn:
        conn.execute("DELETE FROM order_status_event WHERE event_id=21")
        conn.execute(
            "INSERT INTO order_status_event VALUES (22,'978080963','UNIVERSAL','RETURNED','2026-07-02','API','2026-07-02','run3','hash3')"
        )
    with pytest.raises(ApiEntryFormulaProofError, match="negative lifecycle"):
        build_sidecar(
            source_db_path=source,
            copied_db_path=copied,
            order_id="978080963",
            store_code="UNIVERSAL",
            merchant_id="30000001",
            expected_entry_count=2,
            output_dir=tmp_path / "out2",
        )


def test_validator_detects_source_and_proof_drift(tmp_path: Path) -> None:
    source, _, out, _ = _build(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE fact_orders_kaspi SET source_file='changed' WHERE id=11")
    proof_path = out / "formula_provenance.jsonl"
    proof_path.write_bytes(proof_path.read_bytes() + b"{}\n")
    report = validate_manifest(out / "manifest.json")
    assert report["ok"] is False
    assert "SOURCE_DB_HASH_DRIFT" in report["errors"]
    assert "PROOF_FILE_HASH_MISMATCH" in report["errors"]
