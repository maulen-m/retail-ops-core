from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.apply_exact_kaspi_api_order_entries as exact_entries
from scripts.apply_exact_kaspi_api_order_entries import (
    PROD_WRITE_ENV_GATE,
    WRITE_ENV_GATE,
    ExactKaspiApiOrderEntryError,
    apply_exact_kaspi_api_order_entries,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_db(path: Path, targets: list[tuple[str, str]]) -> None:
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
            CREATE TABLE sales_fact_v2 (
                order_id TEXT,
                store_code TEXT
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
                raw_json TEXT,
                updated_at TEXT,
                point_of_service_id TEXT
            );
            """
        )
        for order_id, store_code in targets:
            conn.execute(
                """
                INSERT INTO fact_orders_kaspi (
                    order_id, store_code, status_updated_at,
                    actual_shipment_date, planned_shipment_date, created_at
                ) VALUES (?, ?, '2026-06-15 12:00:00', '2026-06-14 18:00:00',
                          '2026-06-14', '2026-06-14 10:00:00')
                """,
                (order_id, store_code),
            )
            conn.execute(
                "INSERT INTO sales_fact_v2 (order_id, store_code) VALUES (?, ?)",
                (order_id, store_code),
            )


def _write_targets(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["order_id", "store_code"])
        writer.writeheader()
        for order_id, store_code in rows:
            writer.writerow({"order_id": order_id, "store_code": store_code})


def _write_expected(path: Path, rows: list[tuple[str, str, str, float, float]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["order_id", "store_code", "entry_rows", "entry_ids", "offer_ids", "quantity", "total_price"],
        )
        writer.writeheader()
        for order_id, store_code, entry_id, quantity, total_price in rows:
            writer.writerow(
                {
                    "order_id": order_id,
                    "store_code": store_code,
                    "entry_rows": 1,
                    "entry_ids": entry_id,
                    "offer_ids": "",
                    "quantity": quantity,
                    "total_price": total_price,
                }
            )


def _api_entry(entry_id: str, *, product_id: str = "PRODUCT", quantity: float = 1.0, total_price: float = 16900.0) -> dict:
    return {
        "id": entry_id,
        "type": "orderentries",
        "attributes": {
            "quantity": quantity,
            "price": 0,
            "totalPrice": total_price,
            "offerId": "",
        },
        "relationships": {
            "product": {"data": {"id": product_id}},
            "pointOfService": {"data": {"id": "POS-1"}},
        },
    }


class FakeClient:
    calls: list[tuple[str, str]] = []
    responses: dict[tuple[str, str], list[dict]] = {}

    def __init__(self, store_code: str):
        self.store_code = store_code

    def get_order_entries(self, order_id: str) -> SimpleNamespace:
        self.calls.append((self.store_code, order_id))
        return SimpleNamespace(success=True, data={"data": self.responses.get((self.store_code, order_id), [])})


def _client_factory(entries: dict[tuple[str, str], list[dict]]) -> type[FakeClient]:
    class BoundFakeClient(FakeClient):
        calls: list[tuple[str, str]] = []
        responses = entries

    return BoundFakeClient


def test_exact_api_order_entry_dry_run_fetches_only_targets_and_writes_no_raw_json(tmp_path: Path) -> None:
    targets = [("957756737", "ACMEWEAR"), ("959124715", "ACMEWEAR")]
    db_path = tmp_path / "app.db"
    target_csv = tmp_path / "targets.csv"
    expected_csv = tmp_path / "expected.csv"
    _make_db(db_path, targets)
    _write_targets(target_csv, targets)
    _write_expected(
        expected_csv,
        [
            ("957756737", "ACMEWEAR", "OTU3NzU2NzM3IyMw", 1.0, 16900.0),
            ("959124715", "ACMEWEAR", "OTU5MTI0NzE1IyMw", 1.0, 16900.0),
        ],
    )
    original_sha = _sha256(db_path)
    fake_client = _client_factory(
        {
            ("ACMEWEAR", "957756737"): [_api_entry("OTU3NzU2NzM3IyMw", product_id="MTM0NTQ3NDc3")],
            ("ACMEWEAR", "959124715"): [_api_entry("OTU5MTI0NzE1IyMw", product_id="MTM0NTQ3NDg2")],
            ("ACMEWEAR", "NON_TARGET"): [_api_entry("NON_TARGET_ENTRY")],
        }
    )

    summary = apply_exact_kaspi_api_order_entries(
        db_path=db_path,
        target_order_csv=target_csv,
        expected_entry_summary_csv=expected_csv,
        output_root=tmp_path / "dry",
        store_code="ACMEWEAR",
        as_of="2026-06-15",
        expected_pre_sha256=original_sha,
        expected_target_order_rows=2,
        expected_fetched_entry_rows=2,
        expected_inserted_entry_rows=2,
        apply=False,
        load_dotenv=False,
        client_factory=fake_client,
    )

    assert summary["apply"]["applied"] is False
    assert summary["fetched_entry_rows"] == 2
    assert summary["would_insert_entry_rows"] == 2
    assert summary["entries"][0]["updated_at"] == "2026-06-15"
    assert fake_client.calls == [("ACMEWEAR", "957756737"), ("ACMEWEAR", "959124715")]
    assert _sha256(db_path) == original_sha
    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert "raw_json" not in json.dumps(persisted)
    assert "TOKEN" not in json.dumps(persisted).upper()


def test_exact_api_order_entry_production_apply_requires_dual_env_and_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = [("957756737", "ACMEWEAR")]
    db_path = tmp_path / "app.db"
    target_csv = tmp_path / "targets.csv"
    _make_db(db_path, targets)
    _write_targets(target_csv, targets)
    original_sha = _sha256(db_path)
    fake_client = _client_factory({("ACMEWEAR", "957756737"): [_api_entry("entry-1")]})
    monkeypatch.setattr(exact_entries, "DEFAULT_DB", db_path.resolve())

    monkeypatch.delenv(WRITE_ENV_GATE, raising=False)
    monkeypatch.delenv(PROD_WRITE_ENV_GATE, raising=False)
    with pytest.raises(ExactKaspiApiOrderEntryError, match=f"{WRITE_ENV_GATE}=1"):
        apply_exact_kaspi_api_order_entries(
            db_path=db_path,
            target_order_csv=target_csv,
            output_root=tmp_path / "blocked_write_env",
            store_code="ACMEWEAR",
            as_of="2026-06-15",
            expected_pre_sha256=original_sha,
            expected_target_order_rows=1,
            expected_fetched_entry_rows=1,
            expected_inserted_entry_rows=1,
            backup_dir=tmp_path / "backups",
            apply=True,
            load_dotenv=False,
            client_factory=fake_client,
        )

    monkeypatch.setenv(WRITE_ENV_GATE, "1")
    with pytest.raises(ExactKaspiApiOrderEntryError, match=f"{PROD_WRITE_ENV_GATE}=1"):
        apply_exact_kaspi_api_order_entries(
            db_path=db_path,
            target_order_csv=target_csv,
            output_root=tmp_path / "blocked_prod_env",
            store_code="ACMEWEAR",
            as_of="2026-06-15",
            expected_pre_sha256=original_sha,
            expected_target_order_rows=1,
            expected_fetched_entry_rows=1,
            expected_inserted_entry_rows=1,
            backup_dir=tmp_path / "backups",
            apply=True,
            load_dotenv=False,
            client_factory=fake_client,
        )

    monkeypatch.setenv(PROD_WRITE_ENV_GATE, "1")
    with pytest.raises(ExactKaspiApiOrderEntryError, match="pre-write SHA mismatch"):
        apply_exact_kaspi_api_order_entries(
            db_path=db_path,
            target_order_csv=target_csv,
            output_root=tmp_path / "blocked_sha",
            store_code="ACMEWEAR",
            as_of="2026-06-15",
            expected_pre_sha256="0" * 64,
            expected_target_order_rows=1,
            expected_fetched_entry_rows=1,
            expected_inserted_entry_rows=1,
            backup_dir=tmp_path / "backups",
            apply=True,
            load_dotenv=False,
            client_factory=fake_client,
        )
    assert _sha256(db_path) == original_sha


def test_exact_api_order_entry_apply_inserts_only_target_entries_with_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = [("957756737", "ACMEWEAR"), ("959124715", "ACMEWEAR")]
    db_path = tmp_path / "app.db"
    target_csv = tmp_path / "targets.csv"
    _make_db(db_path, targets)
    _write_targets(target_csv, targets)
    original_sha = _sha256(db_path)
    fake_client = _client_factory(
        {
            ("ACMEWEAR", "957756737"): [_api_entry("entry-1", product_id="P1")],
            ("ACMEWEAR", "959124715"): [_api_entry("entry-2", product_id="P2")],
            ("ACMEWEAR", "NOT_TARGET"): [_api_entry("entry-extra", product_id="P3")],
        }
    )
    monkeypatch.setattr(exact_entries, "DEFAULT_DB", db_path.resolve())
    monkeypatch.setenv(WRITE_ENV_GATE, "1")
    monkeypatch.setenv(PROD_WRITE_ENV_GATE, "1")

    summary = apply_exact_kaspi_api_order_entries(
        db_path=db_path,
        target_order_csv=target_csv,
        output_root=tmp_path / "apply",
        store_code="ACMEWEAR",
        as_of="2026-06-15",
        expected_pre_sha256=original_sha,
        expected_target_order_rows=2,
        expected_fetched_entry_rows=2,
        expected_inserted_entry_rows=2,
        backup_dir=tmp_path / "backups",
        apply=True,
        load_dotenv=False,
        client_factory=fake_client,
    )

    assert summary["apply"]["applied"] is True
    assert summary["inserted_entry_rows"] == 2
    assert Path(summary["backup_path"]).exists()
    assert summary["integrity_check"]["after"] == "ok"
    assert "cp " in summary["rollback"]["restore_command"]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT entry_id, order_id, store_code, updated_at FROM fact_order_entries_kaspi ORDER BY entry_id"
        ).fetchall()
    assert rows == [
        ("entry-1", "957756737", "ACMEWEAR", "2026-06-15"),
        ("entry-2", "959124715", "ACMEWEAR", "2026-06-15"),
    ]


def test_exact_api_order_entry_stops_on_zero_entries_and_existing_target_rows(tmp_path: Path) -> None:
    targets = [("957756737", "ACMEWEAR")]
    db_path = tmp_path / "app.db"
    target_csv = tmp_path / "targets.csv"
    _make_db(db_path, targets)
    _write_targets(target_csv, targets)
    original_sha = _sha256(db_path)
    fake_client = _client_factory({("ACMEWEAR", "957756737"): []})

    with pytest.raises(ExactKaspiApiOrderEntryError, match="zero target entries"):
        apply_exact_kaspi_api_order_entries(
            db_path=db_path,
            target_order_csv=target_csv,
            output_root=tmp_path / "zero",
            store_code="ACMEWEAR",
            as_of="2026-06-15",
            expected_pre_sha256=original_sha,
            expected_target_order_rows=1,
            expected_fetched_entry_rows=1,
            expected_inserted_entry_rows=1,
            apply=False,
            load_dotenv=False,
            client_factory=fake_client,
        )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, raw_json, updated_at
            ) VALUES ('already-there', '957756737', 'ACMEWEAR', '{}', '2026-06-15')
            """
        )
    fake_client = _client_factory({("ACMEWEAR", "957756737"): [_api_entry("entry-1")]})
    with pytest.raises(ExactKaspiApiOrderEntryError, match="already has order-entry rows"):
        apply_exact_kaspi_api_order_entries(
            db_path=db_path,
            target_order_csv=target_csv,
            output_root=tmp_path / "existing",
            store_code="ACMEWEAR",
            as_of="2026-06-15",
            expected_target_order_rows=1,
            expected_fetched_entry_rows=1,
            expected_inserted_entry_rows=1,
            apply=False,
            load_dotenv=False,
            client_factory=fake_client,
        )
