#!/usr/bin/env python3
"""Materialize STOREB header-only source-gap quarantine rows on a temp DB only."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.truth_views import ensure_sales_truth_views  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
WRITE_ENV_GATE = "ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY"
QUARANTINE_TABLE = "fact_order_entry_header_only_source_gap_quarantine"
REASON_CODE = "HEADER_ONLY_NO_REAL_ITEM_ENTRY_EVIDENCE"


class HeaderOnlySourceGapQuarantineError(RuntimeError):
    """Raised when header-only quarantine materialization cannot prove exclusion."""


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _truthy(value: Any) -> bool:
    return _upper(value) in {"1", "TRUE", "YES", "Y"}


def _int_or_none(value: Any) -> int | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _relation_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(conn, name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _read_header_only_candidates(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        raise HeaderOnlySourceGapQuarantineError(f"classification file missing: {path}")
    with path.open("r", newline="", encoding="utf-8") as fh:
        source_rows = list(csv.DictReader(fh, delimiter="\t"))
    if not source_rows:
        raise HeaderOnlySourceGapQuarantineError("classification file has no rows")

    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for row in source_rows:
        if _upper(row.get("recommended_action")) != "HEADER_ONLY_BLOCKER":
            continue
        store_code = _upper(row.get("store_code"))
        order_id = _norm(row.get("order_id"))
        pair = (store_code, order_id)
        if store_code != "STOREB" or not order_id:
            raise HeaderOnlySourceGapQuarantineError(f"invalid header-only row store/order: {row}")
        if pair in seen:
            raise HeaderOnlySourceGapQuarantineError(f"duplicate header-only row: {pair}")
        seen.add(pair)
        if _truthy(row.get("real_api_item_entry_evidence_exists")):
            raise HeaderOnlySourceGapQuarantineError(f"real API item-entry evidence exists for {pair}")
        source_evidence = _norm(row.get("real_api_item_entry_evidence_source"))
        if not source_evidence:
            raise HeaderOnlySourceGapQuarantineError(f"missing source hierarchy proof for {pair}")
        if source_evidence != "NONE_IN_AGENT69B_APPROVED_SOURCE_HIERARCHY":
            raise HeaderOnlySourceGapQuarantineError(
                f"unexpected source hierarchy proof for {pair}: {source_evidence}"
            )
        if not _truthy(row.get("crm_header_evidence_present")):
            raise HeaderOnlySourceGapQuarantineError(f"CRM/header evidence missing for {pair}")
        if not _truthy(row.get("crm_header_evidence_only")):
            raise HeaderOnlySourceGapQuarantineError(f"row is not header-only for {pair}")
        if _truthy(row.get("overlaps_agent69c_23")):
            raise HeaderOnlySourceGapQuarantineError(
                f"Agent69C API-backed row must use strict product-identity quarantine: {pair}"
            )
        header_source_file = _norm(row.get("sales_fact_source_file"))
        if not header_source_file:
            raise HeaderOnlySourceGapQuarantineError(f"missing header source file for {pair}")

        source_hierarchy = {
            "approved_hierarchy_checked": True,
            "approved_hierarchy_name": "Agent69B approved order-entry evidence hierarchy",
            "real_item_entry_evidence_exists": False,
            "real_item_entry_evidence_source": source_evidence,
            "crm_header_evidence_present": True,
            "crm_header_evidence_only": True,
            "overlaps_agent69c_23": False,
            "classification_reason": _norm(row.get("classification_reason")),
        }
        candidates.append(
            {
                "store_code": store_code,
                "order_id": order_id,
                "sale_id": _int_or_none(row.get("sale_id")),
                "order_date": _norm(row.get("order_date")),
                "reason_code": REASON_CODE,
                "header_sku_key": _norm(row.get("sales_fact_sku_key")),
                "header_sku_id": _norm(row.get("sales_fact_sku_id")),
                "header_my_size": _norm(row.get("sales_fact_my_size")),
                "header_kaspi_offer_name": _norm(row.get("sales_fact_kaspi_offer_name")),
                "header_quantity": _float_or_none(row.get("sales_fact_quantity")),
                "header_source_file": header_source_file,
                "source_hierarchy_checked_json": json.dumps(
                    source_hierarchy,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )
    if not candidates:
        raise HeaderOnlySourceGapQuarantineError("classification file has no HEADER_ONLY_BLOCKER rows")
    return candidates, len(source_rows)


def _guard_apply_path(db_path: Path, *, allow_production_apply: bool = False) -> None:
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise HeaderOnlySourceGapQuarantineError(f"{WRITE_ENV_GATE}=1 is required for --apply")
    if not allow_production_apply:
        _guard_production_apply_path(db_path)


def _guard_production_apply_path(db_path: Path) -> None:
    try:
        resolved = db_path.resolve()
        production = DEFAULT_DB.resolve()
    except FileNotFoundError:
        resolved = db_path.absolute()
        production = DEFAULT_DB.absolute()
    if resolved == production:
        raise HeaderOnlySourceGapQuarantineError("refusing to apply header-only quarantine to production db/app.db")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            sale_id INTEGER,
            order_date TEXT NOT NULL,
            reason_code TEXT NOT NULL CHECK(reason_code='{REASON_CODE}'),
            header_sku_key TEXT,
            header_sku_id TEXT,
            header_my_size TEXT,
            header_kaspi_offer_name TEXT,
            header_quantity REAL,
            header_source_file TEXT NOT NULL,
            source_hierarchy_checked_json TEXT NOT NULL,
            publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
            product_stock_excluded INTEGER NOT NULL DEFAULT 1,
            product_cogs_excluded INTEGER NOT NULL DEFAULT 1,
            product_profit_excluded INTEGER NOT NULL DEFAULT 1,
            sku_publication_excluded INTEGER NOT NULL DEFAULT 1,
            publication_exclusion_proof_json TEXT NOT NULL,
            owner_or_codecaptain_review_status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
            active_flag INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (store_code, order_id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_header_only_source_gap_order
        ON {QUARANTINE_TABLE}(order_id, store_code)
        """
    )


