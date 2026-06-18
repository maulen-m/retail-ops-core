#!/usr/bin/env python3
"""Apply the owner-observed LINE31 Whale Blue current-stock decision.

Dry-run is the default. Apply mode is production-safe and requires:
  ENABLE_LINE31_WHALE_BLUE_OWNER_STOCK_WRITE=1
  ALLOW_PRODUCTION_LINE31_WHALE_BLUE_OWNER_STOCK_WRITE=1 for db/app.db

This script intentionally writes physical stock truth only. It does not update
Kaspi marketplace/pricelist/display stock.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402
from core.db.ledger import rebuild_snapshot_from_ledger  # noqa: E402
from scripts.backup_db import backup_database  # noqa: E402


ALMATY = ZoneInfo("Asia/Almaty")
SKU_KEY = "CL_OF_ARC_WM_LINE31_C-025_WHALE-BLUE"
COLOR_CODE = "C-025"
COLOR_EN = "Whale Blue"
COLOR_CN = "香鲸蓝"
ARTICLE_HINT = "OF_LINE31_ST_WB"
STORE_CODE = "UNIVERSAL"
EVENT_TYPE = "ADJUSTMENT"
INPUT_SOURCE = "OWNER_OBSERVED_LINE31_WHALE_BLUE_STOCK"
CREATED_BY = "codex_line31_whale_blue_owner_stock_2026_06_17"
ENV_GATE = "ENABLE_LINE31_WHALE_BLUE_OWNER_STOCK_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_LINE31_WHALE_BLUE_OWNER_STOCK_WRITE"
OBSERVED_AT = "2026-06-17T16:14:45+05:00"
DEFAULT_SNAPSHOT_DATE = date(2026, 6, 17)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation/line31_whale_blue_owner_stock"
CURRENT_OUTPUT_DIR = PROJECT_ROOT / "exports/current/line31_whale_blue_owner_stock"

HANDOFF_DIR = Path(
    "~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/"
    "LINE31_WHALE_BLUE_CURRENT_STOCK_OWNER_DECISION_AB_HANDOFF__2026-06-17"
)
HANDOFF_MD = HANDOFF_DIR / "00_HANDOFF.md"
HANDOFF_CSV = HANDOFF_DIR / "line31_whale_blue_current_stock_observed_quantities.csv"
SIDE_CAR_JSON = Path(
    "~/Cowork/Projects/Sourcing-Research/captures/processed/2026-06-17/"
    "161445__owner_line31_whale_blue_never_sold_current_stock_observation/"
    "whale_blue_current_stock_basis.json"
)
APRIL_STOCK_MD = Path(
    "~/Cowork/Projects/E-commerce/docs/inventory/products/"
    "LINE31_sales__STOCK_13.4.26.md"
)
APRIL_SALES_MD = Path(
    "~/Cowork/Projects/E-commerce/docs/inventory/products/"
    "LINE31_sales__LINE31_sales.md"
)
PO1A_EVENT_MD = Path(
    "~/Cowork/Projects/Sourcing-Research/captures/processed/2026-05-24/"
    "100000__owner_line31_po1a_non_olive_arrived_astana_cargo_pickup_sales_handoff/"
    "event_summary.md"
)
PO1A_CSV = Path(
    "~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/"
    "LINE31_PO1A_NON_OLIVE_ASTANA_SALES_ACTIVATION__2026-05-24/"
    "line31_po1a_non_olive_arrived_quantities.csv"
)

SIZE_ORDER = ("S", "M", "L", "XL", "2XL", "3XL")
APRIL_COMPONENT = {"S": 0, "M": 5, "L": 4, "XL": 9, "2XL": 5, "3XL": 0}
PO1A_COMPONENT = {"S": 2, "M": 11, "L": 7, "XL": 7, "2XL": 0, "3XL": 0}
FINAL_TARGET = {
    size: APRIL_COMPONENT.get(size, 0) + PO1A_COMPONENT.get(size, 0)
    for size in SIZE_ORDER
}

SOURCE_LAYERS = (
    {
        "layer": "april_stock_evidence_correction",
        "event_date": "2026-04-13",
        "reference_id": "LINE31_WHALE_BLUE_APRIL_STOCK_EVIDENCE_20260413",
        "reference_type": "OWNER_APRIL_STOCK_EVIDENCE_CORRECTION",
        "source_path": str(APRIL_STOCK_MD),
        "deltas": {"M": 1, "XL": 1, "2XL": 1},
        "description": (
            "Correct old AB 20pct baseline so ARC-1/April observed Whale Blue "
            "remaining stock is 23 rather than 20."
        ),
    },
    {
        "layer": "po1a_arrived_stock",
        "event_date": "2026-05-24",
        "reference_id": "LINE31_WHALE_BLUE_PO1A_ARRIVAL_20260524",
        "reference_type": "OWNER_CONFIRMED_PO1A_ARRIVAL",
        "source_path": str(PO1A_CSV),
        "deltas": {"S": 2, "M": 11, "L": 7, "XL": 7},
        "description": "Add owner-confirmed PO1A arrived Whale Blue physical stock.",
    },
)

TEXT_TERMS = (COLOR_EN, "WHALE-BLUE", COLOR_CODE, COLOR_CN, ARTICLE_HINT)


@dataclass
class Candidate:
    layer: str
    event_date: str
    reference_id: str
    reference_type: str
    sku_id: str
    my_size: str
    qty_change: int
    idempotency_key: str
    action: str
    notes: str


@dataclass
class ScanResult:
    table: str
    status: str
    row_count: int = 0
    qty_total: float = 0
    sql: str = ""
    samples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Plan:
    candidates: list[Candidate] = field(default_factory=list)
    contradiction_scans: list[ScanResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    current_balance: dict[str, int] = field(default_factory=dict)
    predicted_balance: dict[str, int] = field(default_factory=dict)
    snapshot_rows: list[dict[str, Any]] = field(default_factory=list)
    sku_rows: dict[str, str] = field(default_factory=dict)

    @property
    def insert_candidates(self) -> list[Candidate]:
        return [row for row in self.candidates if row.action == "INSERT"]


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    with _connect(path, readonly=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RuntimeError(f"refusing production apply while SQLite sidecars exist: {joined}")


def _is_production_db(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_DB_PATH.resolve()
    except FileNotFoundError:
        return path.absolute() == DEFAULT_DB_PATH.absolute()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _size_sort_key(size: str) -> int:
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else 999


def _load_source_basis() -> dict[str, Any]:
    required_paths = [
        HANDOFF_MD,
        HANDOFF_CSV,
        SIDE_CAR_JSON,
        APRIL_STOCK_MD,
        APRIL_SALES_MD,
        PO1A_EVENT_MD,
        PO1A_CSV,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise RuntimeError(f"missing required source evidence: {missing}")

    sidecar = json.loads(SIDE_CAR_JSON.read_text(encoding="utf-8"))
    if sidecar.get("canonical_sku_key") != SKU_KEY:
        raise RuntimeError("source sidecar SKU key mismatch")
    if _sizes_from_mapping(sidecar["april_stock_evidence"]) != APRIL_COMPONENT:
        raise RuntimeError("source sidecar April stock component mismatch")
    if _sizes_from_mapping(sidecar["po1a_arrived_whale_blue"]) != PO1A_COMPONENT:
        raise RuntimeError("source sidecar PO1A component mismatch")
    if _sizes_from_mapping(sidecar["current_owner_observed_stock"]) != FINAL_TARGET:
        raise RuntimeError("source sidecar current target mismatch")

    rows: dict[str, dict[str, str]] = {}
    with HANDOFF_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[str(row["source_layer"])] = row
    expected_csv = {
        "april_stock_evidence": APRIL_COMPONENT,
        "po1a_arrived_stock": PO1A_COMPONENT,
        "current_owner_observed_total": FINAL_TARGET,
    }
    for layer, expected in expected_csv.items():
        if layer not in rows:
            raise RuntimeError(f"handoff CSV missing layer {layer}")
        observed = {size: int(rows[layer][size.lower()]) for size in SIZE_ORDER}
        if observed != expected:
            raise RuntimeError(f"handoff CSV mismatch for {layer}: {observed} != {expected}")

    stock_text = APRIL_STOCK_MD.read_text(encoding="utf-8")
    po1a_text = PO1A_CSV.read_text(encoding="utf-8")
    sales_text = APRIL_SALES_MD.read_text(encoding="utf-8")
    if SKU_KEY not in stock_text or "|0|5|4|9|5|0|23|" not in stock_text:
        raise RuntimeError("April stock evidence row not found or changed")
    if ARTICLE_HINT not in po1a_text or ",2,11,7,7,0,0,27," not in po1a_text:
        raise RuntimeError("PO1A Whale Blue arrival row not found or changed")
    if any(term in sales_text for term in (COLOR_EN, "WHALE-BLUE", COLOR_CODE, COLOR_CN)):
        raise RuntimeError("April sales evidence unexpectedly contains Whale Blue terms")

    return {
        "sidecar": str(SIDE_CAR_JSON),
        "handoff_csv": str(HANDOFF_CSV),
        "april_stock_evidence": str(APRIL_STOCK_MD),
        "april_sales_evidence": str(APRIL_SALES_MD),
        "po1a_arrival_event": str(PO1A_EVENT_MD),
        "po1a_arrival_csv": str(PO1A_CSV),
    }


def _sizes_from_mapping(mapping: dict[str, Any]) -> dict[str, int]:
    return {size: int(mapping[size.lower()]) for size in SIZE_ORDER}


def _load_sku_rows(conn: sqlite3.Connection, plan: Plan) -> None:
    if not _table_exists(conn, "dim_sku_size"):
        plan.blockers.append("dim_sku_size table missing; cannot match stable SKU identity")
        return
    rows = conn.execute(
        """
        SELECT sku_id, my_size, active_flag
        FROM dim_sku_size
        WHERE sku_key = ?
        """,
        (SKU_KEY,),
    ).fetchall()
    by_size = {str(row["my_size"]): str(row["sku_id"]) for row in rows}
    plan.sku_rows = by_size
    for size, target_qty in FINAL_TARGET.items():
        if target_qty > 0 and size not in by_size:
            plan.blockers.append(f"missing active SKU row for nonzero target size {size}")
    if "3XL" not in by_size and FINAL_TARGET["3XL"] == 0:
        return
    for row in rows:
        if int(row["active_flag"] or 0) != 1 and FINAL_TARGET.get(str(row["my_size"]), 0) > 0:
            plan.blockers.append(f"inactive SKU row for nonzero target size {row['my_size']}")


def _current_balance(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT my_size, COALESCE(SUM(qty_change), 0) AS qty
        FROM stock_ledger
        WHERE sku_key = ?
        GROUP BY my_size
        """,
        (SKU_KEY,),
    ).fetchall()
    balances = {size: 0 for size in SIZE_ORDER}
    for row in rows:
        balances[str(row["my_size"])] = int(row["qty"] or 0)
    return balances


