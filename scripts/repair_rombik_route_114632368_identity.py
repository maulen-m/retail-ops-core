#!/usr/bin/env python3
"""Targeted ROMBIK 114632368 identity repair.

Dry-run by default. Apply requires:
  ENABLE_ROMBIK_ROUTE_REPAIR_APPLY=1
  --apply

The repair is intentionally narrow:
- one Universal dim_kaspi_article_map row
- affected Universal API order-entry rows whose raw offer code is 114632368
- matching already-materialized fact_orders_kaspi rows
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "rombik_route_114632368_identity_repair"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "db" / "backups"
WRITE_ENV_GATE = "ENABLE_ROMBIK_ROUTE_REPAIR_APPLY"

STORE_CODE = "UNIVERSAL"
TARGET_ARTICLE = "CL_NEW-CLO_MEN_ROMBIK_BLACK_3XL_114632368"
TARGET_SKU_KEY = "CL_NEW-CLO_MEN_ROMBIK_BLACK"
TARGET_SKU_ID = "CL_NEW-CLO_MEN_ROMBIK_BLACK_3XL"
TARGET_SIZE = "3XL"
OLD_BAD_SKU_ID = "CL_NEW-CLO_MEN_ROMBIK_BLACK_4XL"
REPAIR_SOURCE = "ROMBIK_ROUTE_114632368_REPAIR_2026_06_13"
CURRENT_BLANK_ROW_REPAIR_START = "2026-06-11"


class RepairError(RuntimeError):
    """Raised when the targeted repair is not safe to execute."""


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _backup_db(db_path: Path, backup_root: Path, stamp: str) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"app.pre_rombik_route_114632368_identity_repair_{stamp}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _json_payload(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _entry_offer(payload: dict[str, Any]) -> tuple[str, str]:
    attrs = payload.get("attributes")
    if not isinstance(attrs, dict):
        return "", ""
    offer = attrs.get("offer")
    if not isinstance(offer, dict):
        return "", ""
    code = str(offer.get("code") or offer.get("offerId") or offer.get("id") or "").strip()
    name = str(offer.get("name") or "").strip()
    return code, name


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _required_schema(conn: sqlite3.Connection) -> None:
    for table in ("dim_kaspi_article_map", "fact_order_entries_kaspi", "fact_orders_kaspi", "dim_sku_size"):
        if not _table_exists(conn, table):
            raise RepairError(f"missing required table: {table}")

    map_cols = _columns(conn, "dim_kaspi_article_map")
    required_map = {"store_code", "kaspi_article", "sku_key", "sku_id", "source", "updated_at"}
    missing_map = required_map - map_cols
    if missing_map:
        raise RepairError(f"dim_kaspi_article_map missing columns: {sorted(missing_map)}")

    entry_cols = _columns(conn, "fact_order_entries_kaspi")
    required_entry = {"entry_id", "order_id", "store_code", "offer_id", "raw_json"}
    missing_entry = required_entry - entry_cols
    if missing_entry:
        raise RepairError(f"fact_order_entries_kaspi missing columns: {sorted(missing_entry)}")

    order_cols = _columns(conn, "fact_orders_kaspi")
    required_order = {"order_id", "store_code", "sku_key", "sku_id", "my_size", "kaspi_offer_name", "updated_at"}
    missing_order = required_order - order_cols
    if missing_order:
        raise RepairError(f"fact_orders_kaspi missing columns: {sorted(missing_order)}")


def _load_map_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id,
               source, active_flag, created_at, updated_at
        FROM dim_kaspi_article_map
        WHERE kaspi_article = ?
        ORDER BY store_code, id
        """,
        (TARGET_ARTICLE,),
    ).fetchall()
    return [_row_dict(row) or {} for row in rows]


def _load_target_map_row(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id,
               source, active_flag, created_at, updated_at
        FROM dim_kaspi_article_map
        WHERE store_code = ? AND kaspi_article = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (STORE_CODE, TARGET_ARTICLE),
    ).fetchone()
    item = _row_dict(row)
    if not item:
        raise RepairError(f"target map row missing for {STORE_CODE} {TARGET_ARTICLE}")
    return item


