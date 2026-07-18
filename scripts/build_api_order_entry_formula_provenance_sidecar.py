#!/usr/bin/env python3
"""Build a deterministic API-entry formula-provenance sidecar.

This is a read-only, all-or-nothing source proof for one order/store.  It uses
immutable Kaspi entry IDs for the complete line population, one source API
order-header seller fee, and an exact source status-change timestamp.  It does
not mutate either database and exposes no raw API payload or customer PII.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import KASPI_COMMISSION, calc_net_rev  # noqa: E402
from core.config.business_params import get_vat_rate  # noqa: E402


BUILD_VERSION = "api_order_entry_formula_provenance_v1"
SAFE_API_HEADER_VERSION = "kaspi_api_order_header_safe_evidence_v1"
CANONICAL_HASH_VERSION = "canonical-json-v1-sort-keys-utf8-no-whitespace"
STATUSDATE_CUTOVER = date(2026, 2, 27)
MONEY = Decimal("0.01")
POLICY_PATHS = (
    PROJECT_ROOT / "core" / "calc" / "economics.py",
    PROJECT_ROOT / "core" / "config" / "business_params.py",
    PROJECT_ROOT / "docs" / "validation" / "SALES_ECONOMICS_TRUTH_CONTRACT.md",
)


class ApiEntryFormulaProofError(RuntimeError):
    """Raised when an all-or-nothing source proof cannot be established."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return text.encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _decimal(value: Any, *, field: str) -> Decimal:
    raw = _text(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not raw:
        raise ApiEntryFormulaProofError(f"missing numeric field: {field}")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ApiEntryFormulaProofError(f"invalid numeric field {field}: {value!r}") from exc


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal) -> str:
    return format(_money(value), ".2f")


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _require_tables(conn: sqlite3.Connection, names: set[str]) -> None:
    existing = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }
    missing = sorted(names - existing)
    if missing:
        raise ApiEntryFormulaProofError("required DB objects missing: " + ", ".join(missing))


def _decode_base64(value: str) -> str:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiEntryFormulaProofError("invalid entry relationship identity") from exc


def _raw_entry_evidence(raw_json: Any) -> dict[str, Any]:
    raw = _text(raw_json)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiEntryFormulaProofError("entry raw_json is invalid") from exc
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else payload
    attributes = entry.get("attributes") or {}
    relationships = entry.get("relationships") or {}
    pos_id = _text(
        (((relationships.get("deliveryPointOfService") or {}).get("data") or {}).get("id"))
        or entry.get("_recovery_delivery_point_of_service_id")
    )
    return {
        "raw_json_sha256": _sha256_bytes(raw.encode("utf-8")),
        "entry_id": _text(entry.get("id")),
        "offer_id": _text((attributes.get("offer") or {}).get("code")),
        "quantity": _decimal(attributes.get("quantity"), field="raw_entry.quantity"),
        "total_price_kzt": _decimal(
            attributes.get("totalPrice"), field="raw_entry.totalPrice"
        ),
        "delivery_pos": _decode_base64(pos_id),
    }


