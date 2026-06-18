from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_internal_cannibalization_guard import (
    build_internal_cannibalization_guard_report,
)


LEAD_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "lead_store",
    "allowed_follower_stores",
    "effective_from",
    "source_artifact",
    "status",
    "owner_decision_id",
    "notes",
]


def _write_sqlite(path: Path, rows: list[dict[str, object]]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE repricer_items (
            fetched_at TEXT,
            store_id INTEGER,
            store_name TEXT,
            row_id INTEGER,
            merchant_sku TEXT,
            kaspi_sku TEXT,
            merchant_title TEXT,
            link TEXT,
            price INTEGER,
            min_price INTEGER,
            max_price INTEGER,
            active INTEGER,
            is_available INTEGER,
            raw_json TEXT
        )
        """
    )
    for row in rows:
        conn.execute(
            """
            INSERT INTO repricer_items VALUES (
                :fetched_at,
                :store_id,
                :store_name,
                :row_id,
                :merchant_sku,
                :kaspi_sku,
                :merchant_title,
                :link,
                :price,
                :min_price,
                :max_price,
                :active,
                :is_available,
                :raw_json
            )
            """,
            row,
        )
    conn.commit()
    conn.close()


def _item(
    *,
    store_id: int = 30000001,
    store_name: str = "UNIVERSAL",
    merchant_sku: str = "SKU1_XL",
    link: str = "https://kaspi.kz/shop/p/example-1",
    price: int = 10000,
    not_competitors: list[str] | None = None,
    competitors: list[dict[str, object]] | None = None,
    active: int = 1,
    is_available: int = 1,
) -> dict[str, object]:
    return {
        "fetched_at": "2026-06-18T12:00:00+05:00",
        "store_id": store_id,
        "store_name": store_name,
        "row_id": store_id,
        "merchant_sku": merchant_sku,
        "kaspi_sku": "KSP1",
        "merchant_title": f"{merchant_sku} title",
        "link": link,
        "price": price,
        "min_price": price,
        "max_price": 14990,
        "active": active,
        "is_available": is_available,
        "raw_json": json.dumps(
            {
                "not_competitors": not_competitors or [],
                "competitors": competitors or [],
            }
        ),
    }


def _write_config(path: Path, *, sqlite_path: Path, lead_map_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "INTERNAL_CANNIBALIZATION_GUARD_V1",
                "gate_id": "G-WA-01",
                "owner_decision_id": "OD-011",
                "repricer_sqlite_path": str(sqlite_path),
                "lead_store_map_csv": str(lead_map_path),
                "max_source_age_days": 7,
                "managed_pricing_store_ids": {
                    "UNIVERSAL": 30000001,
                    "STORE-B": 30000002,
                },
                "own_store_ids": {
                    "UNIVERSAL": 30000001,
                    "STORE-B": 30000002,
                    "11KZ": 30290083,
                },
                "own_store_name_tokens": ["Universal", "STORE-B", "ИП STORE-B", "11KZ"],
                "active_map_statuses": ["ACTIVE"],
                "armed_when_no_active_lead_rows": True,
                "required_lead_store_columns": LEAD_COLUMNS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_lead_map(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEAD_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _lead_row(**overrides: str) -> dict[str, str]:
    row = {
        "tranche_id": "T1",
        "sku_key": "SKU1",
        "size": "XL",
        "lead_store": "UNIVERSAL",
        "allowed_follower_stores": "",
        "effective_from": "2026-06-18T12:00:00+05:00",
        "source_artifact": "exports/validation/example.csv",
        "status": "ACTIVE",
        "owner_decision_id": "OD-011",
        "notes": "test",
    }
    row.update(overrides)
    return row


def test_header_only_lead_map_is_armed_when_own_store_exclusions_pass(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "repricer.sqlite"
    lead_map = tmp_path / "lead.csv"
    config = tmp_path / "config.json"
    _write_sqlite(
        sqlite_path,
        [
            _item(
                not_competitors=["30000002"],
                competitors=[{"mid": "30000002", "name": "ИП STORE-B", "price": 9900}],
            )
        ],
    )
    _write_lead_map(lead_map, [])
    _write_config(config, sqlite_path=sqlite_path, lead_map_path=lead_map)

    report = build_internal_cannibalization_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:05:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["ok"] is True
    assert report["first_liquidation_lead_map_required"] is True
    assert report["own_store_not_excluded_count"] == 0


def test_missing_own_store_not_competitor_is_red(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "repricer.sqlite"
    lead_map = tmp_path / "lead.csv"
    config = tmp_path / "config.json"
    _write_sqlite(
        sqlite_path,
        [
            _item(
                price=10000,
                not_competitors=[],
                competitors=[{"mid": "30000002", "name": "ИП STORE-B", "price": 9000}],
            )
        ],
    )
    _write_lead_map(lead_map, [])
    _write_config(config, sqlite_path=sqlite_path, lead_map_path=lead_map)

    report = build_internal_cannibalization_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:05:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["own_store_not_excluded_count"] == 1
    assert report["own_store_undercut_violation_count"] == 1


def test_active_lead_map_clean_promotes_green(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "repricer.sqlite"
    lead_map = tmp_path / "lead.csv"
    config = tmp_path / "config.json"
    _write_sqlite(
        sqlite_path,
        [
            _item(
                store_id=30000001,
                store_name="UNIVERSAL",
                merchant_sku="SKU1_XL",
                not_competitors=["30000002"],
                competitors=[{"mid": "30000002", "name": "ИП STORE-B", "price": 9999}],
            ),
            _item(
                store_id=30000002,
                store_name="STORE-B",
                merchant_sku="SKU1_XL",
                price=9999,
                active=1,
                is_available=0,
                not_competitors=["30000001"],
                competitors=[{"mid": "30000001", "name": "Universal", "price": 10000}],
            ),
        ],
    )
    _write_lead_map(lead_map, [_lead_row()])
    _write_config(config, sqlite_path=sqlite_path, lead_map_path=lead_map)

    report = build_internal_cannibalization_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:05:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["active_lead_map_rows"] == 1
    assert report["lead_map_error_count"] == 0


def test_non_lead_visible_store_for_active_map_is_red(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "repricer.sqlite"
    lead_map = tmp_path / "lead.csv"
    config = tmp_path / "config.json"
    _write_sqlite(
        sqlite_path,
        [
            _item(
                store_id=30000001,
                store_name="UNIVERSAL",
                merchant_sku="SKU1_XL",
                not_competitors=["30000002"],
                competitors=[{"mid": "30000002", "name": "ИП STORE-B", "price": 9999}],
            ),
            _item(
                store_id=30000002,
                store_name="STORE-B",
                merchant_sku="SKU1_XL",
                price=9999,
                not_competitors=["30000001"],
                competitors=[{"mid": "30000001", "name": "Universal", "price": 10000}],
            ),
        ],
    )
    _write_lead_map(lead_map, [_lead_row()])
    _write_config(config, sqlite_path=sqlite_path, lead_map_path=lead_map)

    report = build_internal_cannibalization_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:05:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["lead_map_error_count"] == 1


def test_duplicate_active_lead_map_rows_are_red(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "repricer.sqlite"
    lead_map = tmp_path / "lead.csv"
    config = tmp_path / "config.json"
    _write_sqlite(
        sqlite_path,
        [
            _item(
                not_competitors=["30000002"],
                competitors=[{"mid": "30000002", "name": "ИП STORE-B", "price": 9900}],
            )
        ],
    )
    _write_lead_map(lead_map, [_lead_row(tranche_id="T1"), _lead_row(tranche_id="T2")])
    _write_config(config, sqlite_path=sqlite_path, lead_map_path=lead_map)

    report = build_internal_cannibalization_guard_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T12:05:00+05:00",
    )

    assert report["gate"] == "RED"
    assert "duplicate active sku_key/size" in report["lead_map_errors"][0]["errors"]
