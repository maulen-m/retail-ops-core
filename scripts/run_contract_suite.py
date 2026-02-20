#!/usr/bin/env python3
"""Run a deterministic contract suite on fixture DBs."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import validate_po_contract
from scripts import validate_po_dashboard_invariants
from scripts import download_waybills_api
from scripts import build_daily_waybills
from scripts import validate_transfer_ledger
from core.transfer_ledger import repository

FIXTURE_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
STAGECODE_TARGET_DATE = date(2026, 1, 27)

FIXTURE_TABLES: dict[str, set[str]] = {
    "po_contract": {"dim_store", "dim_sku", "dim_sku_size"},
    "po_dashboard_invariants": {"portfolio_active"},
    "stagecode_waybill": {"fact_orders_kaspi"},
    "transfer_ledger": {
        "transfer_ledger",
        "binance_c2c_orders",
        "binance_withdrawals",
        "binance_deposits",
        "binance_transfers",
        "binance_funding_balances",
        "exchanger_orders",
        "po_funding_allocations",
    },
}

STAGECODE_REQUIRED_COLUMNS = {
    "order_id",
    "store_code",
    "kaspi_offer_name",
    "sku_key",
    "sku_id",
    "quantity",
    "assigned_size",
    "my_size",
    "planned_shipment_date",
    "kaspi_status",
    "kaspi_status_detail",
    "internal_status",
    "signature_required",
    "courier_transmission_date",
    "pre_order",
    "waybill_url",
    "delivery_mode",
    "returned_to_warehouse",
    "actual_shipment_date",
    "courier_transmission_planning_date",
}


def list_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def list_columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def missing_tables(db_path: Path, required: Iterable[str]) -> list[str]:
    tables = list_tables(db_path)
    return sorted([name for name in required if name not in tables])


def _reset_db(path: Path) -> None:
    if path.exists():
        path.unlink()


def _init_po_contract_db(path: Path) -> None:
    _reset_db(path)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE dim_store (
                store_code TEXT PRIMARY KEY
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                model TEXT,
                product_type TEXT,
                base_cost_cny REAL,
                weight_kg REAL
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT,
                my_size TEXT
            );
            """
        )
        conn.execute("INSERT INTO dim_store (store_code) VALUES (?)", ("UNIVERSAL",))
        conn.execute(
            """
            INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("SKU_FIX", "FIX", "CL", 10.0, 1.0),
        )
        conn.execute(
            "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
            ("SKU_FIX_L", "SKU_FIX", "L"),
        )
        conn.commit()


def _init_stagecode_waybill_db(path: Path) -> None:
    _reset_db(path)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                quantity INTEGER,
                assigned_size TEXT,
                my_size TEXT,
                planned_shipment_date TEXT,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                signature_required INTEGER,
                courier_transmission_date TEXT,
                pre_order INTEGER,
                waybill_url TEXT,
                delivery_mode TEXT,
                returned_to_warehouse INTEGER,
                actual_shipment_date TEXT,
                courier_transmission_planning_date TEXT
            );
            """
        )
        rows = [
            (
                "1001",
                "UNIVERSAL",
                "Fixture Item",
                "SKU_FIX",
                "SKU_FIX_L",
                1,
                "L",
                "",
                "2026-01-27",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "READY",
                0,
                None,
                0,
                None,
                "DELIVERY",
                0,
                None,
                None,
            ),
            (
                "1002",
                "UNIVERSAL",
                "Fixture Item",
                "SKU_FIX",
                "SKU_FIX_L",
                1,
                "L",
                "",
                "2026-01-27",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "READY",
                1,
                None,
                0,
                None,
                "DELIVERY",
                0,
                None,
                None,
            ),
            (
                "1003",
                "UNIVERSAL",
                "Fixture Item",
                "SKU_FIX",
                "SKU_FIX_L",
                1,
                "L",
                "",
                "2026-01-27",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "READY",
                0,
                "2026-01-27",
                0,
                None,
                "DELIVERY",
                0,
                None,
                None,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_offer_name, sku_key, sku_id,
                quantity, assigned_size, my_size, planned_shipment_date,
                kaspi_status, kaspi_status_detail, internal_status,
                signature_required, courier_transmission_date, pre_order,
                waybill_url, delivery_mode, returned_to_warehouse,
                actual_shipment_date, courier_transmission_planning_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _init_po_dashboard_invariants_db(path: Path) -> None:
    _reset_db(path)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE portfolio_active (
                sku_key TEXT PRIMARY KEY,
                active_flag INTEGER DEFAULT 1
            );
            """
        )
        conn.executemany(
            "INSERT INTO portfolio_active (sku_key, active_flag) VALUES (?, 1)",
            [("SKU_FIX",), ("SKU_FIX_2",)],
        )
        conn.commit()


def _init_transfer_ledger_db(path: Path) -> None:
    _reset_db(path)
    repository.ensure_schema(path)

    exchanger_order_id = "EX-001"
    withdraw_id = "WD-001"
    address = "TABC1234567890XYZ"

    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            INSERT INTO exchanger_orders (
                exchanger_order_id, exchanger, order_id, status, direction,
                amount_usdt, amount_cny, rate_usdt_cny, deposit_address,
                receiver_account, message_id, message_date, subject
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exchanger_order_id,
                "ALFA",
                "ORDER-1",
                "COMPLETED",
                "SELL",
                100.0,
                0.0,
                7.1,
                address,
                "ACC-1",
                "MSG-1",
                "2026-01-12T10:00:00+00:00",
                "Fixture order",
            ),
        )
        conn.execute(
            """
            INSERT INTO binance_withdrawals (
                withdraw_id, tx_id, coin, network, amount, transaction_fee,
                address, apply_time, success_time, status, exchanger_order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                withdraw_id,
                "TX-1",
                "USDT",
                "TRC20",
                100.0,
                0.0,
                address,
                "2026-01-12T12:00:00+00:00",
                "2026-01-12T12:10:00+00:00",
                "COMPLETED",
                exchanger_order_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO transfer_ledger (
                entry_date, amount, currency, amount_kzt, fx_rate_to_kzt,
                fx_source, reference_type, reference_id, from_account, to_account, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-12",
                100.0,
                "USDT",
                50000.0,
                500.0,
                "FIXTURE",
                "BINANCE_WITHDRAWAL",
                withdraw_id,
                "BINANCE",
                "EXCHANGER",
                "fixture",
            ),
        )
        conn.execute(
            """
            INSERT INTO binance_c2c_orders (
                order_number, adv_no, trade_type, asset, fiat,
                fiat_amount, crypto_amount, unit_price, order_status, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "P2P-1",
                "ADV-1",
                "BUY",
                "USDT",
                "KZT",
                50000.0,
                100.0,
                500.0,
                "COMPLETED",
                "2026-01-12T08:00:00+00:00",
            ),
        )
        conn.executemany(
            """
            INSERT INTO binance_funding_balances (
                snapshot_time, asset, free, locked, total
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("2026-01-13T00:00:00+06:00", "USDT", 100.0, 0.0, 100.0),
                ("2026-01-14T00:00:00+06:00", "USDT", 100.0, 0.0, 100.0),
            ],
        )
        conn.commit()


def build_fixture_dbs(fixture: str, base_dir: Path) -> dict[str, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "po_contract": base_dir / f"po_contract_{fixture}.db",
        "po_dashboard_invariants": base_dir / f"po_dashboard_invariants_{fixture}.db",
        "stagecode_waybill": base_dir / f"stagecode_waybill_{fixture}.db",
        "transfer_ledger": base_dir / f"transfer_ledger_{fixture}.db",
    }
    _init_po_contract_db(paths["po_contract"])
    _init_po_dashboard_invariants_db(paths["po_dashboard_invariants"])
    _init_stagecode_waybill_db(paths["stagecode_waybill"])
    _init_transfer_ledger_db(paths["transfer_ledger"])
    return paths


def _run_po_contract(fixture: str) -> dict:
    cases_path, expected_path = validate_po_contract.resolve_fixture_paths(fixture)
    result = validate_po_contract.run_contract(
        cases_path=cases_path,
        expected_path=expected_path,
    )
    return {
        "ok": bool(result.get("ok")),
        "failures": result.get("failures", []),
    }


def _build_dashboard_invariants_payload(db_path: Path) -> dict:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT sku_key FROM portfolio_active WHERE active_flag = 1"
        ).fetchall()
    skus = [row[0] for row in rows]
    sku_level = [{"sku_key": sku, "notes": ""} for sku in skus]
    summary = {
        "total_skus": len(sku_level),
        "skus_with_orders": 0,
        "total_units": 0,
    }
    return {
        "generated_at": "2026-01-15T00:00:00",
        "base_stock_date": "2026-01-14",
        "cutoff_date": "2026-01-14",
        "day_complete_ok": True,
        "summary": summary,
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "summary": {
                    "total_skus": len(sku_level),
                    "total_units": 0,
                },
                "sku_level": sku_level,
                "size_level": [],
            }
        },
        "active_pos": ["PLAN-0"],
        "archived_pos": [],
        "real_pos": [],
    }


