from __future__ import annotations

import copy
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import pytest

from core.integrations.google_ops_board import load_ops_board_contract, rows_to_matrix
from core.integrations.kaspi_order_stage import (
    StageCode,
    classify_kaspi_order_stage,
    classify_kaspi_stage_from_db_row,
)
from core.ops.waybill_overdue_carryforward import (
    get_overdue_waybill_ready_order_ids_from_db,
)
from core.ops.waybill_shipping_obligations import (
    active_obligation_ids_by_store,
    normalize_store_code,
    obligation_key,
    reconcile_shipping_obligations,
)
from scripts import build_daily_waybills as daily_waybill_mod
from scripts import run_google_ops_board_prewindow_health as prewindow_mod
from scripts import sync_google_ops_board as board_mod
from scripts import validate_google_closeout_expected_orders as expected_mod


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "expected_status"
SYNTHETIC_WORLD_PATH = FIXTURE_ROOT / "synthetic_world.json"
REAL_DAY_PATH = FIXTURE_ROOT / "real_day_2026_07_18.json"
GOLDEN_PATH = FIXTURE_ROOT / "expected_status_goldens.json"
ALMATY = ZoneInfo("Asia/Almaty")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _serial_ids(values: Mapping[str, Iterable[Any]]) -> dict[str, list[str]]:
    return {
        str(store): sorted(str(order_id) for order_id in order_ids)
        for store, order_ids in sorted(values.items())
    }


def _iso_to_epoch_ms(value: str | None) -> int | None:
    if not value:
        return None
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def _api_order(fact: Mapping[str, Any]) -> dict[str, Any]:
    delivery: dict[str, Any] = {}
    if fact.get("waybill_url"):
        delivery["waybill"] = fact["waybill_url"]
    if fact.get("courier_transmission_date"):
        delivery["courierTransmissionDate"] = fact["courier_transmission_date"]
    attrs: dict[str, Any] = {
        "code": fact["order_id"],
        "state": fact.get("state") or "",
        "status": fact.get("status") or "",
        "signatureRequired": fact.get("signature_required", 0),
        "preOrder": fact.get("pre_order", 0),
        "deliveryMode": fact.get("delivery_mode") or "DELIVERY",
        "returnedToWarehouse": fact.get("returned_to_warehouse", 0),
    }
    if delivery:
        attrs["kaspiDelivery"] = delivery
    return {"attributes": attrs}


def _stage_source(stage: str) -> tuple[str, str, str, str]:
    if stage == StageCode.ASSEMBLED_PENDING_HANDOVER.value:
        return (
            "KASPI_DELIVERY",
            "ACCEPTED_BY_MERCHANT",
            "READY",
            "https://example.invalid/recorded-waybill.pdf",
        )
    return "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "ACCEPTED", ""


