from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.apply_kaspi_order_entry_sidecar import (
    WRITE_ENV_GATE,
    OrderEntrySidecarError,
    apply_order_entry_sidecar,
    load_validated_sidecar,
)
from scripts.export_api_orders import write_order_entry_sidecar


TARGET_DATE = "2026-07-15"
TARGET_LABEL = "15.07.2026"
STORES = ["ACMEWEAR", "UNIVERSAL"]


def _entry(entry_id: str, order_id: str, *, quantity: float = 1.0) -> dict:
    return {
        "id": entry_id,
        "type": "orderentries",
        "attributes": {
            "quantity": quantity,
            "price": 1000.0,
            "totalPrice": 1000.0 * quantity,
            "offerId": "SKU-1",
            "offer": {"code": "SKU-1", "name": "Safe offer"},
        },
        "relationships": {
            "order": {"data": {"id": order_id}},
            "product": {"data": {"id": "PRODUCT-1"}},
            "pointOfService": {"data": {"id": "POS-1"}},
        },
    }


def _write_sidecar(path: Path, records: list[dict]) -> dict:
    return write_order_entry_sidecar(
        records,
        path,
        target_date=TARGET_LABEL,
        stores=STORES,
        state="KASPI_DELIVERY",
        days=5,
        include_overdue=True,
        include_archive=False,
    )


def _make_db(path: Path, orders: list[tuple[str, str]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                status_updated_at TEXT,
                actual_shipment_date TEXT,
                planned_shipment_date TEXT,
                created_at TEXT
            );
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                product_id TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                unit_type TEXT,
                min_allowed_weight REAL,
                weight_kg REAL,
                entry_number INTEGER,
                category_code TEXT,
                category_title TEXT,
                delivery_cost_kzt REAL,
                base_price_kzt REAL,
                point_of_service_id TEXT,
                delivery_point_of_service_id TEXT,
                raw_json TEXT,
                updated_at TEXT
            );
            """
        )
        for order_id, store_code in orders:
            conn.execute(
                """
                INSERT INTO fact_orders_kaspi (
                    order_id, store_code, status_updated_at,
                    actual_shipment_date, planned_shipment_date, created_at
                ) VALUES (?, ?, '2026-07-15T10:00:00Z', NULL, '2026-07-15', '2026-07-15')
                """,
                (order_id, store_code),
            )


def test_sidecar_writer_and_loader_pin_scope_counts_and_hash(tmp_path: Path) -> None:
    sidecar = tmp_path / "sidecar.json"
    summary = _write_sidecar(
        sidecar,
        [
            {
                "order_id": "O-1",
                "store_code": "ACMEWEAR",
                "planned_date": TARGET_LABEL,
                "entries": [_entry("E-1", "O-1")],
            }
        ],
    )

    payload, entries = load_validated_sidecar(
        sidecar,
        expected_payload_sha256=summary["payload_sha256"],
        expected_target_date=TARGET_DATE,
        expected_store_roster=STORES,
    )

    assert payload["order_count"] == 1
    assert payload["entry_count"] == 1
    assert entries[0]["order_id"] == "O-1"
    assert "customer" not in sidecar.read_text(encoding="utf-8").lower()


def test_sidecar_loader_rejects_tamper_date_roster_and_identity(tmp_path: Path) -> None:
    sidecar = tmp_path / "sidecar.json"
    summary = _write_sidecar(
        sidecar,
        [
            {
                "order_id": "O-1",
                "store_code": "ACMEWEAR",
                "planned_date": TARGET_LABEL,
                "entries": [_entry("E-1", "O-1")],
            }
        ],
    )
    envelope = json.loads(sidecar.read_text(encoding="utf-8"))
    envelope["payload"]["orders"][0]["entries"][0]["attributes"]["quantity"] = 2
    sidecar.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(OrderEntrySidecarError, match="payload hash mismatch"):
        load_validated_sidecar(
            sidecar,
            expected_payload_sha256=summary["payload_sha256"],
            expected_target_date=TARGET_DATE,
            expected_store_roster=STORES,
        )


def test_sidecar_apply_is_atomic_idempotent_and_non_target_preserving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    sidecar = tmp_path / "sidecar.json"
    report_path = tmp_path / "receipt.json"
    _make_db(db_path, [("O-1", "ACMEWEAR"), ("O-2", "UNIVERSAL")])
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, product_id, offer_id, quantity,
                unit_price_kzt, total_price_kzt, point_of_service_id, raw_json, updated_at
            ) VALUES ('OLD', 'OLD-ORDER', 'UNIVERSAL', 'P', 'S', 1, 1, 1, 'P', '{}', '2026-07-01')
            """
        )
    summary = _write_sidecar(
        sidecar,
        [
            {
                "order_id": "O-1",
                "store_code": "ACMEWEAR",
                "planned_date": TARGET_LABEL,
                "entries": [_entry("E-1", "O-1")],
            },
            {
                "order_id": "O-2",
                "store_code": "UNIVERSAL",
                "planned_date": TARGET_LABEL,
                "entries": [_entry("E-2", "O-2")],
            },
        ],
    )
    monkeypatch.setenv(WRITE_ENV_GATE, "1")

    first = apply_order_entry_sidecar(
        sidecar_path=sidecar,
        expected_payload_sha256=summary["payload_sha256"],
        target_date=TARGET_DATE,
        db_path=db_path,
        report_path=report_path,
        expected_store_roster=STORES,
        apply=True,
    )
    second = apply_order_entry_sidecar(
        sidecar_path=sidecar,
        expected_payload_sha256=summary["payload_sha256"],
        target_date=TARGET_DATE,
        db_path=db_path,
        expected_store_roster=STORES,
        apply=True,
    )

    assert first["inserted_entry_count"] == 2
    assert first["non_target_hash_before"] == first["non_target_hash_after"]
    assert first["readback_complete"] is True
    assert second["inserted_entry_count"] == 0
    assert second["preexisting_entry_count"] == 2
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0] == 3
        assert conn.execute(
            "SELECT raw_json FROM fact_order_entries_kaspi WHERE entry_id='OLD'"
        ).fetchone()[0] == "{}"


def test_sidecar_apply_rejects_existing_drift_and_rolls_back_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    sidecar = tmp_path / "sidecar.json"
    _make_db(db_path, [("O-1", "ACMEWEAR"), ("O-2", "UNIVERSAL")])
    summary = _write_sidecar(
        sidecar,
        [
            {
                "order_id": "O-1",
                "store_code": "ACMEWEAR",
                "planned_date": TARGET_LABEL,
                "entries": [_entry("E-1", "O-1")],
            },
            {
                "order_id": "O-2",
                "store_code": "UNIVERSAL",
                "planned_date": TARGET_LABEL,
                "entries": [_entry("E-2", "O-2")],
            },
        ],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_second_entry
            BEFORE INSERT ON fact_order_entries_kaspi
            WHEN NEW.entry_id='E-2'
            BEGIN SELECT RAISE(ABORT, 'forced rollback'); END;
            """
        )
    monkeypatch.setenv(WRITE_ENV_GATE, "1")

    with pytest.raises(sqlite3.IntegrityError, match="forced rollback"):
        apply_order_entry_sidecar(
            sidecar_path=sidecar,
            expected_payload_sha256=summary["payload_sha256"],
            target_date=TARGET_DATE,
            db_path=db_path,
            expected_store_roster=STORES,
            apply=True,
        )
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0] == 0
