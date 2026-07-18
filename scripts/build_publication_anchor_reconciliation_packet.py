#!/usr/bin/env python3
"""Build a read-only packet for workbook-anchor publication conflicts.

The packet separates three independent questions for every mismatch:

1. does the underlying source row reproduce canonical economics;
2. does the published workbook-anchor surface bind that source exactly; and
3. is the economic date backed by terminal status-change evidence.

It never edits SQLite, a workbook, or an external system.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable


class PacketError(RuntimeError):
    """Raised when pinned inputs are inconsistent or incomplete."""


CANONICAL_HASH_VERSION = "canonical-json-v1-sort-keys-utf8-no-whitespace"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _object_exists(conn: sqlite3.Connection, kind: str, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type=? AND name=?",
            (kind, name),
        ).fetchone()
        is not None
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _object_exists(conn, "table", table):
        return set()
    return {_text(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _decimal_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(_text(left)) == Decimal(_text(right))
    except (InvalidOperation, ValueError):
        return False


def _source_line_identity_proof(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
    expected_source_line_count: int,
) -> dict[str, Any]:
    required_sales = {
        "sale_id",
        "order_id",
        "store_code",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "sell_price_kzt",
        "kaspi_article",
        "source_entry_id",
        "line_identity_key",
    }
    order_columns = _table_columns(conn, "fact_orders_kaspi")
    required_orders = {
        "id",
        "order_id",
        "store_code",
        "sku_key",
        "sku_id",
        "quantity",
        "unit_price_kzt",
        "kaspi_article",
        "source_entry_id",
        "source",
    }
    if not required_sales.issubset(_table_columns(conn, "sales_fact_v2")) or not required_orders.issubset(
        order_columns
    ) or not ({"my_size", "assigned_size"} & order_columns):
        return {"proven": False, "line_count": 0, "evidence": []}
    if {"my_size", "assigned_size"}.issubset(order_columns):
        order_size_sql = "COALESCE(my_size, assigned_size)"
    elif "my_size" in order_columns:
        order_size_sql = "my_size"
    else:
        order_size_sql = "assigned_size"

    sales = [
        dict(row)
        for row in conn.execute(
            """
            SELECT sale_id, CAST(order_id AS TEXT) AS order_id,
                   UPPER(TRIM(store_code)) AS store_code,
                   sku_key, sku_id, my_size, quantity, sell_price_kzt,
                   kaspi_article, source_entry_id, line_identity_key
            FROM sales_fact_v2
            WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
            ORDER BY sale_id
            """,
            (order_id, store_code),
        )
    ]
    orders = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT id, CAST(order_id AS TEXT) AS order_id,
                   UPPER(TRIM(store_code)) AS store_code,
                   sku_key, sku_id, {order_size_sql} AS my_size,
                   quantity, unit_price_kzt, kaspi_article, source_entry_id,
                   UPPER(TRIM(source)) AS source
            FROM fact_orders_kaspi
            WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
            ORDER BY id
            """,
            (order_id, store_code),
        )
    ]
    if len(sales) != expected_source_line_count or not sales:
        return {"proven": False, "line_count": len(sales), "evidence": []}
    entry_ids = [_text(row["source_entry_id"]) for row in sales]
    if any(not value for value in entry_ids) or len(entry_ids) != len(set(entry_ids)):
        return {"proven": False, "line_count": len(sales), "evidence": []}

    evidence: list[dict[str, Any]] = []
    for sale in sales:
        entry_id = _text(sale["source_entry_id"])
        if _text(sale["line_identity_key"]) != f"ENTRY:{entry_id}":
            return {"proven": False, "line_count": len(sales), "evidence": []}
        matches = [
            order
            for order in orders
            if _text(order["source_entry_id"]) == entry_id
            and _text(order["source"]).upper() == "API"
            and _text(order["sku_key"]) == _text(sale["sku_key"])
            and _text(order["sku_id"]) == _text(sale["sku_id"])
            and _text(order["my_size"]).upper() == _text(sale["my_size"]).upper()
            and _decimal_equal(order["quantity"], sale["quantity"])
            and _decimal_equal(order["unit_price_kzt"], sale["sell_price_kzt"])
            and _text(order["kaspi_article"]) == _text(sale["kaspi_article"])
        ]
        if len(matches) != 1:
            return {"proven": False, "line_count": len(sales), "evidence": []}
        sale_payload = dict(sale)
        order_payload = dict(matches[0])
        evidence.append(
            {
                "source_entry_id": entry_id,
                "line_identity_key": _text(sale["line_identity_key"]),
                "sales_row_id": int(sale["sale_id"]),
                "sales_row_sha256": _canonical_sha(sale_payload),
                "api_order_row_id": int(matches[0]["id"]),
                "api_order_row_sha256": _canonical_sha(order_payload),
            }
        )
    return {
        "proven": True,
        "line_count": len(sales),
        "evidence": evidence,
        "evidence_sha256": _canonical_sha(evidence),
    }