def _order_id_params(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    order_ids = [str(row["order_id"]) for row in rows]
    placeholders = ",".join("?" for _ in order_ids)
    return placeholders, order_ids


def _product_cashflow_where_clause() -> str:
    return """
    (
      UPPER(COALESCE(event_type, '')) IN ('COGS_RECOGNIZED', 'INVENTORY_MOVE')
      OR UPPER(COALESCE(event_type, '')) LIKE '%COGS%'
      OR UPPER(COALESCE(account, '')) LIKE 'INVENTORY_%'
      OR UPPER(COALESCE(account, '')) = 'COGS'
    )
    """


def _leakage_counts(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {
            "stock_ledger_reference_count": 0,
            "product_cashflow_reference_count": 0,
            "published_sales_truth_line_count": 0,
            "fact_order_entries_count": 0,
            "sales_fact_cogs_profit_count": 0,
        }
    placeholders, params = _order_id_params(rows)
    counts = {
        "stock_ledger_reference_count": 0,
        "product_cashflow_reference_count": 0,
        "published_sales_truth_line_count": 0,
        "fact_order_entries_count": 0,
        "sales_fact_cogs_profit_count": 0,
    }
    if _table_exists(conn, "stock_ledger"):
        counts["stock_ledger_reference_count"] = int(
            conn.execute(
                f"SELECT COUNT(*) FROM stock_ledger WHERE CAST(reference_id AS TEXT) IN ({placeholders})",
                params,
            ).fetchone()[0]
            or 0
        )
    if _table_exists(conn, "fact_cashflow_events"):
        counts["product_cashflow_reference_count"] = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM fact_cashflow_events
                WHERE CAST(ref_id AS TEXT) IN ({placeholders})
                  AND {_product_cashflow_where_clause()}
                """,
                params,
            ).fetchone()[0]
            or 0
        )
    if _relation_exists(conn, "view_sales_line_truth"):
        counts["published_sales_truth_line_count"] = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM view_sales_line_truth
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = 'STOREB'
                  AND CAST(order_id AS TEXT) IN ({placeholders})
                """,
                params,
            ).fetchone()[0]
            or 0
        )
    if _table_exists(conn, "fact_order_entries_kaspi"):
        counts["fact_order_entries_count"] = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM fact_order_entries_kaspi
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = 'STOREB'
                  AND CAST(order_id AS TEXT) IN ({placeholders})
                """,
                params,
            ).fetchone()[0]
            or 0
        )
    sales_cols = _table_columns(conn, "sales_fact_v2")
    if {"store_code", "order_id"}.issubset(sales_cols):
        profit_clauses = []
        if "cogs" in sales_cols:
            profit_clauses.append("cogs IS NOT NULL")
        if "profit" in sales_cols:
            profit_clauses.append("profit IS NOT NULL")
        profit_where = " OR ".join(profit_clauses) or "0"
        counts["sales_fact_cogs_profit_count"] = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM sales_fact_v2
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = 'STOREB'
                  AND CAST(order_id AS TEXT) IN ({placeholders})
                  AND ({profit_where})
                """,
                params,
            ).fetchone()[0]
            or 0
        )
    return counts


