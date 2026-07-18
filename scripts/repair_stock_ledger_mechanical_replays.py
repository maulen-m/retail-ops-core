#!/usr/bin/env python3
"""Remove source-proven mechanical stock-ledger replays, backup first.

This repair is deliberately narrow:

* a coarse PO receipt is removable only when one exact fact line and one exact
  pre-existing mapped ``PO_PART`` twin prove the physical receipt already exists;
* an active quarantine leak is removable only when the existing quarantine
  contract explicitly excludes product stock; and
* a legacy SALE excess is removable only when every identity field and payload
  field matches one unique current ``sales_fact_v2`` row.

Dry-run is the default. Apply requires explicit gates, an expected pre-write
SHA/plan pin for production, a verified SQLite backup, staging-copy replay, and
an unchanged plan under ``BEGIN IMMEDIATE``.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from core.db.ledger import get_accepted_negative_active_zero_sku_ids
from scripts.backup_db import backup_database


ENV_GATE = "ENABLE_STOCK_LEDGER_MECHANICAL_REPAIR_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_STOCK_LEDGER_MECHANICAL_REPAIR_WRITE"
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT / "exports" / "validation" / "ws7_stock_ledger_repair_20260712"
)
LOCK_PATH = PROJECT_ROOT / "logs" / ".stock_ledger_mechanical_repair.lock"
QUARANTINE_TABLES = (
    "fact_order_entry_header_only_source_gap_quarantine",
    "fact_order_entry_product_identity_quarantine",
)


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity(path: Path) -> str:
    with _connect(path, readonly=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _id_hash(ids: Iterable[int]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(int(value) for value in ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_hash(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: int(item["ledger_id"])):
        digest.update(
            (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
    return digest.hexdigest()


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _candidate(row: sqlite3.Row, *, category: str, proof: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": category,
        "ledger_id": int(row["ledger_id"]),
        "event_date": _norm(row["event_date"]),
        "event_type": _upper(row["event_type"]),
        "sku_key": _norm(row["sku_key"]),
        "sku_id": _norm(row["sku_id"]),
        "my_size": _upper(row["my_size"]),
        "store_code": _upper(row["store_code"]) or "UNIVERSAL",
        "qty_change": int(row["qty_change"] or 0),
        "reference_id": _norm(row["reference_id"]),
        "reference_type": _upper(row["reference_type"]),
        "proof": proof,
    }


def _po_candidates(
    conn: sqlite3.Connection,
    *,
    batch_created_start: str,
    batch_created_end: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    rows = conn.execute(
        """
        SELECT *
        FROM stock_ledger
        WHERE UPPER(COALESCE(event_type, '')) = 'INBOUND'
          AND UPPER(COALESCE(reference_type, '')) = 'PO'
          AND notes = 'Backfill PO arrival from fact_po_lines'
          AND UPPER(COALESCE(input_source, '')) = 'SYSTEM'
          AND LOWER(COALESCE(created_by, '')) = 'system'
          AND idempotency_key IS NULL
          AND created_at BETWEEN ? AND ?
        ORDER BY ledger_id
        """,
        (batch_created_start, batch_created_end),
    ).fetchall()
    for row in rows:
        facts = conn.execute(
            """
            SELECT *
            FROM fact_po_lines
            WHERE po_id = ?
              AND sku_key = ?
              AND sku_id = ?
              AND UPPER(TRIM(my_size)) = UPPER(TRIM(?))
              AND actual_arrival_date = ?
              AND CAST(received_qty AS INTEGER) = ?
            """,
            (
                row["reference_id"],
                row["sku_key"],
                row["sku_id"],
                row["my_size"],
                row["event_date"],
                int(row["qty_change"] or 0),
            ),
        ).fetchall()
        if len(facts) != 1:
            unresolved.append(
                {
                    "reason": "PO_REPLAY_SOURCE_NOT_ONE_TO_ONE",
                    "ledger_id": int(row["ledger_id"]),
                    "source_match_count": len(facts),
                }
            )
            continue
        parts = conn.execute(
            """
            SELECT DISTINCT TRIM(po_part_id) AS po_part_id
            FROM po_line
            WHERE po_id = ?
              AND sku_id = ?
              AND UPPER(TRIM(my_size)) = UPPER(TRIM(?))
              AND COALESCE(TRIM(po_part_id), '') <> ''
            ORDER BY po_part_id
            """,
            (row["reference_id"], row["sku_id"], row["my_size"]),
        ).fetchall()
        if len(parts) != 1:
            unresolved.append(
                {
                    "reason": "PO_REPLAY_PART_MAPPING_NOT_ONE_TO_ONE",
                    "ledger_id": int(row["ledger_id"]),
                    "part_match_count": len(parts),
                }
            )
            continue
        part_id = _norm(parts[0][0])
        twins = conn.execute(
            """
            SELECT ledger_id
            FROM stock_ledger
            WHERE UPPER(COALESCE(event_type, '')) = 'INBOUND'
              AND UPPER(COALESCE(reference_type, '')) = 'PO_PART'
              AND reference_id = ?
              AND event_date = ?
              AND sku_key = ?
              AND sku_id = ?
              AND UPPER(TRIM(my_size)) = UPPER(TRIM(?))
              AND UPPER(COALESCE(store_code, 'UNIVERSAL')) =
                  UPPER(COALESCE(?, 'UNIVERSAL'))
              AND qty_change = ?
            ORDER BY ledger_id
            """,
            (
                part_id,
                row["event_date"],
                row["sku_key"],
                row["sku_id"],
                row["my_size"],
                row["store_code"],
                int(row["qty_change"] or 0),
            ),
        ).fetchall()
        if len(twins) != 1 or int(twins[0][0]) >= int(row["ledger_id"]):
            unresolved.append(
                {
                    "reason": "PO_REPLAY_TWIN_NOT_ONE_OLDER_ROW",
                    "ledger_id": int(row["ledger_id"]),
                    "twin_match_count": len(twins),
                }
            )
            continue
        candidates.append(
            _candidate(
                row,
                category="PO_REPLAY",
                proof={
                    "fact_po_line_id": int(facts[0]["id"]),
                    "mapped_po_part_id": part_id,
                    "existing_twin_ledger_id": int(twins[0][0]),
                },
            )
        )
    return candidates, unresolved


def _active_quarantine_orders(
    conn: sqlite3.Connection,
) -> tuple[dict[str, set[str]], list[dict[str, Any]]]:
    stores_by_order: dict[str, set[str]] = {}
    unresolved: list[dict[str, Any]] = []
    for table in QUARANTINE_TABLES:
        required = {
            "store_code",
            "order_id",
            "publication_exclusion_required",
            "product_stock_excluded",
            "active_flag",
        }
        if not required.issubset(_columns(conn, table)):
            continue
        rows = conn.execute(
            f"""
            SELECT store_code, order_id
            FROM {table}
            WHERE COALESCE(active_flag, 1) = 1
              AND COALESCE(publication_exclusion_required, 0) = 1
              AND COALESCE(product_stock_excluded, 0) = 1
            """
        ).fetchall()
        for row in rows:
            order_id = _norm(row["order_id"])
            if not order_id:
                continue
            stores_by_order.setdefault(order_id, set()).add(_upper(row["store_code"]) or "UNIVERSAL")
    for order_id, stores in stores_by_order.items():
        if len(stores) > 1:
            unresolved.append(
                {
                    "reason": "QUARANTINE_ORDER_REUSED_ACROSS_STORES",
                    "order_id": order_id,
                    "store_codes": sorted(stores),
                }
            )
    return stores_by_order, unresolved


def _quarantine_candidates(
    conn: sqlite3.Connection,
    *,
    stores_by_order: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for order_id, stores in sorted(stores_by_order.items()):
        if len(stores) != 1:
            continue
        rows = conn.execute(
            "SELECT * FROM stock_ledger WHERE CAST(reference_id AS TEXT) = ? ORDER BY ledger_id",
            (order_id,),
        ).fetchall()
        if not rows:
            continue
        safe = all(
            _upper(row["event_type"]) == "SALE"
            and _upper(row["reference_type"]) == "SALE"
            and int(row["qty_change"] or 0) < 0
            and _upper(row["input_source"]) == "IMPORT"
            and _norm(row["created_by"]).lower() == "system"
            and not _norm(row["notes"])
            and row["idempotency_key"] is None
            for row in rows
        )
        if not safe:
            unresolved.append(
                {
                    "reason": "QUARANTINE_LEDGER_PAYLOAD_OUTSIDE_PROVEN_LEGACY_SHAPE",
                    "order_id": order_id,
                    "ledger_ids": [int(row["ledger_id"]) for row in rows],
                }
            )
            continue
        for row in rows:
            candidates.append(
                _candidate(
                    row,
                    category="ACTIVE_QUARANTINE_STOCK_LEAK",
                    proof={
                        "quarantine_store_code": next(iter(stores)),
                        "active_flag": 1,
                        "publication_exclusion_required": 1,
                        "product_stock_excluded": 1,
                    },
                )
            )
    return candidates, unresolved


def _sale_tuple(row: sqlite3.Row) -> tuple[str, str, str, str, str, str, str, int]:
    return (
        _norm(row["reference_id"]),
        _norm(row["event_date"]),
        _norm(row["sku_key"]),
        _norm(row["sku_id"]),
        _upper(row["my_size"]),
        _norm(row["kaspi_offer_name"]),
        _upper(row["store_code"]) or "UNIVERSAL",
        int(row["qty_change"] or 0),
    )


def _source_tuple(row: sqlite3.Row) -> tuple[str, str, str, str, str, str, str, int]:
    return (
        _norm(row["order_id"]),
        _norm(row["order_date"]),
        _norm(row["sku_key"]),
        _norm(row["sku_id"]),
        _upper(row["my_size"]),
        _norm(row["kaspi_offer_name"]),
        "UNIVERSAL",
        -abs(int(row["quantity"] or 0)),
    )


def _sale_replay_candidates(
    conn: sqlite3.Connection,
    *,
    quarantine_order_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    all_sale_rows = conn.execute(
        """
        SELECT *
        FROM stock_ledger
        WHERE UPPER(COALESCE(event_type, '')) = 'SALE'
          AND UPPER(COALESCE(reference_type, '')) = 'SALE'
          AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = 'UNIVERSAL'
        ORDER BY ledger_id
        """
    ).fetchall()
    all_groups: dict[tuple[str, str, str, str, str, str, str, int], list[sqlite3.Row]] = {}
    for row in all_sale_rows:
        if _norm(row["reference_id"]) in quarantine_order_ids:
            continue
        all_groups.setdefault(_sale_tuple(row), []).append(row)

    source_groups: dict[tuple[str, str, str, str, str, str, str, int], list[sqlite3.Row]] = {}
    for source in conn.execute("SELECT * FROM sales_fact_v2 ORDER BY sale_id").fetchall():
        source_groups.setdefault(_source_tuple(source), []).append(source)

    for identity, rows in sorted(all_groups.items()):
        if len(rows) <= 1:
            continue
        sources = source_groups.get(identity, [])
        legacy_shape = all(
            _upper(row["input_source"]) == "IMPORT"
            and _norm(row["created_by"]).lower() == "system"
            and not _norm(row["notes"])
            and row["idempotency_key"] is None
            for row in rows
        )
        if len(sources) != 1:
            unresolved.append(
                {
                    "reason": (
                        "SALE_REPLAY_SOURCE_MISSING"
                        if not sources
                        else "SALE_REPLAY_SOURCE_NOT_UNIQUE_ACROSS_STORES"
                    ),
                    "ledger_ids": [int(row["ledger_id"]) for row in rows],
                    "reference_id": identity[0],
                    "sku_id": identity[3],
                    "source_match_count": len(sources),
                }
            )
            continue
        if not legacy_shape:
            unresolved.append(
                {
                    "reason": "SALE_REPLAY_GROUP_CONTAINS_NONLEGACY_EVENT",
                    "ledger_ids": [int(row["ledger_id"]) for row in rows],
                    "reference_id": identity[0],
                    "sku_id": identity[3],
                }
            )
            continue
        keep = min(rows, key=lambda row: int(row["ledger_id"]))
        for row in rows:
            if int(row["ledger_id"]) == int(keep["ledger_id"]):
                continue
            candidates.append(
                _candidate(
                    row,
                    category="EXACT_SOURCE_SALE_REPLAY",
                    proof={
                        "source_sale_id": int(sources[0]["sale_id"]),
                        "kept_ledger_id": int(keep["ledger_id"]),
                        "exact_group_size": len(rows),
                    },
                )
            )
    return candidates, unresolved


def _balances(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    rows = conn.execute(
        """
        SELECT sku_id,
               UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               COALESCE(SUM(qty_change), 0) AS balance
        FROM stock_ledger
        GROUP BY sku_id, UPPER(COALESCE(store_code, 'UNIVERSAL'))
        """
    ).fetchall()
    return {
        (_norm(row["sku_id"]), _upper(row["store_code"]) or "UNIVERSAL"): int(row["balance"] or 0)
        for row in rows
    }


def _negative_rows(
    balances: dict[tuple[str, str], int],
    *,
    accepted: set[str],
) -> list[dict[str, Any]]:
    return [
        {
            "sku_id": sku_id,
            "store_code": store_code,
            "balance": balance,
            "owner_accepted_active_zero": sku_id in accepted,
        }
        for (sku_id, store_code), balance in sorted(balances.items())
        if balance < 0
    ]


def build_mechanical_repair_plan(
    conn: sqlite3.Connection,
    *,
    batch_created_start: str,
    batch_created_end: str,
) -> dict[str, Any]:
    po, po_unresolved = _po_candidates(
        conn,
        batch_created_start=batch_created_start,
        batch_created_end=batch_created_end,
    )
    quarantine_orders, quarantine_order_unresolved = _active_quarantine_orders(conn)
    quarantine, quarantine_unresolved = _quarantine_candidates(
        conn,
        stores_by_order=quarantine_orders,
    )
    sales, sale_unresolved = _sale_replay_candidates(
        conn,
        quarantine_order_ids=set(quarantine_orders),
    )

    candidates = sorted([*po, *quarantine, *sales], key=lambda row: int(row["ledger_id"]))
    ids = [int(row["ledger_id"]) for row in candidates]
    if len(ids) != len(set(ids)):
        raise RuntimeError("candidate ledger IDs overlap across repair categories")
    unresolved = [
        *po_unresolved,
        *quarantine_order_unresolved,
        *quarantine_unresolved,
        *sale_unresolved,
    ]

    before = _balances(conn)
    projected = dict(before)
    for row in candidates:
        key = (str(row["sku_id"]), str(row["store_code"]))
        projected[key] = projected.get(key, 0) - int(row["qty_change"])
    accepted = get_accepted_negative_active_zero_sku_ids(conn)
    negative_before = _negative_rows(before, accepted=accepted)
    negative_projected = _negative_rows(projected, accepted=accepted)

    by_category: dict[str, dict[str, Any]] = {}
    for category in ("PO_REPLAY", "ACTIVE_QUARANTINE_STOCK_LEAK", "EXACT_SOURCE_SALE_REPLAY"):
        rows = [row for row in candidates if row["category"] == category]
        by_category[category] = {
            "rows": len(rows),
            "qty_change_sum": sum(int(row["qty_change"]) for row in rows),
            "id_hash": _id_hash(int(row["ledger_id"]) for row in rows),
        }

    return {
        "summary": {
            "po_replay_rows": by_category["PO_REPLAY"]["rows"],
            "po_replay_qty_change_sum": by_category["PO_REPLAY"]["qty_change_sum"],
            "quarantine_leak_rows": by_category["ACTIVE_QUARANTINE_STOCK_LEAK"]["rows"],
            "quarantine_leak_qty_change_sum": by_category["ACTIVE_QUARANTINE_STOCK_LEAK"]["qty_change_sum"],
            "sale_replay_rows": by_category["EXACT_SOURCE_SALE_REPLAY"]["rows"],
            "sale_replay_qty_change_sum": by_category["EXACT_SOURCE_SALE_REPLAY"]["qty_change_sum"],
            "candidate_rows": len(candidates),
            "candidate_qty_change_sum": sum(int(row["qty_change"]) for row in candidates),
            "unresolved_finding_count": len(unresolved),
            "negative_before_count": len(negative_before),
            "negative_before_units": sum(int(row["balance"]) for row in negative_before),
            "negative_projected_count": len(negative_projected),
            "negative_projected_units": sum(int(row["balance"]) for row in negative_projected),
            "unaccepted_negative_projected_count": sum(
                not bool(row["owner_accepted_active_zero"]) for row in negative_projected
            ),
            "unaccepted_negative_projected_units": sum(
                int(row["balance"])
                for row in negative_projected
                if not bool(row["owner_accepted_active_zero"])
            ),
        },
        "category_fingerprints": by_category,
        "candidate_id_hash": _id_hash(ids),
        "candidate_payload_hash": _payload_hash(candidates),
        "candidates": candidates,
        "unresolved": unresolved,
        "negative_before": negative_before,
        "negative_projected": negative_projected,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flattened: list[dict[str, Any]] = []
    for row in rows:
        flattened.append(
            {
                key: (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, set, tuple))
                    else value
                )
                for key, value in row.items()
            }
        )
    fields = sorted({key for row in flattened for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def _write_plan(output_root: Path, plan: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(output_root / "candidates.csv", plan["candidates"])
    _write_csv(output_root / "unresolved.csv", plan["unresolved"])
    _write_csv(output_root / "negative_before.csv", plan["negative_before"])
    _write_csv(output_root / "negative_projected.csv", plan["negative_projected"])


def _sidecars(path: Path) -> list[Path]:
    return [Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-journal")]


def _assert_apply_allowed(
    db_path: Path,
    *,
    env_gate_value: str | None,
    expected_pre_sha256: str | None,
    expected_candidate_rows: int | None,
    expected_candidate_id_hash: str | None,
) -> None:
    gate = env_gate_value if env_gate_value is not None else os.environ.get(ENV_GATE)
    if gate != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for --apply")
    if db_path.resolve() == DEFAULT_DB_PATH.resolve():
        if os.environ.get(PRODUCTION_ENV_GATE) != "1":
            raise RuntimeError(f"{PRODUCTION_ENV_GATE}=1 is required for production DB apply")
        if not expected_pre_sha256 or expected_candidate_rows is None or not expected_candidate_id_hash:
            raise RuntimeError("production apply requires expected pre-SHA, candidate count, and ID hash")


def _validate_expected(
    *,
    pre_sha256: str,
    plan: dict[str, Any],
    expected_pre_sha256: str | None,
    expected_candidate_rows: int | None,
    expected_candidate_id_hash: str | None,
) -> None:
    if expected_pre_sha256 is not None and pre_sha256 != expected_pre_sha256:
        raise RuntimeError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha256}"
        )
    actual_rows = int(plan["summary"]["candidate_rows"])
    if expected_candidate_rows is not None and actual_rows != int(expected_candidate_rows):
        raise RuntimeError(
            f"candidate count mismatch: expected {expected_candidate_rows}, got {actual_rows}"
        )
    actual_hash = str(plan["candidate_id_hash"])
    if expected_candidate_id_hash is not None and actual_hash != expected_candidate_id_hash:
        raise RuntimeError(
            f"candidate ID hash mismatch: expected {expected_candidate_id_hash}, got {actual_hash}"
        )


def _delete_candidates(conn: sqlite3.Connection, ids: list[int]) -> int:
    deleted = 0
    for start in range(0, len(ids), 800):
        chunk = ids[start : start + 800]
        placeholders = ",".join("?" for _ in chunk)
        cursor = conn.execute(
            f"DELETE FROM stock_ledger WHERE ledger_id IN ({placeholders})",
            chunk,
        )
        deleted += max(int(cursor.rowcount or 0), 0)
    return deleted


def _recompute_running_balances(
    conn: sqlite3.Connection,
    affected_pools: set[tuple[str, str]],
) -> int:
    updated = 0
    for sku_id, store_code in sorted(affected_pools):
        rows = conn.execute(
            """
            SELECT ledger_id, qty_change, running_balance
            FROM stock_ledger
            WHERE sku_id = ?
              AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
            ORDER BY ledger_id
            """,
            (sku_id, store_code),
        ).fetchall()
        running = 0
        for row in rows:
            running += int(row["qty_change"] or 0)
            if row["running_balance"] is None or int(row["running_balance"]) != running:
                conn.execute(
                    "UPDATE stock_ledger SET running_balance = ? WHERE ledger_id = ?",
                    (running, int(row["ledger_id"])),
                )
                updated += 1
    return updated


def _running_balance_mismatches(
    conn: sqlite3.Connection,
    affected_pools: set[tuple[str, str]],
) -> int:
    mismatches = 0
    for sku_id, store_code in sorted(affected_pools):
        running = 0
        for row in conn.execute(
            """
            SELECT qty_change, running_balance
            FROM stock_ledger
            WHERE sku_id = ?
              AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
            ORDER BY ledger_id
            """,
            (sku_id, store_code),
        ).fetchall():
            running += int(row["qty_change"] or 0)
            if row["running_balance"] is None or int(row["running_balance"]) != running:
                mismatches += 1
    return mismatches


def _apply_exact_plan(
    conn: sqlite3.Connection,
    *,
    plan: dict[str, Any],
) -> tuple[int, int, int]:
    ids = [int(row["ledger_id"]) for row in plan["candidates"]]
    affected = {
        (_norm(row["sku_id"]), _upper(row["store_code"]) or "UNIVERSAL")
        for row in conn.execute(
            """
            SELECT DISTINCT sku_id,
                   UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code
            FROM stock_ledger
            """
        ).fetchall()
    }
    deleted = _delete_candidates(conn, ids)
    if deleted != len(ids):
        raise RuntimeError(f"delete count mismatch: expected {len(ids)}, got {deleted}")
    running_updates = _recompute_running_balances(conn, affected)
    mismatches = _running_balance_mismatches(conn, affected)
    if mismatches:
        raise RuntimeError(f"running_balance mismatches remain in affected pools: {mismatches}")
    return deleted, running_updates, len(affected)


def _sqlite_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with _connect(source, readonly=True) as source_conn, _connect(target) as target_conn:
        source_conn.backup(target_conn)


def repair_stock_ledger_mechanical_replays(
    *,
    db_path: Path,
    output_root: Path,
    batch_created_start: str,
    batch_created_end: str,
    apply: bool = False,
    env_gate_value: str | None = None,
    expected_pre_sha256: str | None = None,
    expected_candidate_rows: int | None = None,
    expected_candidate_id_hash: str | None = None,
) -> dict[str, Any]:
    db_path = Path(db_path).resolve()
    output_root = Path(output_root).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    integrity_before = _integrity(db_path)
    if integrity_before.lower() != "ok":
        raise RuntimeError(f"pre-write integrity_check failed: {integrity_before}")
    pre_sha256 = _sha256(db_path)
    with _connect(db_path, readonly=True) as conn:
        plan = build_mechanical_repair_plan(
            conn,
            batch_created_start=batch_created_start,
            batch_created_end=batch_created_end,
        )
    _write_plan(output_root, plan)
    _validate_expected(
        pre_sha256=pre_sha256,
        plan=plan,
        expected_pre_sha256=expected_pre_sha256,
        expected_candidate_rows=expected_candidate_rows,
        expected_candidate_id_hash=expected_candidate_id_hash,
    )

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "pre_sha256": pre_sha256,
        "post_sha256": pre_sha256,
        "candidate_id_hash": plan["candidate_id_hash"],
        "candidate_payload_hash": plan["candidate_payload_hash"],
        "plan_summary": plan["summary"],
        "category_fingerprints": plan["category_fingerprints"],
        "applied": False,
        "deleted_rows": 0,
        "running_balance_rows_updated": 0,
        "affected_pools": 0,
        "backup_path": None,
        "backup_sha256": None,
        "staging_path": None,
        "staging_retained": None,
        "integrity_check": {"before": integrity_before, "backup": None, "staging": None, "after": integrity_before},
        "rollback": None,
    }
    if not apply:
        (output_root / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return summary

    _assert_apply_allowed(
        db_path,
        env_gate_value=env_gate_value,
        expected_pre_sha256=expected_pre_sha256,
        expected_candidate_rows=expected_candidate_rows,
        expected_candidate_id_hash=expected_candidate_id_hash,
    )
    if db_path.resolve() == DEFAULT_DB_PATH.resolve():
        existing_sidecars = [path for path in _sidecars(db_path) if path.exists()]
        if existing_sidecars:
            raise RuntimeError(
                "refusing production apply while SQLite sidecars exist: "
                + ", ".join(str(path) for path in existing_sidecars)
            )

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup_path = backup_database(db_path, output_root / "backups", compress=False)
        backup_integrity = _integrity(backup_path)
        if backup_integrity.lower() != "ok":
            raise RuntimeError(f"backup integrity_check failed: {backup_integrity}")
        backup_sha256 = _sha256(backup_path)
        if _sha256(db_path) != pre_sha256:
            raise RuntimeError("database SHA changed while backup was created; refusing apply")

        staging_path = output_root / "staging" / "app_stock_ledger_repair_staging.db"
        _sqlite_copy(backup_path, staging_path)
        with _connect(staging_path) as staging_conn:
            staging_conn.execute("BEGIN IMMEDIATE")
            staged_plan = build_mechanical_repair_plan(
                staging_conn,
                batch_created_start=batch_created_start,
                batch_created_end=batch_created_end,
            )
            if staged_plan["candidate_id_hash"] != plan["candidate_id_hash"]:
                raise RuntimeError("staging plan drifted from dry-run plan")
            _apply_exact_plan(staging_conn, plan=staged_plan)
            staging_conn.commit()
            staged_after = build_mechanical_repair_plan(
                staging_conn,
                batch_created_start=batch_created_start,
                batch_created_end=batch_created_end,
            )
            if int(staged_after["summary"]["candidate_rows"]) != 0:
                raise RuntimeError("staging replay left mechanical candidates")
        staging_integrity = _integrity(staging_path)
        if staging_integrity.lower() != "ok":
            raise RuntimeError(f"staging integrity_check failed: {staging_integrity}")

        with _connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            locked_plan = build_mechanical_repair_plan(
                conn,
                batch_created_start=batch_created_start,
                batch_created_end=batch_created_end,
            )
            if locked_plan["candidate_id_hash"] != plan["candidate_id_hash"]:
                conn.rollback()
                raise RuntimeError("production plan drifted under write lock")
            deleted, running_updates, affected_pools = _apply_exact_plan(conn, plan=locked_plan)
            conn.commit()

        integrity_after = _integrity(db_path)
        if integrity_after.lower() != "ok":
            raise RuntimeError(f"post-write integrity_check failed: {integrity_after}")
        with _connect(db_path, readonly=True) as conn:
            after_plan = build_mechanical_repair_plan(
                conn,
                batch_created_start=batch_created_start,
                batch_created_end=batch_created_end,
            )
        if int(after_plan["summary"]["candidate_rows"]) != 0:
            raise RuntimeError("production repair left mechanical candidates")
        staging_path.unlink(missing_ok=True)

        summary.update(
            {
                "post_sha256": _sha256(db_path),
                "applied": True,
                "deleted_rows": deleted,
                "running_balance_rows_updated": running_updates,
                "affected_pools": affected_pools,
                "backup_path": str(backup_path),
                "backup_sha256": backup_sha256,
                "staging_path": str(staging_path),
                "staging_retained": False,
                "integrity_check": {
                    "before": integrity_before,
                    "backup": backup_integrity,
                    "staging": staging_integrity,
                    "after": integrity_after,
                },
                "post_repair_plan_summary": after_plan["summary"],
                "rollback": (
                    "Stop DB writers, then restore with SQLite backup API from "
                    f"{backup_path} to {db_path}; rerun PRAGMA integrity_check and all stock gates."
                ),
            }
        )
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair source-proven stock-ledger replays")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--batch-created-start", default="2026-07-03 16:27:00")
    parser.add_argument("--batch-created-end", default="2026-07-03 16:29:59")
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--expected-candidate-rows", type=int)
    parser.add_argument("--expected-candidate-id-hash")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        summary = repair_stock_ledger_mechanical_replays(
            db_path=args.db,
            output_root=args.output_root,
            batch_created_start=args.batch_created_start,
            batch_created_end=args.batch_created_end,
            apply=bool(args.apply),
            expected_pre_sha256=args.expected_pre_sha256,
            expected_candidate_rows=args.expected_candidate_rows,
            expected_candidate_id_hash=args.expected_candidate_id_hash,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