def _run_po_dashboard_invariants(db_path: Path) -> dict:
    payload = _build_dashboard_invariants_payload(db_path)
    errors = validate_po_dashboard_invariants.validate_payload(
        payload,
        db_path=db_path,
        strict_portfolio=True,
    )
    return {
        "ok": len(errors) == 0,
        "errors": errors,
    }


def _run_stagecode_waybill(db_path: Path) -> dict:
    expected = {"UNIVERSAL": {"1001", "1002", "1003"}}
    actual = download_waybills_api.get_target_order_ids_from_db(
        db_path=db_path,
        target_date=STAGECODE_TARGET_DATE,
        exact_date=True,
    )
    orders = build_daily_waybills.read_db_orders(
        db_path=db_path,
        target_date=STAGECODE_TARGET_DATE,
        lookback_days=None,
    )
    order_ids = {o.order_id for o in orders}
    # API-target selection includes all READY-stage rows for the date.
    # Waybill builder keeps only size-resolved actionable rows.
    ok = actual == expected and order_ids == {"1001"}
    return {
        "ok": ok,
        "expected": {k: sorted(v) for k, v in expected.items()},
        "actual": {k: sorted(v) for k, v in actual.items()},
        "order_ids": sorted(order_ids),
    }


def _run_transfer_ledger(db_path: Path) -> dict:
    orders = repository.list_exchanger_orders(db_path=db_path)
    withdrawals = repository.list_withdrawals(db_path=db_path)

    results = [
        validate_transfer_ledger.validate_matching_invariants(
            orders, withdrawals, FIXTURE_NOW
        ),
        validate_transfer_ledger.validate_allocation_invariants(db_path),
        validate_transfer_ledger.validate_reconciliation_invariants(db_path),
        validate_transfer_ledger.validate_freshness_invariants(db_path, FIXTURE_NOW),
    ]

    errors: list[str] = []
    warnings: list[str] = []
    for res in results:
        errors.extend(res.errors)
        warnings.extend(res.warnings)

    return {
        "ok": len(errors) == 0 and len(warnings) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _hash_payload(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def run_contract_suite(fixture: str = "small", work_dir: Path | None = None) -> dict:
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="contract_suite_"))
    fixture_paths = build_fixture_dbs(fixture, work_dir)

    po_result = _run_po_contract(fixture)
    dashboard_result = _run_po_dashboard_invariants(fixture_paths["po_dashboard_invariants"])
    stage_result = _run_stagecode_waybill(fixture_paths["stagecode_waybill"])
    transfer_result = _run_transfer_ledger(fixture_paths["transfer_ledger"])

    ok = (
        po_result["ok"]
        and dashboard_result["ok"]
        and stage_result["ok"]
        and transfer_result["ok"]
    )
    summary = {
        "fixture": fixture,
        "po_contract": {
            "ok": po_result["ok"],
            "failure_count": len(po_result["failures"]),
        },
        "po_dashboard_invariants": {
            "ok": dashboard_result["ok"],
            "error_count": len(dashboard_result["errors"]),
        },
        "stagecode_waybill": {
            "ok": stage_result["ok"],
            "expected": stage_result["expected"],
            "actual": stage_result["actual"],
            "order_ids": stage_result["order_ids"],
        },
        "transfer_ledger": {
            "ok": transfer_result["ok"],
            "error_count": len(transfer_result["errors"]),
            "warning_count": len(transfer_result["warnings"]),
        },
    }
    suite_hash = _hash_payload(summary)
    return {
        "ok": ok,
        "suite_hash": suite_hash,
        "summary": summary,
        "fixture_dir": str(work_dir),
        "fixture_paths": {k: str(v) for k, v in fixture_paths.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic contract suite on fixtures")
    parser.add_argument("--fixture", type=str, default="small", help="Fixture set name")
    parser.add_argument("--work-dir", type=Path, default=None, help="Directory for fixture DBs")
    args = parser.parse_args()

    result = run_contract_suite(args.fixture, args.work_dir)
    summary = result["summary"]
    print("CONTRACT SUITE")
    print(f"  fixture: {summary['fixture']}")
    print(f"  po_contract: {'OK' if summary['po_contract']['ok'] else 'FAIL'}")
    print(
        "  po_dashboard_invariants: "
        + ("OK" if summary["po_dashboard_invariants"]["ok"] else "FAIL")
    )
    print(
        "  stagecode_waybill: "
        + ("OK" if summary["stagecode_waybill"]["ok"] else "FAIL")
    )
    print(
        "  transfer_ledger: "
        + ("OK" if summary["transfer_ledger"]["ok"] else "FAIL")
    )
    print(f"  suite_hash: {result['suite_hash']}")
    if not result["ok"]:
        print("  errors: contract suite failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
