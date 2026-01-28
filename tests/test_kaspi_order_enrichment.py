import os
import sqlite3
from pathlib import Path

from core.sync.kaspi_order_enrichment import enrich_orders
from scripts.migrate_019_kaspi_enrichment import migrate


class FakeResponse:
    def __init__(self, success=True, data=None):
        self.success = success
        self.data = data or {}
        self.error = None


class FakeClient:
    def __init__(self, store_code):
        self.store_code = store_code
        self.calls = []

    def get_order_entries(self, order_code):
        self.calls.append(("entries", order_code))
        return FakeResponse(
            True,
            {
                "data": [
                    {
                        "id": "ENTRY1",
                        "attributes": {"quantity": 2, "price": 1000, "totalPrice": 2000},
                        "relationships": {
                            "order": {"data": {"id": order_code}},
                            "product": {"data": {"id": "PROD1"}},
                        },
                    }
                ]
            },
        )

    def _request(self, method, path, params=None):
        self.calls.append((method, path))
        return FakeResponse(True, {"data": {"id": path.split("/")[-1], "attributes": {}}})


def _init_orders_db(db_path: Path):
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
                created_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, status_updated_at, actual_shipment_date, planned_shipment_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ORD1", "UNIVERSAL", "2026-01-20", None, None, "2026-01-20"),
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
            "SELECT entry_id, order_id, quantity, unit_price_kzt FROM fact_order_entries_kaspi"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("ENTRY1", "ORD1", 2, 1000.0)]
