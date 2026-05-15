#!/usr/bin/env python3
"""Materialize STOREB product-identity quarantine rows on a temp DB only."""

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
WRITE_ENV_GATE = "ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_TEMP_APPLY"
QUARANTINE_TABLE = "fact_order_entry_product_identity_quarantine"
REASON_CODE = "MISSING_APPROVED_CANONICAL_PRODUCT_IDENTITY"


class QuarantineMaterializationError(RuntimeError):
    """Raised when quarantine materialization cannot prove publication exclusion."""


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


def _semicolon_count(value: Any) -> int:
    text = _norm(value)
    if not text:
        return 0
    return len([part for part in text.split(";") if part.strip()])


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


def _read_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise QuarantineMaterializationError(f"candidate file missing: {path}")
    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise QuarantineMaterializationError("candidate file has no rows")

    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        store_code = _upper(row.get("store_code"))
        order_id = _norm(row.get("order_id"))
        if store_code != "STOREB" or not order_id:
            raise QuarantineMaterializationError(f"invalid quarantine row store/order: {row}")
        pair = (store_code, order_id)
        if pair in seen:
            raise QuarantineMaterializationError(f"duplicate quarantine row: {pair}")
        seen.add(pair)
        reason_code = _upper(row.get("reason_code"))
        if not reason_code and _truthy(row.get("strict_quarantine_candidate")):
            reason_code = REASON_CODE
        if reason_code != REASON_CODE:
            raise QuarantineMaterializationError(f"invalid reason_code for {pair}: {reason_code}")
        if not _norm(row.get("api_entry_ids")) or not _norm(row.get("api_offer_codes")):
            raise QuarantineMaterializationError(f"missing API evidence for {pair}")
        if not _truthy(row.get("publication_exclusion_required")):
            raise QuarantineMaterializationError(f"publication exclusion not required for {pair}")
        normalized.append(
            {
                "store_code": store_code,
                "order_id": order_id,
                "sale_id": _int_or_none(row.get("sale_id") or row.get("validator_row_id")),
                "order_date": _norm(row.get("order_date")),
                "reason_code": REASON_CODE,
                "api_entry_ids": _norm(row.get("api_entry_ids")),
                "api_offer_codes": _norm(row.get("api_offer_codes")),
                "api_product_ids": _norm(row.get("api_product_ids")),
                "api_entry_count": _int_or_none(row.get("api_entry_count")) or _semicolon_count(row.get("api_entry_ids")),
                "api_entries_with_complete_sku_id_size": _int_or_none(
                    row.get("api_entries_with_complete_sku_id_size")
                )
                or 0,
            }
        )
    return normalized