def _safe_row(row: sqlite3.Row | dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    source = dict(row)
    payload = {field: source.get(field) for field in fields}
    payload["safe_row_sha256"] = _canonical_hash(payload)
    return payload


def _policy_manifest() -> dict[str, Any]:
    files = []
    for path in POLICY_PATHS:
        if not path.exists():
            raise ApiEntryFormulaProofError(f"policy file missing: {path}")
        files.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    return {"files": files, "sha256": _canonical_hash(files)}


def _load_entries(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
    merchant_id: str,
    expected_entry_count: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT entry_id, order_id, store_code, product_id, offer_id, quantity,
               unit_price_kzt, total_price_kzt, raw_json, entry_number
        FROM fact_order_entries_kaspi
        WHERE CAST(order_id AS TEXT)=?
        ORDER BY COALESCE(entry_number, 2147483647), entry_id
        """,
        (order_id,),
    ).fetchall()
    if len(rows) != expected_entry_count:
        raise ApiEntryFormulaProofError(
            f"entry count mismatch: expected {expected_entry_count}, got {len(rows)}"
        )
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        entry_id = _text(row["entry_id"])
        if not entry_id or entry_id in seen:
            raise ApiEntryFormulaProofError("entry IDs are blank or duplicated")
        seen.add(entry_id)
        if _upper(row["store_code"]) != store_code:
            raise ApiEntryFormulaProofError(f"entry store mismatch for {entry_id}")
        raw = _raw_entry_evidence(row["raw_json"])
        quantity = _decimal(row["quantity"], field="entry.quantity")
        total_price = _decimal(row["total_price_kzt"], field="entry.total_price_kzt")
        unit_price = _decimal(row["unit_price_kzt"], field="entry.unit_price_kzt")
        offer_id = _text(row["offer_id"])
        if raw["entry_id"] != entry_id:
            raise ApiEntryFormulaProofError(f"stored/raw entry ID mismatch for {entry_id}")
        if raw["offer_id"] != offer_id:
            raise ApiEntryFormulaProofError(f"stored/raw offer mismatch for {entry_id}")
        if raw["quantity"] != quantity or _money(raw["total_price_kzt"]) != _money(total_price):
            raise ApiEntryFormulaProofError(
                f"stored/raw quantity or total mismatch for {entry_id}"
            )
        if raw["delivery_pos"] != f"{merchant_id}_PP1":
            raise ApiEntryFormulaProofError(f"delivery POS mismatch for {entry_id}")
        if quantity <= 0:
            raise ApiEntryFormulaProofError(f"entry quantity is nonpositive for {entry_id}")
        stored_unit_price = unit_price
        unit_price_source = "STORED_FIRST_PARTY_ENTRY_UNIT_PRICE"
        if unit_price <= 0:
            unit_price = total_price / quantity
            unit_price_source = "FIRST_PARTY_ENTRY_TOTAL_DIV_QUANTITY"
        if _money(unit_price * quantity) != _money(total_price):
            raise ApiEntryFormulaProofError(f"entry unit/gross mismatch for {entry_id}")
        mapping_rows = conn.execute(
            """
            SELECT id, store_code, merchant_id, kaspi_article, sku_key, sku_id,
                   active_flag, source
            FROM dim_kaspi_article_map
            WHERE UPPER(TRIM(store_code))=? AND TRIM(COALESCE(merchant_id,''))=?
              AND TRIM(kaspi_article)=? AND COALESCE(active_flag,1)=1
            ORDER BY id
            """,
            (store_code, merchant_id, offer_id),
        ).fetchall()
        if len(mapping_rows) != 1:
            raise ApiEntryFormulaProofError(
                f"exact active mapping count for {entry_id} is {len(mapping_rows)}, expected 1"
            )
        mapping = mapping_rows[0]
        size_rows = conn.execute(
            """
            SELECT sku_key, sku_id, my_size, active_flag
            FROM dim_sku_size
            WHERE sku_id=? AND COALESCE(active_flag,1)=1
            """,
            (_text(mapping["sku_id"]),),
        ).fetchall()
        if len(size_rows) != 1:
            raise ApiEntryFormulaProofError(
                f"active canonical size count for {entry_id} is {len(size_rows)}, expected 1"
            )
        size_row = size_rows[0]
        if _text(size_row["sku_key"]) != _text(mapping["sku_key"]):
            raise ApiEntryFormulaProofError(f"mapping/catalog key mismatch for {entry_id}")
        safe = {
            "entry_id": entry_id,
            "entry_number": row["entry_number"],
            "order_id": order_id,
            "store_code": store_code,
            "merchant_id": merchant_id,
            "product_id": _text(row["product_id"]),
            "offer_id": offer_id,
            "quantity": _decimal_text(quantity),
            "unit_price_kzt": _money_text(unit_price),
            "stored_unit_price_kzt": _money_text(stored_unit_price),
            "unit_price_source": unit_price_source,
            "total_price_kzt": _money_text(total_price),
            "raw_json_sha256": raw["raw_json_sha256"],
            "delivery_pos": raw["delivery_pos"],
            "mapping_row_id": int(mapping["id"]),
            "mapping_source": _text(mapping["source"]),
            "sku_key": _text(mapping["sku_key"]),
            "sku_id": _text(mapping["sku_id"]),
            "size": _upper(size_row["my_size"]),
        }
        safe["safe_evidence_sha256"] = _canonical_hash(safe)
        entries.append(safe)
    return entries


def _load_order_header(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
    gross_total: Decimal,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, order_id, store_code, quantity, unit_price_kzt,
               delivery_cost_for_seller, created_at, status_updated_at,
               kaspi_status, internal_status, source, source_file,
               line_identity_key
        FROM fact_orders_kaspi
        WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
        ORDER BY id
        """,
        (order_id, store_code),
    ).fetchall()
    if not rows:
        raise ApiEntryFormulaProofError("source order header rows are missing")
    fee_rows = [row for row in rows if row["delivery_cost_for_seller"] is not None]
    if len(fee_rows) != 1:
        raise ApiEntryFormulaProofError(
            f"order-level seller fee row count is {len(fee_rows)}, expected 1"
        )
    row = fee_rows[0]
    if _upper(row["source"]) != "API":
        raise ApiEntryFormulaProofError("seller fee row is not API-sourced")
    if _upper(row["internal_status"]) != "COMPLETED" or _upper(row["kaspi_status"]) != "ARCHIVE":
        raise ApiEntryFormulaProofError("seller fee row is not terminal COMPLETED/ARCHIVE")
    header_gross = _decimal(row["unit_price_kzt"], field="order_header.unit_price_kzt")
    if _money(header_gross) != _money(gross_total):
        raise ApiEntryFormulaProofError("order-header gross does not equal complete entry gross")
    fee = _decimal(row["delivery_cost_for_seller"], field="order_header.seller_fee")
    if fee < 0:
        raise ApiEntryFormulaProofError("order-level seller fee is negative")
    safe_fields = (
            "id",
            "order_id",
            "store_code",
            "quantity",
            "unit_price_kzt",
            "delivery_cost_for_seller",
            "created_at",
            "status_updated_at",
            "kaspi_status",
            "internal_status",
            "source",
            "source_file",
            "line_identity_key",
        )
    safe_rows = [_safe_row(candidate, safe_fields) for candidate in rows]
    safe = dict(next(item for item in safe_rows if int(item["id"]) == int(row["id"])))
    safe["source_order_row_count"] = len(rows)
    safe["source_order_non_fee_row_count"] = len(rows) - 1
    safe["source_order_rows"] = safe_rows
    safe["source_order_row_set_sha256"] = _canonical_hash(safe_rows)
    safe["seller_delivery_fee_total_kzt"] = _money_text(fee)
    safe["header_gross_total_kzt"] = _money_text(header_gross)
    safe["evidence_kind"] = "API_ORDER_HEADER_GROSS_AND_SELLER_FEE"
    return safe


def _load_safe_api_order_header(
    path: Path,
    *,
    expected_sha256: str,
    order_id: str,
    store_code: str,
    merchant_id: str,
    expected_entry_count: int,
    gross_total: Decimal,
) -> dict[str, Any]:
    """Load a strict, PII-free, hash-pinned first-party API header packet."""
    path = path.resolve()
    if not expected_sha256:
        raise ApiEntryFormulaProofError("safe API order-header SHA-256 is required")
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ApiEntryFormulaProofError("safe API order-header file/hash mismatch")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiEntryFormulaProofError("safe API order-header evidence is unreadable") from exc
    allowed_top = {
        "schema_version",
        "source_kind",
        "captured_at",
        "store_code",
        "merchant_id",
        "order_id",
        "entry_count",
        "raw_order_json_sha256",
        "raw_entries_json_sha256",
        "customer_fields_excluded",
        "attributes",
    }
    allowed_attributes = {
        "code",
        "completionDate",
        "creationDate",
        "deliveryCost",
        "deliveryCostForSeller",
        "deliveryMode",
        "paymentMode",
        "preOrder",
        "state",
        "status",
        "totalPrice",
    }
    if set(payload) != allowed_top:
        raise ApiEntryFormulaProofError("safe API order-header top-level schema mismatch")
    attributes = payload.get("attributes")
    if not isinstance(attributes, dict) or set(attributes) != allowed_attributes:
        raise ApiEntryFormulaProofError("safe API order-header attribute schema mismatch")
    if payload.get("schema_version") != SAFE_API_HEADER_VERSION:
        raise ApiEntryFormulaProofError("safe API order-header schema version mismatch")
    if payload.get("source_kind") != "FIRST_PARTY_KASPI_ORDER_API_GET":
        raise ApiEntryFormulaProofError("safe API order-header source kind mismatch")
    if payload.get("customer_fields_excluded") is not True:
        raise ApiEntryFormulaProofError("safe API order-header PII exclusion flag is invalid")
    if _text(payload.get("order_id")) != order_id or _text(attributes.get("code")) != order_id:
        raise ApiEntryFormulaProofError("safe API order-header order identity mismatch")
    if _upper(payload.get("store_code")) != store_code:
        raise ApiEntryFormulaProofError("safe API order-header store mismatch")
    if _text(payload.get("merchant_id")) != merchant_id:
        raise ApiEntryFormulaProofError("safe API order-header merchant mismatch")
    if int(payload.get("entry_count") or 0) != expected_entry_count:
        raise ApiEntryFormulaProofError("safe API order-header entry count mismatch")
    for field in ("raw_order_json_sha256", "raw_entries_json_sha256"):
        value = _text(payload.get(field)).lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ApiEntryFormulaProofError(f"safe API order-header {field} is invalid")
    if _upper(attributes.get("state")) != "ARCHIVE" or _upper(attributes.get("status")) != "COMPLETED":
        raise ApiEntryFormulaProofError("safe API order-header is not terminal COMPLETED/ARCHIVE")
    header_gross = _decimal(attributes.get("totalPrice"), field="api_header.totalPrice")
    if _money(header_gross) != _money(gross_total):
        raise ApiEntryFormulaProofError("safe API order-header gross does not equal complete entry gross")
    seller_fee = _decimal(
        attributes.get("deliveryCostForSeller"),
        field="api_header.deliveryCostForSeller",
    )
    if seller_fee < 0:
        raise ApiEntryFormulaProofError("safe API order-header seller fee is negative")
    try:
        creation_ms = int(attributes.get("creationDate"))
        completion_ms = int(attributes.get("completionDate"))
        creation_utc = datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc)
        completion_utc = datetime.fromtimestamp(completion_ms / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError) as exc:
        raise ApiEntryFormulaProofError(
            "safe API order-header creationDate/completionDate is invalid"
        ) from exc
    if completion_utc < creation_utc:
        raise ApiEntryFormulaProofError("safe API completionDate precedes creationDate")
    safe = {
        "order_id": order_id,
        "store_code": store_code,
        "merchant_id": merchant_id,
        "source": "API",
        "source_file": str(path),
        "source_file_sha256": expected_sha256,
        "source_packet_schema": SAFE_API_HEADER_VERSION,
        "captured_at": _text(payload.get("captured_at")),
        "raw_order_json_sha256": _text(payload.get("raw_order_json_sha256")).lower(),
        "raw_entries_json_sha256": _text(payload.get("raw_entries_json_sha256")).lower(),
        "source_entry_count": expected_entry_count,
        "header_gross_total_kzt": _money_text(header_gross),
        "seller_delivery_fee_total_kzt": _money_text(seller_fee),
        "created_at_utc": creation_utc.isoformat(),
        "creation_date": creation_utc.date().isoformat(),
        "completed_at_utc": completion_utc.isoformat(),
        "completion_date": completion_utc.date().isoformat(),
        "state": _upper(attributes.get("state")),
        "status": _upper(attributes.get("status")),
        "delivery_mode": _upper(attributes.get("deliveryMode")),
        "payment_mode": _upper(attributes.get("paymentMode")),
        "pre_order": bool(attributes.get("preOrder")),
        "evidence_kind": "FIRST_PARTY_API_ORDER_HEADER_GROSS_AND_SELLER_FEE",
        "customer_fields_excluded": True,
    }
    safe["safe_evidence_sha256"] = _canonical_hash(safe)
    return safe