def _load_derived_order_id_conflict(
    path: Path | None,
    expected_sha256: str | None,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any] | None]:
    if path is None and expected_sha256 is None:
        return {}, None
    if path is None or expected_sha256 is None:
        raise PacketError(
            "derived-order conflict evidence path and expected SHA-256 must be supplied together"
        )
    if not path.is_file():
        raise PacketError(f"derived-order conflict evidence missing: {path}")
    actual_sha = _sha256(path)
    if actual_sha != expected_sha256:
        raise PacketError(
            "derived-order conflict evidence hash mismatch: "
            f"expected {expected_sha256}, got {actual_sha}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if _text(payload.get("schema")) != "derived_order_id_conflict_packet_v2":
        raise PacketError("unsupported derived-order conflict evidence schema")
    if _text(payload.get("verdict")) != "DERIVED_ORDER_ID_CONFLICT_QUARANTINE":
        raise PacketError("derived-order conflict evidence verdict is not quarantine")
    claimed_evidence_sha = _text(payload.get("evidence_sha256"))
    canonical_payload = dict(payload)
    canonical_payload.pop("evidence_sha256", None)
    if claimed_evidence_sha != _canonical_sha(canonical_payload):
        raise PacketError("derived-order conflict evidence internal hash mismatch")
    proofs = payload.get("proofs") or {}
    required_true = {
        "derived_and_raw_ids_differ",
        "all_pinned_workbooks_match_one_safe_row",
        "derived_anchor_exists",
        "raw_anchor_absent",
        "derived_terminal_evidence_absent",
        "raw_terminal_evidence_present",
        "raw_product_identity_matches_workbook",
    }
    if any(proofs.get(key) is not True for key in required_true):
        raise PacketError("derived-order conflict evidence is missing a required proof")
    if proofs.get("production_write_authorized") is not False:
        raise PacketError("derived-order conflict evidence must prohibit production writes")
    derived_order_id = _text(payload.get("derived_order_id"))
    raw_order_id = _text(payload.get("raw_order_id"))
    store_code = _text(payload.get("expected_store")).upper()
    if not derived_order_id or not raw_order_id or not store_code:
        raise PacketError("derived-order conflict evidence has incomplete identity")
    record = {
        "raw_order_id": raw_order_id,
        "evidence_sha256": claimed_evidence_sha,
        "evidence_file_sha256": actual_sha,
        "workbook_safe_row_sha256": _text(payload.get("workbook_safe_row_sha256")),
    }
    return {(derived_order_id, store_code): record}, {
        "path": str(path.resolve()),
        "sha256": actual_sha,
        "evidence_sha256": claimed_evidence_sha,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_cash_order_rows(cash_report_path: Path) -> tuple[dict[str, Any], dict[tuple[str, str], dict[str, str]], Path]:
    report = json.loads(cash_report_path.read_text(encoding="utf-8"))
    order_rows_path = Path(_text(report.get("order_rows_csv"))).expanduser().resolve()
    if not order_rows_path.is_file():
        raise PacketError(f"cash order rows missing: {order_rows_path}")
    rows = {
        (_text(row.get("order_id")), _text(row.get("store_code")).upper()): row
        for row in _read_csv(order_rows_path)
    }
    return report, rows, order_rows_path


def _load_anchors(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    if not _object_exists(conn, "table", "fact_sales_workbook_anchor"):
        raise PacketError("fact_sales_workbook_anchor is missing")
    return {
        (_text(row["order_id"]), _text(row["store_code"]).upper()): dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM fact_sales_workbook_anchor
            ORDER BY CAST(order_id AS TEXT), UPPER(TRIM(store_code))
            """
        )
    }


def _evidence_row(
    *,
    rank: int,
    status: str,
    event_date: str,
    source: str,
    source_table: str,
    row_id: Any,
    payload: dict[str, Any],
    evidence_kind: str,
) -> dict[str, Any] | None:
    normalized_date = _text(event_date)[:10]
    if not normalized_date:
        return None
    try:
        date.fromisoformat(normalized_date)
    except ValueError:
        return None
    return {
        "rank": rank,
        "status": status,
        "event_date": normalized_date,
        "source": source,
        "source_table": source_table,
        "evidence_kind": evidence_kind,
        "row_id": _text(row_id),
        "row_preimage": payload,
        "row_sha256": _canonical_sha(payload),
    }


def _load_lifecycle_evidence(
    conn: sqlite3.Connection,
    keys: set[tuple[str, str]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    if _object_exists(conn, "table", "fact_order_status_observations"):
        for raw in conn.execute(
            """
            SELECT id, CAST(order_id AS TEXT) AS order_id,
                   UPPER(TRIM(store_code)) AS store_code,
                   UPPER(TRIM(status_internal)) AS status_internal,
                   UPPER(TRIM(source)) AS source, observed_at
            FROM fact_order_status_observations
            WHERE UPPER(TRIM(status_internal)) IN
                  ('DELIVERED', 'COMPLETED', 'CANCELLED', 'RETURNED')
            ORDER BY id
            """
        ):
            row = dict(raw)
            key = (_text(row["order_id"]), _text(row["store_code"]).upper())
            if key not in keys:
                continue
            status = _text(row["status_internal"]).upper()
            source = _text(row["source"]).upper()
            if status == "DELIVERED" and source == "WEBUI":
                rank = 1
            elif status == "COMPLETED" and source == "API":
                rank = 3
            else:
                rank = 8
            item = _evidence_row(
                rank=rank,
                status=status,
                event_date=_text(row["observed_at"]),
                source=source,
                source_table="fact_order_status_observations",
                row_id=row["id"],
                payload=row,
                evidence_kind="TERMINAL_STATUS_OBSERVATION",
            )
            if item:
                evidence[key].append(item)

    if _object_exists(conn, "table", "order_status_event"):
        for raw in conn.execute(
            """
            SELECT event_id, CAST(order_id AS TEXT) AS order_id,
                   UPPER(TRIM(store_code)) AS store_code,
                   UPPER(TRIM(stage_code)) AS stage_code,
                   UPPER(TRIM(source)) AS source, event_ts,
                   source_status_change_at, source_row_hash
            FROM order_status_event
            WHERE UPPER(TRIM(stage_code)) IN
                  ('COMPLETED', 'CANCELLED', 'RETURNED')
            ORDER BY event_id
            """
        ):
            row = dict(raw)
            key = (_text(row["order_id"]), _text(row["store_code"]).upper())
            if key not in keys:
                continue
            status = _text(row["stage_code"]).upper()
            source = _text(row["source"]).upper()
            rank = (
                2
                if status == "COMPLETED" and source == "WEBUI_STATUS_LEDGER_SCOPED"
                else 5
                if status == "COMPLETED"
                else 9
            )
            item = _evidence_row(
                rank=rank,
                status=status,
                event_date=_text(row["source_status_change_at"] or row["event_ts"]),
                source=source,
                source_table="order_status_event",
                row_id=row["event_id"],
                payload=row,
                evidence_kind=(
                    "SOURCE_STATUS_CHANGE_TIMESTAMP"
                    if _text(row["source_status_change_at"])
                    else "TERMINAL_STATUS_EVENT_OBSERVATION"
                ),
            )
            if item:
                evidence[key].append(item)

    if _object_exists(conn, "table", "fact_orders_kaspi"):
        columns = {
            _text(row[1]) for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)")
        }
        required = {
            "id",
            "order_id",
            "store_code",
            "internal_status",
            "kaspi_status",
            "source",
            "status_updated_at",
        }
        if required.issubset(columns):
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for raw in conn.execute(
                """
                SELECT id, CAST(order_id AS TEXT) AS order_id,
                       UPPER(TRIM(store_code)) AS store_code,
                       UPPER(TRIM(internal_status)) AS internal_status,
                       UPPER(TRIM(kaspi_status)) AS kaspi_status,
                       UPPER(TRIM(source)) AS source, status_updated_at
                FROM fact_orders_kaspi
                ORDER BY id
                """
            ):
                row = dict(raw)
                key = (_text(row["order_id"]), _text(row["store_code"]).upper())
                if key in keys:
                    grouped[key].append(row)
            for key, rows in grouped.items():
                for row in rows:
                    status = _text(row["internal_status"]).upper()
                    if status not in {"CANCELLED", "RETURNED"}:
                        continue
                    item = _evidence_row(
                        rank=9,
                        status=status,
                        event_date=_text(row["status_updated_at"]),
                        source=_text(row["source"]).upper(),
                        source_table="fact_orders_kaspi",
                        row_id=row["id"],
                        payload=row,
                        evidence_kind="CURRENT_API_ORDER_NEGATIVE",
                    )
                    if item:
                        evidence[key].append(item)
                complete_api_order = bool(rows) and all(
                    _text(row["internal_status"]).upper() == "COMPLETED"
                    and _text(row["kaspi_status"]).upper() == "ARCHIVE"
                    and _text(row["source"]).upper() == "API"
                    and bool(_text(row["status_updated_at"])[:10])
                    for row in rows
                )
                if not complete_api_order:
                    continue
                dates = sorted(
                    {_text(row["status_updated_at"])[:10] for row in rows}
                )
                aggregate = {
                    "order_id": key[0],
                    "store_code": key[1],
                    "complete_order_row_count": len(rows),
                    "rows": rows,
                }
                row_ids = ",".join(_text(row["id"]) for row in rows)
                for observed_date in dates:
                    item = _evidence_row(
                        rank=4,
                        status="COMPLETED",
                        event_date=observed_date,
                        source="API",
                        source_table="fact_orders_kaspi",
                        row_id=row_ids,
                        payload=aggregate,
                        evidence_kind="COMPLETE_API_ORDER_STATUS_UPDATED_AT",
                    )
                    if item:
                        evidence[key].append(item)

    return evidence


def _terminal_resolution(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    evidence = list(items)
    sort_key = lambda item: (  # noqa: E731 - shared deterministic evidence order
        int(item["rank"]),
        item["event_date"],
        item["source_table"],
        item["row_id"],
    )
    positives = sorted(
        (
            item
            for item in evidence
            if item["status"] in {"DELIVERED", "COMPLETED"}
        ),
        key=sort_key,
    )
    negatives = sorted(
        (
            item
            for item in evidence
            if item["status"] in {"CANCELLED", "RETURNED"}
        ),
        key=sort_key,
    )
    if not positives:
        return {
            "status": "NO_TERMINAL_POSITIVE",
            "canonical_date": "",
            "rank": None,
            "direct": False,
            "date_semantics": "NO_TERMINAL_DATE",
            "activation_eligible": False,
            "evidence": [],
            "all_positive_evidence": [],
            "later_positive_evidence": [],
            "negative_evidence": negatives,
            "negative_after_or_on_terminal": False,
        }
    best_rank = min(int(item["rank"]) for item in positives)
    best = [item for item in positives if int(item["rank"]) == best_rank]
    dates = sorted({item["event_date"] for item in best})
    if len(dates) != 1:
        return {
            "status": "AMBIGUOUS_TOP_RANK_TERMINAL_DATE",
            "canonical_date": "",
            "rank": best_rank,
            "direct": best_rank <= 4,
            "date_semantics": "AMBIGUOUS_TERMINAL_DATE",
            "activation_eligible": False,
            "evidence": best,
            "all_positive_evidence": positives,
            "later_positive_evidence": [],
            "negative_evidence": negatives,
            "negative_after_or_on_terminal": False,
        }
    canonical_date = dates[0]
    negative_after = any(item["event_date"] >= canonical_date for item in negatives)
    later_positives = [
        item for item in positives if item["event_date"] > canonical_date
    ]
    top_evidence_kinds = {item["evidence_kind"] for item in best}
    status_change_proven = top_evidence_kinds == {"SOURCE_STATUS_CHANGE_TIMESTAMP"}
    date_semantics = (
        "STATUS_CHANGE_TIMESTAMP_PROVEN"
        if status_change_proven
        else "TERMINAL_OBSERVATION_DATE_CANDIDATE"
    )
    direct = best_rank <= 4
    activation_eligible = direct and status_change_proven and not negative_after
    return {
        "status": (
            "NEGATIVE_LIFECYCLE_CONFLICT"
            if negative_after
            else "DIRECT_TERMINAL_STATUS_CHANGE_DATE"
            if activation_eligible
            else "DIRECT_TERMINAL_OBSERVATION_DATE_CANDIDATE"
            if direct
            else "DERIVED_TERMINAL_DATE_PROVISIONAL"
        ),
        "canonical_date": canonical_date,
        "rank": best_rank,
        "direct": direct,
        "date_semantics": date_semantics,
        "activation_eligible": activation_eligible,
        "evidence": best,
        "all_positive_evidence": positives,
        "later_positive_evidence": later_positives,
        "negative_evidence": negatives,
        "negative_after_or_on_terminal": negative_after,
    }


def _next_action(
    *,
    classification: str,
    source_formula_proven: bool,
    terminal: dict[str, Any],
    selected_dates: set[str],
    source_dates: set[str],
    statusdate_cutover: date,
    source_line_identity_proven: bool = False,
    derived_order_id_conflict_proven: bool = False,
) -> str:
    if derived_order_id_conflict_proven:
        return "QUARANTINE_DERIVED_ORDER_ID_CONFLICT"
    if classification.startswith("UNEXPLAINED_"):
        if source_line_identity_proven:
            return (
                "SOURCE_LINE_PUBLICATION_BINDING_PROOF_REQUIRED"
                if source_formula_proven
                else "SOURCE_LINE_ECONOMICS_PROOF_REQUIRED"
            )
        return "SOURCE_LINE_IDENTITY_PROOF_REQUIRED"
    if not source_formula_proven:
        return "SOURCE_FORMULA_REPAIR_REQUIRED"
    canonical_date_text = _text(terminal.get("canonical_date"))
    canonical_date = date.fromisoformat(canonical_date_text) if canonical_date_text else None
    if canonical_date is None:
        return "TERMINAL_DATE_PROOF_REQUIRED"
    if bool(terminal.get("negative_after_or_on_terminal")):
        return "QUARANTINE_LIFECYCLE_CONFLICT"
    if canonical_date < statusdate_cutover:
        return "PRE_CUTOVER_PROVISIONAL_SOURCE_VALUES_AVAILABLE"
    if not bool(terminal.get("direct")):
        return "DIRECT_TERMINAL_DATE_PROOF_REQUIRED"
    if canonical_date_text not in source_dates:
        return (
            "RECOMPUTE_SOURCE_FORMULA_AT_TERMINAL_DATE"
            if bool(terminal.get("activation_eligible"))
            else "RECOMPUTE_SOURCE_FORMULA_AT_TERMINAL_OBSERVATION_CANDIDATE_DATE"
        )
    if canonical_date_text not in selected_dates:
        return (
            "SOURCE_VALUES_READY_FOR_COPIED_PUBLICATION_REPAIR"
            if bool(terminal.get("activation_eligible"))
            else "SOURCE_VALUES_MATCH_TERMINAL_OBSERVATION_CANDIDATE"
        )
    return (
        "SOURCE_PUBLICATION_ALREADY_EXACT"
        if bool(terminal.get("activation_eligible"))
        else "SOURCE_PUBLICATION_MATCHES_OBSERVATION_CANDIDATE_UNPROVEN"
    )


def build_packet(
    *,
    db_path: Path,
    classification_csv: Path,
    cash_report_path: Path,
    output_dir: Path,
    statusdate_cutover: date,
    expected_mismatch_rows: int | None,
    expected_source_formula_proven: int | None,
    derived_order_conflict_evidence_path: Path | None = None,
    expected_derived_order_conflict_evidence_sha256: str | None = None,
) -> dict[str, Any]:
    inputs = [db_path, classification_csv, cash_report_path]
    for path in inputs:
        if not path.is_file():
            raise PacketError(f"required input missing: {path}")
    db_sha_before = _sha256(db_path)
    mismatch_rows = _read_csv(classification_csv)
    derived_order_conflicts, derived_conflict_input = _load_derived_order_id_conflict(
        derived_order_conflict_evidence_path,
        expected_derived_order_conflict_evidence_sha256,
    )
    if expected_mismatch_rows is not None and len(mismatch_rows) != expected_mismatch_rows:
        raise PacketError(
            f"mismatch row count changed: {len(mismatch_rows)}/{expected_mismatch_rows}"
        )
    cash_report, cash_rows, cash_order_rows_path = _load_cash_order_rows(cash_report_path)
    keys = {
        (_text(row.get("order_id")), _text(row.get("store_code")).upper())
        for row in mismatch_rows
    }
    if len(keys) != len(mismatch_rows):
        raise PacketError("classification rows contain duplicate order/store keys")

    with _connect_read_only(db_path) as conn:
        integrity = _text(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise PacketError(f"DB integrity failed: {integrity}")
        anchors = _load_anchors(conn)
        lifecycle = _load_lifecycle_evidence(conn, keys)
        source_line_identity = {}
        for raw in mismatch_rows:
            if not _text(raw.get("classification")).startswith("UNEXPLAINED_"):
                continue
            key = (
                _text(raw.get("order_id")),
                _text(raw.get("store_code")).upper(),
            )
            source_line_identity[key] = _source_line_identity_proof(
                conn,
                order_id=key[0],
                store_code=key[1],
                expected_source_line_count=int(
                    float(raw.get("source_line_count") or 0)
                ),
            )

    output_rows: list[dict[str, Any]] = []
    for raw in sorted(mismatch_rows, key=lambda row: (_text(row.get("store_code")), _text(row.get("order_id")))):
        order_id = _text(raw.get("order_id"))
        store_code = _text(raw.get("store_code")).upper()
        key = (order_id, store_code)
        cash = cash_rows.get(key)
        if cash is None:
            raise PacketError(f"cash diagnostic missing order/store: {key}")
        anchor = anchors.get(key)
        terminal = _terminal_resolution(lifecycle.get(key, []))
        selected_dates = set(filter(None, _text(raw.get("selected_sale_dates")).split("|")))
        source_dates = set(filter(None, _text(raw.get("source_dates")).split("|")))
        source_formula_proven = _bool(cash.get("sales_amount_source_formula_proven"))
        publication_binding_proven = _bool(
            cash.get("sales_amount_publication_binding_proven")
        )
        identity = source_line_identity.get(
            key, {"proven": False, "line_count": 0, "evidence": []}
        )
        derived_conflict = derived_order_conflicts.get(key)
        if publication_binding_proven:
            raise PacketError(f"classification contains publication-bound row: {key}")
        action = _next_action(
            classification=_text(raw.get("classification")),
            source_formula_proven=source_formula_proven,
            terminal=terminal,
            selected_dates=selected_dates,
            source_dates=source_dates,
            statusdate_cutover=statusdate_cutover,
            source_line_identity_proven=bool(identity["proven"]),
            derived_order_id_conflict_proven=derived_conflict is not None,
        )
        source_classification = _text(raw.get("classification"))
        effective_classification = (
            "DERIVED_ORDER_ID_CONFLICT_QUARANTINE"
            if derived_conflict is not None
            else "SOURCE_LINE_IDENTITY_PROVEN_ECONOMICS_UNRESOLVED"
            if source_classification.startswith("UNEXPLAINED_")
            and bool(identity["proven"])
            else source_classification
        )
        output_rows.append(
            {
                "order_id": order_id,
                "store_code": store_code,
                "classification": source_classification,
                "effective_classification": effective_classification,
                "source_formula_proven": source_formula_proven,
                "source_formula_unproven_line_count": int(
                    float(cash.get("sales_amount_source_formula_unproven_line_count") or 0)
                ),
                "publication_binding_proven": publication_binding_proven,
                "source_line_identity_proven": bool(identity["proven"]),
                "source_line_identity_count": int(identity["line_count"]),
                "source_line_identity_evidence_sha256": _text(
                    identity.get("evidence_sha256")
                ),
                "derived_order_id_conflict_proven": derived_conflict is not None,
                "derived_order_id_conflict_raw_order_id": _text(
                    (derived_conflict or {}).get("raw_order_id")
                ),
                "derived_order_id_conflict_evidence_sha256": _text(
                    (derived_conflict or {}).get("evidence_sha256")
                ),
                "selected_sale_dates": "|".join(sorted(selected_dates)),
                "source_dates": "|".join(sorted(source_dates)),
                "anchor_present": anchor is not None,
                "anchor_row_sha256": _canonical_sha(anchor) if anchor else "",
                "anchor_sale_date": _text((anchor or {}).get("sale_date")),
                "anchor_units": _text((anchor or {}).get("quantity")),
                "anchor_net_rev_kzt": _text((anchor or {}).get("net_rev_kzt")),
                "terminal_date_status": terminal["status"],
                "terminal_date": terminal["canonical_date"],
                "terminal_rank": terminal["rank"] if terminal["rank"] is not None else "",
                "terminal_direct": bool(terminal["direct"]),
                "terminal_date_semantics": terminal["date_semantics"],
                "terminal_activation_eligible": bool(
                    terminal["activation_eligible"]
                ),
                "terminal_evidence_count": len(terminal["evidence"]),
                "terminal_evidence_sha256": _canonical_sha(terminal["evidence"]),
                "terminal_all_positive_evidence_count": len(
                    terminal["all_positive_evidence"]
                ),
                "terminal_all_positive_evidence_sha256": _canonical_sha(
                    terminal["all_positive_evidence"]
                ),
                "terminal_later_positive_evidence_count": len(
                    terminal["later_positive_evidence"]
                ),
                "terminal_later_positive_evidence_sha256": _canonical_sha(
                    terminal["later_positive_evidence"]
                ),
                "terminal_negative_evidence_count": len(
                    terminal["negative_evidence"]
                ),
                "terminal_negative_evidence_sha256": _canonical_sha(
                    terminal["negative_evidence"]
                ),
                "canonical_hash_version": CANONICAL_HASH_VERSION,
                "negative_after_or_on_terminal": bool(
                    terminal["negative_after_or_on_terminal"]
                ),
                "next_action": action,
            }
        )

    db_sha_after = _sha256(db_path)
    if db_sha_after != db_sha_before:
        raise PacketError("DB bytes changed during read-only packet build")

    source_classification_counts = Counter(
        row["classification"] for row in output_rows
    )
    classification_counts = Counter(
        row["effective_classification"] for row in output_rows
    )
    action_counts = Counter(row["next_action"] for row in output_rows)
    terminal_counts = Counter(row["terminal_date_status"] for row in output_rows)
    terminal_semantics_counts = Counter(
        row["terminal_date_semantics"] for row in output_rows
    )
    terminal_activation_eligible_count = sum(
        row["terminal_activation_eligible"] for row in output_rows
    )
    terminal_later_positive_order_count = sum(
        row["terminal_later_positive_evidence_count"] > 0 for row in output_rows
    )
    source_formula_proven_count = sum(row["source_formula_proven"] for row in output_rows)
    if (
        expected_source_formula_proven is not None
        and source_formula_proven_count != expected_source_formula_proven
    ):
        raise PacketError(
            "source-formula-proven count changed: "
            f"{source_formula_proven_count}/{expected_source_formula_proven}"
        )
    manifest = {
        "schema": "publication_anchor_reconciliation_v5",
        "canonical_hash_version": CANONICAL_HASH_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "production_write_authorized": False,
        "statusdate_cutover": statusdate_cutover.isoformat(),
        "db_path": str(db_path.resolve()),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": db_sha_after,
        "db_integrity": integrity,
        "mismatch_row_count": len(output_rows),
        "source_formula_proven_count": source_formula_proven_count,
        "source_formula_unproven_count": len(output_rows) - source_formula_proven_count,
        "source_line_identity_proven_count": sum(
            row["source_line_identity_proven"] for row in output_rows
        ),
        "derived_order_id_conflict_quarantine_count": sum(
            row["derived_order_id_conflict_proven"] for row in output_rows
        ),
        "source_classification_counts": dict(
            sorted(source_classification_counts.items())
        ),
        "classification_counts": dict(sorted(classification_counts.items())),
        "terminal_date_status_counts": dict(sorted(terminal_counts.items())),
        "terminal_date_semantics_counts": dict(
            sorted(terminal_semantics_counts.items())
        ),
        "terminal_activation_eligible_count": terminal_activation_eligible_count,
        "terminal_later_positive_evidence_order_count": (
            terminal_later_positive_order_count
        ),
        "next_action_counts": dict(sorted(action_counts.items())),
        "inputs": {
            "classification_csv": {
                "path": str(classification_csv.resolve()),
                "sha256": _sha256(classification_csv),
            },
            "cash_report": {
                "path": str(cash_report_path.resolve()),
                "sha256": _sha256(cash_report_path),
            },
            "cash_order_rows": {
                "path": str(cash_order_rows_path),
                "sha256": _sha256(cash_order_rows_path),
            },
        },
        "cash_report_status": _text(cash_report.get("status")),
        "cash_covered_pairs": int(cash_report.get("covered_pairs") or 0),
    }
    if derived_conflict_input is not None:
        manifest["inputs"]["derived_order_id_conflict_evidence"] = (
            derived_conflict_input
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "publication_anchor_reconciliation.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]) if output_rows else [])
        writer.writeheader()
        writer.writerows(output_rows)
    manifest["rows_csv"] = {
        "path": str(csv_path.resolve()),
        "sha256": _sha256(csv_path),
    }
    manifest["packet_sha256"] = _canonical_sha(
        {key: value for key, value in manifest.items() if key not in {"generated_at", "packet_sha256"}}
    )
    manifest_path = output_dir / "publication_anchor_reconciliation_summary.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    closeout = output_dir / "CLOSEOUT.md"
    closeout.write_text(
        "\n".join(
            [
                "# Publication and workbook-anchor reconciliation packet",
                "",
                "Gate: YELLOW",
                "",
                "This packet is read-only and authorizes no production repair.",
                "",
                f"- mismatch rows: `{len(output_rows)}`",
                f"- raw source formula proven: `{source_formula_proven_count}`",
                f"- raw source formula unproven: `{len(output_rows) - source_formula_proven_count}`",
                f"- terminal activation eligible: `{terminal_activation_eligible_count}`",
                f"- orders with later positive terminal evidence: `{terminal_later_positive_order_count}`",
                f"- cash-covered pairs: `{manifest['cash_covered_pairs']}`",
                f"- DB SHA-256 unchanged: `{db_sha_before}`",
                "",
                "## Next-action counts",
                "",
                *[f"- `{key}`: `{value}`" for key, value in sorted(action_counts.items())],
                "",
                "No workbook, DB, cash, sales, stock, Sheet, scheduler, order, or external system was changed.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {**manifest, "manifest_path": str(manifest_path), "closeout_path": str(closeout)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--classification-csv", type=Path, required=True)
    parser.add_argument("--cash-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--statusdate-cutover", type=date.fromisoformat, default=date(2026, 2, 27))
    parser.add_argument("--expected-mismatch-rows", type=int)
    parser.add_argument("--expected-source-formula-proven", type=int)
    parser.add_argument("--derived-order-conflict-evidence", type=Path)
    parser.add_argument("--expected-derived-order-conflict-evidence-sha256")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = build_packet(
        db_path=args.db,
        classification_csv=args.classification_csv,
        cash_report_path=args.cash_report,
        output_dir=args.output_dir,
        statusdate_cutover=args.statusdate_cutover,
        expected_mismatch_rows=args.expected_mismatch_rows,
        expected_source_formula_proven=args.expected_source_formula_proven,
        derived_order_conflict_evidence_path=args.derived_order_conflict_evidence,
        expected_derived_order_conflict_evidence_sha256=(
            args.expected_derived_order_conflict_evidence_sha256
        ),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
