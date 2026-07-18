#!/usr/bin/env python3
"""Build a deterministic, non-applying historical order-entry repair manifest.

The manifest freezes source-proven line identity corrections while keeping
historical cash/economics and duplicate-source rows explicitly unwritten. It is
read-only against the source DB and never exposes the stored raw API payload.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable


class OrderEntryIdentityManifestError(RuntimeError):
    """Raised when source identity is incomplete, ambiguous, or mismatched."""


PROJECTION_ID_COLUMNS = {
    "fact_sales": "id",
    "sales_fact_v2": "sale_id",
    "fact_orders_kaspi": "id",
}
REQUIRED_LINE_IDENTITY_COLUMNS = {
    "source_entry_id",
    "kaspi_article",
    "line_identity_key",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_row_hash(payload: dict[str, Any]) -> str:
    return _sha256_bytes(_canonical_bytes(payload))


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _require_tables(conn: sqlite3.Connection, tables: set[str]) -> None:
    existing = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing = sorted(tables - existing)
    if missing:
        raise OrderEntryIdentityManifestError(
            "required tables missing: " + ", ".join(missing)
        )


def _decode_base64_id(value: str) -> str:
    if not value:
        return ""
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise OrderEntryIdentityManifestError(
            f"invalid base64 relationship identity: {value}"
        ) from exc


def _raw_evidence(raw_json: Any) -> tuple[str, str, str, float, float]:
    raw = str(raw_json or "")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OrderEntryIdentityManifestError("entry raw_json is invalid") from exc
    attributes = payload.get("attributes") or {}
    relationships = payload.get("relationships") or {}
    offer_code = str((attributes.get("offer") or {}).get("code") or "")
    pos_id = str(
        (((relationships.get("deliveryPointOfService") or {}).get("data") or {}).get("id"))
        or ""
    )
    return (
        _sha256_bytes(raw.encode("utf-8")),
        offer_code,
        _decode_base64_id(pos_id),
        float(attributes.get("quantity") or 0),
        float(attributes.get("totalPrice") or 0),
    )


def _numbers(value: Any) -> set[str]:
    return set(re.findall(r"(?<!\d)\d{2,}(?!\d)", str(value or "")))


def _contains_size(value: Any, size: str) -> bool:
    return bool(
        re.search(
            r"(^|[^A-Z0-9])" + re.escape(size.upper()) + r"($|[^A-Z0-9])",
            str(value or "").upper(),
        )
    )


def _projection_score(
    row: dict[str, Any],
    entry: dict[str, Any],
    *,
    fact_orders: bool,
) -> int:
    score = 0
    if str(row.get("store_code") or "").upper() == str(entry["store_code"]).upper():
        score += 20 if fact_orders else 10
    if str(row.get("sku_key") or "") == str(entry["canonical_sku_key"]):
        score += 30 if fact_orders else 40
    if str(row.get("sku_id") or "") == str(entry["canonical_sku_id"]):
        score += 30 if fact_orders else 80
    size_values = {
        str(row.get("my_size") or "").upper(),
        str(row.get("assigned_size") or "").upper(),
    }
    if str(entry["canonical_size"]).upper() in size_values:
        score += 50 if fact_orders else 60
    row_price = row.get("unit_price_kzt")
    if row_price is None:
        row_price = row.get("sell_price_kzt")
    if row_price is not None and abs(float(row_price or 0) - float(entry["total_price_kzt"])) < 0.005:
        score += 30
    if _numbers(row.get("kaspi_offer_name")) & _numbers(entry["offer_id"]):
        score += 15
    if _contains_size(row.get("kaspi_offer_name"), str(entry["canonical_size"])):
        score += 20 if not fact_orders else 10
    return score


def _unique_assignment(
    *,
    table: str,
    rows: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    scorer: Callable[[dict[str, Any], dict[str, Any]], int],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if len(rows) < len(entries):
        raise OrderEntryIdentityManifestError(
            f"{table} row count {len(rows)} is below entry count {len(entries)}"
        )
    candidates: list[tuple[int, tuple[int, ...]]] = []
    for indexes in itertools.permutations(range(len(rows)), len(entries)):
        scores = [scorer(rows[row_index], entry) for row_index, entry in zip(indexes, entries)]
        if any(score <= 0 for score in scores):
            continue
        candidates.append((sum(scores), indexes))
    if not candidates:
        raise OrderEntryIdentityManifestError(f"{table} has no complete positive-score assignment")
    best_score = max(score for score, _ in candidates)
    best = [indexes for score, indexes in candidates if score == best_score]
    if len(best) != 1:
        raise OrderEntryIdentityManifestError(
            f"{table} assignment is ambiguous at score {best_score}: {len(best)} candidates"
        )
    return [(rows[index], entry) for index, entry in zip(best[0], entries)]


def _safe_projection_row(table: str, row: sqlite3.Row) -> dict[str, Any]:
    allowed = {
        PROJECTION_ID_COLUMNS[table],
        "order_id",
        "store_code",
        "kaspi_offer_name",
        "sku_key",
        "sku_id",
        "my_size",
        "assigned_size",
        "quantity",
        "unit_price_kzt",
        "sell_price_kzt",
        "kaspi_status",
        "internal_status",
        "status",
        "return_flag",
        "source",
    }
    payload = {key: row[key] for key in row.keys() if key in allowed}
    payload["safe_row_sha256"] = _safe_row_hash(payload)
    return payload


def _projection_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    order_id: str,
    store_only: bool,
    store_code: str,
) -> list[dict[str, Any]]:
    id_column = PROJECTION_ID_COLUMNS[table]
    where = "CAST(order_id AS TEXT)=?"
    params: list[Any] = [order_id]
    if store_only:
        where += " AND UPPER(TRIM(COALESCE(store_code,'')))=?"
        params.append(store_code.upper())
    rows = conn.execute(
        f'SELECT * FROM "{table}" WHERE {where} ORDER BY "{id_column}"',
        tuple(params),
    ).fetchall()
    return [_safe_projection_row(table, row) for row in rows]


def _projection_patch(
    table: str,
    row: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    id_column = PROJECTION_ID_COLUMNS[table]
    before = dict(row)
    after = {
        "store_code": entry["store_code"],
        "sku_key": entry["canonical_sku_key"],
        "sku_id": entry["canonical_sku_id"],
        "my_size": entry["canonical_size"],
        "source_entry_id": entry["entry_id"],
        "kaspi_article": entry["offer_id"],
        "line_identity_key": f"ENTRY:{entry['entry_id']}",
    }
    if table == "fact_orders_kaspi":
        after["assigned_size"] = entry["canonical_size"]
    return {
        "table": table,
        "id_column": id_column,
        "row_id": before[id_column],
        "entry_id": entry["entry_id"],
        "before": before,
        "after": after,
        "action": "COPIED_DB_IDENTITY_PATCH_CANDIDATE_ONLY",
    }


def _entry_rows(
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
               unit_price_kzt, total_price_kzt, raw_json
        FROM fact_order_entries_kaspi
        WHERE CAST(order_id AS TEXT)=?
        ORDER BY entry_id
        """,
        (order_id,),
    ).fetchall()
    if len(rows) != expected_entry_count:
        raise OrderEntryIdentityManifestError(
            f"entry count mismatch: expected {expected_entry_count}, got {len(rows)}"
        )
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        entry_id = str(row["entry_id"] or "")
        if not entry_id or entry_id in seen:
            raise OrderEntryIdentityManifestError("entry IDs are blank or duplicated")
        seen.add(entry_id)
        if str(row["store_code"] or "").upper() != store_code.upper():
            raise OrderEntryIdentityManifestError(
                f"entry store mismatch for {entry_id}: {row['store_code']}"
            )
        raw_sha, raw_offer, pos_decoded, raw_qty, raw_total = _raw_evidence(row["raw_json"])
        offer_id = str(row["offer_id"] or "")
        if raw_offer != offer_id:
            raise OrderEntryIdentityManifestError(
                f"stored/raw offer mismatch for {entry_id}"
            )
        if pos_decoded != f"{merchant_id}_PP1":
            raise OrderEntryIdentityManifestError(
                f"delivery POS mismatch for {entry_id}: {pos_decoded}"
            )
        quantity = float(row["quantity"] or 0)
        total = float(row["total_price_kzt"] or 0)
        if quantity <= 0 or quantity != raw_qty or abs(total - raw_total) >= 0.005:
            raise OrderEntryIdentityManifestError(
                f"stored/raw quantity or total mismatch for {entry_id}"
            )
        mapping_rows = conn.execute(
            """
            SELECT id, store_code, merchant_id, kaspi_article, sku_key, sku_id
            FROM dim_kaspi_article_map
            WHERE UPPER(TRIM(COALESCE(store_code,'')))=?
              AND TRIM(COALESCE(merchant_id,''))=?
              AND TRIM(kaspi_article)=?
              AND COALESCE(active_flag,1)=1
            ORDER BY id
            """,
            (store_code.upper(), merchant_id, offer_id),
        ).fetchall()
        if len(mapping_rows) != 1:
            raise OrderEntryIdentityManifestError(
                f"exact active mapping count for {entry_id} is {len(mapping_rows)}, expected 1"
            )
        mapping = mapping_rows[0]
        size_rows = conn.execute(
            """
            SELECT sku_key, sku_id, my_size
            FROM dim_sku_size
            WHERE sku_id=? AND COALESCE(active_flag,1)=1
            """,
            (str(mapping["sku_id"] or ""),),
        ).fetchall()
        if len(size_rows) != 1:
            raise OrderEntryIdentityManifestError(
                f"active canonical size count for {entry_id} is {len(size_rows)}, expected 1"
            )
        size_row = size_rows[0]
        if str(size_row["sku_key"]) != str(mapping["sku_key"]):
            raise OrderEntryIdentityManifestError(
                f"mapping/catalog sku_key mismatch for {entry_id}"
            )
        safe = {
            "entry_id": entry_id,
            "order_id": order_id,
            "store_code": store_code.upper(),
            "merchant_id": merchant_id,
            "product_id": str(row["product_id"] or ""),
            "offer_id": offer_id,
            "quantity": quantity,
            "total_price_kzt": total,
            "raw_json_sha256": raw_sha,
            "delivery_pos_decoded": pos_decoded,
            "mapping_row_id": int(mapping["id"]),
            "canonical_sku_key": str(mapping["sku_key"]),
            "canonical_sku_id": str(mapping["sku_id"]),
            "canonical_size": str(size_row["my_size"]),
        }
        safe["safe_evidence_sha256"] = _safe_row_hash(safe)
        entries.append(safe)
    canonical_keys = {entry["canonical_sku_key"] for entry in entries}
    if len(canonical_keys) != 1:
        raise OrderEntryIdentityManifestError(
            f"entries map to multiple canonical sku_key values: {sorted(canonical_keys)}"
        )
    return entries


