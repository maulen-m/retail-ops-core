#!/usr/bin/env python3
"""Deactivate stale header-only quarantine rows superseded by real API entries."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_db import backup_database  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
HEADER_ONLY_TABLE = "fact_order_entry_header_only_source_gap_quarantine"
WRITE_ENV_GATE = "ENABLE_HEADER_ONLY_REAL_ENTRY_RECLASSIFICATION_APPLY"
REVIEW_STATUS = "SUPERSEDED_BY_REAL_API_ENTRY_EVIDENCE"


class HeaderOnlyRealEntryReclassificationError(RuntimeError):
    """Raised when the reclassification cannot prove its evidence contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_check(path: Path) -> str:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise HeaderOnlyRealEntryReclassificationError(
            f"refusing production apply while SQLite sidecars exist: {joined}"
        )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _product_cashflow_where_clause() -> str:
    return """
    (
      UPPER(COALESCE(event_type, '')) IN ('COGS_RECOGNIZED', 'INVENTORY_MOVE')
      OR UPPER(COALESCE(event_type, '')) LIKE '%COGS%'
      OR UPPER(COALESCE(account, '')) LIKE 'INVENTORY_%'
      OR UPPER(COALESCE(account, '')) = 'COGS'
    )
    """


def _offer_code_from_entry(row: sqlite3.Row) -> str:
    raw = str(row["raw_json"] or "") if "raw_json" in row.keys() else ""
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        offer = (((payload.get("attributes") or {}).get("offer")) or {})
        code = str(offer.get("code") or "").strip()
        if code:
            return code
    return str(row["offer_id"] or "").strip() if "offer_id" in row.keys() else ""


def _offer_matches_header_sku_id(*, offer_code: str, header_sku_id: str) -> bool:
    offer = offer_code.strip().upper()
    header = header_sku_id.strip().upper()
    return bool(header and (offer == header or offer.startswith(f"{header}_")))