def _delete_product_leakage(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {
            "deleted_stock_ledger_rows": 0,
            "deleted_product_cashflow_rows": 0,
            "nulled_sales_fact_product_profit_rows": 0,
        }
    placeholders, params = _order_id_params(rows)
    deleted_stock = 0
    deleted_cashflow = 0
    nulled_profit_rows = 0
    if _table_exists(conn, "stock_ledger"):
        cur = conn.execute(
            f"DELETE FROM stock_ledger WHERE CAST(reference_id AS TEXT) IN ({placeholders})",
            params,
        )
        deleted_stock = int(cur.rowcount or 0)
    if _table_exists(conn, "fact_cashflow_events"):
        cur = conn.execute(
            f"""
            DELETE FROM fact_cashflow_events
            WHERE CAST(ref_id AS TEXT) IN ({placeholders})
              AND {_product_cashflow_where_clause()}
            """,
            params,
        )
        deleted_cashflow = int(cur.rowcount or 0)
    sales_cols = _table_columns(conn, "sales_fact_v2")
    profit_updates = [col for col in ("cogs", "profit") if col in sales_cols]
    if profit_updates and {"store_code", "order_id"}.issubset(sales_cols):
        assignments = ", ".join(f"{col}=NULL" for col in profit_updates)
        cur = conn.execute(
            f"""
            UPDATE sales_fact_v2
            SET {assignments}
            WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = 'STOREB'
              AND CAST(order_id AS TEXT) IN ({placeholders})
              AND ({' OR '.join(f'{col} IS NOT NULL' for col in profit_updates)})
            """,
            params,
        )
        nulled_profit_rows = int(cur.rowcount or 0)
    return {
        "deleted_stock_ledger_rows": deleted_stock,
        "deleted_product_cashflow_rows": deleted_cashflow,
        "nulled_sales_fact_product_profit_rows": nulled_profit_rows,
    }


def _upsert_quarantine_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    proof_json: str,
    proof_applied: bool,
    created_at: str,
) -> int:
    inserted = 0
    for row in rows:
        cur = conn.execute(
            f"""
            INSERT INTO {QUARANTINE_TABLE} (
                store_code, order_id, sale_id, order_date, reason_code,
                header_sku_key, header_sku_id, header_my_size,
                header_kaspi_offer_name, header_quantity, header_source_file,
                source_hierarchy_checked_json, publication_exclusion_required,
                product_stock_excluded, product_cogs_excluded, product_profit_excluded,
                sku_publication_excluded, publication_exclusion_proof_json,
                owner_or_codecaptain_review_status, active_flag, created_by, created_at
            ) VALUES (
                :store_code, :order_id, :sale_id, :order_date, :reason_code,
                :header_sku_key, :header_sku_id, :header_my_size,
                :header_kaspi_offer_name, :header_quantity, :header_source_file,
                :source_hierarchy_checked_json, 1,
                :product_stock_excluded, :product_cogs_excluded, :product_profit_excluded,
                :sku_publication_excluded, :publication_exclusion_proof_json,
                'REVIEW_REQUIRED', 1, :created_by, :created_at
            )
            ON CONFLICT(store_code, order_id)
            DO UPDATE SET
                sale_id=excluded.sale_id,
                order_date=excluded.order_date,
                reason_code=excluded.reason_code,
                header_sku_key=excluded.header_sku_key,
                header_sku_id=excluded.header_sku_id,
                header_my_size=excluded.header_my_size,
                header_kaspi_offer_name=excluded.header_kaspi_offer_name,
                header_quantity=excluded.header_quantity,
                header_source_file=excluded.header_source_file,
                source_hierarchy_checked_json=excluded.source_hierarchy_checked_json,
                publication_exclusion_required=1,
                product_stock_excluded=excluded.product_stock_excluded,
                product_cogs_excluded=excluded.product_cogs_excluded,
                product_profit_excluded=excluded.product_profit_excluded,
                sku_publication_excluded=excluded.sku_publication_excluded,
                publication_exclusion_proof_json=excluded.publication_exclusion_proof_json,
                owner_or_codecaptain_review_status='REVIEW_REQUIRED',
                active_flag=1,
                created_by=excluded.created_by,
                created_at=excluded.created_at
            """,
            {
                **row,
                "product_stock_excluded": 1 if proof_applied else 0,
                "product_cogs_excluded": 1 if proof_applied else 0,
                "product_profit_excluded": 1 if proof_applied else 0,
                "sku_publication_excluded": 1 if proof_applied else 0,
                "publication_exclusion_proof_json": proof_json,
                "created_by": "agent696_header_only_source_gap_quarantine",
                "created_at": created_at,
            },
        )
        inserted += int(cur.rowcount or 0)
    return inserted


