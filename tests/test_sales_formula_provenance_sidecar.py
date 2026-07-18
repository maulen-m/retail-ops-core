from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.build_sales_formula_provenance_sidecar import build_sidecar, validate_manifest
from scripts.apply_sales_formula_provenance_sidecar import SidecarApplyError, promote_sidecar


HEADERS = [
    "№ заказа",
    "Дата поступления заказа",
    "Артикул",
    "Сумма",
    "Количество",
    "Стоимость доставки для продавца",
    "Статус",
    "Причина отмены",
    "mapping_source_store_code",
    "mapped_sku_key",
    "mapped_size",
]


def _init_db(path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY,
                order_id TEXT,
                order_date TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                store_code TEXT,
                quantity REAL,
                sell_price_kzt REAL,
                delivery_fee REAL,
                cogs REAL,
                net_rev REAL,
                profit REAL,
                status TEXT,
                return_flag INTEGER,
                source_file TEXT,
                source_entry_id TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT
            );
            CREATE VIEW view_sales_line_truth AS
            SELECT order_id, date(order_date) AS sale_date, store_code,
                   sku_key, sku_id, my_size, quantity AS units, net_rev AS net_rev_kzt,
                   cogs AS cogs_kzt, profit AS profit_kzt, 'legacy' AS cogs_source,
                   'sales_fact_v2' AS source_table,
                   sku_key AS source_sku_key, sku_id AS source_sku_id,
                   quantity AS source_units, net_rev AS source_net_rev_kzt,
                   cogs AS source_cogs_kzt, profit AS source_profit_kzt
            FROM sales_fact_v2
            WHERE status='DELIVERED' AND COALESCE(return_flag,0)=0;
            """
        )
        conn.executemany(
            """
            INSERT INTO sales_fact_v2 (
                sale_id, order_id, order_date, sku_key, sku_id, my_size, store_code,
                quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit,
                status, return_flag, source_file, source_entry_id, kaspi_article,
                line_identity_key
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _source_row(order_id: str, *, gross: str, quantity: str, fee: str, row_article: str = "ART") -> dict[str, str]:
    return {
        "№ заказа": order_id,
        "Дата поступления заказа": "31.12.2025",
        "Артикул": row_article,
        "Сумма": gross,
        "Количество": quantity,
        "Стоимость доставки для продавца": fee,
        "Статус": "Завершен",
        "Причина отмены": "",
        "mapping_source_store_code": "ACMEWEAR",
        "mapped_sku_key": "SKU_A",
        "mapped_size": "M",
    }


def _db_row(order_id: str, *, sale_id: int = 1, order_date: str = "2025-12-31", quantity: float = 1, price: float = 10000, fee: float = 1000, net: float = 10000) -> tuple:
    return (
        sale_id,
        order_id,
        order_date,
        "SKU_A",
        "SKU_A_M",
        "M",
        "ACMEWEAR",
        quantity,
        price,
        fee,
        2000,
        net,
        net - 2000,
        "DELIVERED",
        0,
        "OCEAN_DROP_ANCHOR",
        None,
        None,
        None,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_is_byte_deterministic_and_validator_passes(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O1")])
    _write_csv(source, [_source_row("O1", gross="10000", quantity="1", fee="1000")])
    out = tmp_path / "out"
    first = build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 1), output_dir=out)
    first_bytes = {name: (out / name).read_bytes() for name in ("manifest.json", "formula_provenance.jsonl", "excluded.jsonl")}
    second = build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 1), output_dir=out)
    assert first == second
    assert first_bytes == {name: (out / name).read_bytes() for name in first_bytes}
    assert first["proof_count"] == 1
    assert first["repair_candidate_count"] == 1
    assert validate_manifest(out / "manifest.json")["ok"] is True


def test_repeated_order_fee_is_allocated_once_after_collapsing_source_rows(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O2", quantity=2, price=10000, fee=2000, net=20000)])
    _write_csv(
        source,
        [
            _source_row("O2", gross="10000", quantity="1", fee="1000", row_article="A"),
            _source_row("O2", gross="10000", quantity="1", fee="1000", row_article="B"),
        ],
    )
    out = tmp_path / "out"
    manifest = build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 1), output_dir=out)
    proof = json.loads((out / "formula_provenance.jsonl").read_text().strip())
    assert manifest["proof_count"] == 1
    assert proof["seller_delivery_fee_total_kzt"] == "1000.00"
    assert proof["seller_delivery_fee_unit_kzt"] == "500.00"
    assert proof["source_locators"] == ["csv:row:2", "csv:row:3"]