def _synthetic_facts(world: Mapping[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row_id, source in enumerate(world["orders"], start=1):
        size = str(source.get("size") or "L")
        order_id = str(source["order_id"])
        facts.append(
            {
                "id": row_id,
                "key": source["key"],
                "order_id": order_id,
                "store_code": source["store_code"],
                "planned_date": source["planned_date"],
                "created_at": source["created_at"],
                "state": source["state"],
                "status": source["status"],
                "internal_status": source.get("internal_status") or "",
                "assigned_size": size,
                "my_size": "",
                "quantity": 1,
                "waybill_url": source.get("waybill_url") or "",
                "waybill_downloaded": source.get("waybill_downloaded", 0),
                "actual_shipment_date": source.get("actual_shipment_date") or "",
                "courier_transmission_date": source.get("courier_transmission_date") or "",
                "signature_required": source.get("signature_required", 0),
                "pre_order": source.get("pre_order", 0),
                "delivery_mode": source.get("delivery_mode") or "DELIVERY",
                "returned_to_warehouse": source.get("returned_to_warehouse", 0),
                "kaspi_article": f"ARTICLE-{order_id}",
                "kaspi_offer_name": f"Golden Offer {order_id} {size}",
                "sku_key": f"SKU-{order_id}",
                "sku_id": f"SKU-{order_id}-{size}",
                "kaspi_name_core": f"Core_{order_id}",
            }
        )
    return facts


def _real_day_facts(real_day: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_lines = {
        str(line["db_row_id"]): (order, line)
        for order in real_day["expected_orders"]["orders"]
        for line in order["lines"]
    }
    facts: list[dict[str, Any]] = []
    for board_row in real_day["salesraw_rows"]:
        row_id = str(board_row["_db_row_id"])
        expected_pair = expected_lines.get(row_id)
        if expected_pair:
            expected_order, expected_line = expected_pair
            state, status, internal_status, waybill_url = _stage_source(
                str(expected_order["stage"])
            )
            kaspi_article = str(expected_line.get("kaspi_article") or f"ARTICLE-{row_id}")
            sku_id = str(expected_line.get("sku_id") or "")
            core = str(expected_line["kaspi_name_core"])
        else:
            state = "KASPI_DELIVERY"
            status = "ACCEPTED_BY_MERCHANT"
            internal_status = "READY"
            waybill_url = f"https://example.invalid/{board_row['OrderID']}.pdf"
            kaspi_article = f"RECORDED-{row_id}"
            sku_id = f"{board_row['SKU_key']}_{board_row['PROBABLE_SIZE']}"
            core = str(board_row["Kaspi_name_core"])
        delivery_status = str(board_row.get("ExpressDeliveryStatus") or "")
        facts.append(
            {
                "id": int(row_id),
                "key": f"recorded_{board_row['OrderID']}",
                "order_id": str(board_row["OrderID"]),
                "store_code": str(board_row["STORE_NAME"]),
                "planned_date": str(board_row["Date"]),
                "created_at": f"{board_row['Date']}T10:00:00+05:00",
                "state": state,
                "status": status,
                "internal_status": internal_status,
                "assigned_size": str(board_row.get("MY_SIZE") or ""),
                "my_size": "",
                "quantity": int(board_row.get("Quantity") or 1),
                "waybill_url": waybill_url,
                "waybill_downloaded": bool(waybill_url),
                "actual_shipment_date": "",
                "courier_transmission_date": "",
                "signature_required": 0,
                "pre_order": 0,
                "delivery_mode": (
                    "PICKUP" if delivery_status == "PICKUP" else "DELIVERY"
                ),
                "express": 1 if delivery_status == "EXPRESS" else 0,
                "returned_to_warehouse": 0,
                "kaspi_article": kaspi_article,
                "kaspi_offer_name": str(board_row["KASPI_OFFER_NAME"]),
                "sku_key": str(board_row["SKU_key"]),
                "sku_id": sku_id,
                "kaspi_name_core": core,
            }
        )
    return facts


def _write_db(path: Path, facts: list[dict[str, Any]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                kaspi_article TEXT,
                planned_shipment_date TEXT,
                created_at TEXT,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                assigned_size TEXT,
                quantity INTEGER,
                waybill_url TEXT,
                waybill_downloaded INTEGER,
                actual_shipment_date TEXT,
                courier_transmission_date TEXT,
                signature_required INTEGER,
                pre_order INTEGER,
                delivery_mode TEXT,
                express INTEGER,
                planned_delivery_date TEXT,
                payment_mode TEXT,
                returned_to_warehouse INTEGER,
                customer_first_name TEXT,
                customer_last_name TEXT,
                customer_phone TEXT,
                customer_height_cm INTEGER,
                customer_weight_kg INTEGER,
                updated_at TEXT
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                product_type TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT,
                kaspi_article TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                kaspi_name_core TEXT,
                active_flag INTEGER,
                updated_at TEXT
            );
            CREATE TABLE fact_sales (
                kaspi_offer_name TEXT,
                sku_key TEXT,
                my_size TEXT,
                quantity INTEGER
            );
            CREATE TABLE dim_size_probability (
                level TEXT,
                key_value TEXT,
                mode_size TEXT,
                mode_share REAL,
                sample_count INTEGER,
                confidence TEXT,
                size_distribution TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO dim_size_probability (
                level, key_value, mode_size, mode_share, sample_count,
                confidence, size_distribution
            ) VALUES ('PRODUCT_TYPE', 'CL', 'L', 0.35, 0, 'LOW', '{"L": 0.35}')
            """
        )
        seen_skus: set[str] = set()
        seen_maps: set[tuple[str, str, str, str]] = set()
        for fact in facts:
            conn.execute(
                """
                INSERT INTO fact_orders_kaspi (
                    id, order_id, store_code, kaspi_article,
                    planned_shipment_date, created_at, kaspi_status,
                    kaspi_status_detail, internal_status, kaspi_offer_name,
                    sku_key, sku_id, my_size, assigned_size, quantity,
                    waybill_url, waybill_downloaded, actual_shipment_date,
                    courier_transmission_date, signature_required, pre_order,
                    delivery_mode, express, planned_delivery_date, payment_mode,
                    returned_to_warehouse, customer_first_name,
                    customer_last_name, customer_phone, customer_height_cm,
                    customer_weight_kg, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    fact["id"],
                    fact["order_id"],
                    fact["store_code"],
                    fact["kaspi_article"],
                    fact["planned_date"],
                    fact["created_at"],
                    fact["state"],
                    fact["status"],
                    fact["internal_status"],
                    fact["kaspi_offer_name"],
                    fact["sku_key"],
                    fact["sku_id"],
                    fact.get("my_size") or "",
                    fact.get("assigned_size") or "",
                    fact.get("quantity", 1),
                    fact.get("waybill_url") or "",
                    int(bool(fact.get("waybill_downloaded"))),
                    fact.get("actual_shipment_date") or "",
                    fact.get("courier_transmission_date") or "",
                    int(bool(fact.get("signature_required"))),
                    int(bool(fact.get("pre_order"))),
                    fact.get("delivery_mode") or "DELIVERY",
                    int(bool(fact.get("express"))),
                    "",
                    "PREPAID",
                    int(bool(fact.get("returned_to_warehouse"))),
                    "",
                    "",
                    "",
                    None,
                    None,
                    fact["created_at"],
                ),
            )
            if fact["sku_key"] not in seen_skus:
                conn.execute(
                    "INSERT INTO dim_sku (sku_key, product_type) VALUES (?, 'CL')",
                    (fact["sku_key"],),
                )
                seen_skus.add(fact["sku_key"])
            map_key = (
                normalize_store_code(fact["store_code"]),
                fact["kaspi_article"],
                fact["kaspi_offer_name"],
                fact["sku_key"],
            )
            if map_key not in seen_maps:
                conn.execute(
                    """
                    INSERT INTO dim_kaspi_article_map (
                        store_code, kaspi_article, kaspi_offer_name, sku_key,
                        sku_id, kaspi_name_core, active_flag, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, '2026-07-18T00:00:00+05:00')
                    """,
                    (
                        map_key[0],
                        fact["kaspi_article"],
                        fact["kaspi_offer_name"],
                        fact["sku_key"],
                        fact["sku_id"],
                        fact["kaspi_name_core"],
                    ),
                )
                seen_maps.add(map_key)


def _write_obligation_ledger(path: Path, facts: list[dict[str, Any]]) -> Path:
    entries = {}
    for fact in facts:
        store = normalize_store_code(fact["store_code"])
        key = obligation_key(store, fact["order_id"])
        entries[key] = {
            "store_code": store,
            "order_id": fact["order_id"],
            "status": "unresolved",
            "first_seen_target_date": fact["planned_date"],
            "last_seen_target_date": fact["planned_date"],
        }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": None,
                "request_identity": {},
                "entries": dict(sorted(entries.items())),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _db_rows(path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM fact_orders_kaspi ORDER BY id").fetchall()
    finally:
        conn.close()


def _project_expected_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": report["ok"],
        "expected_order_ids": report["expected_order_ids"],
        "overdue_order_ids": report["overdue_order_ids"],
        "orders": {
            str(order["order_id"]): {
                "store_code": order["store_code"],
                "planned_shipment_date": order["planned_shipment_date"],
                "stage": order["stage"],
                "overdue": order["overdue"],
            }
            for order in report["orders"]
        },
        "line_scope_hash": report["line_scope_hash"],
        "counts": report["counts"],
        "counts_by_store": report["counts_by_store"],
        "counts_by_stage": report["counts_by_stage"],
        "excluded_counts": report["excluded_counts"],
        "missing_active_order_ids_by_store": report[
            "missing_active_order_ids_by_store"
        ],
        "active_order_blockers": report["active_order_blockers"],
    }


def _board_projection(
    *,
    db_path: Path,
    facts: list[dict[str, Any]],
    target: date,
) -> dict[str, Any]:
    contract = load_ops_board_contract()
    rows = _db_rows(db_path)
    waybill_overdue = get_overdue_waybill_ready_order_ids_from_db(
        db_path,
        target_date=target,
        lookback_days=None,
    )
    board_overdue = board_mod._build_board_overdue_ids_by_store(
        rows,
        waybill_overdue_ids_by_store=waybill_overdue,
        target_date=target,
        contract=contract,
    )
    nonpackable = board_mod._nonpackable_order_keys(rows)
    selected = board_mod._select_operational_rows(
        rows,
        overdue_ids_by_store=board_overdue,
        target_date=target,
        contract=contract,
    )
    selected_ids = {str(row["order_id"]) for row in selected}
    facts_by_id = {str(fact["order_id"]): fact for fact in facts}
    return {
        "waybill_overdue_ids_by_store": _serial_ids(waybill_overdue),
        "board_overdue_ids_by_store": _serial_ids(board_overdue),
        "nonpackable_order_keys": sorted(
            f"{store}:{order_id}" for store, order_id in nonpackable
        ),
        "orders": {
            facts_by_id[str(row["order_id"])]["key"]: {
                "normalized_store": board_mod._normalize_store_key(row["store_code"]),
                "pending_carryforward": board_mod._is_pending_carryforward_row(
                    row,
                    target_date=target,
                    contract=contract,
                ),
                "nonpackable": board_mod._order_key(row) in nonpackable,
                "selected": str(row["order_id"]) in selected_ids,
                "rendered_status": board_mod._operational_status(row, board_overdue),
            }
            for row in rows
        },
    }


def _obligation_projection(
    *,
    facts: list[dict[str, Any]],
    target: date,
    now: datetime,
    ready_set_at: str,
) -> dict[str, Any]:
    prior_entries = {}
    detail_results = {}
    for fact in facts:
        store = normalize_store_code(fact["store_code"])
        key = obligation_key(store, fact["order_id"])
        prior_entries[key] = {
            "store_code": store,
            "order_id": fact["order_id"],
            "status": "unresolved",
            "first_seen_target_date": fact["planned_date"],
            "last_seen_target_date": fact["planned_date"],
        }
        detail_results[key] = {"order": _api_order(fact)}
    result = reconcile_shipping_obligations(
        prior_ledger={"schema_version": 1, "entries": prior_entries},
        current_active_order_ids_by_store={},
        detail_results=detail_results,
        target_date=target,
        ready_set_at=ready_set_at,
        now=now,
    )
    issues_by_key = {
        str(issue["key"]): str(issue["code"]) for issue in result["issues"]
    }
    entries = result["ledger"]["entries"]

    alias_union = reconcile_shipping_obligations(
        prior_ledger={"schema_version": 1, "entries": {}},
        current_active_order_ids_by_store={
            "Universal": ["G01"],
            "UNIVERSAL": ["G02"],
            "30000001_PP1": ["G03"],
        },
        detail_results={},
        target_date=target,
        ready_set_at=ready_set_at,
        now=now,
    )
    return {
        "ok": result["ok"],
        "issues": result["issues"],
        "active_order_ids_by_store": _serial_ids(
            active_obligation_ids_by_store(result["ledger"])
        ),
        "store_alias_active_union": _serial_ids(
            active_obligation_ids_by_store(alias_union["ledger"])
        ),
        "orders": {
            fact["key"]: {
                "ledger_status": entries[
                    obligation_key(fact["store_code"], fact["order_id"])
                ]["status"],
                "last_stage": entries[
                    obligation_key(fact["store_code"], fact["order_id"])
                ].get("last_stage", ""),
                "discharge_reason": entries[
                    obligation_key(fact["store_code"], fact["order_id"])
                ].get("discharge_reason", ""),
                "suspension_reason": entries[
                    obligation_key(fact["store_code"], fact["order_id"])
                ].get("suspension_reason", ""),
                "issue_code": issues_by_key.get(
                    obligation_key(fact["store_code"], fact["order_id"]), ""
                ),
            }
            for fact in facts
        },
    }


def _stage_projection(facts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        fact["key"]: {
            "api_stage": classify_kaspi_order_stage(_api_order(fact)).value,
            "db_stage": classify_kaspi_stage_from_db_row(
                {
                    "kaspi_status": fact["state"],
                    "kaspi_status_detail": fact["status"],
                    "internal_status": fact["internal_status"],
                    "signature_required": fact.get("signature_required", 0),
                    "pre_order": fact.get("pre_order", 0),
                    "waybill_url": fact.get("waybill_url") or "",
                    "delivery_mode": fact.get("delivery_mode") or "DELIVERY",
                    "returned_to_warehouse": fact.get("returned_to_warehouse", 0),
                    "courier_transmission_date": fact.get(
                        "courier_transmission_date"
                    )
                    or "",
                    "actual_shipment_date": fact.get("actual_shipment_date") or "",
                }
            ).value,
        }
        for fact in facts
    }


def _daily_waybill_projection(
    world: Mapping[str, Any], target: date
) -> dict[str, Any]:
    groups_by_store: dict[str, list[daily_waybill_mod.WaybillGroup]] = defaultdict(list)
    for index, case in enumerate(world["group_cases"], start=1):
        items = [
            daily_waybill_mod.OrderItem(
                order_id=f"GROUP-{index}",
                store_name=case["store"],
                kaspi_name_core="Core",
                my_size="L",
                sku_key="SKU",
                sku_id="SKU-L",
                quantity=1,
                kaspi_offer_name="Offer L",
                planned_date=(date.fromisoformat(value) if value else None),
            )
            for value in case["planned_dates"]
        ]
        group = daily_waybill_mod.WaybillGroup(
            group_type="MULTI_LINE" if len(items) > 1 else "NORMAL",
            store_name=case["store"],
            items=items,
        )
        group.output_filename = case["key"]
        groups_by_store[case["store"]].append(group)
    today, overdue = daily_waybill_mod.split_groups_by_overdue(groups_by_store, target)

    api_dates = {}
    for case in world["api_date_cases"]:
        attrs: dict[str, Any] = {}
        creation_ms = _iso_to_epoch_ms(case.get("creation_at"))
        planned_ms = _iso_to_epoch_ms(case.get("planned_at"))
        if creation_ms is not None:
            attrs["creationDate"] = creation_ms
        if planned_ms is not None:
            attrs["kaspiDelivery"] = {
                "courierTransmissionPlanningDate": planned_ms
            }
        observed = daily_waybill_mod._planned_date_from_order(
            {"attributes": attrs},
            store_code=case["store_code"],
        )
        api_dates[case["key"]] = observed.isoformat() if observed else None

    return {
        "today_groups": sorted(
            group.output_filename for groups in today.values() for group in groups
        ),
        "overdue_groups": sorted(
            group.output_filename for groups in overdue.values() for group in groups
        ),
        "api_date_fallbacks": api_dates,
    }


class _SnapshotClient:
    def __init__(self, matrices: Mapping[str, list[list[Any]]]) -> None:
        self.matrices = copy.deepcopy(dict(matrices))

    def snapshot_tabs(self, tab_names: Iterable[str]) -> dict[str, list[list[Any]]]:
        return {name: copy.deepcopy(self.matrices[name]) for name in tab_names}


@contextmanager
def _deterministic_board_dependencies(ledger_path: Path):
    original_ledger = board_mod.DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH
    original_stores = board_mod.load_sync_enabled_kaspi_store_codes
    original_storeb = board_mod.load_storeb_packing_excluded
    board_mod.DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH = ledger_path
    board_mod.load_sync_enabled_kaspi_store_codes = lambda: [
        "UNIVERSAL",
        "ACMEWEAR",
        "STOREB",
    ]
    board_mod.load_storeb_packing_excluded = lambda *args, **kwargs: False
    board_mod._cached_probable_size.cache_clear()
    try:
        yield
    finally:
        board_mod.DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH = original_ledger
        board_mod.load_sync_enabled_kaspi_store_codes = original_stores
        board_mod.load_storeb_packing_excluded = original_storeb
        board_mod._cached_probable_size.cache_clear()


def _parity_projection(
    *,
    db_path: Path,
    ledger_path: Path,
    target: date,
    before_snapshot: Mapping[str, list[list[Any]]] | None = None,
) -> dict[str, Any]:
    contract = load_ops_board_contract()
    with _deterministic_board_dependencies(ledger_path):
        if before_snapshot is None:
            payload = board_mod.build_phase1_payload(
                db_path=db_path,
                contract=contract,
                target_date=target,
                lookback_days=5,
                now_iso=f"{target.isoformat()}T13:00:00+05:00",
                obligation_ledger_path=ledger_path,
                allowed_store_codes={"UNIVERSAL", "ACMEWEAR", "STOREB"},
            )
            before_snapshot = {
                tab_name: rows_to_matrix(
                    contract.tabs[tab_name].headers,
                    list(payload.get(tab_name) or []),
                )
                for tab_name in ("README", "SalesRaw_Today", "Run_Control", "Exceptions")
            }
        report = prewindow_mod._build_live_board_parity_report(
            client=_SnapshotClient(before_snapshot),
            db_path=db_path,
            contract=contract,
            target_date=target,
        )
    return {
        "ok": report["ok"],
        "same_day_preserve": report["same_day_preserve"],
        "previous_target_date": report["previous_target_date"],
        "visibility_annotation_ok": report["visibility_annotation"]["ok"],
        "tabs": {
            tab_name: {
                "ok": tab_report["ok"],
                "expected_row_count": tab_report["expected_row_count"],
                "live_row_count": tab_report["live_row_count"],
                "issues": tab_report["issues"],
            }
            for tab_name, tab_report in report["tabs"].items()
        },
        "issues": report["issues"],
    }


def _collect_synthetic(root: Path) -> dict[str, Any]:
    world = _load_json(SYNTHETIC_WORLD_PATH)
    target = date.fromisoformat(world["target_date"])
    now = datetime.fromisoformat(world["now"])
    facts = _synthetic_facts(world)
    db_path = root / "synthetic.db"
    _write_db(db_path, facts)
    ledger_path = _write_obligation_ledger(
        root / "synthetic_ledger.json",
        [fact for fact in facts if fact["planned_date"] < target.isoformat()],
    )
    all_active = {
        "UNIVERSAL": sorted(str(fact["order_id"]) for fact in facts)
    }
    unfiltered = expected_mod.build_expected_orders_from_db(
        db_path=db_path,
        target_date=target,
        lookback_days=None,
    )
    active_filtered = expected_mod.build_expected_orders_from_db(
        db_path=db_path,
        target_date=target,
        lookback_days=None,
        active_order_ids_by_store=all_active,
        request_identity={
            "target_date": target.isoformat(),
            "ready_set_at": world["ready_set_at"],
        },
    )
    alias_collision = expected_mod.normalize_active_order_ids_by_store(
        {
            "Universal": ["G01"],
            "UNIVERSAL": ["G02"],
            "30000001_PP1": ["G03"],
        }
    )
    return {
        "site_1_google_board": _board_projection(
            db_path=db_path,
            facts=facts,
            target=target,
        ),
        "site_2_expected_orders": {
            "unfiltered": _project_expected_report(unfiltered),
            "active_filtered": _project_expected_report(active_filtered),
            "store_alias_normalization_collision": _serial_ids(alias_collision or {}),
        },
        "site_3_shipping_obligations": _obligation_projection(
            facts=facts,
            target=target,
            now=now,
            ready_set_at=world["ready_set_at"],
        ),
        "site_4_waybill_overdue": _serial_ids(
            get_overdue_waybill_ready_order_ids_from_db(
                db_path,
                target_date=target,
                lookback_days=None,
            )
        ),
        "site_5_prewindow_parity": _parity_projection(
            db_path=db_path,
            ledger_path=ledger_path,
            target=target,
        ),
        "site_6_stage_classifier": _stage_projection(facts),
        "site_7_daily_waybills": _daily_waybill_projection(world, target),
    }


def _collect_real_day(root: Path) -> dict[str, Any]:
    real_day = _load_json(REAL_DAY_PATH)
    target = date.fromisoformat(real_day["target_date"])
    facts = _real_day_facts(real_day)
    db_path = root / "real_day.db"
    _write_db(db_path, facts)
    ledger_path = _write_obligation_ledger(
        root / "real_day_ledger.json",
        [fact for fact in facts if fact["planned_date"] < target.isoformat()],
    )

    recorded_overdue: dict[str, set[str]] = defaultdict(set)
    for row in real_day["salesraw_rows"]:
        if row["Status"] == "OVERDUE":
            recorded_overdue[board_mod._normalize_store_key(row["STORE_NAME"])].add(
                str(row["OrderID"])
            )
    site_1_rows = [
        {
            "order_id": str(row["OrderID"]),
            "store_code": str(row["STORE_NAME"]),
            "recorded_status": str(row["Status"]),
            "replayed_status": board_mod._operational_status(
                {
                    "order_id": row["OrderID"],
                    "store_code": row["STORE_NAME"],
                },
                recorded_overdue,
            ),
        }
        for row in real_day["salesraw_rows"]
    ]

    rebuilt_expected = expected_mod.build_expected_orders_from_db(
        db_path=db_path,
        target_date=target,
        lookback_days=None,
        active_order_ids_by_store=real_day["expected_active_ids_by_store"],
        request_identity={
            "target_date": target.isoformat(),
            "ready_set_at": real_day["run_control_rows"][0]["ready_set_at"],
        },
    )
    contract = load_ops_board_contract()
    before_snapshot = {
        "README": rows_to_matrix(
            contract.tabs["README"].headers,
            [
                {
                    "field": "target_date",
                    "value": target.isoformat(),
                    "notes": "",
                }
            ],
        ),
        "SalesRaw_Today": rows_to_matrix(
            contract.tabs["SalesRaw_Today"].headers,
            real_day["salesraw_rows"],
        ),
        "Run_Control": rows_to_matrix(
            contract.tabs["Run_Control"].headers,
            real_day["run_control_rows"],
        ),
        "Exceptions": rows_to_matrix(contract.tabs["Exceptions"].headers, []),
    }
    expected_truth = real_day["expected_orders"]
    projected_rebuilt = _project_expected_report(rebuilt_expected)
    return {
        "source_run_id": real_day["source_run_id"],
        "source_artifact_sha256": {
            name: item["sha256"]
            for name, item in real_day["source_artifacts"].items()
        },
        "site_1_google_board": {
            "row_count": len(site_1_rows),
            "recorded_status_counts": dict(
                sorted(Counter(row["recorded_status"] for row in site_1_rows).items())
            ),
            "replayed_status_counts": dict(
                sorted(Counter(row["replayed_status"] for row in site_1_rows).items())
            ),
            "mismatches": [
                row
                for row in site_1_rows
                if row["recorded_status"] != row["replayed_status"]
            ],
            "overdue_order_ids": sorted(
                row["order_id"]
                for row in site_1_rows
                if row["replayed_status"] == "OVERDUE"
            ),
        },
        "site_2_expected_orders": {
            "replayed": projected_rebuilt,
            "recorded_projection": {
                "expected_order_ids": expected_truth["expected_order_ids"],
                "overdue_order_ids": expected_truth["overdue_order_ids"],
                "counts": expected_truth["counts"],
                "counts_by_store": expected_truth["counts_by_store"],
                "counts_by_stage": expected_truth["counts_by_stage"],
                "line_scope_hash": expected_truth["line_scope_hash"],
            },
            "projection_matches_recorded": (
                projected_rebuilt["expected_order_ids"]
                == expected_truth["expected_order_ids"]
                and projected_rebuilt["overdue_order_ids"]
                == expected_truth["overdue_order_ids"]
                and projected_rebuilt["counts"]["orders"]
                == expected_truth["counts"]["orders"]
                and projected_rebuilt["counts"]["order_lines"]
                == expected_truth["counts"]["order_lines"]
                and projected_rebuilt["counts"]["overdue_orders"]
                == expected_truth["counts"]["overdue_orders"]
                and projected_rebuilt["counts_by_store"]
                == expected_truth["counts_by_store"]
                and projected_rebuilt["counts_by_stage"]
                == expected_truth["counts_by_stage"]
                and projected_rebuilt["line_scope_hash"]
                == expected_truth["line_scope_hash"]
            ),
        },
        "site_5_prewindow_parity": _parity_projection(
            db_path=db_path,
            ledger_path=ledger_path,
            target=target,
            before_snapshot=before_snapshot,
        ),
    }


def _known_divergences(captured: Mapping[str, Any]) -> list[dict[str, Any]]:
    synthetic = captured["synthetic"]
    return [
        {
            "id": "KNOWN_DIVERGENCE_STORE_ALIAS_COLLISION",
            "sites": [
                "validate_google_closeout_expected_orders.normalize_active_order_ids_by_store",
                "waybill_shipping_obligations.reconcile_shipping_obligations",
            ],
            "input_key": "Universal/UNIVERSAL/30000001_PP1",
            "outputs": {
                "expected_orders_normalizer": synthetic["site_2_expected_orders"][
                    "store_alias_normalization_collision"
                ],
                "obligation_normalizer": synthetic["site_3_shipping_obligations"][
                    "store_alias_active_union"
                ],
            },
        },
        {
            "id": "KNOWN_DIVERGENCE_ARCHIVE_AMBIGUITY",
            "sites": [
                "kaspi_order_stage.classify_kaspi_order_stage",
                "waybill_shipping_obligations.reconcile_shipping_obligations",
            ],
            "input_key": "archive_ambiguous",
            "outputs": {
                "stage_classifier": synthetic["site_6_stage_classifier"][
                    "archive_ambiguous"
                ],
                "obligation_classifier": synthetic[
                    "site_3_shipping_obligations"
                ]["orders"]["archive_ambiguous"],
            },
        },
        {
            "id": "KNOWN_DIVERGENCE_SAME_DAY_AFTER_CUTOFF",
            "sites": [
                "sync_google_ops_board._select_operational_rows",
                "validate_google_closeout_expected_orders.build_expected_orders_from_db",
            ],
            "input_key": "today_after_cutoff_display_alias",
            "outputs": {
                "board": synthetic["site_1_google_board"]["orders"][
                    "today_after_cutoff_display_alias"
                ],
                "expected_orders_unfiltered": synthetic[
                    "site_2_expected_orders"
                ]["unfiltered"]["orders"].get("G04"),
            },
        },
        {
            "id": "KNOWN_DIVERGENCE_OVERDUE_ACCEPTED_WITHOUT_WAYBILL",
            "sites": [
                "sync_google_ops_board._build_board_overdue_ids_by_store",
                "waybill_overdue_carryforward.get_overdue_waybill_ready_order_ids_from_db",
            ],
            "input_key": "overdue_accepted_no_waybill",
            "outputs": {
                "board": synthetic["site_1_google_board"]["orders"][
                    "overdue_accepted_no_waybill"
                ],
                "waybill_overdue_ids_by_store": synthetic[
                    "site_4_waybill_overdue"
                ],
            },
        },
        {
            "id": "KNOWN_DIVERGENCE_ACTIVE_TERMINAL_TRUST",
            "sites": [
                "validate_google_closeout_expected_orders.build_expected_orders_from_db",
                "waybill_shipping_obligations.reconcile_shipping_obligations",
            ],
            "input_key": "archive_cancelled",
            "outputs": {
                "expected_orders_active_filtered": synthetic[
                    "site_2_expected_orders"
                ]["active_filtered"]["orders"].get("G11"),
                "obligations": synthetic["site_3_shipping_obligations"]["orders"][
                    "archive_cancelled"
                ],
            },
        },
    ]


@pytest.fixture(scope="module")
def captured_outputs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("expected_status_goldens")
    captured = {
        "synthetic": _collect_synthetic(root),
        "real_2026_07_18": _collect_real_day(root),
    }
    captured["known_divergences"] = _known_divergences(captured)
    return captured


def test_synthetic_world_matches_golden(captured_outputs: Mapping[str, Any]) -> None:
    golden = _load_json(GOLDEN_PATH)
    assert captured_outputs["synthetic"] == golden["synthetic"]


def test_recorded_2026_07_18_matches_golden(
    captured_outputs: Mapping[str, Any],
) -> None:
    golden = _load_json(GOLDEN_PATH)
    assert captured_outputs["real_2026_07_18"] == golden["real_2026_07_18"]


def test_known_divergence_registry_is_exact(
    captured_outputs: Mapping[str, Any],
) -> None:
    golden = _load_json(GOLDEN_PATH)
    assert captured_outputs["known_divergences"] == golden["known_divergences"]
