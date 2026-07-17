import json
import os
import sqlite3
from pathlib import Path

import pytest

from core.sync.kaspi_order_enrichment import enrich_orders
from scripts.migrate_019_kaspi_enrichment import migrate


class FakeResponse:
    def __init__(self, success=True, data=None):
        self.success = success
        self.data = data or {}
        self.error = None


class FakeClient:
    def __init__(self, store_code, entries=None, entry_detail=None):
        self.store_code = store_code
        self.calls = []
        self.entries = entries
        self.entry_detail = entry_detail or {
            "id": "ENTRY1",
            "attributes": {
                "unitType": "PCS",
                "minAllowedWeight": 1.2,
                "weight": 0.7,
                "entryNumber": 5,
                "basePrice": 900,
                "deliveryCost": 120,
                "category": {"code": "CAT1", "title": "Category 1"},
            },
            "relationships": {"deliveryPointOfService": {"data": {"id": "POS_DEL"}}},
        }
        self.entry_product = {"id": "PROD1", "attributes": {"name": "MP"}}
        self.masterproduct = {"id": "PROD1", "attributes": {"name": "MP"}}
        self.merchantproduct = {"id": "MERCH1", "attributes": {"code": "SKU1"}}
        self.point_of_service = {"id": "POS1", "attributes": {"displayName": "POS1"}}

    def _clone_entries(self, order_code):
        entries = self.entries or [
            {
                "id": "ENTRY1",
                "attributes": {
                    "quantity": 2,
                    "price": 1000,
                    "totalPrice": 2000,
                    "offerId": "SKU1",
                },
                "relationships": {
                    "order": {"data": {"id": order_code}},
                    "product": {"data": {"id": "PROD1"}},
                    "pointOfService": {"data": {"id": "POS1"}},
                },
            }
        ]
        cloned = json.loads(json.dumps(entries))
        for entry in cloned:
            rel = entry.setdefault("relationships", {})
            rel.setdefault("order", {"data": {"id": order_code}})
        return cloned

    def get_order_entries(self, order_code):
        self.calls.append(("entries", order_code))
        return FakeResponse(True, {"data": self._clone_entries(order_code)})

    def get_order_entry(self, entry_id):
        self.calls.append(("entry_detail", entry_id))
        payload = json.loads(json.dumps(self.entry_detail))
        payload["id"] = entry_id
        return FakeResponse(True, {"data": payload})

    def get_order_entry_product(self, entry_id):
        self.calls.append(("entry_product", entry_id))
        payload = json.loads(json.dumps(self.entry_product))
        payload["id"] = self.entry_product.get("id")
        return FakeResponse(True, {"data": payload})

    def get_masterproduct(self, masterproduct_id):
        self.calls.append(("masterproduct", masterproduct_id))
        payload = json.loads(json.dumps(self.masterproduct))
        payload["id"] = masterproduct_id
        return FakeResponse(True, {"data": payload})

    def get_merchantproduct(self, masterproduct_id):
        self.calls.append(("merchantproduct", masterproduct_id))
        payload = json.loads(json.dumps(self.merchantproduct))
        payload["id"] = self.merchantproduct.get("id")
        return FakeResponse(True, {"data": payload})

    def get_point_of_service(self, pos_id):
        self.calls.append(("point_of_service", pos_id))
        payload = json.loads(json.dumps(self.point_of_service))
        payload["id"] = pos_id
        return FakeResponse(True, {"data": payload})

    def _request(self, method, path, params=None):
        self.calls.append((method, path))
        return FakeResponse(True, {"data": {"id": path.split("/")[-1], "attributes": {}}})