def test_conflicting_same_rank_fee_excludes_complete_order(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O3", quantity=2, price=10000, fee=2000, net=20000)])
    _write_csv(
        source,
        [
            _source_row("O3", gross="10000", quantity="1", fee="1000"),
            _source_row("O3", gross="10000", quantity="1", fee="1200"),
        ],
    )
    out = tmp_path / "out"
    manifest = build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 1), output_dir=out)
    excluded = json.loads((out / "excluded.jsonl").read_text().strip())
    assert manifest["proof_count"] == 0
    assert "conflicting seller delivery fee" in excluded["reasons"][0]


def test_view_exclusion_never_reenters_from_source_packet(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O4")])
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sales_fact_v2 SET return_flag=1 WHERE order_id='O4'")
    _write_csv(source, [_source_row("O4", gross="10000", quantity="1", fee="1000")])
    out = tmp_path / "out"
    manifest = build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 1), output_dir=out)
    assert manifest["selected_view_order_count"] == 0
    assert manifest["proof_count"] == 0


def test_validator_fails_on_source_and_proof_drift(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O5")])
    _write_csv(source, [_source_row("O5", gross="10000", quantity="1", fee="1000")])
    out = tmp_path / "out"
    build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 1), output_dir=out)
    source.write_text(source.read_text() + "\n", encoding="utf-8")
    proof_path = out / "formula_provenance.jsonl"
    proof_path.write_text(proof_path.read_text() + "{}\n", encoding="utf-8")
    report = validate_manifest(out / "manifest.json")
    assert report["ok"] is False
    assert "SOURCE_HASH_DRIFT" in report["errors"]
    assert "PROOF_HASH_MISMATCH" in report["errors"]


