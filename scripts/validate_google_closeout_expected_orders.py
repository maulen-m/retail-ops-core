#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import dump_json  # noqa: E402
from core.integrations.kaspi_order_stage import (  # noqa: E402
    StageCode,
    classify_kaspi_order_stage,
    classify_kaspi_stage_from_db_row,
)
from core.paths import data_path  # noqa: E402
from core.ops.waybill_shipping_obligations import required_line_scope_hash  # noqa: E402
from core.ops.waybill_package_count import calculate_package_count_from_lines  # noqa: E402
from core.utils.kaspi_dates import parse_kaspi_date  # noqa: E402
from core.waybill.pdf_grouper import _extract_name_core as extract_name_core  # noqa: E402
from core.utils.kaspi_name_core_resolver import (  # noqa: E402
    load_active_kaspi_name_core_maps,
    resolve_kaspi_name_core,
)
from core.utils.kaspi_order_core_overrides import load_order_name_core_overrides  # noqa: E402


READY_TO_CLOSEOUT_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
}
DEFAULT_EXPECTED_FILENAME = "expected_closeout_orders.json"
DEFAULT_GATE_FILENAME = "expected_order_manifest_gate.json"


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _has_text(value: Any) -> bool:
    text = _clean(value).lower()
    return text not in {"", "nan", "none", "nat", "null", "<na>"}


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "no", "n", "none", "nan", "nat", "null", "<na>"}


def _normalize_store_code(value: Any) -> str:
    raw = _clean(value)
    upper = raw.upper().replace(" ", "")
    aliases = {
        "STORE-B": "STOREB",
        "STORE_B": "STOREB",
        "30137883_PP1": "ACMEWEAR",
        "30000001_PP1": "UNIVERSAL",
        "30290083_PP1": "11KZ",
        "30000002_PP1": "STOREB",
        "30362323_PP1": "MELVIS",
        "PP1": "ACMEWEAR",
        "PP2": "ACMEWEAR",
    }
    return aliases.get(upper, upper)


def normalize_active_order_ids_by_store(
    active_order_ids_by_store: Mapping[str, Iterable[Any]] | None,
) -> dict[str, set[str]] | None:
    if active_order_ids_by_store is None:
        return None
    normalized: dict[str, set[str]] = {}
    for store_code, order_ids in active_order_ids_by_store.items():
        normalized_store = _normalize_store_code(store_code)
        normalized[normalized_store] = {
            order_id
            for order_id in (_clean(value) for value in order_ids)
            if order_id
        }
    return normalized


def fetch_api_active_order_ids_by_store(
    *,
    target_date: date,
    lookback_days: int,
    store_codes: Iterable[str] | None = None,
    api_since_days: int = 14,
    verbose: bool = False,
) -> dict[str, set[str]]:
    """
    Independently fetch live Kaspi delivery-stage targets for the closeout window.

    This deliberately uses the overdue-inclusive API selector rather than trusting the
    downstream download cache. If the download path regresses to exact-date filtering,
    this expected set still contains the live overdue orders that must be bundled.
    """
    from core.integrations.kaspi_api_client import STORE_TOKEN_MAP  # noqa: WPS433
    from scripts.download_waybills_api import get_target_orders_from_api  # noqa: WPS433

    selected_store_codes = [
        _normalize_store_code(store_code)
        for store_code in (store_codes if store_codes is not None else STORE_TOKEN_MAP.keys())
    ]
    selected_store_codes = [store for store in selected_store_codes if store in STORE_TOKEN_MAP]
    since_days = max(int(api_since_days), int(lookback_days or 0))
    active: dict[str, set[str]] = {}
    api_errors: list[str] = []
    for store_code in selected_store_codes:
        orders, had_error = get_target_orders_from_api(
            store_code,
            target_date,
            since_days=since_days,
            exact_date=False,
            include_overdue=True,
            all_dates=False,
            verbose=verbose,
        )
        if had_error:
            api_errors.append(store_code)
        order_ids = {
            _clean((order.get("attributes") or {}).get("code"))
            for order in orders
            if isinstance(order, Mapping)
            and classify_kaspi_order_stage(order) in READY_TO_CLOSEOUT_STAGES
        }
        active[store_code] = {order_id for order_id in order_ids if order_id}
    if api_errors:
        raise RuntimeError("API expected-order selection failed for stores: " + ", ".join(sorted(api_errors)))
    return active


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _select_expr(columns: set[str], column: str, alias: str | None = None, default: str = "NULL") -> str:
    output = alias or column
    if column in columns:
        return column if output == column else f"{column} AS {output}"
    return f"{default} AS {output}"