def _cash_residuals(conn: sqlite3.Connection, *, order_id: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact_sku_ids = {entry["canonical_sku_id"] for entry in entries}
    rows = conn.execute(
        """
        SELECT id, event_date, event_type, account, amount_kzt, store_code,
               sku_key, sku_id, ref_type, ref_id, source, run_id, event_hash
        FROM fact_cashflow_events
        WHERE ref_type='ORDER' AND ref_id=? AND event_type='CASH_IN'
        ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    residuals: list[dict[str, Any]] = []
    for row in rows:
        safe = {key: row[key] for key in row.keys()}
        safe["safe_row_sha256"] = _safe_row_hash(safe)
        store = str(row["store_code"] or "").upper()
        sku_id = str(row["sku_id"] or "")
        if store in {"", "UNKNOWN"}:
            classification = "WRONG_STORE_DUPLICATE_CANDIDATE"
        elif sku_id in exact_sku_ids:
            classification = "ORDER_LEVEL_ENTRY_BINDING_REQUIRED_ECONOMICS_UNPROVEN"
        else:
            classification = "WRONG_SIZE_EVENT_ECONOMICS_UNPROVEN"
        residuals.append(
            {
                **safe,
                "classification": classification,
                "action": "NO_WRITE_ECONOMICS_OR_QUARANTINE_PROOF_REQUIRED",
            }
        )
    return residuals


def build_order_entry_identity_repair_manifest(
    *,
    db_path: Path,
    order_id: str,
    store_code: str,
    merchant_id: str,
    expected_entry_count: int,
    expected_db_sha256: str | None = None,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    if not db_path.is_file():
        raise OrderEntryIdentityManifestError(f"source DB not found: {db_path}")
    db_sha = _sha256_file(db_path)
    if expected_db_sha256 and db_sha != expected_db_sha256:
        raise OrderEntryIdentityManifestError(
            f"source DB SHA mismatch: expected {expected_db_sha256}, got {db_sha}"
        )
    conn = _connect_readonly(db_path)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise OrderEntryIdentityManifestError(
                f"source DB integrity_check failed: {integrity}"
            )
        required_tables = {
            "fact_order_entries_kaspi",
            "dim_kaspi_article_map",
            "dim_sku_size",
            "fact_sales",
            "sales_fact_v2",
            "fact_orders_kaspi",
            "fact_cashflow_events",
        }
        _require_tables(conn, required_tables)
        entries = _entry_rows(
            conn,
            order_id=str(order_id),
            store_code=store_code,
            merchant_id=merchant_id,
            expected_entry_count=expected_entry_count,
        )
        projection_patches: dict[str, list[dict[str, Any]]] = {}
        selected_fact_order_ids: set[Any] = set()
        for table in ("fact_sales", "sales_fact_v2", "fact_orders_kaspi"):
            rows = _projection_rows(
                conn,
                table=table,
                order_id=str(order_id),
                store_only=table != "fact_orders_kaspi",
                store_code=store_code,
            )
            if table != "fact_orders_kaspi" and len(rows) != expected_entry_count:
                raise OrderEntryIdentityManifestError(
                    f"{table} row count mismatch: expected {expected_entry_count}, got {len(rows)}"
                )
            assignments = _unique_assignment(
                table=table,
                rows=rows,
                entries=entries,
                scorer=lambda row, entry, table=table: _projection_score(
                    row,
                    entry,
                    fact_orders=table == "fact_orders_kaspi",
                ),
            )
            patches = [_projection_patch(table, row, entry) for row, entry in assignments]
            projection_patches[table] = patches
            if table == "fact_orders_kaspi":
                selected_fact_order_ids = {patch["row_id"] for patch in patches}
                fact_order_rows = rows

        quarantine_candidates = []
        for row in fact_order_rows:
            if row["id"] in selected_fact_order_ids:
                continue
            quarantine_candidates.append(
                {
                    **row,
                    "classification": "LEGACY_DUPLICATE_SOURCE_SNAPSHOT",
                    "action": "NO_WRITE_QUARANTINE_REQUIRED",
                }
            )
        cash_residuals = _cash_residuals(conn, order_id=str(order_id), entries=entries)
        migration_missing = {
            table: sorted(REQUIRED_LINE_IDENTITY_COLUMNS - _table_columns(conn, table))
            for table in PROJECTION_ID_COLUMNS
        }
    finally:
        conn.close()

    payload: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "NON_APPLYING_SOURCE_PROVEN_ORDER_ENTRY_IDENTITY_REPAIR_CANDIDATE",
        "source_db": {
            "path": str(db_path),
            "sha256": db_sha,
            "integrity_check": "ok",
        },
        "order_id": str(order_id),
        "store_code": store_code.upper(),
        "merchant_id": str(merchant_id),
        "expected_entry_count": int(expected_entry_count),
        "entries": entries,
        "projection_patches": projection_patches,
        "identity_patch_candidate_count": sum(len(rows) for rows in projection_patches.values()),
        "fact_orders_quarantine_candidates": quarantine_candidates,
        "fact_orders_quarantine_candidate_count": len(quarantine_candidates),
        "cash_in_residuals": cash_residuals,
        "cash_in_residual_count": len(cash_residuals),
        "migration_031_missing_columns": migration_missing,
        "requires_migration_031": any(migration_missing.values()),
        "copied_apply_ready": False,
        "production_apply_authorized": False,
        "blocked_reasons": [
            "migration_031_not_applied_to_source_db" if any(migration_missing.values()) else "",
            "fact_orders_duplicate_snapshot_quarantine_semantics_not_materialized"
            if quarantine_candidates
            else "",
            "cash_event_entry_binding_and_economics_unresolved" if cash_residuals else "",
        ],
        "next_safe_steps": [
            "apply migration 031 only to a disposable copied DB",
            "apply only the six exact projection identity candidates on that copy",
            "materialize explicit duplicate-snapshot and cash-event quarantine semantics",
            "replay cash, lifecycle, stock, cohort, and non-target validators",
            "request a new exact production-write approval only after all blockers are zero",
        ],
    }
    payload["blocked_reasons"] = [value for value in payload["blocked_reasons"] if value]
    payload["manifest_sha256"] = _sha256_bytes(_canonical_bytes(payload))
    return payload


def write_manifest(path: Path, manifest: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return _sha256_file(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--store-code", required=True)
    parser.add_argument("--merchant-id", required=True)
    parser.add_argument("--expected-entry-count", type=int, required=True)
    parser.add_argument("--expected-db-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = build_order_entry_identity_repair_manifest(
        db_path=args.db,
        order_id=args.order_id,
        store_code=args.store_code,
        merchant_id=args.merchant_id,
        expected_entry_count=args.expected_entry_count,
        expected_db_sha256=args.expected_db_sha256,
    )
    file_sha = write_manifest(args.output, manifest)
    print(f"manifest_path={args.output.resolve()}")
    print(f"manifest_internal_sha256={manifest['manifest_sha256']}")
    print(f"manifest_file_sha256={file_sha}")
    print(f"identity_patch_candidate_count={manifest['identity_patch_candidate_count']}")
    print(f"fact_orders_quarantine_candidate_count={manifest['fact_orders_quarantine_candidate_count']}")
    print(f"cash_in_residual_count={manifest['cash_in_residual_count']}")
    print("production_apply_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