def _existing_idempotency_keys(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT idempotency_key
        FROM stock_ledger
        WHERE sku_key = ?
          AND idempotency_key IS NOT NULL
          AND idempotency_key != ''
        """,
        (SKU_KEY,),
    ).fetchall()
    return {str(row["idempotency_key"]) for row in rows}


def _find_source_double_count_risks(conn: sqlite3.Connection) -> list[str]:
    reference_ids = [str(layer["reference_id"]) for layer in SOURCE_LAYERS]
    placeholders = ",".join("?" for _ in reference_ids)
    rows = conn.execute(
        f"""
        SELECT reference_id, my_size, qty_change, idempotency_key
        FROM stock_ledger
        WHERE sku_key = ?
          AND reference_id IN ({placeholders})
          AND (
              idempotency_key IS NULL
              OR idempotency_key NOT LIKE 'LINE31_WHALE_BLUE_OWNER_STOCK:%'
          )
        """,
        [SKU_KEY, *reference_ids],
    ).fetchall()
    return [
        (
            "source reference already exists without this script's idempotency key: "
            f"{row['reference_id']} {row['my_size']} qty={row['qty_change']} key={row['idempotency_key']}"
        )
        for row in rows
    ]


def _contradiction_scan(conn: sqlite3.Connection) -> list[ScanResult]:
    scans = [
        _scan_generic(
            conn,
            "sales_fact_v2",
            quantity_col="quantity",
            key_cols=("sku_key", "sku_id"),
            text_cols=("kaspi_offer_name",),
        ),
        _scan_generic(
            conn,
            "fact_orders_kaspi",
            quantity_col="quantity",
            key_cols=("sku_key", "sku_id"),
            text_cols=("kaspi_offer_name",),
        ),
        _scan_generic(
            conn,
            "fact_order_entries_kaspi",
            quantity_col="quantity",
            key_cols=(),
            text_cols=("product_id", "offer_id", "raw_json"),
        ),
        _scan_generic(
            conn,
            "fact_sales",
            quantity_col="quantity",
            key_cols=("sku_key", "sku_id"),
            text_cols=("kaspi_offer_name",),
        ),
        _scan_generic(
            conn,
            "fact_sales_v16",
            quantity_col="quantity",
            key_cols=("sku_key", "sku_id"),
            text_cols=("offer_id",),
        ),
        _scan_generic(
            conn,
            "fact_sales_raw",
            quantity_col="quantity",
            key_cols=("sku_id",),
            text_cols=("kaspi_offer", "kaspi_article", "kaspi_offer_name"),
        ),
        _scan_generic(
            conn,
            "fact_sales_daily_size",
            quantity_col="units",
            key_cols=("sku_key", "sku_id"),
            text_cols=(),
        ),
        _scan_generic(
            conn,
            "kaspi_orders_y",
            quantity_col="quantity",
            key_cols=("sku_key", "sku_id"),
            text_cols=("kaspi_offer_name",),
        ),
        _scan_stock_ledger_sale_like(conn),
    ]
    return scans


def _scan_generic(
    conn: sqlite3.Connection,
    table: str,
    *,
    quantity_col: str,
    key_cols: tuple[str, ...],
    text_cols: tuple[str, ...],
) -> ScanResult:
    if not _table_exists(conn, table):
        return ScanResult(table=table, status="MISSING")
    cols = _table_columns(conn, table)
    conditions: list[str] = []
    params: list[Any] = []
    if "sku_key" in key_cols and "sku_key" in cols:
        conditions.append("sku_key = ?")
        params.append(SKU_KEY)
    if "sku_id" in key_cols and "sku_id" in cols:
        conditions.append("sku_id LIKE ?")
        params.append(f"{SKU_KEY}%")
    for col in text_cols:
        if col not in cols:
            continue
        for term in TEXT_TERMS:
            conditions.append(f"{col} LIKE ?")
            params.append(f"%{term}%")
    if not conditions:
        return ScanResult(table=table, status="NO_MATCHABLE_COLUMNS")
    where = " OR ".join(f"({condition})" for condition in conditions)
    qty_expr = f"COALESCE(SUM({quantity_col}), 0)" if quantity_col in cols else "0"
    sql = f"SELECT COUNT(*) AS row_count, {qty_expr} AS qty_total FROM {table} WHERE {where}"
    row = conn.execute(sql, params).fetchone()
    sample_cols = [col for col in ("order_id", "entry_id", "sku_key", "sku_id", "my_size", "kaspi_offer_name") if col in cols]
    samples: list[dict[str, Any]] = []
    if row and int(row["row_count"] or 0) > 0 and sample_cols:
        sample_sql = f"SELECT {', '.join(sample_cols)} FROM {table} WHERE {where} LIMIT 10"
        samples = [dict(sample) for sample in conn.execute(sample_sql, params).fetchall()]
    return ScanResult(
        table=table,
        status="OK",
        row_count=int(row["row_count"] or 0) if row else 0,
        qty_total=float(row["qty_total"] or 0) if row else 0,
        sql=sql,
        samples=samples,
    )


def _scan_stock_ledger_sale_like(conn: sqlite3.Connection) -> ScanResult:
    if not _table_exists(conn, "stock_ledger"):
        return ScanResult(table="stock_ledger_sale_like", status="MISSING")
    sql = """
        SELECT COUNT(*) AS row_count, COALESCE(SUM(qty_change), 0) AS qty_total
        FROM stock_ledger
        WHERE sku_key = ?
          AND (
              event_type IN ('SALE', 'SALES', 'ORDER', 'SHIPMENT', 'RETURN', 'CANCEL')
              OR reference_type IN ('SALE', 'ORDER', 'KASPI_ORDER', 'ORDER_ENTRY', 'RETURN', 'CANCEL')
              OR input_source LIKE '%SALE%'
              OR input_source LIKE '%ORDER%'
          )
    """
    row = conn.execute(sql, (SKU_KEY,)).fetchone()
    samples: list[dict[str, Any]] = []
    if row and int(row["row_count"] or 0) > 0:
        sample_sql = """
            SELECT ledger_id, event_date, event_type, my_size, qty_change, reference_id, input_source
            FROM stock_ledger
            WHERE sku_key = ?
              AND (
                  event_type IN ('SALE', 'SALES', 'ORDER', 'SHIPMENT', 'RETURN', 'CANCEL')
                  OR reference_type IN ('SALE', 'ORDER', 'KASPI_ORDER', 'ORDER_ENTRY', 'RETURN', 'CANCEL')
                  OR input_source LIKE '%SALE%'
                  OR input_source LIKE '%ORDER%'
              )
            LIMIT 10
        """
        samples = [dict(sample) for sample in conn.execute(sample_sql, (SKU_KEY,)).fetchall()]
    return ScanResult(
        table="stock_ledger_sale_like",
        status="OK",
        row_count=int(row["row_count"] or 0) if row else 0,
        qty_total=float(row["qty_total"] or 0) if row else 0,
        sql=sql.strip(),
        samples=samples,
    )


def build_plan(conn: sqlite3.Connection) -> Plan:
    plan = Plan()
    _load_sku_rows(conn, plan)
    plan.current_balance = _current_balance(conn)
    existing_keys = _existing_idempotency_keys(conn)
    plan.contradiction_scans = _contradiction_scan(conn)

    contradiction_rows = [
        scan for scan in plan.contradiction_scans if scan.status == "OK" and scan.row_count > 0
    ]
    for scan in contradiction_rows:
        plan.blockers.append(
            f"contradictory Whale Blue sale/order evidence in {scan.table}: rows={scan.row_count}"
        )

    plan.blockers.extend(_find_source_double_count_risks(conn))

    for layer in SOURCE_LAYERS:
        for size, delta in layer["deltas"].items():
            sku_id = plan.sku_rows.get(size)
            if not sku_id:
                plan.blockers.append(f"cannot plan {layer['layer']} {size}: SKU row missing")
                continue
            idempotency_key = (
                f"LINE31_WHALE_BLUE_OWNER_STOCK:{layer['layer']}:{layer['event_date']}:{sku_id}"
            )
            notes = json.dumps(
                {
                    "observed_at": OBSERVED_AT,
                    "owner_decision": "Whale Blue was never in sale; current stock is April evidence plus PO1A arrival.",
                    "layer": layer["layer"],
                    "description": layer["description"],
                    "source_path": layer["source_path"],
                    "handoff": str(HANDOFF_MD),
                    "source_sidecar": str(SIDE_CAR_JSON),
                    "april_component": APRIL_COMPONENT,
                    "po1a_component": PO1A_COMPONENT,
                    "final_target": FINAL_TARGET,
                    "exclude_future_line31_507_route": True,
                    "marketplace_write": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            plan.candidates.append(
                Candidate(
                    layer=str(layer["layer"]),
                    event_date=str(layer["event_date"]),
                    reference_id=str(layer["reference_id"]),
                    reference_type=str(layer["reference_type"]),
                    sku_id=sku_id,
                    my_size=size,
                    qty_change=int(delta),
                    idempotency_key=idempotency_key,
                    action="EXISTS" if idempotency_key in existing_keys else "INSERT",
                    notes=notes,
                )
            )

    predicted = dict(plan.current_balance)
    for candidate in plan.insert_candidates:
        predicted[candidate.my_size] = predicted.get(candidate.my_size, 0) + candidate.qty_change
    plan.predicted_balance = {size: int(predicted.get(size, 0)) for size in SIZE_ORDER}
    if plan.predicted_balance != FINAL_TARGET:
        plan.blockers.append(
            "predicted final stock does not match owner target: "
            f"{plan.predicted_balance} != {FINAL_TARGET}"
        )

    return plan


def _insert_candidate(conn: sqlite3.Connection, candidate: Candidate) -> None:
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_time, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, kaspi_offer_name, notes,
            input_source, created_by, idempotency_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate.event_date,
            OBSERVED_AT,
            EVENT_TYPE,
            SKU_KEY,
            candidate.sku_id,
            candidate.my_size,
            STORE_CODE,
            candidate.qty_change,
            candidate.reference_id,
            candidate.reference_type,
            "LINE31 Whale Blue owner-observed stock",
            candidate.notes,
            INPUT_SOURCE,
            CREATED_BY,
            candidate.idempotency_key,
        ),
    )


def _snapshot_rows(conn: sqlite3.Connection, snapshot_date: date) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fact_inventory_snapshot_size"):
        return []
    rows = conn.execute(
        """
        SELECT snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
          AND sku_key = ?
        """,
        (snapshot_date.isoformat(), SKU_KEY),
    ).fetchall()
    return sorted((dict(row) for row in rows), key=lambda row: _size_sort_key(str(row["my_size"])))


def _stock_rows_from_balance(balance: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "sku_key": SKU_KEY,
            "my_size": size,
            "stock": int(balance.get(size, 0)),
            "april_component": APRIL_COMPONENT[size],
            "po1a_component": PO1A_COMPONENT[size],
            "target": FINAL_TARGET[size],
        }
        for size in SIZE_ORDER
    ]


def _write_outputs(
    *,
    output_root: Path,
    run_id: str,
    summary: dict[str, Any],
    plan: Plan,
    source_basis: dict[str, Any],
) -> Path:
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    CURRENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary_payload = dict(summary)
    summary_payload["source_basis"] = source_basis
    summary_payload["source_layers"] = SOURCE_LAYERS
    summary_payload["current_balance"] = plan.current_balance
    summary_payload["predicted_balance"] = plan.predicted_balance
    summary_payload["final_target"] = FINAL_TARGET
    summary_payload["blockers"] = plan.blockers
    summary_payload["snapshot_rows"] = plan.snapshot_rows
    summary_payload["rollback"] = _rollback_text(summary)

    (run_dir / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (CURRENT_OUTPUT_DIR / "latest_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with (run_dir / "candidate_events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "action",
                "layer",
                "event_date",
                "my_size",
                "sku_id",
                "qty_change",
                "reference_id",
                "reference_type",
                "idempotency_key",
            ],
        )
        writer.writeheader()
        for row in plan.candidates:
            writer.writerow(
                {
                    "action": row.action,
                    "layer": row.layer,
                    "event_date": row.event_date,
                    "my_size": row.my_size,
                    "sku_id": row.sku_id,
                    "qty_change": row.qty_change,
                    "reference_id": row.reference_id,
                    "reference_type": row.reference_type,
                    "idempotency_key": row.idempotency_key,
                }
            )

    with (run_dir / "contradiction_scan.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["table", "status", "row_count", "qty_total", "samples"],
        )
        writer.writeheader()
        for scan in plan.contradiction_scans:
            writer.writerow(
                {
                    "table": scan.table,
                    "status": scan.status,
                    "row_count": scan.row_count,
                    "qty_total": scan.qty_total,
                    "samples": json.dumps(scan.samples, ensure_ascii=False, sort_keys=True),
                }
            )

    stock_rows = _stock_rows_from_balance(plan.predicted_balance)
    with (run_dir / "line31_whale_blue_current_stock.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sku_key", "my_size", "stock", "april_component", "po1a_component", "target"],
        )
        writer.writeheader()
        writer.writerows(stock_rows)
    with (CURRENT_OUTPUT_DIR / "latest_current_stock.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sku_key", "my_size", "stock", "april_component", "po1a_component", "target"],
        )
        writer.writeheader()
        writer.writerows(stock_rows)

    (run_dir / "rollback.md").write_text(_rollback_text(summary), encoding="utf-8")
    return run_dir


def _rollback_text(summary: dict[str, Any]) -> str:
    backup_path = summary.get("backup_path") or ""
    db_path = summary.get("db_path") or str(DEFAULT_DB_PATH)
    if backup_path:
        return (
            "# Rollback\n\n"
            f"Restore DB backup `{backup_path}` over `{db_path}` after stopping DB writers, "
            "then rerun SQLite integrity and the Whale Blue stock verification queries. "
            "No marketplace/pricelist write was performed by this script.\n"
        )
    return (
        "# Rollback\n\n"
        "Dry-run only; no DB write occurred. No rollback is required. "
        "No marketplace/pricelist write was performed by this script.\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, default=DEFAULT_SNAPSHOT_DATE)
    parser.add_argument("--apply", action="store_true", help="Insert stock_ledger events and rebuild snapshot")
    parser.add_argument("--expected-pre-sha256", default="", help="Required for apply")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Required for production apply")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser()
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    output_root = args.output_root.expanduser()
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    output_root.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    if args.snapshot_date <= date(2026, 5, 24):
        raise SystemExit("snapshot date must be after PO1A arrival date 2026-05-24")

    source_basis = _load_source_basis()
    pre_sha = _file_sha256(db_path)
    backup_path = ""
    snapshot_rows_rebuilt = 0
    run_id = datetime.now(ALMATY).strftime("%Y%m%d_%H%M%S")

    with _connect(db_path, readonly=not args.apply) as conn:
        plan = build_plan(conn)

    status = "DRY_RUN"
    if args.apply:
        if os.environ.get(ENV_GATE) != "1":
            raise SystemExit(f"apply requires {ENV_GATE}=1")
        if not args.expected_pre_sha256:
            raise SystemExit("apply requires --expected-pre-sha256")
        if args.expected_pre_sha256 != pre_sha:
            raise SystemExit(
                f"pre-sha mismatch: expected {args.expected_pre_sha256}, observed {pre_sha}"
            )
        if plan.blockers:
            raise SystemExit(f"blocked; refusing apply: {plan.blockers}")
        if _is_production_db(db_path):
            if os.environ.get(PRODUCTION_ENV_GATE) != "1":
                raise SystemExit(f"production apply requires {PRODUCTION_ENV_GATE}=1")
            _fail_on_sqlite_sidecars(db_path)
            if args.backup_dir is None:
                raise SystemExit("production apply requires --backup-dir")
        backup_dir = args.backup_dir or (output_root / "backups")
        backup_path = str(backup_database(db_path, backup_dir, compress=False))
        with _connect(db_path, readonly=False) as conn:
            for candidate in plan.insert_candidates:
                _insert_candidate(conn, candidate)
            conn.commit()
        snapshot_rows_rebuilt = rebuild_snapshot_from_ledger(
            snapshot_date=args.snapshot_date,
            db_path=db_path,
        )
        with _connect(db_path, readonly=True) as conn:
            plan = build_plan(conn)
            plan.snapshot_rows = _snapshot_rows(conn, args.snapshot_date)
        status = "APPLIED"

    post_sha = _file_sha256(db_path)
    summary = {
        "status": status,
        "mode": "apply" if args.apply else "dry_run",
        "generated_at_almaty": datetime.now(ALMATY).isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "snapshot_date": args.snapshot_date.isoformat(),
        "sku_key": SKU_KEY,
        "color_code": COLOR_CODE,
        "color_en": COLOR_EN,
        "observed_at": OBSERVED_AT,
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "sqlite_integrity_check": _sqlite_integrity_check(db_path),
        "backup_path": backup_path,
        "candidate_rows": len(plan.candidates),
        "insert_candidate_rows": len(plan.insert_candidates),
        "existing_rows": len([row for row in plan.candidates if row.action == "EXISTS"]),
        "contradiction_rows": sum(scan.row_count for scan in plan.contradiction_scans if scan.status == "OK"),
        "blocker_count": len(plan.blockers),
        "snapshot_rows_rebuilt": snapshot_rows_rebuilt,
        "future_line31_507_excluded": True,
        "marketplace_write": False,
        "run_dir": str(output_root / run_id),
        "current_stock_report_csv": str(CURRENT_OUTPUT_DIR / "latest_current_stock.csv"),
        "current_stock_report_json": str(CURRENT_OUTPUT_DIR / "latest_summary.json"),
    }
    run_dir = _write_outputs(
        output_root=output_root,
        run_id=run_id,
        summary=summary,
        plan=plan,
        source_basis=source_basis,
    )
    summary["run_dir"] = str(run_dir)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status={summary['status']}")
        print(f"run_dir={run_dir}")
        print(f"pre_sha256={pre_sha}")
        print(f"post_sha256={post_sha}")
        print(f"backup_path={backup_path}")
        print(f"insert_candidate_rows={summary['insert_candidate_rows']}")
        print(f"blocker_count={summary['blocker_count']}")
        print(f"predicted_balance={plan.predicted_balance}")
    return 0 if not plan.blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