def _row_to_dict(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()} if isinstance(row, sqlite3.Row) else dict(row)


def _load_candidate_rows(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            raise RuntimeError("DB missing fact_orders_kaspi table")

        columns = _table_columns(conn, "fact_orders_kaspi")
        required = {"order_id", "planned_shipment_date"}
        missing = sorted(required - columns)
        if missing:
            raise RuntimeError(f"fact_orders_kaspi missing required columns: {', '.join(missing)}")

        select_parts = [
            _select_expr(columns, "id", default="NULL"),
            _select_expr(columns, "order_id"),
            _select_expr(columns, "store_code"),
            _select_expr(columns, "sku_key"),
            _select_expr(columns, "sku_id"),
            _select_expr(columns, "kaspi_offer_name"),
            _select_expr(columns, "quantity", default="1"),
            _select_expr(columns, "assigned_size"),
            _select_expr(columns, "my_size"),
            _select_expr(columns, "planned_shipment_date"),
            _select_expr(columns, "kaspi_status"),
            _select_expr(columns, "kaspi_status_detail"),
            _select_expr(columns, "internal_status"),
            _select_expr(columns, "signature_required", default="0"),
            _select_expr(columns, "pre_order", default="0"),
            _select_expr(columns, "courier_transmission_date"),
            _select_expr(columns, "actual_shipment_date"),
            _select_expr(columns, "delivery_mode"),
            _select_expr(columns, "waybill_url"),
            _select_expr(columns, "returned_to_warehouse", default="0"),
        ]
        rows = conn.execute(
            f"""
            SELECT {", ".join(select_parts)}
            FROM fact_orders_kaspi
            WHERE planned_shipment_date IS NOT NULL
              AND planned_shipment_date != ''
            """
        ).fetchall()
        candidates = [_row_to_dict(row) for row in rows]
        concrete_keys = {
            (
                _clean(row.get("order_id")),
                _normalize_store_code(row.get("store_code")),
                _clean(row.get("planned_shipment_date")),
            )
            for row in candidates
            if any(
                _has_text(row.get(field))
                for field in ("kaspi_offer_name", "sku_key", "sku_id")
            )
        }
        # Legacy import paths can leave an order-level placeholder alongside
        # concrete product rows. Preserve every terminal/handover fact from the
        # placeholder before dropping it; otherwise a duplicate row proving the
        # parcel already left the warehouse can be silently discarded.
        terminal_facts: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in candidates:
            key = (
                _clean(row.get("order_id")),
                _normalize_store_code(row.get("store_code")),
                _clean(row.get("planned_shipment_date")),
            )
            facts = terminal_facts.setdefault(key, {})
            for field in ("signature_required", "returned_to_warehouse"):
                if _is_truthy(row.get(field)):
                    facts[field] = row.get(field)
            for field in ("courier_transmission_date", "actual_shipment_date"):
                if _has_text(row.get(field)):
                    facts.setdefault(field, row.get(field))
        for row in candidates:
            key = (
                _clean(row.get("order_id")),
                _normalize_store_code(row.get("store_code")),
                _clean(row.get("planned_shipment_date")),
            )
            if key in concrete_keys:
                row.update(terminal_facts.get(key) or {})
        return [
            row
            for row in candidates
            if not (
                not any(
                    _has_text(row.get(field))
                    for field in ("kaspi_offer_name", "sku_key", "sku_id")
                )
                and (
                    _clean(row.get("order_id")),
                    _normalize_store_code(row.get("store_code")),
                    _clean(row.get("planned_shipment_date")),
                )
                in concrete_keys
            )
        ]
    finally:
        conn.close()


def load_db_open_obligation_ids_by_store(
    *,
    db_path: Path,
    target_date: date,
    allowed_store_codes: Iterable[str] | None = None,
) -> dict[str, set[str]]:
    """Return unbounded DB candidates that require fresh source-truth reconciliation.

    This is a bootstrap surface for the durable obligation ledger, not authority to
    pack. Every candidate absent from the fresh active-list selector is exact-read
    from Kaspi before it can remain active or be discharged.
    """
    allowed_stores = (
        {_normalize_store_code(value) for value in allowed_store_codes}
        if allowed_store_codes is not None
        else None
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _load_candidate_rows(Path(db_path)):
        order_id = _clean(row.get("order_id"))
        store_code = _normalize_store_code(row.get("store_code"))
        if allowed_stores is not None and store_code not in allowed_stores:
            continue
        if order_id and store_code:
            grouped.setdefault((store_code, order_id), []).append(row)

    result: dict[str, set[str]] = {}
    for (store_code, order_id), rows in sorted(grouped.items()):
        planned_dates = [
            value
            for value in (parse_kaspi_date(row.get("planned_shipment_date")) for row in rows)
            if value is not None
        ]
        if not planned_dates or min(planned_dates) > target_date:
            continue
        if any(
            _has_text(row.get("courier_transmission_date"))
            or _has_text(row.get("actual_shipment_date"))
            for row in rows
        ):
            continue
        if any(_is_truthy(row.get("signature_required")) for row in rows):
            continue
        if any(_is_truthy(row.get("pre_order")) for row in rows):
            continue
        if any(_is_truthy(row.get("returned_to_warehouse")) for row in rows):
            continue
        # Internal status is never discharge authority. Every historical row
        # without physical-handover/terminal facts remains an exact-read hint,
        # including legacy KASPI_DELIVERY + SHIPPED/COMPLETED combinations.
        result.setdefault(store_code, set()).add(order_id)
    return {store: set(order_ids) for store, order_ids in sorted(result.items())}


def build_expected_orders_from_db(
    *,
    db_path: Path,
    target_date: date,
    lookback_days: int | None,
    active_order_ids_by_store: Mapping[str, Iterable[Any]] | None = None,
    request_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the canonical order set that must be present in today's send manifest.

    This is intentionally DB-first and generated after final size writeback. It catches
    the high-cost class where the PDF/send manifest is self-consistent but silently
    omits an overdue or freshly-sized closeout order.
    """
    min_date = (
        target_date - timedelta(days=max(int(lookback_days), 0))
        if lookback_days is not None
        else None
    )
    active_lookup = normalize_active_order_ids_by_store(active_order_ids_by_store)
    expected_rows: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    excluded_by_pair: dict[tuple[str, str], list[str]] = {}
    grouped_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}

    candidate_rows = _load_candidate_rows(Path(db_path))
    core_conn = sqlite3.connect(Path(db_path))
    core_conn.row_factory = sqlite3.Row
    try:
        kaspi_core_maps = load_active_kaspi_name_core_maps(
            core_conn,
            sku_keys={_clean(row.get("sku_key")) for row in candidate_rows},
            store_offer_pairs={
                (_clean(row.get("store_code")), _clean(row.get("kaspi_offer_name")))
                for row in candidate_rows
            },
        )
    finally:
        core_conn.close()
    order_core_overrides = load_order_name_core_overrides()

    for row in candidate_rows:
        order_id = _clean(row.get("order_id"))
        if not order_id:
            excluded["missing_order_id"] += 1
            continue
        store_code = _normalize_store_code(row.get("store_code"))
        grouped_rows.setdefault((store_code, order_id), []).append(row)

    for (store_code, order_id), rows in sorted(grouped_rows.items()):
        reasons: list[str] = []
        planned_dates = [
            parsed
            for parsed in (parse_kaspi_date(row.get("planned_shipment_date")) for row in rows)
            if parsed is not None
        ]
        eligible_planned_dates = [
            planned
            for planned in planned_dates
            if planned <= target_date and (min_date is None or planned >= min_date)
        ]
        if not eligible_planned_dates:
            if not planned_dates:
                reasons.append("invalid_planned_date")
            elif all(planned > target_date for planned in planned_dates):
                reasons.append("future_planned_date")
            else:
                reasons.append("outside_lookback")

        terminal_reasons: list[str] = []
        if any(_is_truthy(row.get("signature_required")) for row in rows):
            terminal_reasons.append("signature_required")
        if any(_is_truthy(row.get("returned_to_warehouse")) for row in rows):
            terminal_reasons.append("returned_to_warehouse")
        if any(
            _has_text(row.get("courier_transmission_date"))
            or _has_text(row.get("actual_shipment_date"))
            for row in rows
        ):
            terminal_reasons.append("already_handed_over")
        if terminal_reasons:
            unique_reasons = list(dict.fromkeys(terminal_reasons))
            excluded_by_pair[(store_code, order_id)] = unique_reasons
            for reason in unique_reasons:
                excluded[reason] += 1
            continue

        line_records: list[dict[str, Any]] = []
        seen_db_row_ids: set[str] = set()
        missing_line_identity = False
        missing_line_size = False
        missing_product_identity = False
        for row in rows:
            db_row_id = _clean(row.get("id"))
            final_size = _clean(row.get("assigned_size")) or _clean(row.get("my_size"))
            if not db_row_id or db_row_id in seen_db_row_ids:
                missing_line_identity = True
                continue
            seen_db_row_ids.add(db_row_id)
            if not final_size:
                missing_line_size = True
                continue
            try:
                quantity = int(row.get("quantity") if row.get("quantity") is not None else 1)
            except (TypeError, ValueError):
                quantity = 0
            if quantity <= 0:
                reasons.append("invalid_quantity")
                continue
            sku_key = _clean(row.get("sku_key"))
            sku_id = _clean(row.get("sku_id"))
            kaspi_offer_name = _clean(row.get("kaspi_offer_name"))
            if not any((sku_key, sku_id, kaspi_offer_name)):
                missing_product_identity = True
                continue
            preferred_core = order_core_overrides.get(order_id, "")
            resolution = resolve_kaspi_name_core(
                store_code=row.get("store_code"),
                kaspi_offer_name=kaspi_offer_name,
                sku_key=sku_key,
                sku_id=sku_id,
                maps=kaspi_core_maps,
                preferred_core=preferred_core,
                preferred_source="forced_core" if preferred_core else "preferred_core",
                extract_fallback=extract_name_core,
            )
            kaspi_name_core = _clean(resolution.core)
            if not kaspi_name_core or kaspi_name_core.lower() == "unknown":
                missing_product_identity = True
                continue
            line_records.append(
                {
                    "db_row_id": db_row_id,
                    "store_code": store_code,
                    "order_id": order_id,
                    "sku_key": sku_key,
                    "sku_id": sku_id,
                    "kaspi_offer_name": kaspi_offer_name,
                    "kaspi_name_core": kaspi_name_core,
                    "quantity": quantity,
                    "assigned_size": _clean(row.get("assigned_size")),
                    "my_size": _clean(row.get("my_size")),
                    "final_size": final_size,
                }
            )
        if missing_line_identity:
            reasons.append("missing_or_duplicate_line_identity")
        if missing_line_size or not line_records:
            reasons.append("missing_size")
        if missing_product_identity:
            reasons.append("missing_product_identity")

        stages = [classify_kaspi_stage_from_db_row(row) for row in rows]
        ready_stages = [stage for stage in stages if stage in READY_TO_CLOSEOUT_STAGES]
        if active_lookup is None and not ready_stages:
            reasons.append("stage_" + (stages[0].value if stages else StageCode.UNKNOWN.value))

        if reasons:
            unique_reasons = list(dict.fromkeys(reasons))
            excluded_by_pair[(store_code, order_id)] = unique_reasons
            for reason in unique_reasons:
                excluded[reason] += 1
            continue

        if active_lookup is not None and order_id not in active_lookup.get(store_code, set()):
            excluded["not_api_active"] += 1
            continue

        planned_date = min(eligible_planned_dates)
        assigned_sizes = sorted(
            {
                _clean(row.get("assigned_size"))
                for row in rows
                if _has_text(row.get("assigned_size"))
            }
        )
        my_sizes = sorted(
            {
                _clean(row.get("my_size"))
                for row in rows
                if _has_text(row.get("my_size"))
            }
        )
        assigned_size = assigned_sizes[0] if assigned_sizes else ""
        my_size = my_sizes[0] if my_sizes else ""
        final_sizes = sorted({line["final_size"] for line in line_records})
        final_size = final_sizes[0] if len(final_sizes) == 1 else "MULTI"
        stage = ready_stages[0] if ready_stages else StageCode.ACCEPTED_PENDING_ASSEMBLY
        line_records.sort(key=lambda item: item["db_row_id"])
        expected_rows.append(
            {
                "order_id": order_id,
                "store_code": store_code,
                "planned_shipment_date": planned_date.isoformat(),
                "assigned_size": assigned_size,
                "my_size": my_size,
                "final_size": final_size,
                "lines": line_records,
                "package_count": calculate_package_count_from_lines(line_records),
                "stage": stage.value,
                "overdue": planned_date < target_date,
            }
        )

    expected_rows.sort(
        key=lambda item: (
            item["planned_shipment_date"],
            item["store_code"],
            item["order_id"],
        )
    )
    required_lines = [
        line
        for order in expected_rows
        for line in order.get("lines") or []
    ]
    line_scope_hash = required_line_scope_hash(required_lines)
    expected_order_ids = sorted({row["order_id"] for row in expected_rows})
    overdue_order_ids = sorted({row["order_id"] for row in expected_rows if row["overdue"]})
    counts_by_store: Counter[str] = Counter()
    seen_store_order_pairs: set[tuple[str, str]] = set()
    for row in expected_rows:
        store_code = row["store_code"] or "UNKNOWN"
        key = (store_code, row["order_id"])
        if key in seen_store_order_pairs:
            continue
        seen_store_order_pairs.add(key)
        counts_by_store[store_code] += 1
    counts_by_stage = Counter(row["stage"] for row in expected_rows)
    expected_pairs = {(row["store_code"], row["order_id"]) for row in expected_rows}
    active_pairs = {
        (store, order_id)
        for store, order_ids in (active_lookup or {}).items()
        for order_id in order_ids
    }
    missing_active_pairs = sorted(active_pairs - expected_pairs)
    missing_active_by_store: dict[str, list[str]] = {}
    active_order_blockers: dict[str, list[str]] = {}
    for store_code, order_id in missing_active_pairs:
        missing_active_by_store.setdefault(store_code, []).append(order_id)
        active_order_blockers[f"{store_code}:{order_id}"] = excluded_by_pair.get(
            (store_code, order_id),
            ["missing_db_row"],
        )

    return {
        "schema_version": 3,
        "ok": not missing_active_pairs,
        "generated_at": datetime.now().astimezone().isoformat(),
        "target_date": target_date.isoformat(),
        "lookback_days": int(lookback_days) if lookback_days is not None else None,
        "min_planned_shipment_date": min_date.isoformat() if min_date is not None else None,
        "request_identity": dict(request_identity or {}),
        "source": "fact_orders_kaspi_after_final_size_writeback",
        "active_order_filter": active_lookup is not None,
        "active_order_filter_counts_by_store": (
            {store: len(order_ids) for store, order_ids in sorted(active_lookup.items())}
            if active_lookup is not None
            else {}
        ),
        "expected_order_ids": expected_order_ids,
        "overdue_order_ids": overdue_order_ids,
        "orders": expected_rows,
        "line_scope_hash": line_scope_hash,
        "counts": {
            "orders": len(expected_order_ids),
            "order_lines": len(required_lines),
            "overdue_orders": len(overdue_order_ids),
            "excluded_rows": int(sum(excluded.values())),
        },
        "counts_by_store": dict(sorted(counts_by_store.items())),
        "counts_by_stage": dict(sorted(counts_by_stage.items())),
        "excluded_counts": dict(sorted(excluded.items())),
        "missing_active_order_ids_by_store": dict(sorted(missing_active_by_store.items())),
        "active_order_blockers": dict(sorted(active_order_blockers.items())),
    }


def validate_required_orders_against_db(
    *,
    required_orders: Mapping[str, Any],
    db_path: Path,
    target_date: date,
) -> dict[str, Any]:
    """Compare a loaded required-order pin with a fresh all-lines DB read."""
    fresh = build_expected_orders_from_db(
        db_path=Path(db_path),
        target_date=target_date,
        lookback_days=None,
        active_order_ids_by_store=required_orders.get("orders_by_store") or {},
        request_identity=required_orders.get("request_identity") or {},
    )
    issues: list[str] = []
    if not fresh.get("ok"):
        issues.append("required_orders_db_coverage_failed")
    if _expected_pairs_from_rows(fresh.get("orders") or []) != {
        (store, order_id)
        for store, order_ids in dict(required_orders.get("orders_by_store") or {}).items()
        for order_id in order_ids
    }:
        issues.append("required_orders_db_order_scope_mismatch")
    if required_orders.get("line_scope_required") and _clean(
        fresh.get("line_scope_hash")
    ) != _clean(required_orders.get("line_scope_hash")):
        issues.append("required_orders_db_line_scope_mismatch")
    fresh_package_counts = {
        _clean(row.get("order_id")): int(row.get("package_count") or 0)
        for row in fresh.get("orders") or []
        if isinstance(row, Mapping) and _clean(row.get("order_id"))
    }
    expected_package_counts = {
        _clean(order_id): int(count or 0)
        for order_id, count in dict(
            required_orders.get("package_counts_by_order") or {}
        ).items()
    }
    if required_orders.get("line_scope_required") and (
        fresh_package_counts != expected_package_counts
    ):
        issues.append("required_orders_db_package_count_mismatch")
    return {
        "ok": not issues,
        "issues": issues,
        "expected_line_scope_hash": _clean(required_orders.get("line_scope_hash")),
        "observed_line_scope_hash": _clean(fresh.get("line_scope_hash")),
        "expected_package_counts": expected_package_counts,
        "observed_package_counts": fresh_package_counts,
        "active_order_blockers": fresh.get("active_order_blockers") or {},
    }


def _expected_pairs_from_rows(rows: Iterable[Any]) -> set[tuple[str, str]]:
    return {
        (_normalize_store_code(row.get("store_code")), _clean(row.get("order_id")))
        for row in rows
        if isinstance(row, Mapping) and _clean(row.get("order_id"))
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return payload


def _manifest_order_ids(manifest: Mapping[str, Any]) -> list[str]:
    order_ids = [_clean(value) for value in manifest.get("send_order_ids") or []]
    if not order_ids:
        seen: set[str] = set()
        for entry in manifest.get("entries") or []:
            if not isinstance(entry, Mapping):
                continue
            for value in entry.get("order_ids") or []:
                order_id = _clean(value)
                if order_id and order_id not in seen:
                    seen.add(order_id)
                    order_ids.append(order_id)
    return sorted({order_id for order_id in order_ids if order_id})


def validate_manifest_against_expected(
    *,
    expected_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    expected = _load_json(Path(expected_path))
    manifest = _load_json(Path(manifest_path))

    expected_ids = sorted({_clean(value) for value in expected.get("expected_order_ids") or [] if _clean(value)})
    manifest_ids = _manifest_order_ids(manifest)
    expected_set = set(expected_ids)
    manifest_set = set(manifest_ids)
    overdue_set = {_clean(value) for value in expected.get("overdue_order_ids") or [] if _clean(value)}

    missing = sorted(expected_set - manifest_set)
    extra = sorted(manifest_set - expected_set)
    missing_overdue = sorted(overdue_set & set(missing))
    issue_codes: list[str] = []

    expected_target = _clean(expected.get("target_date"))
    manifest_target = _clean(manifest.get("target_date"))
    if expected_target and manifest_target and expected_target != manifest_target:
        issue_codes.append("manifest_target_date_mismatch")
    expected_request_identity = expected.get("request_identity") or {}
    manifest_request_identity = manifest.get("request_identity") or {}
    if expected_request_identity and expected_request_identity != manifest_request_identity:
        issue_codes.append("manifest_request_identity_mismatch")
    expected_sha256 = hashlib.sha256(Path(expected_path).read_bytes()).hexdigest()
    if (
        expected_request_identity
        and _clean(manifest.get("expected_orders_sha256")) != expected_sha256
    ):
        issue_codes.append("manifest_expected_orders_sha256_mismatch")
    if missing:
        issue_codes.append("expected_orders_missing_from_manifest")
    if missing_overdue:
        issue_codes.append("expected_overdue_missing_from_manifest")
    if extra:
        issue_codes.append("manifest_has_unexpected_orders")
    if len(expected_ids) != len(manifest_ids):
        issue_codes.append("manifest_order_count_mismatch")

    expected_line_scope_hash = ""
    manifest_line_scope_hash = ""
    if int(expected.get("schema_version") or 1) >= 2:
        expected_lines = [
            line
            for order in expected.get("orders") or []
            if isinstance(order, Mapping)
            for line in order.get("lines") or []
            if isinstance(line, Mapping)
        ]
        manifest_lines = [
            line
            for entry in manifest.get("entries") or []
            if isinstance(entry, Mapping)
            for line in entry.get("source_lines") or []
            if isinstance(line, Mapping)
        ]
        try:
            expected_line_scope_hash = required_line_scope_hash(expected_lines)
        except ValueError:
            issue_codes.append("expected_line_scope_invalid")
        try:
            manifest_line_scope_hash = required_line_scope_hash(manifest_lines)
        except ValueError:
            issue_codes.append("manifest_line_scope_invalid")
        if _clean(expected.get("line_scope_hash")) != expected_line_scope_hash:
            issue_codes.append("expected_line_scope_hash_mismatch")
        if _clean(manifest.get("line_scope_hash")) != manifest_line_scope_hash:
            issue_codes.append("manifest_declared_line_scope_hash_mismatch")
        if expected_line_scope_hash != manifest_line_scope_hash:
            issue_codes.append("manifest_line_size_scope_mismatch")

    manifest_counts = manifest.get("counts") if isinstance(manifest.get("counts"), Mapping) else {}
    manifest_order_count = manifest_counts.get("orders")
    try:
        if manifest_order_count is not None and int(manifest_order_count) != len(manifest_ids):
            issue_codes.append("manifest_declared_order_count_mismatch")
    except (TypeError, ValueError):
        issue_codes.append("manifest_declared_order_count_invalid")

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "ok": not issue_codes,
        "expected_path": str(Path(expected_path)),
        "manifest_path": str(Path(manifest_path)),
        "target_date": expected_target,
        "manifest_target_date": manifest_target,
        "expected_orders_sha256": expected_sha256,
        "manifest_expected_orders_sha256": _clean(manifest.get("expected_orders_sha256")),
        "expected_count": len(expected_ids),
        "manifest_count": len(manifest_ids),
        "missing_order_ids": missing,
        "extra_order_ids": extra,
        "missing_overdue_order_ids": missing_overdue,
        "expected_line_scope_hash": expected_line_scope_hash,
        "manifest_line_scope_hash": manifest_line_scope_hash,
        "issue_codes": issue_codes,
    }


def find_latest_send_manifest(today_folder: Path) -> Path | None:
    root = Path(today_folder).expanduser() / "MERGED" / "SEND"
    if not root.exists():
        return None
    candidates = sorted(
        root.glob("*/send_batch_manifest.json"),
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )
    return candidates[0] if candidates else None


def write_expected_orders_report(report: Mapping[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_path, dict(report))
    return output_path


def _resolve_date(value: str) -> date:
    text = str(value or "").strip()
    if text.lower() in {"", "today"}:
        return datetime.now().astimezone().date()
    return date.fromisoformat(text)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Google closeout expected orders against send manifest.")
    parser.add_argument("--db-path", type=Path, default=data_path("db", "app.db"))
    parser.add_argument("--target-date", default="today")
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--expected-path", type=Path, default=None)
    parser.add_argument("--manifest-path", type=Path, default=None)
    parser.add_argument("--today-folder", type=Path, default=data_path("excel_ui", "Kaspi_orders", "Today"))
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--build-expected-only", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    expected_path = args.expected_path
    if expected_path is None:
        expected_path = Path(DEFAULT_EXPECTED_FILENAME)

    if args.build_expected_only or not expected_path.exists():
        expected = build_expected_orders_from_db(
            db_path=args.db_path,
            target_date=_resolve_date(args.target_date),
            lookback_days=args.lookback_days,
        )
        write_expected_orders_report(expected, expected_path)
        if args.build_expected_only:
            print(f"Expected closeout orders: {expected_path}")
            return 0

    manifest_path = args.manifest_path or find_latest_send_manifest(args.today_folder)
    if manifest_path is None:
        raise SystemExit(f"No send_batch_manifest.json found under {Path(args.today_folder) / 'MERGED' / 'SEND'}")

    gate = validate_manifest_against_expected(expected_path=expected_path, manifest_path=manifest_path)
    if args.output_json:
        dump_json(args.output_json, gate)
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if gate.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