def _refresh_sales_truth_views(conn: sqlite3.Connection) -> bool:
    if not (_table_exists(conn, "sales_fact_v2") or _table_exists(conn, "fact_sales")):
        return False
    ensure_sales_truth_views(conn)
    return True


def _write_outputs(output_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fieldnames = [
        "store_code",
        "order_id",
        "sale_id",
        "order_date",
        "reason_code",
        "header_sku_key",
        "header_sku_id",
        "header_my_size",
        "header_kaspi_offer_name",
        "header_quantity",
        "header_source_file",
        "source_hierarchy_checked_json",
    ]
    with (output_root / "quarantine_rows.tsv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def materialize_header_only_source_gap_quarantine(
    *,
    db_path: Path,
    classification_path: Path,
    output_root: Path,
    apply: bool = False,
    allow_production_apply: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise HeaderOnlySourceGapQuarantineError(f"db not found: {db_path}")
    rows, source_row_count = _read_header_only_candidates(classification_path)
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    conn_uri = str(db_path) if apply else f"file:{db_path}?mode=ro"
    with sqlite3.connect(conn_uri, uri=not apply) as conn:
        conn.row_factory = sqlite3.Row
        leakage_before = _leakage_counts(conn, rows)
        action = {
            "applied": False,
            "inserted_quarantine_rows": 0,
            "deleted_stock_ledger_rows": 0,
            "deleted_product_cashflow_rows": 0,
            "nulled_sales_fact_product_profit_rows": 0,
            "sales_truth_views_refreshed": False,
        }
        leakage_after = dict(leakage_before)

        if apply:
            # The production override is Python-only and intended solely for the
            # vetted production wrapper after its external safety gates pass.
            _guard_apply_path(db_path, allow_production_apply=allow_production_apply)
            _ensure_table(conn)
            provisional_proof = json.dumps(
                {
                    "generated_at": generated_at,
                    "proof_status": "PENDING_PUBLICATION_EXCLUSION_APPLY",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            _upsert_quarantine_rows(
                conn,
                rows,
                proof_json=provisional_proof,
                proof_applied=False,
                created_at=generated_at,
            )
            deleted = _delete_product_leakage(conn, rows)
            action.update(deleted)
            action["sales_truth_views_refreshed"] = _refresh_sales_truth_views(conn)
            leakage_after = _leakage_counts(conn, rows)
            proof_json = json.dumps(
                {
                    "generated_at": generated_at,
                    "leakage_before": leakage_before,
                    "leakage_after": leakage_after,
                    "cash_in_preserved": True,
                    "product_level_publication_excluded": True,
                    "header_fields_are_evidence_only": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if leakage_after.get("fact_order_entries_count"):
                raise HeaderOnlySourceGapQuarantineError(
                    f"canonical entry rows exist for header-only quarantined orders: {leakage_after}"
                )
            blocking_leaks = {
                key: value
                for key, value in leakage_after.items()
                if key != "fact_order_entries_count" and value
            }
            if blocking_leaks:
                raise HeaderOnlySourceGapQuarantineError(
                    f"publication exclusion proof failed: {leakage_after}"
                )
            action["inserted_quarantine_rows"] = _upsert_quarantine_rows(
                conn,
                rows,
                proof_json=proof_json,
                proof_applied=True,
                created_at=generated_at,
            )
            action["applied"] = True
            conn.commit()

    summary = {
        "generated_at": generated_at,
        "db_path": str(db_path),
        "classification_path": str(classification_path),
        "output_root": str(output_root),
        "source_rows": source_row_count,
        "candidate_rows": len(rows),
        "order_ids": [row["order_id"] for row in rows],
        "leakage_before": leakage_before,
        "leakage_after": leakage_after,
        "apply": action,
        "reason_code": REASON_CODE,
        "production_db_modified": False,
        "fact_order_entries_inserted": 0,
        "header_fields_used_as_canonical_item_entry_truth": False,
    }
    _write_outputs(output_root, summary, rows)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = materialize_header_only_source_gap_quarantine(
            db_path=args.db,
            classification_path=args.classification,
            output_root=args.output_root,
            apply=bool(args.apply),
        )
    except HeaderOnlySourceGapQuarantineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"summary_json={args.output_root / 'summary.json'}")
    print(f"candidate_rows={summary['candidate_rows']}")
    print(f"applied={summary['apply']['applied']}")
    print(f"deleted_stock_ledger_rows={summary['apply']['deleted_stock_ledger_rows']}")
    print(f"deleted_product_cashflow_rows={summary['apply']['deleted_product_cashflow_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