def _init_orders_db(db_path: Path, rows: list[dict] | None = None):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                status_updated_at TEXT,
                actual_shipment_date TEXT,
                planned_shipment_date TEXT,
                created_at TEXT,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                signature_required INTEGER,
                pre_order INTEGER,
                courier_transmission_date TEXT,
                delivery_mode TEXT,
                returned_to_warehouse INTEGER
            );
            """
        )
        if rows is None:
            rows = [
                {
                    "order_id": "ORD1",
                    "store_code": "UNIVERSAL",
                    "status_updated_at": "2026-01-20",
                    "actual_shipment_date": None,
                    "planned_shipment_date": None,
                    "created_at": "2026-01-20",
                    "kaspi_status": "NEW",
                    "kaspi_status_detail": "APPROVED_BY_BANK",
                    "signature_required": 0,
                    "pre_order": 0,
                    "courier_transmission_date": None,
                    "delivery_mode": "DELIVERY",
                    "returned_to_warehouse": 0,
                }
            ]
        for row in rows:
            conn.execute(
                """
                INSERT INTO fact_orders_kaspi (
                    order_id,
                    store_code,
                    status_updated_at,
                    actual_shipment_date,
                    planned_shipment_date,
                    created_at,
                    kaspi_status,
                    kaspi_status_detail,
                    signature_required,
                    pre_order,
                    courier_transmission_date,
                    delivery_mode,
                    returned_to_warehouse
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["order_id"],
                    row["store_code"],
                    row["status_updated_at"],
                    row["actual_shipment_date"],
                    row["planned_shipment_date"],
                    row["created_at"],
                    row["kaspi_status"],
                    row["kaspi_status_detail"],
                    row["signature_required"],
                    row["pre_order"],
                    row["courier_transmission_date"],
                    row["delivery_mode"],
                    row["returned_to_warehouse"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_enrichment_respects_flag(tmp_path):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: false\n", encoding="utf-8")

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_enrichment_flag_defaults_off(tmp_path):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "missing.yaml"

    result = enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=False,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    assert result.get("enabled") is False
    assert result.get("inserted") == 0


def test_enrichment_fail_open_does_not_break_sync(tmp_path):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    class FailingClient(FakeClient):
        def get_order_entries(self, order_code):
            raise RuntimeError("boom")

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    result = enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=False,
        config_path=config_path,
        client_factory=lambda store: FailingClient(store),
    )

    assert result.get("enabled") is True
    assert result.get("inserted") == 0


def test_enrichment_inserts_entries(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT entry_id, order_id, quantity, unit_price_kzt, updated_at FROM fact_order_entries_kaspi"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("ENTRY1", "ORD1", 2, 1000.0, "2026-01-20")]


def test_enrichment_uses_created_at_when_status_timestamp_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(
        db_path,
        rows=[
            {
                "order_id": "ORD_FALLBACK",
                "store_code": "UNIVERSAL",
                "status_updated_at": None,
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-21 14:15:00",
                "kaspi_status": "ARCHIVE",
                "kaspi_status_detail": "COMPLETED",
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            }
        ],
    )

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-21",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT updated_at FROM fact_order_entries_kaspi WHERE order_id='ORD_FALLBACK'"
        ).fetchone()
    finally:
        conn.close()

    assert row == ("2026-01-21",)


def test_enrichment_clamps_updated_at_to_until_for_historical_backfill(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(
        db_path,
        rows=[
            {
                "order_id": "ORD_CLAMP",
                "store_code": "UNIVERSAL",
                "status_updated_at": "2026-01-22 09:00:00",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-20 08:00:00",
                "kaspi_status": "ARCHIVE",
                "kaspi_status_detail": "COMPLETED",
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            }
        ],
    )

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT updated_at FROM fact_order_entries_kaspi WHERE order_id='ORD_CLAMP'"
        ).fetchone()
    finally:
        conn.close()

    assert row == ("2026-01-21",)


def test_enrichment_selection_filters_by_stage(tmp_path):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(
        db_path,
        rows=[
            {
                "order_id": "IN_APPROVED",
                "store_code": "UNIVERSAL",
                "status_updated_at": "2026-01-20",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-20",
                "kaspi_status": "NEW",
                "kaspi_status_detail": "APPROVED_BY_BANK",
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            },
            {
                "order_id": "IN_CANCELLED",
                "store_code": "UNIVERSAL",
                "status_updated_at": "2026-01-20",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-20",
                "kaspi_status": "KASPI_DELIVERY",
                "kaspi_status_detail": "CANCELLED",
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            },
            {
                "order_id": "EX_SIGN_REQUIRED",
                "store_code": "UNIVERSAL",
                "status_updated_at": "2026-01-20",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-20",
                "kaspi_status": "SIGN_REQUIRED",
                "kaspi_status_detail": "APPROVED_BY_BANK",
                "signature_required": 1,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            },
            {
                "order_id": "EX_UNKNOWN",
                "store_code": "UNIVERSAL",
                "status_updated_at": "2026-01-20",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-20",
                "kaspi_status": None,
                "kaspi_status_detail": None,
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": None,
                "returned_to_warehouse": 0,
            },
            {
                "order_id": "EX_OUTSIDE_RANGE",
                "store_code": "UNIVERSAL",
                "status_updated_at": "2026-01-10",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": "2026-01-10",
                "kaspi_status": "NEW",
                "kaspi_status_detail": "APPROVED_BY_BANK",
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            },
        ],
    )

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    client = FakeClient("UNIVERSAL")
    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=False,
        config_path=config_path,
        client_factory=lambda store: client,
    )

    entry_calls = [call for call in client.calls if call[0] == "entries"]
    assert sorted(entry_calls) == [("entries", "IN_APPROVED"), ("entries", "IN_CANCELLED")]