def _precutover_creation_date_evidence(header: dict[str, Any]) -> dict[str, Any]:
    raw_date = _text(header.get("creation_date"))
    try:
        source_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ApiEntryFormulaProofError("pre-cutover source creation date is missing") from exc
    if source_date >= STATUSDATE_CUTOVER:
        raise ApiEntryFormulaProofError("creation-date fallback is forbidden after status-date cutover")
    safe = {
        "terminal_date": source_date.isoformat(),
        "evidence_kind": "CREATION_DATE_FALLBACK_PRE_CUTOVER",
        "terminal_date_semantics": "PROVISIONAL_SOURCE_DATE_NOT_STATUS_CHANGE",
        "statusdate_cutover": STATUSDATE_CUTOVER.isoformat(),
        "source_header_evidence_sha256": _text(header.get("safe_evidence_sha256")),
        "publication_binding_authorized": False,
        "decision_grade_date_authorized": False,
    }
    safe["safe_evidence_sha256"] = _canonical_hash(safe)
    return safe


def _api_completion_date_evidence(header: dict[str, Any]) -> dict[str, Any]:
    raw_date = _text(header.get("completion_date"))
    try:
        completion_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ApiEntryFormulaProofError("API completion date is missing") from exc
    safe = {
        "terminal_date": completion_date.isoformat(),
        "event_ts": _text(header.get("completed_at_utc")),
        "evidence_kind": "FIRST_PARTY_API_COMPLETION_DATE",
        "terminal_date_semantics": "STATUS_CHANGE_TIMESTAMP_PROVEN",
        "source_header_evidence_sha256": _text(header.get("safe_evidence_sha256")),
        "publication_binding_authorized": True,
        "decision_grade_date_authorized": True,
    }
    safe["safe_evidence_sha256"] = _canonical_hash(safe)
    return safe