def test_missing_stored_delivery_fee_is_a_repair_candidate(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    row = list(_db_row("O8"))
    row[9] = None
    _init_db(db, [tuple(row)])
    _write_csv(source, [_source_row("O8", gross="10000", quantity="1", fee="1000")])
    out = tmp_path / "out"
    manifest = build_sidecar(
        db_path=db,
        ocean_csv_path=source,
        since=date(2025, 1, 1),
        until=date(2026, 1, 1),
        output_dir=out,
    )
    proof = json.loads((out / "formula_provenance.jsonl").read_text().strip())
    assert manifest["proof_count"] == 1
    assert proof["stored_delivery_fee_total_kzt"] is None
    assert proof["repair_required"] is True


def test_source_date_mismatch_excludes_order(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O9", order_date="2025-12-30")])
    _write_csv(source, [_source_row("O9", gross="10000", quantity="1", fee="1000")])
    out = tmp_path / "out"
    manifest = build_sidecar(
        db_path=db,
        ocean_csv_path=source,
        since=date(2025, 1, 1),
        until=date(2026, 1, 1),
        output_dir=out,
    )
    excluded = json.loads((out / "excluded.jsonl").read_text().strip())
    assert manifest["proof_count"] == 0
    assert "source and DB order date mismatch" in excluded["reasons"][0]


def test_numeric_zero_stored_fee_is_not_collapsed_to_null(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O12", price=3716, fee=0, net=3716)])
    _write_csv(source, [_source_row("O12", gross="3716", quantity="1", fee="0")])
    out = tmp_path / "out"
    build_sidecar(
        db_path=db,
        ocean_csv_path=source,
        since=date(2025, 1, 1),
        until=date(2026, 1, 1),
        output_dir=out,
    )
    proof = json.loads((out / "formula_provenance.jsonl").read_text().strip())
    assert proof["stored_delivery_fee_total_kzt"] == "0.00"
    assert proof["seller_delivery_fee_total_kzt"] == "0.00"
    assert proof["canonical_line_net_rev_kzt"] == "3153.95"


def test_noncompleted_source_status_excludes_order(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(db, [_db_row("O13")])
    row = _source_row("O13", gross="10000", quantity="1", fee="1000")
    row["Статус"] = "Отменен"
    row["Причина отмены"] = "Покупатель отказался"
    _write_csv(source, [row])
    out = tmp_path / "out"
    build_sidecar(
        db_path=db,
        ocean_csv_path=source,
        since=date(2025, 1, 1),
        until=date(2026, 1, 1),
        output_dir=out,
    )
    excluded = json.loads((out / "excluded.jsonl").read_text().strip())
    assert "source lifecycle status is not completed" in excluded["reasons"][0]


def test_effective_vat_boundary_changes_canonical_target(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    source = tmp_path / "ocean.csv"
    _init_db(
        db,
        [
            _db_row("O6", sale_id=1, order_date="2025-12-31"),
            _db_row("O7", sale_id=2, order_date="2026-01-01"),
        ],
    )
    rows = [
        _source_row("O6", gross="10000", quantity="1", fee="1000"),
        {**_source_row("O7", gross="10000", quantity="1", fee="1000"), "Дата поступления заказа": "01.01.2026"},
    ]
    _write_csv(source, rows)
    out = tmp_path / "out"
    build_sidecar(db_path=db, ocean_csv_path=source, since=date(2025, 1, 1), until=date(2026, 1, 2), output_dir=out)
    proofs = [json.loads(line) for line in (out / "formula_provenance.jsonl").read_text().splitlines()]
    amounts = {row["order_id"]: row["canonical_line_net_rev_kzt"] for row in proofs}
    assert Decimal(amounts["O6"]) > Decimal(amounts["O7"])


def test_copied_db_promotion_is_gated_target_only_and_read_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_db = tmp_path / "source.db"
    copied_db = tmp_path / "copied.db"
    source = tmp_path / "ocean.csv"
    _init_db(
        source_db,
        [
            _db_row("O10", sale_id=1, fee=1000, net=10000),
            _db_row("O11", sale_id=2, fee=1000, net=10000),
        ],
    )
    _write_csv(source, [_source_row("O10", gross="10000", quantity="1", fee="1000")])
    out = tmp_path / "out"
    manifest = build_sidecar(
        db_path=source_db,
        ocean_csv_path=source,
        since=date(2025, 1, 1),
        until=date(2026, 1, 1),
        output_dir=out,
    )
    shutil.copy2(source_db, copied_db)
    pre_sha = _sha256(copied_db)
    dry = promote_sidecar(
        manifest_path=out / "manifest.json",
        db_path=copied_db,
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_db_sha256=pre_sha,
        apply=False,
    )
    assert dry["status"] == "PASS"
    assert _sha256(copied_db) == pre_sha

    with __import__("pytest").raises(SidecarApplyError, match="requires AB_ALLOW"):
        promote_sidecar(
            manifest_path=out / "manifest.json",
            db_path=copied_db,
            expected_manifest_sha256=manifest["manifest_sha256"],
            expected_db_sha256=pre_sha,
            apply=True,
            backup_dir=tmp_path / "backups",
        )
    monkeypatch.setenv("AB_ALLOW_COPIED_DB_SALES_FORMULA_REPAIR", "1")
    applied = promote_sidecar(
        manifest_path=out / "manifest.json",
        db_path=copied_db,
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_db_sha256=pre_sha,
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert applied["status"] == "PASS"
    assert applied["target_count"] == 1
    assert applied["non_target_sales_fact_v2_sha256_before"] == applied[
        "non_target_sales_fact_v2_sha256_after"
    ]
    assert applied["backup_sha256"] == pre_sha
    with sqlite3.connect(copied_db) as conn:
        target = conn.execute(
            "SELECT delivery_fee, net_rev, cogs, profit FROM sales_fact_v2 WHERE sale_id=1"
        ).fetchone()
        untouched = conn.execute(
            "SELECT delivery_fee, net_rev, cogs, profit FROM sales_fact_v2 WHERE sale_id=2"
        ).fetchone()
    assert target == (1000.0, 7517.5, 2000.0, 5517.5)
    assert untouched == (1000.0, 10000.0, 2000.0, 8000.0)