def test_enrichment_entry_detail_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text(
        "enabled: true\nfetch_entries: true\nfetch_entry_detail: true\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT
                unit_type,
                min_allowed_weight,
                weight_kg,
                entry_number,
                category_code,
                category_title,
                delivery_cost_kzt,
                base_price_kzt,
                point_of_service_id,
                delivery_point_of_service_id
            FROM fact_order_entries_kaspi
            """
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "PCS",
        1.2,
        0.7,
        5,
        "CAT1",
        "Category 1",
        120.0,
        900.0,
        "POS1",
        "POS_DEL",
    )


def test_enrichment_cache_hits(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text(
        "\n".join(
            [
                "enabled: true",
                "fetch_entries: true",
                "fetch_masterproduct: true",
                "fetch_merchantproduct: true",
                "fetch_point_of_service: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    entries = [
        {
            "id": "ENTRY1",
            "attributes": {"quantity": 1, "price": 1000, "totalPrice": 1000, "offerId": "SKU1"},
            "relationships": {
                "order": {"data": {"id": "ORD1"}},
                "product": {"data": {"id": "PROD1"}},
                "pointOfService": {"data": {"id": "POS1"}},
            },
        },
        {
            "id": "ENTRY2",
            "attributes": {"quantity": 1, "price": 1200, "totalPrice": 1200, "offerId": "SKU1"},
            "relationships": {
                "order": {"data": {"id": "ORD1"}},
                "product": {"data": {"id": "PROD1"}},
                "pointOfService": {"data": {"id": "POS1"}},
            },
        },
    ]

    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")
    client = FakeClient("UNIVERSAL", entries=entries)

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: client,
    )

    master_calls = [call for call in client.calls if call[0] == "masterproduct"]
    merchant_calls = [call for call in client.calls if call[0] == "merchantproduct"]
    pos_calls = [call for call in client.calls if call[0] == "point_of_service"]

    assert master_calls == [("masterproduct", "PROD1")]
    assert merchant_calls == [("merchantproduct", "PROD1")]
    assert pos_calls == [("point_of_service", "POS1")]


def test_enrichment_idempotent_inserts(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )
    enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_enrichment_allowlist_skips_store(tmp_path):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)

    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text(
        "enabled: true\nstores_allowlist:\n  - ACMEWEAR\n",
        encoding="utf-8",
    )

    created = {"count": 0}

    def _factory(store):
        created["count"] += 1
        return FakeClient(store)

    result = enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=False,
        config_path=config_path,
        client_factory=_factory,
    )

    assert result.get("enabled") is True
    assert result.get("inserted") == 0
    assert created["count"] == 0


def test_strict_enrichment_success_proves_api_and_db_readback(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)
    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")
    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    result = enrich_orders(
        db_path=db_path,
        store_code="UNIVERSAL",
        since="2026-01-19",
        until="2026-01-21",
        apply=True,
        require_complete=True,
        config_path=config_path,
        client_factory=lambda store: FakeClient(store),
    )

    assert result["selected_order_count"] == 1
    assert result["fetched_order_count"] == 1
    assert result["expected_entry_count"] == 1
    assert result["readback_entry_count"] == 1
    assert result["failure_count"] == 0


def test_strict_enrichment_partial_api_failure_rolls_back_store(tmp_path, monkeypatch):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(
        db_path,
        rows=[
            {
                "order_id": order_id,
                "store_code": "UNIVERSAL",
                "status_updated_at": f"2026-01-{day}",
                "actual_shipment_date": None,
                "planned_shipment_date": None,
                "created_at": f"2026-01-{day}",
                "kaspi_status": "NEW",
                "kaspi_status_detail": "APPROVED_BY_BANK",
                "signature_required": 0,
                "pre_order": 0,
                "courier_transmission_date": None,
                "delivery_mode": "DELIVERY",
                "returned_to_warehouse": 0,
            }
            for order_id, day in (("ORD_OK", "20"), ("ORD_FAIL", "21"))
        ],
    )
    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")
    monkeypatch.setenv("ENABLE_KASPI_ENRICHMENT", "1")

    class PartialClient(FakeClient):
        def get_order_entries(self, order_code):
            if order_code == "ORD_FAIL":
                raise RuntimeError("simulated API failure")
            return super().get_order_entries(order_code)

    with pytest.raises(RuntimeError, match="strict Kaspi entry enrichment incomplete"):
        enrich_orders(
            db_path=db_path,
            store_code="UNIVERSAL",
            since="2026-01-19",
            until="2026-01-21",
            apply=True,
            require_complete=True,
            config_path=config_path,
            client_factory=lambda store: PartialClient(store),
        )

    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0] == 0


def test_strict_enrichment_rejects_zero_entry_success_response(tmp_path):
    db_path = tmp_path / "enrich.db"
    sqlite3.connect(str(db_path)).close()
    migrate(db_path)
    _init_orders_db(db_path)
    config_path = tmp_path / "kaspi_enrichment.yaml"
    config_path.write_text("enabled: true\nfetch_entries: true\n", encoding="utf-8")

    class EmptyClient(FakeClient):
        def get_order_entries(self, order_code):
            return FakeResponse(True, {"data": []})

    with pytest.raises(RuntimeError, match="api_zero_entries"):
        enrich_orders(
            db_path=db_path,
            store_code="UNIVERSAL",
            since="2026-01-19",
            until="2026-01-21",
            apply=False,
            require_complete=True,
            config_path=config_path,
            client_factory=lambda store: EmptyClient(store),
        )