def _load_terminal_evidence(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT event_id, order_id, store_code, stage_code, event_ts, source,
               source_status_change_at, source_run_id, source_row_hash
        FROM order_status_event
        WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
          AND UPPER(TRIM(stage_code)) IN ('COMPLETED','CANCELLED','RETURNED')
        ORDER BY event_id
        """,
        (order_id, store_code),
    ).fetchall()
    positives = [
        row
        for row in rows
        if _upper(row["stage_code"]) == "COMPLETED"
        and _text(row["source_status_change_at"])
        and _upper(row["source"]) == "WEBUI_STATUS_LEDGER_SCOPED"
    ]
    dates = {_text(row["source_status_change_at"])[:10] for row in positives}
    if len(positives) != 1 or len(dates) != 1:
        raise ApiEntryFormulaProofError(
            "exact completed source-status-change evidence is missing or ambiguous"
        )
    terminal_date = next(iter(dates))
    try:
        date.fromisoformat(terminal_date)
    except ValueError as exc:
        raise ApiEntryFormulaProofError("terminal status-change date is invalid") from exc
    negatives = [
        row
        for row in rows
        if _upper(row["stage_code"]) in {"CANCELLED", "RETURNED"}
        and _text(row["source_status_change_at"] or row["event_ts"])[:10] >= terminal_date
    ]
    if negatives:
        raise ApiEntryFormulaProofError("negative lifecycle evidence exists on/after terminal date")
    safe_fields = (
            "event_id",
            "order_id",
            "store_code",
            "stage_code",
            "event_ts",
            "source",
            "source_status_change_at",
            "source_run_id",
            "source_row_hash",
        )
    safe_rows = [_safe_row(row, safe_fields) for row in rows]
    safe = dict(
        next(
            item
            for item in safe_rows
            if int(item["event_id"]) == int(positives[0]["event_id"])
        )
    )
    safe["terminal_date"] = terminal_date
    safe["evidence_kind"] = "SOURCE_STATUS_CHANGE_TIMESTAMP"
    safe["negative_after_or_on_terminal_count"] = 0
    safe["terminal_event_row_count"] = len(rows)
    safe["terminal_event_rows"] = safe_rows
    safe["terminal_event_row_set_sha256"] = _canonical_hash(safe_rows)
    return safe


def _load_selected_lines(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    view_rows = conn.execute(
        """
        SELECT CAST(order_id AS TEXT) AS order_id, date(sale_date) AS sale_date,
               UPPER(TRIM(store_code)) AS store_code, sku_key, sku_id, my_size,
               units, net_rev_kzt, source_table, source_sku_key, source_sku_id,
               source_units, source_net_rev_kzt
        FROM view_sales_line_truth
        WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
        ORDER BY source_table, source_sku_key, source_sku_id, my_size,
                 source_units, source_net_rev_kzt
        """,
        (order_id, store_code),
    ).fetchall()
    if len(view_rows) != len(entries):
        raise ApiEntryFormulaProofError(
            f"selected view line count {len(view_rows)} does not equal entry count {len(entries)}"
        )
    view_safe = [
        _safe_row(
            row,
            (
                "order_id",
                "sale_date",
                "store_code",
                "sku_key",
                "sku_id",
                "my_size",
                "units",
                "net_rev_kzt",
                "source_table",
                "source_sku_key",
                "source_sku_id",
                "source_units",
                "source_net_rev_kzt",
            ),
        )
        for row in view_rows
    ]
    db_rows = conn.execute(
        """
        SELECT sale_id, CAST(order_id AS TEXT) AS order_id, date(order_date) AS order_date,
               UPPER(TRIM(store_code)) AS store_code, sku_key, sku_id, my_size,
               quantity, sell_price_kzt, delivery_fee, net_rev, cogs, profit,
               status, return_flag, source_file, source_entry_id, kaspi_article,
               line_identity_key
        FROM sales_fact_v2
        WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
          AND UPPER(TRIM(COALESCE(status,'DELIVERED')))='DELIVERED'
          AND COALESCE(return_flag,0)=0
        ORDER BY source_entry_id, sale_id
        """,
        (order_id, store_code),
    ).fetchall()
    if len(db_rows) != len(entries):
        raise ApiEntryFormulaProofError(
            f"selected DB line count {len(db_rows)} does not equal entry count {len(entries)}"
        )
    by_entry = {_text(row["source_entry_id"]): row for row in db_rows}
    if len(by_entry) != len(entries):
        raise ApiEntryFormulaProofError("selected DB entry identities are blank or duplicated")
    selected: list[dict[str, Any]] = []
    view_keys = {
        (
            _text(row["source_sku_key"]),
            _text(row["source_sku_id"]),
            _upper(row["my_size"]),
            _decimal_text(_decimal(row["source_units"], field="view.source_units")),
            _money_text(_decimal(row["source_net_rev_kzt"], field="view.source_net_rev")),
        )
        for row in view_rows
    }
    for entry in entries:
        row = by_entry.get(entry["entry_id"])
        if row is None:
            raise ApiEntryFormulaProofError(f"selected line missing for {entry['entry_id']}")
        expected_line_key = f"ENTRY:{entry['entry_id']}"
        checks = (
            _text(row["sku_key"]) == entry["sku_key"],
            _text(row["sku_id"]) == entry["sku_id"],
            _upper(row["my_size"]) == entry["size"],
            _text(row["kaspi_article"]) == entry["offer_id"],
            _text(row["line_identity_key"]) == expected_line_key,
            _decimal(row["quantity"], field="sales.quantity")
            == _decimal(entry["quantity"], field="entry.quantity"),
            _money(_decimal(row["sell_price_kzt"], field="sales.sell_price"))
            == _money(_decimal(entry["unit_price_kzt"], field="entry.unit_price")),
        )
        if not all(checks):
            raise ApiEntryFormulaProofError(f"selected line identity mismatch for {entry['entry_id']}")
        view_key = (
            entry["sku_key"],
            entry["sku_id"],
            entry["size"],
            entry["quantity"],
            _money_text(
                _decimal(
                    row["net_rev"] if row["net_rev"] is not None else 0,
                    field="sales.net_rev",
                )
            ),
        )
        if view_key not in view_keys:
            raise ApiEntryFormulaProofError(f"selected view/source multiset mismatch for {entry['entry_id']}")
        selected.append(
            _safe_row(
                row,
                (
                    "sale_id",
                    "order_id",
                    "order_date",
                    "store_code",
                    "sku_key",
                    "sku_id",
                    "my_size",
                    "quantity",
                    "sell_price_kzt",
                    "delivery_fee",
                    "net_rev",
                    "cogs",
                    "profit",
                    "status",
                    "return_flag",
                    "source_file",
                    "source_entry_id",
                    "kaspi_article",
                    "line_identity_key",
                ),
            )
        )
    return selected, _canonical_hash(view_safe)


def _allocate_fee(entries: list[dict[str, Any]], total_fee: Decimal) -> list[Decimal]:
    gross = [_decimal(entry["total_price_kzt"], field="entry.total") for entry in entries]
    gross_total = sum(gross, Decimal("0"))
    if gross_total <= 0:
        raise ApiEntryFormulaProofError("complete entry gross is nonpositive")
    allocations: list[Decimal] = []
    allocated = Decimal("0")
    for index, line_gross in enumerate(gross):
        if index == len(gross) - 1:
            amount = _money(total_fee - allocated)
        else:
            amount = _money(total_fee * line_gross / gross_total)
            allocated += amount
        if amount < 0:
            raise ApiEntryFormulaProofError("seller fee allocation became negative")
        allocations.append(amount)
    if sum(allocations, Decimal("0")) != _money(total_fee):
        raise ApiEntryFormulaProofError("seller fee allocation does not conserve total")
    return allocations


def _collect(
    *,
    source_db_path: Path,
    copied_db_path: Path,
    order_id: str,
    store_code: str,
    merchant_id: str,
    expected_entry_count: int,
    expected_source_db_sha256: str | None,
    expected_copied_db_sha256: str | None,
    api_order_header_evidence_path: Path | None,
    expected_api_order_header_evidence_sha256: str | None,
    allow_precutover_creation_date_fallback: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_db_path = source_db_path.resolve()
    copied_db_path = copied_db_path.resolve()
    if source_db_path == copied_db_path or os.path.samefile(source_db_path, copied_db_path):
        raise ApiEntryFormulaProofError("source and copied DB paths must be different")
    source_sha_before = sha256_file(source_db_path)
    copied_sha_before = sha256_file(copied_db_path)
    if expected_source_db_sha256 and source_sha_before != expected_source_db_sha256:
        raise ApiEntryFormulaProofError("source DB SHA-256 mismatch")
    if expected_copied_db_sha256 and copied_sha_before != expected_copied_db_sha256:
        raise ApiEntryFormulaProofError("copied DB SHA-256 mismatch")
    store_code = _upper(store_code)
    order_id = _text(order_id)
    merchant_id = _text(merchant_id)
    with _connect_readonly(source_db_path) as source_conn:
        _require_tables(
            source_conn,
            {
                "fact_order_entries_kaspi",
                "fact_orders_kaspi",
                "order_status_event",
                "dim_kaspi_article_map",
                "dim_sku_size",
            },
        )
        integrity = _text(source_conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise ApiEntryFormulaProofError(f"source DB integrity failed: {integrity}")
        entries = _load_entries(
            source_conn,
            order_id=order_id,
            store_code=store_code,
            merchant_id=merchant_id,
            expected_entry_count=expected_entry_count,
        )
        gross_total = sum(
            (_decimal(row["total_price_kzt"], field="entry.total") for row in entries),
            Decimal("0"),
        )
        if api_order_header_evidence_path is not None:
            header = _load_safe_api_order_header(
                api_order_header_evidence_path,
                expected_sha256=_text(expected_api_order_header_evidence_sha256),
                order_id=order_id,
                store_code=store_code,
                merchant_id=merchant_id,
                expected_entry_count=expected_entry_count,
                gross_total=gross_total,
            )
        else:
            header = _load_order_header(
                source_conn,
                order_id=order_id,
                store_code=store_code,
                gross_total=gross_total,
            )
        if allow_precutover_creation_date_fallback:
            if api_order_header_evidence_path is None:
                raise ApiEntryFormulaProofError(
                    "pre-cutover creation-date fallback requires safe API header evidence"
                )
            terminal = _precutover_creation_date_evidence(header)
        elif api_order_header_evidence_path is not None:
            terminal = _api_completion_date_evidence(header)
        else:
            terminal = _load_terminal_evidence(
                source_conn,
                order_id=order_id,
                store_code=store_code,
            )
    with _connect_readonly(copied_db_path) as copied_conn:
        _require_tables(copied_conn, {"sales_fact_v2", "view_sales_line_truth"})
        integrity = _text(copied_conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise ApiEntryFormulaProofError(f"copied DB integrity failed: {integrity}")
        selected, selected_multiset_sha = _load_selected_lines(
            copied_conn,
            order_id=order_id,
            store_code=store_code,
            entries=entries,
        )
    source_sha_after = sha256_file(source_db_path)
    copied_sha_after = sha256_file(copied_db_path)
    if source_sha_after != source_sha_before:
        raise ApiEntryFormulaProofError("source DB changed during read-only proof")
    if copied_sha_after != copied_sha_before:
        raise ApiEntryFormulaProofError("copied DB changed during read-only proof")
    policy = _policy_manifest()
    total_fee = _decimal(
        header["seller_delivery_fee_total_kzt"], field="order_header.seller_fee"
    )
    allocations = _allocate_fee(entries, total_fee)
    terminal_date = date.fromisoformat(terminal["terminal_date"])
    selected_by_entry = {_text(row["source_entry_id"]): row for row in selected}
    line_proofs: list[dict[str, Any]] = []
    canonical_total = Decimal("0")
    stored_total = Decimal("0")
    for entry, fee in zip(entries, allocations):
        quantity = _decimal(entry["quantity"], field="entry.quantity")
        unit_price = _decimal(entry["unit_price_kzt"], field="entry.unit_price")
        fee_unit = fee / quantity
        canonical = _money(
            Decimal(
                str(
                    calc_net_rev(
                        float(unit_price),
                        delivery_fee=float(fee_unit),
                        as_of_date=terminal_date,
                    )
                )
            )
            * quantity
        )
        selected_row = selected_by_entry[entry["entry_id"]]
        stored = (
            _money(_decimal(selected_row["net_rev"], field="selected.net_rev"))
            if selected_row["net_rev"] is not None
            else None
        )
        current_fee = (
            _money(_decimal(selected_row["delivery_fee"], field="selected.delivery_fee"))
            if selected_row["delivery_fee"] is not None
            else None
        )
        line = {
            "entry_id": entry["entry_id"],
            "line_identity_key": f"ENTRY:{entry['entry_id']}",
            "entry_evidence_sha256": entry["safe_evidence_sha256"],
            "sale_id": selected_row["sale_id"],
            "selected_row_sha256": selected_row["safe_row_sha256"],
            "selected_row_preimage": selected_row,
            "sku_key": entry["sku_key"],
            "sku_id": entry["sku_id"],
            "size": entry["size"],
            "quantity": entry["quantity"],
            "unit_sell_price_kzt": entry["unit_price_kzt"],
            "gross_line_kzt": entry["total_price_kzt"],
            "seller_delivery_fee_line_kzt": _money_text(fee),
            "seller_delivery_fee_unit_kzt": _money_text(fee_unit),
            "canonical_line_net_rev_kzt": _money_text(canonical),
            "stored_delivery_fee_line_kzt": (
                _money_text(current_fee) if current_fee is not None else None
            ),
            "stored_line_net_rev_kzt": _money_text(stored) if stored is not None else None,
            "repair_required": current_fee != fee or stored is None or stored != canonical,
        }
        line["line_proof_sha256"] = _canonical_hash(line)
        line_proofs.append(line)
        canonical_total += canonical
        stored_total += stored or Decimal("0")
    source_entry_set_sha = _canonical_hash(
        [
            {
                "entry_id": entry["entry_id"],
                "safe_evidence_sha256": entry["safe_evidence_sha256"],
            }
            for entry in entries
        ]
    )
    provisional_date = terminal.get("decision_grade_date_authorized") is False
    proof = {
        "schema_version": BUILD_VERSION,
        "proof_status": (
            "SOURCE_PROVEN_PROVISIONAL_REPAIR_CANDIDATE"
            if provisional_date
            else "SOURCE_PROVEN_REPAIR_CANDIDATE"
        ),
        "operation": "READ_ONLY_API_ORDER_ENTRY_SOURCE_FORMULA_PROOF",
        "order_id": order_id,
        "store_code": store_code,
        "merchant_id": merchant_id,
        "source_db_path": str(source_db_path),
        "source_db_sha256": source_sha_before,
        "copied_db_path": str(copied_db_path),
        "copied_db_sha256": copied_sha_before,
        "source_entry_count": len(entries),
        "source_entry_set_sha256": source_entry_set_sha,
        "selected_view_line_count": len(selected),
        "selected_view_multiset_sha256": selected_multiset_sha,
        "order_header_evidence": header,
        "terminal_evidence": terminal,
        "terminal_effective_date": terminal_date.isoformat(),
        "terminal_date_semantics": terminal.get(
            "terminal_date_semantics", "STATUS_CHANGE_TIMESTAMP_PROVEN"
        ),
        "provisional_economic_date": provisional_date,
        "publication_binding_authorized": not provisional_date,
        "decision_grade_date_authorized": not provisional_date,
        "gross_order_total_kzt": _money_text(gross_total),
        "seller_delivery_fee_order_total_kzt": _money_text(total_fee),
        "fee_allocation_method": "GROSS_LINE_PROPORTION_CENT_RESIDUAL_TO_LAST_ENTRY",
        "commission_rate": _decimal_text(Decimal(str(KASPI_COMMISSION))),
        "vat_rate": _decimal_text(Decimal(str(get_vat_rate(terminal_date)))),
        "ads_cost_unit_kzt": "0.00",
        "canonical_order_net_rev_kzt": _money_text(canonical_total),
        "stored_selected_order_net_rev_kzt": _money_text(stored_total),
        "repair_required": any(line["repair_required"] for line in line_proofs),
        "line_proofs": line_proofs,
        "economics_policy_sha256": policy["sha256"],
        "cash_evidence_used_as_formula_proof": False,
        "raw_payload_exposed": False,
        "production_apply_authorized": False,
        "copied_apply_authorized": False,
    }
    proof["proof_key"] = _canonical_hash(proof)
    manifest_core = {
        "schema_version": BUILD_VERSION,
        "canonical_hash_version": CANONICAL_HASH_VERSION,
        "operation": "READ_ONLY_API_ORDER_ENTRY_SOURCE_FORMULA_PROOF",
        "order_id": order_id,
        "store_code": store_code,
        "merchant_id": merchant_id,
        "source_db_path": str(source_db_path),
        "source_db_sha256": source_sha_before,
        "copied_db_path": str(copied_db_path),
        "copied_db_sha256": copied_sha_before,
        "source_integrity_check": "ok",
        "copied_integrity_check": "ok",
        "expected_entry_count": expected_entry_count,
        "proof_count": 1,
        "line_count": len(line_proofs),
        "excluded_count": 0,
        "source_entry_set_sha256": source_entry_set_sha,
        "selected_view_multiset_sha256": selected_multiset_sha,
        "economics_policy": policy,
        "proof_key": proof["proof_key"],
        "canonical_order_net_rev_kzt": _money_text(canonical_total),
        "provisional_economic_date": provisional_date,
        "publication_binding_authorized": not provisional_date,
        "decision_grade_date_authorized": not provisional_date,
        "api_order_header_evidence_path": (
            str(api_order_header_evidence_path.resolve())
            if api_order_header_evidence_path is not None
            else None
        ),
        "api_order_header_evidence_sha256": (
            _text(expected_api_order_header_evidence_sha256)
            if api_order_header_evidence_path is not None
            else None
        ),
        "production_apply_authorized": False,
        "copied_apply_authorized": False,
    }
    return manifest_core, proof


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def build_sidecar(
    *,
    source_db_path: Path,
    copied_db_path: Path,
    order_id: str,
    store_code: str,
    merchant_id: str,
    expected_entry_count: int,
    output_dir: Path,
    expected_source_db_sha256: str | None = None,
    expected_copied_db_sha256: str | None = None,
    api_order_header_evidence_path: Path | None = None,
    expected_api_order_header_evidence_sha256: str | None = None,
    allow_precutover_creation_date_fallback: bool = False,
) -> dict[str, Any]:
    manifest, proof = _collect(
        source_db_path=source_db_path,
        copied_db_path=copied_db_path,
        order_id=order_id,
        store_code=store_code,
        merchant_id=merchant_id,
        expected_entry_count=expected_entry_count,
        expected_source_db_sha256=expected_source_db_sha256,
        expected_copied_db_sha256=expected_copied_db_sha256,
        api_order_header_evidence_path=api_order_header_evidence_path,
        expected_api_order_header_evidence_sha256=expected_api_order_header_evidence_sha256,
        allow_precutover_creation_date_fallback=allow_precutover_creation_date_fallback,
    )
    proof_bytes = _canonical_bytes(proof) + b"\n"
    excluded_bytes = b""
    manifest["proof_file"] = "formula_provenance.jsonl"
    manifest["proof_file_sha256"] = _sha256_bytes(proof_bytes)
    manifest["excluded_file"] = "excluded.jsonl"
    manifest["excluded_file_sha256"] = _sha256_bytes(excluded_bytes)
    manifest["manifest_sha256"] = _canonical_hash(manifest)
    output_dir = output_dir.resolve()
    _write_atomic(output_dir / "formula_provenance.jsonl", proof_bytes)
    _write_atomic(output_dir / "excluded.jsonl", excluded_bytes)
    _write_atomic(output_dir / "manifest.json", _canonical_bytes(manifest, pretty=True))
    return manifest


def validate_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    internal = manifest.get("manifest_sha256")
    core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if internal != _canonical_hash(core):
        errors.append("MANIFEST_HASH_MISMATCH")
    source_path = Path(manifest.get("source_db_path", ""))
    copied_path = Path(manifest.get("copied_db_path", ""))
    if not source_path.exists() or sha256_file(source_path) != manifest.get("source_db_sha256"):
        errors.append("SOURCE_DB_HASH_DRIFT")
    if not copied_path.exists() or sha256_file(copied_path) != manifest.get("copied_db_sha256"):
        errors.append("COPIED_DB_HASH_DRIFT")
    api_header_path_raw = manifest.get("api_order_header_evidence_path")
    if api_header_path_raw:
        api_header_path = Path(str(api_header_path_raw))
        if (
            not api_header_path.exists()
            or sha256_file(api_header_path)
            != manifest.get("api_order_header_evidence_sha256")
        ):
            errors.append("API_ORDER_HEADER_EVIDENCE_HASH_DRIFT")
    for item in manifest.get("economics_policy", {}).get("files", []):
        policy_path = Path(item.get("path", ""))
        if not policy_path.exists() or sha256_file(policy_path) != item.get("sha256"):
            errors.append("ECONOMICS_POLICY_HASH_DRIFT")
            break
    proof_path = path.parent / manifest.get("proof_file", "")
    excluded_path = path.parent / manifest.get("excluded_file", "")
    if not proof_path.exists() or sha256_file(proof_path) != manifest.get("proof_file_sha256"):
        errors.append("PROOF_FILE_HASH_MISMATCH")
    if not excluded_path.exists() or sha256_file(excluded_path) != manifest.get("excluded_file_sha256"):
        errors.append("EXCLUDED_FILE_HASH_MISMATCH")
    proof_rows: list[dict[str, Any]] = []
    if proof_path.exists():
        try:
            proof_rows = [json.loads(line) for line in proof_path.read_text().splitlines() if line]
        except json.JSONDecodeError:
            errors.append("PROOF_JSON_INVALID")
    if len(proof_rows) != manifest.get("proof_count"):
        errors.append("PROOF_COUNT_MISMATCH")
    if proof_rows:
        proof = proof_rows[0]
        proof_key = proof.get("proof_key")
        proof_core = {key: value for key, value in proof.items() if key != "proof_key"}
        if proof_key != _canonical_hash(proof_core) or proof_key != manifest.get("proof_key"):
            errors.append("PROOF_KEY_MISMATCH")
        lines = proof.get("line_proofs", [])
        if len(lines) != manifest.get("line_count"):
            errors.append("LINE_COUNT_MISMATCH")
        allocated = sum(
            (_decimal(line.get("seller_delivery_fee_line_kzt"), field="proof.line_fee") for line in lines),
            Decimal("0"),
        )
        total_fee = _decimal(
            proof.get("seller_delivery_fee_order_total_kzt"), field="proof.order_fee"
        )
        if _money(allocated) != _money(total_fee):
            errors.append("FEE_ALLOCATION_NOT_CONSERVED")
        for line in lines:
            line_hash = line.get("line_proof_sha256")
            line_core = {key: value for key, value in line.items() if key != "line_proof_sha256"}
            if line_hash != _canonical_hash(line_core):
                errors.append("LINE_PROOF_HASH_MISMATCH")
                break
    return {"ok": not errors, "errors": sorted(set(errors)), "manifest_sha256": internal}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-manifest", type=Path)
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--copied-db", type=Path)
    parser.add_argument("--order-id")
    parser.add_argument("--store-code")
    parser.add_argument("--merchant-id")
    parser.add_argument("--expected-entry-count", type=int)
    parser.add_argument("--expected-source-db-sha256")
    parser.add_argument("--expected-copied-db-sha256")
    parser.add_argument("--api-order-header-evidence", type=Path)
    parser.add_argument("--expected-api-order-header-evidence-sha256")
    parser.add_argument("--allow-precutover-creation-date-fallback", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.validate_manifest:
        report = validate_manifest(args.validate_manifest)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    required = {
        "source_db": args.source_db,
        "copied_db": args.copied_db,
        "order_id": args.order_id,
        "store_code": args.store_code,
        "merchant_id": args.merchant_id,
        "expected_entry_count": args.expected_entry_count,
        "output_dir": args.output_dir,
    }
    missing = sorted(key for key, value in required.items() if value is None)
    if missing:
        parser.error("missing build arguments: " + ", ".join(missing))
    manifest = build_sidecar(
        source_db_path=args.source_db,
        copied_db_path=args.copied_db,
        order_id=args.order_id,
        store_code=args.store_code,
        merchant_id=args.merchant_id,
        expected_entry_count=args.expected_entry_count,
        output_dir=args.output_dir,
        expected_source_db_sha256=args.expected_source_db_sha256,
        expected_copied_db_sha256=args.expected_copied_db_sha256,
        api_order_header_evidence_path=args.api_order_header_evidence,
        expected_api_order_header_evidence_sha256=(
            args.expected_api_order_header_evidence_sha256
        ),
        allow_precutover_creation_date_fallback=(
            args.allow_precutover_creation_date_fallback
        ),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
