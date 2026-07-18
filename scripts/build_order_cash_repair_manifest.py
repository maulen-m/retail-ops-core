#!/usr/bin/env python3
"""Build an exact append-only mapped-order cash repair manifest."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_sales_publication_binding_manifest import (  # noqa: E402
    canonical_sha256,
    sha256_file,
)
from scripts.translate_orders_to_cashflow_events import _event_hash  # noqa: E402
from scripts.validate_sales_publication_binding import validate as validate_binding  # noqa: E402


SCHEMA_VERSION = "mapped_order_cash_repair_manifest_v1"
CANONICAL_HASH_VERSION = "canonical-json-v1-sort-keys-utf8-no-whitespace"


class OrderCashRepairManifestError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OrderCashRepairManifestError(f"expected JSON object: {path}")
    return value


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _logical_hash(conn: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
    rows = [dict(zip(columns, row)) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    return canonical_sha256(sorted(rows, key=canonical_sha256))


def _replacement_event(
    *,
    order_id: str,
    store_code: str,
    target: dict[str, Any],
    publication_manifest: dict[str, Any],
    run_id: str,
    repair_key: str,
) -> dict[str, Any]:
    source = target["source_row_preimage"]
    publication = target["publication"]
    event = {
        "event_date": publication["sale_date"],
        "event_ts": publication_manifest["terminal_event_ts"],
        "event_type": "CASH_IN",
        "account": f"KASPI_PAY_{store_code}",
        "amount_kzt": round(float(publication["net_rev_kzt"]), 2),
        "store_code": store_code,
        "sku_key": source["sku_key"],
        "sku_id": source["sku_id"],
        "ref_type": "ORDER_ENTRY",
        "ref_id": source["source_entry_id"],
        "notes": (
            "D1 cash-in from source-proven ORDER_ENTRY repair; "
            f"order_id={order_id}; proof_key={publication_manifest['source_proof_key']}; "
            f"repair_key={repair_key}"
        ),
        "source": "ORDER_MODELLED",
        "run_id": run_id,
    }
    event["event_hash"] = _event_hash(event)
    return event


def build_manifest(
    *,
    db_path: Path,
    publication_manifest_path: Path,
    order_id: str,
    store_code: str,
    supersede_event_ids: list[int],
    repair_key: str,
    run_id: str,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    store_code = store_code.strip().upper()
    publication_manifest_path = publication_manifest_path.resolve()
    publication = _load_json(publication_manifest_path)
    if str(publication.get("order_id")) != order_id or str(publication.get("store_code")).upper() != store_code:
        raise OrderCashRepairManifestError("publication binding identity mismatch")
    if bool(publication.get("provisional_flag")):
        raise OrderCashRepairManifestError("provisional publication cannot authorize cash repair")
    binding_validation = validate_binding(
        db_path=db_path,
        manifest_path=publication_manifest_path,
    )
    if binding_validation.get("status") != "PASS":
        raise OrderCashRepairManifestError("publication binding validator is not PASS")
    if not supersede_event_ids or len(set(supersede_event_ids)) != len(supersede_event_ids):
        raise OrderCashRepairManifestError("supersede event IDs must be a nonempty unique set")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise OrderCashRepairManifestError(f"copied DB integrity_check failed: {integrity}")
        placeholders = ",".join("?" for _ in supersede_event_ids)
        rows = conn.execute(
            f"SELECT * FROM fact_cashflow_events WHERE id IN ({placeholders}) ORDER BY id",
            supersede_event_ids,
        ).fetchall()
        if len(rows) != len(supersede_event_ids):
            raise OrderCashRepairManifestError(
                f"expected {len(supersede_event_ids)} stale events, observed {len(rows)}"
            )
        stale_rows = [_row_dict(row) for row in rows]
        for row in stale_rows:
            if str(row.get("ref_type") or "").upper() != "ORDER" or str(row.get("ref_id")) != order_id:
                raise OrderCashRepairManifestError(f"stale event {row['id']} is not the exact ORDER reference")
            if float(row.get("amount_kzt") or 0) <= 0:
                raise OrderCashRepairManifestError(f"stale event {row['id']} is not positive")
            if not (
                str(row.get("event_type") or "").upper() == "CASH_IN"
                or str(row.get("account") or "").upper() == "CASH"
            ):
                raise OrderCashRepairManifestError(f"stale event {row['id']} is not a cash-account inflow")

        entry_ids = [
            str(target["source_row_preimage"]["source_entry_id"])
            for target in publication["targets"]
        ]
        entry_placeholders = ",".join("?" for _ in entry_ids)
        entries = conn.execute(
            f"""
            SELECT entry_id, order_id, UPPER(TRIM(store_code)) AS store_code,
                   quantity, offer_id, total_price_kzt
            FROM fact_order_entries_kaspi
            WHERE entry_id IN ({entry_placeholders})
            ORDER BY entry_id
            """,
            entry_ids,
        ).fetchall()
        if len(entries) != len(entry_ids):
            raise OrderCashRepairManifestError("complete current ORDER_ENTRY set is unavailable")
        entry_by_id = {str(row["entry_id"]): _row_dict(row) for row in entries}
        for target in publication["targets"]:
            source = target["source_row_preimage"]
            entry = entry_by_id.get(str(source["source_entry_id"]))
            if not entry:
                raise OrderCashRepairManifestError("publication entry missing from current entry table")
            expected = (
                order_id,
                store_code,
                float(source["quantity"]),
                str(source["kaspi_article"]),
                float(source["sell_price_kzt"]) * float(source["quantity"]),
            )
            observed = (
                str(entry["order_id"]),
                str(entry["store_code"]),
                float(entry["quantity"]),
                str(entry["offer_id"]),
                float(entry["total_price_kzt"]),
            )
            if observed != expected:
                raise OrderCashRepairManifestError(
                    f"current entry identity mismatch: expected {expected}, observed {observed}"
                )

        cash_table_sha = _logical_hash(conn, "fact_cashflow_events")
    finally:
        conn.close()

    reversals: list[dict[str, Any]] = []
    for row in stale_rows:
        event = {
            "event_date": row["event_date"],
            "event_ts": None,
            "event_type": row["event_type"],
            "account": row["account"],
            "amount_kzt": round(-float(row["amount_kzt"]), 2),
            "store_code": row["store_code"],
            "sku_key": row["sku_key"],
            "sku_id": row["sku_id"],
            "ref_type": row["ref_type"],
            "ref_id": row["ref_id"],
            "notes": (
                "exact mapped-order cash reversal; "
                f"order_id={order_id}; supersedes_cash_id={row['id']}; "
                f"supersedes_cash_hash={row['event_hash']}; repair_key={repair_key}"
            ),
            "source": "ORDER_CASH_REPAIR",
            "run_id": run_id,
        }
        event["event_hash"] = _event_hash(event)
        reversals.append(
            {
                "superseded_preimage": row,
                "superseded_preimage_sha256": canonical_sha256(row),
                "event": event,
                "event_sha256": canonical_sha256(event),
            }
        )
    replacements = [
        {
            "source_sale_id": int(target["sale_id"]),
            "source_entry_id": target["source_entry_id"],
            "event": _replacement_event(
                order_id=order_id,
                store_code=store_code,
                target=target,
                publication_manifest=publication,
                run_id=run_id,
                repair_key=repair_key,
            ),
        }
        for target in publication["targets"]
    ]
    proposed_hashes = [item["event"]["event_hash"] for item in reversals + replacements]
    if len(set(proposed_hashes)) != len(proposed_hashes):
        raise OrderCashRepairManifestError("proposed event hashes are not unique")
    conn = sqlite3.connect(str(db_path))
    try:
        existing = conn.execute(
            f"SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({','.join('?' for _ in proposed_hashes)})",
            proposed_hashes,
        ).fetchall()
    finally:
        conn.close()
    if existing:
        raise OrderCashRepairManifestError("one or more proposed event hashes already exist")

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "operation": "COPIED_DB_APPEND_ONLY_MAPPED_ORDER_CASH_REPAIR",
        "production_apply_authorized": False,
        "copied_apply_ready": True,
        "canonical_hash_version": CANONICAL_HASH_VERSION,
        "db_path": str(db_path),
        "db_sha256": sha256_file(db_path),
        "db_integrity_check": integrity,
        "cash_table_logical_sha256": cash_table_sha,
        "order_id": order_id,
        "store_code": store_code,
        "repair_key": repair_key,
        "run_id": run_id,
        "publication_binding_id": publication["binding_id"],
        "publication_manifest_path": str(publication_manifest_path),
        "publication_manifest_file_sha256": sha256_file(publication_manifest_path),
        "publication_manifest_internal_sha256": publication["manifest_sha256"],
        "publication_binding_validation": binding_validation,
        "superseded_event_count": len(reversals),
        "replacement_event_count": len(replacements),
        "expected_insert_count": len(reversals) + len(replacements),
        "reversal_total_kzt": round(sum(float(item["event"]["amount_kzt"]) for item in reversals), 2),
        "replacement_total_kzt": round(sum(float(item["event"]["amount_kzt"]) for item in replacements), 2),
        "reversals": reversals,
        "replacements": replacements,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--publication-manifest", type=Path, required=True)
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--store-code", required=True)
    parser.add_argument("--supersede-event-ids", required=True)
    parser.add_argument("--repair-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        ids = [int(value.strip()) for value in args.supersede_event_ids.split(",") if value.strip()]
        manifest = build_manifest(
            db_path=args.db,
            publication_manifest_path=args.publication_manifest,
            order_id=args.order_id,
            store_code=args.store_code,
            supersede_event_ids=ids,
            repair_key=args.repair_key,
            run_id=args.run_id,
        )
    except (OrderCashRepairManifestError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "manifest_sha256": manifest["manifest_sha256"], "insert_count": manifest["expected_insert_count"], "reversal_total_kzt": manifest["reversal_total_kzt"], "replacement_total_kzt": manifest["replacement_total_kzt"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