def _guard_apply_path(db_path: Path) -> None:
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise QuarantineMaterializationError(f"{WRITE_ENV_GATE}=1 is required for --apply")
    try:
        resolved = db_path.resolve()
        production = DEFAULT_DB.resolve()
    except FileNotFoundError:
        resolved = db_path.absolute()
        production = DEFAULT_DB.absolute()
    if resolved == production:
        raise QuarantineMaterializationError("refusing to apply STOREB quarantine to production db/app.db")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            sale_id INTEGER,
            order_date TEXT,
            reason_code TEXT NOT NULL,
            api_entry_ids TEXT NOT NULL,
            api_offer_codes TEXT NOT NULL,
            api_product_ids TEXT,
            api_entry_count INTEGER NOT NULL DEFAULT 0,
            api_entries_with_complete_sku_id_size INTEGER NOT NULL DEFAULT 0,
            publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
            product_stock_excluded INTEGER NOT NULL DEFAULT 0,
            product_cogs_excluded INTEGER NOT NULL DEFAULT 0,
            product_profit_excluded INTEGER NOT NULL DEFAULT 0,
            sku_publication_excluded INTEGER NOT NULL DEFAULT 0,
            publication_exclusion_proof_json TEXT,
            active_flag INTEGER NOT NULL DEFAULT 1,
            evidence_source TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (store_code, order_id)
        )
        """
    )
    conn.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_product_identity_quarantine_order
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
        }
    placeholders, params = _order_id_params(rows)
    counts = {
        "stock_ledger_reference_count": 0,
        "product_cashflow_reference_count": 0,
        "published_sales_truth_line_count": 0,
        "fact_order_entries_count": 0,
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
    return counts


def _delete_product_leakage(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {"deleted_stock_ledger_rows": 0, "deleted_product_cashflow_rows": 0}
    placeholders, params = _order_id_params(rows)
    deleted_stock = 0
    deleted_cashflow = 0
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
    return {
        "deleted_stock_ledger_rows": deleted_stock,
        "deleted_product_cashflow_rows": deleted_cashflow,
    }


def _upsert_quarantine_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    proof_json: str | None,
    proof_applied: bool,
    created_at: str,
) -> int:
    inserted = 0
    for row in rows:
        cur = conn.execute(
            f"""
            INSERT INTO {QUARANTINE_TABLE} (
                store_code, order_id, sale_id, order_date, reason_code,
                api_entry_ids, api_offer_codes, api_product_ids, api_entry_count,
                api_entries_with_complete_sku_id_size, publication_exclusion_required,
                product_stock_excluded, product_cogs_excluded, product_profit_excluded,
                sku_publication_excluded, publication_exclusion_proof_json, active_flag,
                evidence_source, created_by, created_at
            ) VALUES (
                :store_code, :order_id, :sale_id, :order_date, :reason_code,
                :api_entry_ids, :api_offer_codes, :api_product_ids, :api_entry_count,
                :api_entries_with_complete_sku_id_size, 1,
                :product_stock_excluded, :product_cogs_excluded, :product_profit_excluded,
                :sku_publication_excluded, :publication_exclusion_proof_json, 1,
                :evidence_source, :created_by, :created_at
            )
            ON CONFLICT(store_code, order_id)
            DO UPDATE SET
                sale_id=excluded.sale_id,
                order_date=excluded.order_date,
                reason_code=excluded.reason_code,
                api_entry_ids=excluded.api_entry_ids,
                api_offer_codes=excluded.api_offer_codes,
                api_product_ids=excluded.api_product_ids,
                api_entry_count=excluded.api_entry_count,
                api_entries_with_complete_sku_id_size=excluded.api_entries_with_complete_sku_id_size,
                publication_exclusion_required=1,
                product_stock_excluded=excluded.product_stock_excluded,
                product_cogs_excluded=excluded.product_cogs_excluded,
                product_profit_excluded=excluded.product_profit_excluded,
                sku_publication_excluded=excluded.sku_publication_excluded,
                publication_exclusion_proof_json=excluded.publication_exclusion_proof_json,
                active_flag=1,
                evidence_source=excluded.evidence_source,
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
                "evidence_source": "agent39_storeb_23_strict_quarantine_candidates",
                "created_by": "agent43_storeb_product_identity_quarantine",
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
    with (output_root / "quarantine_rows.csv").open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "store_code",
            "order_id",
            "sale_id",
            "order_date",
            "reason_code",
            "api_entry_ids",
            "api_offer_codes",
            "api_product_ids",
            "api_entry_count",
            "api_entries_with_complete_sku_id_size",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def materialize_storeb_product_identity_quarantine(
    *,
    db_path: Path,
    candidates_path: Path,
    output_root: Path,
    apply: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise QuarantineMaterializationError(f"db not found: {db_path}")
    rows = _read_candidates(candidates_path)
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
            "sales_truth_views_refreshed": False,
        }
        leakage_after = dict(leakage_before)

        if apply:
            _guard_apply_path(db_path)
            _ensure_table(conn)
            _upsert_quarantine_rows(
                conn,
                rows,
                proof_json=None,
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
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if any(value for key, value in leakage_after.items() if key != "fact_order_entries_count"):
                raise QuarantineMaterializationError(
                    f"publication exclusion proof failed: {leakage_after}"
                )
            if leakage_after.get("fact_order_entries_count"):
                raise QuarantineMaterializationError(
                    f"canonical entry rows still exist for quarantined orders: {leakage_after}"
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
        "candidates_path": str(candidates_path),
        "output_root": str(output_root),
        "candidate_rows": len(rows),
        "order_ids": [row["order_id"] for row in rows],
        "leakage_before": leakage_before,
        "leakage_after": leakage_after,
        "apply": action,
        "production_db_modified": False,
        "fact_order_entries_inserted": 0,
        "header_fallback_identity_used_as_product_truth": False,
    }
    _write_outputs(output_root, summary, rows)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = materialize_storeb_product_identity_quarantine(
            db_path=args.db,
            candidates_path=args.candidates,
            output_root=args.output_root,
            apply=bool(args.apply),
        )
    except QuarantineMaterializationError as exc:
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
