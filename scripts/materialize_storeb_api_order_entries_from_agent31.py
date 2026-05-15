#!/usr/bin/env python3
"""Materialize Agent 31 STOREB API item-entry evidence into a temp DB only.

This lane is intentionally narrower than the general order-entry recovery path.
It consumes Agent 31's sealed evidence files, inserts only rows classified as
API_ITEM_ENTRY_SKU_ID_SIZE_MAPPED, and refuses production db/app.db writes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
WRITE_ENV_GATE = "ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY"
SAFE_STATUS = "API_ITEM_ENTRY_SKU_ID_SIZE_MAPPED"
SAFE_SOURCE_NAME = "KASPI_API_READONLY_STOREB_EXACT_ORDER_IDS"
SAFE_SOURCE_KIND = "kaspi_api_readonly_order_entry"
HEADER_ONLY_PREFIXES = ("target_sku", "target_quantity", "target_sale", "header_target")


class MaterializationError(RuntimeError):
    """Raised when Agent 31 evidence cannot be safely materialized."""


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _upper(value) in {"1", "TRUE", "YES", "Y"}


def _float_or_none(value: Any) -> float | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    if number is None:
        return None
    return int(number)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise MaterializationError(f"missing JSONL evidence file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MaterializationError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise MaterializationError(f"expected JSON object at {path}:{line_number}")
            rows.append(payload)
    return rows


def _read_csv(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        raise MaterializationError(f"missing CSV evidence file: {path}")
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def _split_entry_ids(value: Any) -> list[str]:
    text = _norm(value)
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _safe_order_index(preview_rows: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], dict[tuple[str, str], set[str]]]:
    safe_pairs: set[tuple[str, str]] = set()
    entry_ids_by_pair: dict[tuple[str, str], set[str]] = {}
    for row in preview_rows:
        if _upper(row.get("evidence_status")) != SAFE_STATUS or not _bool(row.get("recommended_temp_apply")):
            continue
        order_id = _norm(row.get("order_id"))
        store_code = _upper(row.get("store_code"))
        if not order_id or store_code != "STOREB":
            raise MaterializationError(f"safe preview row has invalid order/store: {row}")
        pair = (order_id, store_code)
        if pair in safe_pairs:
            raise MaterializationError(f"duplicate safe preview order row: {pair}")
        entry_ids = set(_split_entry_ids(row.get("entry_ids")))
        if not entry_ids:
            raise MaterializationError(f"safe preview row lacks entry_ids for order_id={order_id}")
        safe_pairs.add(pair)
        entry_ids_by_pair[pair] = entry_ids
    return safe_pairs, entry_ids_by_pair


def _quarantine_pairs(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        order_id = _norm(row.get("order_id"))
        store_code = _upper(row.get("store_code")) or "STOREB"
        if order_id:
            pairs.add((order_id, store_code))
    return pairs


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _guard_apply_path(db_path: Path) -> None:
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise MaterializationError(f"{WRITE_ENV_GATE}=1 is required with --apply")
    try:
        resolved = db_path.resolve()
        production = DEFAULT_DB.resolve()
    except FileNotFoundError:
        resolved = db_path.absolute()
        production = DEFAULT_DB.absolute()
    if resolved == production:
        raise MaterializationError("refusing to apply Agent 31 STOREB evidence to production db/app.db")


def _raw_json_payload(row: dict[str, Any]) -> str:
    payload: dict[str, Any] = {}
    allowed_keys = {
        "api_order_base64_id",
        "api_order_code",
        "api_order_creation_date",
        "api_order_state",
        "api_order_status",
        "article_map_sku_id",
        "article_map_sku_key",
        "base_price_kzt",
        "category_code",
        "category_title",
        "entry_id",
        "entry_number",
        "offer_code",
        "offer_name",
        "product_id",
        "quantity",
        "real_item_entry_evidence",
        "sku_rebuild_mappable",
        "source_kind",
        "source_name",
        "total_price_kzt",
        "unit_price_kzt",
    }
    for key in sorted(allowed_keys):
        if key in row:
            payload[key] = row[key]
    payload["identity_truth_source"] = "api_entry_offer_code_plus_dim_kaspi_article_map"
    payload["raw_customer_payload_written"] = False
    payload["materialized_by"] = "materialize_storeb_api_order_entries_from_agent31"
    for key in payload:
        if key.startswith(HEADER_ONLY_PREFIXES):
            raise MaterializationError(f"header-only key leaked into raw_json payload: {key}")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _entry_from_api_row(row: dict[str, Any], *, materialized_at: str) -> dict[str, Any]:
    order_id = _norm(row.get("target_order_id") or row.get("api_order_code"))
    store_code = _upper(row.get("target_store_code"))
    entry_id = _norm(row.get("entry_id"))
    offer_id = _norm(row.get("offer_code"))
    product_id = _norm(row.get("product_id"))
    quantity = _float_or_none(row.get("quantity"))
    total = _float_or_none(row.get("total_price_kzt"))
    unit = _float_or_none(row.get("unit_price_kzt"))
    if unit is None and total is not None and quantity and quantity > 0:
        unit = total / quantity

    if not order_id or store_code != "STOREB" or not entry_id:
        raise MaterializationError(f"API row lacks required order/store/entry identity: {row}")
    if not offer_id or not product_id:
        raise MaterializationError(f"API row lacks offer/product identity for order_id={order_id} entry_id={entry_id}")
    if quantity is None or quantity <= 0:
        raise MaterializationError(f"API row has invalid quantity for order_id={order_id} entry_id={entry_id}")
    if not _bool(row.get("real_item_entry_evidence")):
        raise MaterializationError(f"API row is not real item-entry evidence: order_id={order_id} entry_id={entry_id}")
    if not _bool(row.get("sku_rebuild_mappable")):
        raise MaterializationError(f"API row is not sku rebuild mappable: order_id={order_id} entry_id={entry_id}")
    if not _norm(row.get("article_map_sku_id")) or not _norm(row.get("article_map_sku_key")):
        raise MaterializationError(f"API row lacks article-map SKU truth: order_id={order_id} entry_id={entry_id}")
    if _norm(row.get("source_name")) != SAFE_SOURCE_NAME or _norm(row.get("source_kind")) != SAFE_SOURCE_KIND:
        raise MaterializationError(f"API row has unexpected source provenance: order_id={order_id} entry_id={entry_id}")

    return {
        "entry_id": entry_id,
        "order_id": order_id,
        "store_code": store_code,
        "product_id": product_id,
        "offer_id": offer_id,
        "quantity": quantity,
        "unit_price_kzt": unit,
        "total_price_kzt": total,
        "raw_json": _raw_json_payload(row),
        "updated_at": materialized_at,
        "entry_number": _int_or_none(row.get("entry_number")),
        "category_code": _norm(row.get("category_code")),
        "category_title": _norm(row.get("category_title")),
        "base_price_kzt": _float_or_none(row.get("base_price_kzt")),
    }


def _candidate_entries(
    *,
    api_rows: list[dict[str, Any]],
    safe_pairs: set[tuple[str, str]],
    entry_ids_by_pair: dict[tuple[str, str], set[str]],
    materialized_at: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_entry_ids: set[str] = set()
    seen_by_pair: dict[tuple[str, str], set[str]] = {pair: set() for pair in safe_pairs}
    for row in api_rows:
        pair = (_norm(row.get("target_order_id") or row.get("api_order_code")), _upper(row.get("target_store_code")))
        if pair not in safe_pairs:
            continue
        entry_id = _norm(row.get("entry_id"))
        if entry_id not in entry_ids_by_pair[pair]:
            continue
        entry = _entry_from_api_row(row, materialized_at=materialized_at)
        if entry["entry_id"] in seen_entry_ids:
            raise MaterializationError(f"duplicate API entry_id in candidate evidence: {entry['entry_id']}")
        seen_entry_ids.add(entry["entry_id"])
        seen_by_pair[pair].add(entry["entry_id"])
        candidates.append(entry)

    missing_by_pair = {
        pair: sorted(expected - seen_by_pair.get(pair, set()))
        for pair, expected in entry_ids_by_pair.items()
        if expected - seen_by_pair.get(pair, set())
    }
    if missing_by_pair:
        raise MaterializationError(f"safe preview entry_ids missing from API sanitized entries: {missing_by_pair}")
    return candidates


def _existing_entry_ids(conn: sqlite3.Connection, entry_ids: list[str]) -> set[str]:
    if not entry_ids:
        return set()
    existing: set[str] = set()
    for idx in range(0, len(entry_ids), 500):
        chunk = entry_ids[idx : idx + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT entry_id FROM fact_order_entries_kaspi WHERE entry_id IN ({placeholders})",
            chunk,
        ).fetchall()
        existing.update(str(row[0]) for row in rows)
    return existing


def _insert_entries(conn: sqlite3.Connection, entries: list[dict[str, Any]]) -> int:
    table_cols = _table_columns(conn, "fact_order_entries_kaspi")
    if not table_cols:
        raise MaterializationError("fact_order_entries_kaspi table missing")
    insert_order = [
        "entry_id",
        "order_id",
        "store_code",
        "product_id",
        "offer_id",
        "quantity",
        "unit_price_kzt",
        "total_price_kzt",
        "raw_json",
        "updated_at",
        "entry_number",
        "category_code",
        "category_title",
        "base_price_kzt",
    ]
    insert_cols = [col for col in insert_order if col in table_cols]
    placeholders = ",".join("?" for _ in insert_cols)
    columns_sql = ",".join(insert_cols)
    inserted = 0
    for entry in entries:
        values = [entry.get(col) for col in insert_cols]
        cur = conn.execute(
            f"INSERT OR IGNORE INTO fact_order_entries_kaspi ({columns_sql}) VALUES ({placeholders})",
            values,
        )
        inserted += int(cur.rowcount or 0)
    return inserted


def _write_outputs(
    output_root: Path,
    *,
    summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    quarantine_rows_path: Path,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_root / "materialized_entries_preview.jsonl").open("w", encoding="utf-8") as fh:
        for entry in candidates:
            preview = {key: value for key, value in entry.items() if key != "raw_json"}
            preview["raw_json_sha256"] = hashlib.sha256(
                str(entry.get("raw_json") or "").encode("utf-8")
            ).hexdigest()
            fh.write(json.dumps(preview, ensure_ascii=False, sort_keys=True) + "\n")
    shutil.copyfile(quarantine_rows_path, output_root / "storeb_still_quarantined_rows.csv")


def materialize_storeb_api_order_entries(
    *,
    db_path: Path,
    safe_rows_path: Path,
    api_entries_path: Path,
    quarantine_rows_path: Path,
    output_root: Path,
    apply: bool = False,
    expected_safe_order_rows: int | None = None,
    expected_quarantine_rows: int | None = None,
) -> dict[str, Any]:
    materialized_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    preview_rows = _read_jsonl(safe_rows_path)
    api_rows = _read_jsonl(api_entries_path)
    quarantine_rows, quarantine_headers = _read_csv(quarantine_rows_path)
    safe_pairs, entry_ids_by_pair = _safe_order_index(preview_rows)
    quarantine_order_pairs = _quarantine_pairs(quarantine_rows)

    overlap = sorted(safe_pairs & quarantine_order_pairs)
    if overlap:
        raise MaterializationError(f"safe rows overlap quarantine rows: {overlap[:10]}")
    if expected_safe_order_rows is not None and len(safe_pairs) != expected_safe_order_rows:
        raise MaterializationError(
            f"safe order row count mismatch: expected {expected_safe_order_rows}, got {len(safe_pairs)}"
        )
    if expected_quarantine_rows is not None and len(quarantine_rows) != expected_quarantine_rows:
        raise MaterializationError(
            f"quarantine row count mismatch: expected {expected_quarantine_rows}, got {len(quarantine_rows)}"
        )

    candidates = _candidate_entries(
        api_rows=api_rows,
        safe_pairs=safe_pairs,
        entry_ids_by_pair=entry_ids_by_pair,
        materialized_at=materialized_at,
    )
    if not candidates and safe_pairs:
        raise MaterializationError("safe preview rows produced no materialization candidates")

    conn_uri = str(db_path) if apply else f"file:{db_path}?mode=ro"
    with sqlite3.connect(conn_uri, uri=not apply) as conn:
        existing = _existing_entry_ids(conn, [entry["entry_id"] for entry in candidates])
        new_entries = [entry for entry in candidates if entry["entry_id"] not in existing]
        inserted = 0
        if apply:
            _guard_apply_path(db_path)
            inserted = _insert_entries(conn, new_entries)
            conn.commit()

    production_db_target = False
    try:
        production_db_target = db_path.resolve() == DEFAULT_DB.resolve()
    except FileNotFoundError:
        production_db_target = db_path.absolute() == DEFAULT_DB.absolute()

    summary = {
        "agent31_inputs": {
            "safe_rows_path": str(safe_rows_path),
            "api_entries_path": str(api_entries_path),
            "quarantine_rows_path": str(quarantine_rows_path),
        },
        "db_path": str(db_path),
        "output_root": str(output_root),
        "materialized_at": materialized_at,
        "safe_status": SAFE_STATUS,
        "safe_order_rows": len(safe_pairs),
        "candidate_entry_rows": len(candidates),
        "quarantine_rows": len(quarantine_rows),
        "quarantine_headers": quarantine_headers,
        "candidate_order_rows": len({(entry["order_id"], entry["store_code"]) for entry in candidates}),
        "apply": {
            "applied": apply,
            "would_insert_entry_rows": len(new_entries),
            "inserted_entry_rows": inserted,
            "skipped_existing_entry_rows": len(candidates) - len(new_entries),
        },
        "production_db_target": production_db_target,
        "production_db_modified": False,
        "header_only_target_identity_used": False,
    }
    _write_outputs(output_root, summary=summary, candidates=candidates, quarantine_rows_path=quarantine_rows_path)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--safe-rows", type=Path, required=True)
    parser.add_argument("--api-entries", type=Path, required=True)
    parser.add_argument("--quarantine-rows", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-safe-order-rows", type=int, default=None)
    parser.add_argument("--expected-quarantine-rows", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = materialize_storeb_api_order_entries(
            db_path=args.db,
            safe_rows_path=args.safe_rows,
            api_entries_path=args.api_entries,
            quarantine_rows_path=args.quarantine_rows,
            output_root=args.output_root,
            apply=bool(args.apply),
            expected_safe_order_rows=args.expected_safe_order_rows,
            expected_quarantine_rows=args.expected_quarantine_rows,
        )
    except MaterializationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"summary_json={args.output_root / 'summary.json'}")
    print(f"safe_order_rows={summary['safe_order_rows']}")
    print(f"candidate_entry_rows={summary['candidate_entry_rows']}")
    print(f"quarantine_rows={summary['quarantine_rows']}")
    print(f"would_insert_entry_rows={summary['apply']['would_insert_entry_rows']}")
    print(f"inserted_entry_rows={summary['apply']['inserted_entry_rows']}")
    print(f"skipped_existing_entry_rows={summary['apply']['skipped_existing_entry_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
