#!/usr/bin/env python3
"""Fetch and apply exact Kaspi API order-entry rows for approved targets.

Default: dry run. Apply requires ENABLE_EXACT_KASPI_API_ORDER_ENTRY_WRITE=1.
Production db/app.db apply additionally requires
ENABLE_EXACT_KASPI_API_ORDER_ENTRY_PROD_WRITE=1, --expected-pre-sha256, and
--backup-dir.

The script intentionally fetches only the order IDs present in the target CSV.
It does not run broad enrichment, write dimensions, or touch any external
system beyond read-only Kaspi API calls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import KaspiAPIClient  # noqa: E402
from core.sync.kaspi_order_enrichment import (  # noqa: E402
    _normalize_entry_updated_at,
    _parse_entry,
)
from scripts.backup_db import backup_database  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "exact_kaspi_api_order_entries"
WRITE_ENV_GATE = "ENABLE_EXACT_KASPI_API_ORDER_ENTRY_WRITE"
PROD_WRITE_ENV_GATE = "ENABLE_EXACT_KASPI_API_ORDER_ENTRY_PROD_WRITE"

ENTRY_INSERT_COLUMNS = [
    "entry_id",
    "order_id",
    "store_code",
    "product_id",
    "offer_id",
    "quantity",
    "unit_price_kzt",
    "total_price_kzt",
    "unit_type",
    "min_allowed_weight",
    "weight_kg",
    "entry_number",
    "category_code",
    "category_title",
    "delivery_cost_kzt",
    "base_price_kzt",
    "point_of_service_id",
    "delivery_point_of_service_id",
    "raw_json",
    "updated_at",
]


class ExactKaspiApiOrderEntryError(RuntimeError):
    """Raised when exact order-entry repair cannot prove safety."""


@dataclass(frozen=True)
class TargetOrder:
    order_id: str
    store_code: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.order_id, self.store_code)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        conn.close()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise ExactKaspiApiOrderEntryError(f"refusing exact order-entry apply while SQLite sidecars exist: {joined}")


def _is_production_db(db_path: Path) -> bool:
    return db_path.resolve() == DEFAULT_DB.resolve()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _load_dotenv_if_available() -> None:
    dotenv_path = PROJECT_ROOT / ".env"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(dotenv_path=dotenv_path, override=False)


def _read_targets(path: Path, *, store_code: str | None = None) -> list[TargetOrder]:
    if not path.exists():
        raise ExactKaspiApiOrderEntryError(f"target order CSV not found: {path}")
    targets: list[TargetOrder] = []
    seen: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"order_id", "store_code"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ExactKaspiApiOrderEntryError(f"target order CSV must contain columns: {sorted(required)}")
        for row in reader:
            order_id = str(row.get("order_id") or "").strip()
            store = str(row.get("store_code") or "").strip().upper()
            if not order_id or not store:
                continue
            if store_code and store != store_code.strip().upper():
                raise ExactKaspiApiOrderEntryError(
                    f"target order {order_id} store mismatch: expected {store_code.upper()}, got {store}"
                )
            target = TargetOrder(order_id=order_id, store_code=store)
            if target.key in seen:
                raise ExactKaspiApiOrderEntryError(f"duplicate target order in CSV: {order_id}/{store}")
            seen.add(target.key)
            targets.append(target)
    if not targets:
        raise ExactKaspiApiOrderEntryError("target order CSV contained no targets")
    return targets


def _split_expected_ids(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [part for part in re.split(r"[|;,\s]+", raw) if part]


def _read_expected_entry_summary(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if path is None:
        return {}
    if not path.exists():
        raise ExactKaspiApiOrderEntryError(f"expected entry summary CSV not found: {path}")
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"order_id", "store_code", "entry_rows", "entry_ids"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ExactKaspiApiOrderEntryError(f"expected entry summary CSV must contain columns: {sorted(required)}")
        for row in reader:
            order_id = str(row.get("order_id") or "").strip()
            store = str(row.get("store_code") or "").strip().upper()
            if not order_id or not store:
                continue
            expected[(order_id, store)] = {
                "entry_rows": int(float(row.get("entry_rows") or 0)),
                "entry_ids": _split_expected_ids(str(row.get("entry_ids") or "")),
                "quantity": float(row["quantity"]) if str(row.get("quantity") or "").strip() else None,
                "total_price": float(row["total_price"]) if str(row.get("total_price") or "").strip() else None,
            }
    return expected


def _sanitized_entry(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": parsed.get("entry_id"),
        "order_id": parsed.get("order_id"),
        "store_code": parsed.get("store_code"),
        "product_id": parsed.get("product_id"),
        "offer_id": parsed.get("offer_id"),
        "quantity": parsed.get("quantity"),
        "unit_price_kzt": parsed.get("unit_price_kzt"),
        "total_price_kzt": parsed.get("total_price_kzt"),
        "point_of_service_id": parsed.get("point_of_service_id"),
        "updated_at": parsed.get("updated_at"),
    }


def _prepare_preconditions(
    conn: sqlite3.Connection,
    targets: list[TargetOrder],
    *,
    as_of: str,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], str]]:
    for table in ("fact_orders_kaspi", "fact_order_entries_kaspi", "sales_fact_v2"):
        if not _table_exists(conn, table):
            raise ExactKaspiApiOrderEntryError(f"missing required table: {table}")

    preconditions: list[dict[str, Any]] = []
    updated_at_by_target: dict[tuple[str, str], str] = {}
    for target in targets:
        order_rows = conn.execute(
            """
            SELECT order_id, store_code, status_updated_at, actual_shipment_date, planned_shipment_date, created_at
            FROM fact_orders_kaspi
            WHERE CAST(order_id AS TEXT)=?
              AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
            ORDER BY COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at) DESC
            """,
            (target.order_id, target.store_code),
        ).fetchall()
        if not order_rows:
            raise ExactKaspiApiOrderEntryError(f"target order header missing: {target.order_id}/{target.store_code}")
        sales_fact_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM sales_fact_v2
                WHERE CAST(order_id AS TEXT)=?
                  AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
                """,
                (target.order_id, target.store_code),
            ).fetchone()[0]
        )
        if sales_fact_count <= 0:
            raise ExactKaspiApiOrderEntryError(f"target sales_fact_v2 row missing: {target.order_id}/{target.store_code}")
        existing_entry_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM fact_order_entries_kaspi
                WHERE CAST(order_id AS TEXT)=?
                  AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
                """,
                (target.order_id, target.store_code),
            ).fetchone()[0]
        )
        if existing_entry_count != 0:
            raise ExactKaspiApiOrderEntryError(
                f"target already has order-entry rows: {target.order_id}/{target.store_code} count={existing_entry_count}"
            )
        updated_at = _normalize_entry_updated_at(order_rows[0], max_date=as_of)
        updated_at_by_target[target.key] = updated_at
        preconditions.append(
            {
                "order_id": target.order_id,
                "store_code": target.store_code,
                "fact_orders_rows": len(order_rows),
                "sales_fact_v2_rows": sales_fact_count,
                "existing_entry_rows": existing_entry_count,
                "entry_updated_at": updated_at,
            }
        )
    return preconditions, updated_at_by_target


def _fetch_entries(
    targets: list[TargetOrder],
    *,
    updated_at_by_target: dict[tuple[str, str], str],
    client_factory: Callable[[str], Any],
) -> list[dict[str, Any]]:
    clients: dict[str, Any] = {}
    parsed_entries: list[dict[str, Any]] = []
    seen_entry_ids: set[str] = set()
    for target in targets:
        client = clients.setdefault(target.store_code, client_factory(target.store_code))
        response = client.get_order_entries(target.order_id)
        if not getattr(response, "success", False):
            error = str(getattr(response, "error", "") or "unknown error")
            raise ExactKaspiApiOrderEntryError(f"Kaspi API order entries fetch failed for {target.order_id}: {error}")
        payload = getattr(response, "data", None) or {}
        entries = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ExactKaspiApiOrderEntryError(f"Kaspi API returned non-list entries for {target.order_id}")
        for entry in entries:
            parsed = _parse_entry(entry, target.order_id, target.store_code)
            if not parsed.get("entry_id"):
                raise ExactKaspiApiOrderEntryError(f"Kaspi API entry missing id for {target.order_id}")
            parsed_order_id = str(parsed.get("order_id") or "").strip()
            if parsed_order_id and parsed_order_id != target.order_id:
                parsed["api_relationship_order_id"] = parsed_order_id
            parsed["order_id"] = target.order_id
            parsed["store_code"] = target.store_code
            parsed["updated_at"] = updated_at_by_target[target.key]
            entry_id = str(parsed["entry_id"])
            if entry_id in seen_entry_ids:
                raise ExactKaspiApiOrderEntryError(f"duplicate fetched entry id: {entry_id}")
            seen_entry_ids.add(entry_id)
            parsed_entries.append(parsed)
    return parsed_entries


def _validate_expected_summary(
    targets: list[TargetOrder],
    fetched_entries: list[dict[str, Any]],
    expected_summary: dict[tuple[str, str], dict[str, Any]],
) -> None:
    if not expected_summary:
        return
    target_keys = {target.key for target in targets}
    extra_keys = sorted(set(expected_summary) - target_keys)
    if extra_keys:
        raise ExactKaspiApiOrderEntryError(f"expected entry summary contains non-target rows: {extra_keys}")
    by_target: dict[tuple[str, str], list[dict[str, Any]]] = {target.key: [] for target in targets}
    for entry in fetched_entries:
        by_target[(str(entry["order_id"]), str(entry["store_code"]).upper())].append(entry)
    for target in targets:
        expected = expected_summary.get(target.key)
        if expected is None:
            raise ExactKaspiApiOrderEntryError(
                f"expected entry summary missing target: {target.order_id}/{target.store_code}"
            )
        entries = by_target[target.key]
        if len(entries) != int(expected["entry_rows"]):
            raise ExactKaspiApiOrderEntryError(
                f"entry_rows mismatch for {target.order_id}/{target.store_code}: "
                f"expected {expected['entry_rows']}, got {len(entries)}"
            )
        expected_ids = sorted(str(value) for value in expected.get("entry_ids") or [])
        observed_ids = sorted(str(entry["entry_id"]) for entry in entries)
        if expected_ids and observed_ids != expected_ids:
            raise ExactKaspiApiOrderEntryError(
                f"entry_ids mismatch for {target.order_id}/{target.store_code}: "
                f"expected {expected_ids}, got {observed_ids}"
            )
        expected_quantity = expected.get("quantity")
        if expected_quantity is not None:
            observed_quantity = sum(float(entry.get("quantity") or 0.0) for entry in entries)
            if abs(observed_quantity - float(expected_quantity)) > 0.0001:
                raise ExactKaspiApiOrderEntryError(
                    f"quantity mismatch for {target.order_id}/{target.store_code}: "
                    f"expected {expected_quantity}, got {observed_quantity}"
                )
        expected_total = expected.get("total_price")
        if expected_total is not None:
            observed_total = sum(float(entry.get("total_price_kzt") or 0.0) for entry in entries)
            if abs(observed_total - float(expected_total)) > 0.0001:
                raise ExactKaspiApiOrderEntryError(
                    f"total_price mismatch for {target.order_id}/{target.store_code}: "
                    f"expected {expected_total}, got {observed_total}"
                )


def _existing_entry_ids(conn: sqlite3.Connection, entry_ids: list[str]) -> list[str]:
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"SELECT entry_id FROM fact_order_entries_kaspi WHERE entry_id IN ({placeholders})",
        entry_ids,
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _entry_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0])


def _insert_entries(conn: sqlite3.Connection, entries: list[dict[str, Any]]) -> int:
    cols = _columns(conn, "fact_order_entries_kaspi")
    missing = [col for col in ("entry_id", "order_id", "store_code", "raw_json", "updated_at") if col not in cols]
    if missing:
        raise ExactKaspiApiOrderEntryError(f"fact_order_entries_kaspi missing columns: {missing}")
    insert_cols = [col for col in ENTRY_INSERT_COLUMNS if col in cols]
    placeholders = ", ".join("?" for _ in insert_cols)
    column_sql = ", ".join(insert_cols)
    inserted = 0
    for entry in entries:
        values = [entry.get(col) for col in insert_cols]
        cur = conn.execute(
            f"INSERT OR IGNORE INTO fact_order_entries_kaspi ({column_sql}) VALUES ({placeholders})",
            values,
        )
        inserted += int(cur.rowcount or 0)
    return inserted


def _prepare_apply_guard(
    db_path: Path,
    *,
    apply: bool,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
) -> dict[str, Any]:
    pre_sha256 = _sha256_file(db_path)
    if expected_pre_sha256 and pre_sha256 != expected_pre_sha256:
        raise ExactKaspiApiOrderEntryError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, observed {pre_sha256}"
        )
    metadata: dict[str, Any] = {
        "pre_sha256": pre_sha256,
        "pre_integrity_check": _sqlite_integrity_check(db_path),
        "production_apply": _is_production_db(db_path),
        "backup_path": None,
        "backup_sha256": None,
        "backup_integrity_check": None,
    }
    if str(metadata["pre_integrity_check"]).lower() != "ok":
        raise ExactKaspiApiOrderEntryError(f"DB integrity_check failed before exact order-entry repair: {metadata['pre_integrity_check']}")
    if not apply:
        return metadata

    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise ExactKaspiApiOrderEntryError(f"{WRITE_ENV_GATE}=1 is required with --apply")

    if metadata["production_apply"]:
        if os.environ.get(PROD_WRITE_ENV_GATE) != "1":
            raise ExactKaspiApiOrderEntryError(f"{PROD_WRITE_ENV_GATE}=1 is required for production --apply")
        if not expected_pre_sha256:
            raise ExactKaspiApiOrderEntryError("--expected-pre-sha256 is required for production --apply")
        if backup_dir is None:
            raise ExactKaspiApiOrderEntryError("--backup-dir is required for production --apply")
        _fail_on_sqlite_sidecars(db_path)

    if backup_dir is not None:
        backup_path = backup_database(db_path, backup_dir, compress=False)
        backup_integrity = _sqlite_integrity_check(backup_path)
        if backup_integrity.lower() != "ok":
            raise ExactKaspiApiOrderEntryError(f"backup integrity_check failed: {backup_integrity}")
        metadata.update(
            {
                "backup_path": str(backup_path),
                "backup_sha256": _sha256_file(backup_path),
                "backup_integrity_check": backup_integrity,
            }
        )
    return metadata


def apply_exact_kaspi_api_order_entries(
    *,
    db_path: Path,
    target_order_csv: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    store_code: str | None = None,
    as_of: str,
    expected_entry_summary_csv: Path | None = None,
    expected_pre_sha256: str | None = None,
    expected_target_order_rows: int | None = None,
    expected_fetched_entry_rows: int | None = None,
    expected_inserted_entry_rows: int | None = None,
    backup_dir: Path | None = None,
    apply: bool = False,
    load_dotenv: bool = True,
    client_factory: Callable[[str], Any] = KaspiAPIClient,
) -> dict[str, Any]:
    target_db = Path(db_path).resolve()
    if not target_db.exists():
        raise ExactKaspiApiOrderEntryError(f"DB not found: {target_db}")
    output = Path(output_root).resolve()
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if load_dotenv:
        _load_dotenv_if_available()

    targets = _read_targets(Path(target_order_csv), store_code=store_code)
    if expected_target_order_rows is not None and len(targets) != expected_target_order_rows:
        raise ExactKaspiApiOrderEntryError(
            f"target order row count mismatch: expected {expected_target_order_rows}, got {len(targets)}"
        )
    expected_summary = _read_expected_entry_summary(expected_entry_summary_csv)
    apply_guard = _prepare_apply_guard(
        target_db,
        apply=apply,
        expected_pre_sha256=expected_pre_sha256,
        backup_dir=backup_dir,
    )

    with sqlite3.connect(str(target_db)) as conn:
        conn.row_factory = sqlite3.Row
        before_entry_count = _entry_count(conn)
        preconditions, updated_at_by_target = _prepare_preconditions(conn, targets, as_of=as_of)

    fetched_entries = _fetch_entries(
        targets,
        updated_at_by_target=updated_at_by_target,
        client_factory=client_factory,
    )
    _validate_expected_summary(targets, fetched_entries, expected_summary)

    fetched_entry_rows = len(fetched_entries)
    if fetched_entry_rows <= 0:
        raise ExactKaspiApiOrderEntryError("Kaspi API returned zero target entries")
    if expected_fetched_entry_rows is not None and fetched_entry_rows != expected_fetched_entry_rows:
        raise ExactKaspiApiOrderEntryError(
            f"fetched entry row count mismatch: expected {expected_fetched_entry_rows}, got {fetched_entry_rows}"
        )

    entry_ids = [str(entry["entry_id"]) for entry in fetched_entries]
    with sqlite3.connect(str(target_db)) as conn:
        conn.row_factory = sqlite3.Row
        existing_ids = _existing_entry_ids(conn, entry_ids)
        if existing_ids:
            raise ExactKaspiApiOrderEntryError(f"fetched entry IDs already exist before apply: {existing_ids}")

    would_insert = fetched_entry_rows
    if expected_inserted_entry_rows is not None and would_insert != expected_inserted_entry_rows:
        raise ExactKaspiApiOrderEntryError(
            f"inserted entry row count mismatch: expected {expected_inserted_entry_rows}, would insert {would_insert}"
        )

    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "db_path": str(target_db),
        "target_order_csv": str(Path(target_order_csv).resolve()),
        "expected_entry_summary_csv": str(Path(expected_entry_summary_csv).resolve()) if expected_entry_summary_csv else None,
        "output_root": str(output),
        "as_of": as_of,
        "env_gate": WRITE_ENV_GATE,
        "prod_env_gate": PROD_WRITE_ENV_GATE,
        "apply": {"requested": bool(apply), "applied": False},
        "expected": {
            "pre_sha256": expected_pre_sha256,
            "target_order_rows": expected_target_order_rows,
            "fetched_entry_rows": expected_fetched_entry_rows,
            "inserted_entry_rows": expected_inserted_entry_rows,
        },
        "preconditions": preconditions,
        "target_orders": [{"order_id": target.order_id, "store_code": target.store_code} for target in targets],
        "fetched_entry_rows": fetched_entry_rows,
        "would_insert_entry_rows": would_insert,
        "inserted_entry_rows": 0,
        "skipped_existing_entry_rows": 0,
        "entries": [_sanitized_entry(entry) for entry in fetched_entries],
        "before_entry_count_total": before_entry_count,
        "after_entry_count_total": before_entry_count,
        "pre_sha256": apply_guard["pre_sha256"],
        "post_sha256": apply_guard["pre_sha256"],
        "integrity_check": {
            "before": apply_guard["pre_integrity_check"],
            "after": apply_guard["pre_integrity_check"],
        },
        "backup_path": apply_guard["backup_path"],
        "backup_sha256": apply_guard["backup_sha256"],
        "backup_integrity_check": apply_guard["backup_integrity_check"],
        "production_db_target": apply_guard["production_apply"],
        "production_db_modified": False,
        "rollback": {
            "backup_path": apply_guard["backup_path"],
            "restore_command": f"cp {apply_guard['backup_path']} {target_db}" if apply_guard["backup_path"] else None,
            "verify_command": f"sqlite3 -readonly {target_db} 'PRAGMA integrity_check;'",
        },
    }

    if apply:
        current_sha = _sha256_file(target_db)
        if current_sha != apply_guard["pre_sha256"]:
            raise ExactKaspiApiOrderEntryError(
                f"DB changed before insert: expected {apply_guard['pre_sha256']}, observed {current_sha}"
            )
        with sqlite3.connect(str(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            before_apply_count = _entry_count(conn)
            inserted = _insert_entries(conn, fetched_entries)
            conn.commit()
            after_apply_count = _entry_count(conn)
            after_target_rows = {
                f"{target.order_id}/{target.store_code}": int(
                    conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM fact_order_entries_kaspi
                        WHERE CAST(order_id AS TEXT)=?
                          AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
                        """,
                        (target.order_id, target.store_code),
                    ).fetchone()[0]
                )
                for target in targets
            }
        if inserted != would_insert:
            raise ExactKaspiApiOrderEntryError(f"inserted row mismatch: expected {would_insert}, inserted {inserted}")
        if after_apply_count - before_apply_count != inserted:
            raise ExactKaspiApiOrderEntryError(
                f"entry table delta mismatch: before={before_apply_count}, after={after_apply_count}, inserted={inserted}"
            )
        for target in targets:
            target_count = after_target_rows[f"{target.order_id}/{target.store_code}"]
            target_expected = len([entry for entry in fetched_entries if entry["order_id"] == target.order_id and entry["store_code"] == target.store_code])
            if target_count != target_expected:
                raise ExactKaspiApiOrderEntryError(
                    f"target post-write count mismatch for {target.order_id}/{target.store_code}: "
                    f"expected {target_expected}, got {target_count}"
                )
        post_integrity = _sqlite_integrity_check(target_db)
        if post_integrity.lower() != "ok":
            raise ExactKaspiApiOrderEntryError(f"post-write integrity_check failed: {post_integrity}")
        summary.update(
            {
                "apply": {"requested": True, "applied": True},
                "inserted_entry_rows": inserted,
                "after_entry_count_total": after_apply_count,
                "after_target_entry_rows": after_target_rows,
                "post_sha256": _sha256_file(target_db),
                "integrity_check": {
                    "before": apply_guard["pre_integrity_check"],
                    "after": post_integrity,
                },
                "production_db_modified": bool(apply_guard["production_apply"]),
            }
        )

    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "summary.json"
    summary["summary_json"] = str(summary_path)
    sanitized_entries_path = output / "fetched_entries_sanitized.json"
    summary["fetched_entries_sanitized_json"] = str(sanitized_entries_path)
    _write_json(sanitized_entries_path, {"entries": summary["entries"]})
    _write_json(summary_path, summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--target-order-csv", type=Path, required=True)
    parser.add_argument("--expected-entry-summary-csv", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--store", dest="store_code", default=None)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--expected-target-order-rows", type=int, default=None)
    parser.add_argument("--expected-fetched-entry-rows", type=int, default=None)
    parser.add_argument("--expected-inserted-entry-rows", type=int, default=None)
    parser.add_argument("--no-dotenv", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = apply_exact_kaspi_api_order_entries(
            db_path=args.db,
            target_order_csv=args.target_order_csv,
            output_root=args.output_root,
            store_code=args.store_code,
            as_of=args.as_of,
            expected_entry_summary_csv=args.expected_entry_summary_csv,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_target_order_rows=args.expected_target_order_rows,
            expected_fetched_entry_rows=args.expected_fetched_entry_rows,
            expected_inserted_entry_rows=args.expected_inserted_entry_rows,
            backup_dir=args.backup_dir,
            apply=bool(args.apply),
            load_dotenv=not bool(args.no_dotenv),
        )
    except ExactKaspiApiOrderEntryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, default=_json_default))
    else:
        print(f"summary_json={summary['summary_json']}")
        print(f"applied={summary['apply']['applied']}")
        print(f"backup_path={summary['backup_path']}")
        print(f"fetched_entry_rows={summary['fetched_entry_rows']}")
        print(f"would_insert_entry_rows={summary['would_insert_entry_rows']}")
        print(f"inserted_entry_rows={summary['inserted_entry_rows']}")
        print(f"post_sha256={summary['post_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