def _query_state(conn: sqlite3.Connection, *, store_code: str, order_id: str) -> dict[str, Any]:
    if not _table_exists(conn, HEADER_ONLY_TABLE):
        raise HeaderOnlyRealEntryReclassificationError(f"missing table: {HEADER_ONLY_TABLE}")
    if not _table_exists(conn, "fact_order_entries_kaspi"):
        raise HeaderOnlyRealEntryReclassificationError("missing table: fact_order_entries_kaspi")

    header_rows = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT *
            FROM {HEADER_ONLY_TABLE}
            WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
              AND CAST(order_id AS TEXT) = ?
              AND COALESCE(active_flag, 1) = 1
            """,
            (store_code, order_id),
        ).fetchall()
    ]
    header_row = header_rows[0] if header_rows else {}
    header_sku_id = str(header_row.get("header_sku_id") or "")

    entry_rows = conn.execute(
        """
        SELECT *
        FROM fact_order_entries_kaspi
        WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
          AND CAST(order_id AS TEXT) = ?
        ORDER BY entry_id
        """,
        (store_code, order_id),
    ).fetchall()
    entry_payloads: list[dict[str, Any]] = []
    compatible_count = 0
    for row in entry_rows:
        offer_code = _offer_code_from_entry(row)
        compatible = _offer_matches_header_sku_id(offer_code=offer_code, header_sku_id=header_sku_id)
        compatible_count += 1 if compatible else 0
        entry_payloads.append(
            {
                "entry_id": str(row["entry_id"] or ""),
                "product_id": str(row["product_id"] or "") if "product_id" in row.keys() else "",
                "offer_code": offer_code,
                "quantity": float(row["quantity"] or 0),
                "total_price_kzt": float(row["total_price_kzt"] or 0),
                "offer_matches_header_sku_id": compatible,
            }
        )

    product_cashflow_count = 0
    if _table_exists(conn, "fact_cashflow_events"):
        product_cashflow_count = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM fact_cashflow_events
                WHERE CAST(ref_id AS TEXT) = ?
                  AND {_product_cashflow_where_clause()}
                """,
                (order_id,),
            ).fetchone()[0]
            or 0
        )

    stock_reference_count = 0
    if _table_exists(conn, "stock_ledger"):
        stock_reference_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM stock_ledger
                WHERE CAST(reference_id AS TEXT) = ?
                """,
                (order_id,),
            ).fetchone()[0]
            or 0
        )

    return {
        "active_header_only_count": len(header_rows),
        "header_row": header_row,
        "api_entry_count": len(entry_rows),
        "api_entries_with_offer_matching_header_sku_id": compatible_count,
        "api_entries": entry_payloads,
        "product_cashflow_reference_count": product_cashflow_count,
        "stock_ledger_reference_count": stock_reference_count,
    }


def _validate_state(
    *,
    state: dict[str, Any],
    expected_active_header_only_count: int,
    expected_api_entry_count: int,
    expected_product_cashflow_reference_count: int,
    expected_stock_ledger_reference_count: int,
) -> None:
    checks = {
        "active_header_only_count": expected_active_header_only_count,
        "api_entry_count": expected_api_entry_count,
        "api_entries_with_offer_matching_header_sku_id": expected_api_entry_count,
        "product_cashflow_reference_count": expected_product_cashflow_reference_count,
        "stock_ledger_reference_count": expected_stock_ledger_reference_count,
    }
    for key, expected in checks.items():
        actual = int(state.get(key) or 0)
        if actual != int(expected):
            raise HeaderOnlyRealEntryReclassificationError(
                f"{key} mismatch: expected {expected}, got {actual}"
            )


def _write_summary(output_root: Path, summary: dict[str, Any]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    summary["summary_json"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def materialize_header_only_real_entry_reclassification(
    *,
    db_path: Path,
    output_root: Path,
    store_code: str,
    order_id: str,
    expected_active_header_only_count: int,
    expected_api_entry_count: int,
    expected_product_cashflow_reference_count: int,
    expected_stock_ledger_reference_count: int,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    db = Path(db_path).resolve()
    output = Path(output_root).resolve()
    backup_root = Path(backup_dir).resolve() if backup_dir else None
    store = store_code.strip().upper() or "UNIVERSAL"
    order = str(order_id).strip()
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    if not db.exists():
        raise HeaderOnlyRealEntryReclassificationError(f"db not found: {db}")
    if not order:
        raise HeaderOnlyRealEntryReclassificationError("order_id is required")
    if apply and os.environ.get(WRITE_ENV_GATE) != "1":
        raise HeaderOnlyRealEntryReclassificationError(f"{WRITE_ENV_GATE}=1 is required with --apply")
    if apply and backup_root is None:
        raise HeaderOnlyRealEntryReclassificationError("--backup-dir is required with --apply")
    if apply and not expected_pre_sha256:
        raise HeaderOnlyRealEntryReclassificationError("--expected-pre-sha256 is required with --apply")
    if apply:
        _fail_on_sqlite_sidecars(db)

    integrity_before = _integrity_check(db)
    if integrity_before.lower() != "ok":
        raise HeaderOnlyRealEntryReclassificationError(f"pre-write integrity_check failed: {integrity_before}")

    pre_sha = _sha256(db)
    if expected_pre_sha256 and pre_sha != expected_pre_sha256:
        raise HeaderOnlyRealEntryReclassificationError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha}"
        )
    backup_path: Path | None = None
    backup_sha: str | None = None
    if apply and backup_root is not None:
        backup_path = backup_database(db, backup_root, compress=False)
        backup_sha = _sha256(backup_path)
        backup_integrity = _integrity_check(backup_path)
        if backup_integrity.lower() != "ok":
            raise HeaderOnlyRealEntryReclassificationError(f"backup integrity_check failed: {backup_integrity}")
    else:
        backup_integrity = None

    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        before = _query_state(conn, store_code=store, order_id=order)
        _validate_state(
            state=before,
            expected_active_header_only_count=expected_active_header_only_count,
            expected_api_entry_count=expected_api_entry_count,
            expected_product_cashflow_reference_count=expected_product_cashflow_reference_count,
            expected_stock_ledger_reference_count=expected_stock_ledger_reference_count,
        )
        updated_rows = 0
        if apply:
            proof_json = json.dumps(
                {
                    "generated_at": generated_at,
                    "reclassification": REVIEW_STATUS,
                    "real_api_entry_evidence": before["api_entries"],
                    "previous_header_only_row": before["header_row"],
                    "product_cashflow_reference_count_preserved": before[
                        "product_cashflow_reference_count"
                    ],
                    "stock_ledger_reference_count": before["stock_ledger_reference_count"],
                    "header_only_quarantine_active_after_apply": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            cur = conn.execute(
                f"""
                UPDATE {HEADER_ONLY_TABLE}
                SET active_flag = 0,
                    publication_exclusion_required = 0,
                    product_stock_excluded = 0,
                    product_cogs_excluded = 0,
                    product_profit_excluded = 0,
                    sku_publication_excluded = 0,
                    owner_or_codecaptain_review_status = ?,
                    publication_exclusion_proof_json = ?
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                  AND COALESCE(active_flag, 1) = 1
                """,
                (REVIEW_STATUS, proof_json, store, order),
            )
            updated_rows = int(cur.rowcount or 0)
            if updated_rows != expected_active_header_only_count:
                raise HeaderOnlyRealEntryReclassificationError(
                    f"updated_rows mismatch: expected {expected_active_header_only_count}, got {updated_rows}"
                )
            conn.commit()
        after = _query_state(conn, store_code=store, order_id=order)

    post_sha = _sha256(db)
    integrity_after = _integrity_check(db)
    if integrity_after.lower() != "ok":
        raise HeaderOnlyRealEntryReclassificationError(f"post-write integrity_check failed: {integrity_after}")

    summary = {
        "generated_at": generated_at,
        "db_path": str(db),
        "output_root": str(output),
        "store_code": store,
        "order_id": order,
        "env_gate": WRITE_ENV_GATE,
        "apply": {"requested": bool(apply), "applied": bool(apply), "updated_rows": updated_rows},
        "expected": {
            "pre_sha256": expected_pre_sha256,
            "active_header_only_count": expected_active_header_only_count,
            "api_entry_count": expected_api_entry_count,
            "product_cashflow_reference_count": expected_product_cashflow_reference_count,
            "stock_ledger_reference_count": expected_stock_ledger_reference_count,
        },
        "before": before,
        "after": after,
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "integrity_check": {"before": integrity_before, "backup": backup_integrity, "after": integrity_after},
        "backup_path": str(backup_path) if backup_path else None,
        "backup_sha256": backup_sha,
        "fact_order_entries_inserted": 0,
        "product_cashflow_deleted": 0,
        "stock_ledger_deleted": 0,
        "rollback": {
            "backup_path": str(backup_path) if backup_path else None,
            "restore_command": (
                "python3 - <<'PY'\n"
                "import sqlite3\n"
                f"backup_path = {str(backup_path)!r}\n"
                f"target_db = {str(db)!r}\n"
                "with sqlite3.connect(backup_path) as source, sqlite3.connect(target_db) as target:\n"
                "    source.backup(target)\n"
                "PY"
                if backup_path
                else None
            ),
        },
    }
    _write_summary(output, summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--store-code", default="STOREB")
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--expected-active-header-only-count", type=int, required=True)
    parser.add_argument("--expected-api-entry-count", type=int, required=True)
    parser.add_argument("--expected-product-cashflow-reference-count", type=int, required=True)
    parser.add_argument("--expected-stock-ledger-reference-count", type=int, required=True)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = materialize_header_only_real_entry_reclassification(
            db_path=args.db,
            output_root=args.output_root,
            backup_dir=args.backup_dir,
            store_code=args.store_code,
            order_id=args.order_id,
            expected_active_header_only_count=args.expected_active_header_only_count,
            expected_api_entry_count=args.expected_api_entry_count,
            expected_product_cashflow_reference_count=args.expected_product_cashflow_reference_count,
            expected_stock_ledger_reference_count=args.expected_stock_ledger_reference_count,
            expected_pre_sha256=args.expected_pre_sha256,
            apply=bool(args.apply),
        )
    except HeaderOnlyRealEntryReclassificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"summary_json={summary['summary_json']}")
        print(f"applied={summary['apply']['applied']}")
        print(f"updated_rows={summary['apply']['updated_rows']}")
        print(f"backup_path={summary['backup_path']}")
        print(f"active_header_only_after={summary['after']['active_header_only_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