def _load_sku_size(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT sku_id, sku_key, my_size, active_flag
        FROM dim_sku_size
        WHERE sku_id = ?
        """,
        (TARGET_SKU_ID,),
    ).fetchone()
    item = _row_dict(row)
    if not item:
        raise RepairError(f"target sku_id missing from dim_sku_size: {TARGET_SKU_ID}")
    if str(item.get("sku_key") or "") != TARGET_SKU_KEY or str(item.get("my_size") or "") != TARGET_SIZE:
        raise RepairError(f"target sku_id has unexpected identity: {item}")
    return item


def _load_candidate_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT entry_id, order_id, store_code, offer_id, raw_json, updated_at
        FROM fact_order_entries_kaspi
        WHERE UPPER(COALESCE(store_code, '')) = ?
        ORDER BY order_id, entry_id
        """,
        (STORE_CODE,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = _json_payload(row["raw_json"])
        offer_code, offer_name = _entry_offer(payload)
        current_offer_id = str(row["offer_id"] or "").strip()
        if current_offer_id != TARGET_ARTICLE and offer_code != TARGET_ARTICLE:
            continue
        if current_offer_id and current_offer_id != TARGET_ARTICLE:
            raise RepairError(
                f"entry {row['entry_id']} has conflicting offer_id {current_offer_id} "
                f"for raw offer {offer_code}"
            )
        item = _row_dict(row) or {}
        item["raw_offer_code"] = offer_code
        item["raw_offer_name"] = offer_name
        out.append(item)
    return out


def _load_candidate_orders(conn: sqlite3.Connection, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order_ids = sorted({str(row["order_id"]) for row in entries if row.get("order_id")})
    if not order_ids:
        return []
    placeholders = ",".join("?" for _ in order_ids)
    rows = conn.execute(
        f"""
        SELECT id, order_id, store_code, created_at, kaspi_offer_name, sku_key, sku_id, my_size,
               assigned_size, size_source, size_confidence, quantity, unit_price_kzt,
               kaspi_status, internal_status, updated_at
        FROM fact_orders_kaspi
        WHERE UPPER(COALESCE(store_code, '')) = ?
          AND order_id IN ({placeholders})
        ORDER BY created_at, order_id
        """,
        [STORE_CODE, *order_ids],
    ).fetchall()
    orders = [row for row in (_row_dict(row) or {} for row in rows) if _is_target_order_row(row)]
    found = {str(row.get("order_id")) for row in orders}
    missing = [oid for oid in order_ids if oid not in found]
    # Historical recovered entries can share an order id with unrelated lines or have
    # no order row left to repair. That is acceptable as long as current target rows
    # and clear ROMBIK rows are repaired. The skipped ids remain visible in reports.
    if len(missing) == len(order_ids):
        raise RepairError(f"candidate entries have no target fact_orders_kaspi rows: {missing}")
    return orders


def _is_target_order_row(row: dict[str, Any]) -> bool:
    sku_id = str(row.get("sku_id") or "").strip()
    offer_name = str(row.get("kaspi_offer_name") or "").strip()
    offer_lower = offer_name.lower()
    created_at = str(row.get("created_at") or "").strip()

    if "line52" in offer_lower or "rash" in offer_lower or "рашгард" in offer_lower:
        return False
    if sku_id in {TARGET_SKU_ID, OLD_BAD_SKU_ID}:
        return True
    if "2300026" in offer_lower or "rombik" in offer_lower or "ромбик" in offer_lower:
        return True
    if not sku_id and not offer_name and created_at >= CURRENT_BLANK_ROW_REPAIR_START:
        return True
    return False


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _validate_plan(target_map: dict[str, Any], entries: list[dict[str, Any]], orders: list[dict[str, Any]]) -> None:
    if str(target_map.get("sku_id") or "") == TARGET_SKU_ID:
        return
    if str(target_map.get("sku_id") or "") != OLD_BAD_SKU_ID:
        raise RepairError(f"target map row has unexpected current sku_id: {target_map}")
    if not entries:
        raise RepairError("no target order entries found for route 114632368")
    if not orders:
        raise RepairError("no target fact_orders_kaspi rows found for route 114632368")


def _entry_name_by_order(entries: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in entries:
        order_id = str(row.get("order_id") or "")
        name = str(row.get("raw_offer_name") or "")
        if order_id and name and order_id not in out:
            out[order_id] = name
    return out


def _apply_repair(
    conn: sqlite3.Connection,
    *,
    target_map: dict[str, Any],
    entries: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> dict[str, int]:
    stats = {"map_updated": 0, "entries_updated": 0, "orders_updated": 0}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    map_result = conn.execute(
        """
        UPDATE dim_kaspi_article_map
        SET sku_key = ?,
            sku_id = ?,
            source = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (TARGET_SKU_KEY, TARGET_SKU_ID, REPAIR_SOURCE, now, target_map["id"]),
    )
    stats["map_updated"] = int(map_result.rowcount or 0)

    entry_ids = [str(row["entry_id"]) for row in entries if row.get("entry_id")]
    for entry_id in entry_ids:
        result = conn.execute(
            """
            UPDATE fact_order_entries_kaspi
            SET offer_id = ?,
                updated_at = ?
            WHERE entry_id = ?
              AND (offer_id IS NULL OR offer_id = '' OR offer_id = ?)
            """,
            (TARGET_ARTICLE, now, entry_id, TARGET_ARTICLE),
        )
        stats["entries_updated"] += int(result.rowcount or 0)

    name_by_order = _entry_name_by_order(entries)
    for row in orders:
        order_id = str(row.get("order_id") or "")
        offer_name = str(row.get("kaspi_offer_name") or "").strip() or name_by_order.get(order_id, "")
        result = conn.execute(
            """
            UPDATE fact_orders_kaspi
            SET kaspi_offer_name = ?,
                sku_key = ?,
                sku_id = ?,
                my_size = ?,
                assigned_size = ?,
                size_source = ?,
                size_confidence = ?,
                updated_at = ?
            WHERE store_code = ?
              AND id = ?
            """,
            (
                offer_name,
                TARGET_SKU_KEY,
                TARGET_SKU_ID,
                TARGET_SIZE,
                TARGET_SIZE,
                REPAIR_SOURCE,
                "HIGH",
                now,
                STORE_CODE,
                row["id"],
            ),
        )
        stats["orders_updated"] += int(result.rowcount or 0)

    return stats


def run_repair(
    *,
    db_path: Path,
    output_root: Path,
    backup_root: Path,
    apply: bool,
    stamp: str | None = None,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if apply and str(os.environ.get(WRITE_ENV_GATE) or "").strip() != "1":
        raise RepairError(f"{WRITE_ENV_GATE}=1 is required with --apply")

    run_stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_root / run_stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    backup_path: Path | None = None
    backup_sha = ""
    if apply:
        backup_path = _backup_db(db_path, backup_root, run_stamp)
        backup_sha = _sha256(backup_path)

    conn = _connect(db_path)
    try:
        _required_schema(conn)
        sku_size = _load_sku_size(conn)
        before_map_rows = _load_map_rows(conn)
        target_map = _load_target_map_row(conn)
        entries_before = _load_candidate_entries(conn)
        orders_before = _load_candidate_orders(conn, entries_before)
        _validate_plan(target_map, entries_before, orders_before)

        stats = {
            "map_updated": 1 if str(target_map.get("sku_id") or "") != TARGET_SKU_ID else 0,
            "entries_updated": len(
                [row for row in entries_before if str(row.get("offer_id") or "").strip() != TARGET_ARTICLE]
            ),
            "orders_updated": len(orders_before),
        }
        apply_status = "DRY_RUN"

        if apply:
            with conn:
                stats = _apply_repair(
                    conn,
                    target_map=target_map,
                    entries=entries_before,
                    orders=orders_before,
                )
            apply_status = "APPLIED"

        after_map_rows = _load_map_rows(conn)
        entries_after = _load_candidate_entries(conn)
        orders_after = _load_candidate_orders(conn, entries_after)
    finally:
        conn.close()

    _write_csv(out_dir / "map_rows_before.csv", before_map_rows)
    _write_csv(out_dir / "orders_before.csv", orders_before)
    _write_csv(out_dir / "entries_before.csv", entries_before)
    _write_csv(out_dir / "map_rows_after.csv", after_map_rows)
    _write_csv(out_dir / "orders_after.csv", orders_after)
    _write_csv(out_dir / "entries_after.csv", entries_after)

    result = {
        "schema_version": "rombik_route_114632368_identity_repair.v1",
        "status": apply_status,
        "db_path": str(db_path),
        "output_dir": str(out_dir),
        "backup_path": str(backup_path) if backup_path else "",
        "backup_sha256": backup_sha,
        "target": {
            "store_code": STORE_CODE,
            "kaspi_article": TARGET_ARTICLE,
            "sku_key": TARGET_SKU_KEY,
            "sku_id": TARGET_SKU_ID,
            "size": TARGET_SIZE,
        },
        "sku_size": sku_size,
        "stats": stats,
        "before": {
            "map_rows": before_map_rows,
            "entry_count": len(entries_before),
            "order_count": len(orders_before),
            "bad_order_sku_count": sum(
                1 for row in orders_before if str(row.get("sku_id") or "") == OLD_BAD_SKU_ID
            ),
        },
        "after": {
            "map_rows": after_map_rows,
            "entry_count": len(entries_after),
            "order_count": len(orders_after),
            "bad_order_sku_count": sum(
                1 for row in orders_after if str(row.get("sku_id") or "") == OLD_BAD_SKU_ID
            ),
        },
        "rollback": (
            f"Restore backup with: cp {backup_path} {db_path}"
            if backup_path
            else "Dry-run only; no rollback required."
        ),
    }
    (out_dir / "repair_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "repair_summary.md").write_text(
        "\n".join(
            [
                "# ROMBIK 114632368 Identity Repair",
                "",
                f"- status: `{apply_status}`",
                f"- db_path: `{db_path}`",
                f"- backup_path: `{backup_path or ''}`",
                f"- backup_sha256: `{backup_sha}`",
                f"- target_store: `{STORE_CODE}`",
                f"- target_article: `{TARGET_ARTICLE}`",
                f"- target_sku_id: `{TARGET_SKU_ID}`",
                f"- map_updated: `{stats['map_updated']}`",
                f"- entries_updated: `{stats['entries_updated']}`",
                f"- orders_updated: `{stats['orders_updated']}`",
                f"- before_bad_order_sku_count: `{result['before']['bad_order_sku_count']}`",
                f"- after_bad_order_sku_count: `{result['after']['bad_order_sku_count']}`",
                "",
                "## Rollback",
                "",
                result["rollback"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair ROMBIK route 114632368 identity mapping")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run_repair(
        db_path=args.db,
        output_root=args.output_root,
        backup_root=args.backup_root,
        apply=bool(args.apply),
        stamp=args.stamp,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
