#!/usr/bin/env python3
"""Backfill recent order identity from deterministic sources (dry-run default)."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import (
    DEFAULT_ACTIVE_STORES,
    StatusError,
    normalize_offer_name,
    normalize_store_code,
    parse_iso_date,
    write_json,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"
DEFAULT_CRM = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
SIZE_TOKENS = ("5XL", "4XL", "3XL", "2XL", "XL", "XS", "S", "M", "L")


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_root / f"app.db.pre_identity_backfill_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return out


def _required_columns(df: pd.DataFrame, synonyms: list[list[str]]) -> dict[str, str]:
    cols = {str(c).strip(): c for c in df.columns}
    resolved: dict[str, str] = {}
    for key, options in zip(
        ["order_id", "store_code", "sku_key", "sku_id", "my_size", "kaspi_offer_name"],
        synonyms,
    ):
        found = next((name for name in options if name in cols), "")
        if not found:
            raise StatusError("IDENTITY_COVERAGE_FAIL", f"CRM workbook missing required column for {key}: {options}")
        resolved[key] = found
    return resolved


def _load_crm_identity_map(workbook: Path) -> dict[str, dict[str, str]]:
    if not workbook.exists():
        raise StatusError("IDENTITY_COVERAGE_FAIL", f"CRM workbook not found: {workbook}")

    df = pd.read_excel(workbook, sheet_name="SALES_KSP_CRM_1", dtype=str).fillna("")
    col = _required_columns(
        df,
        [
            ["OrderID", "№ заказа"],
            ["STORE_NAME", "Склад передачи КД"],
            ["SKU_key"],
            ["SKU_ID"],
            ["MY_SIZE"],
            ["KASPI_OFFER_NAME", "Название товара в Kaspi Магазине"],
        ],
    )

    out: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        order_id = str(row[col["order_id"]] or "").strip()
        if not order_id:
            continue
        store_code = normalize_store_code(row[col["store_code"]])
        if not store_code:
            continue
        key = f"{store_code}:{order_id}"

        payload = {
            "sku_key": str(row[col["sku_key"]] or "").strip(),
            "sku_id": str(row[col["sku_id"]] or "").strip(),
            "my_size": str(row[col["my_size"]] or "").strip().upper(),
            "kaspi_offer_name": str(row[col["kaspi_offer_name"]] or "").strip(),
            "source": "CRM_ORDER_ID_EXACT",
        }
        # Last row wins (newest appended rows are later in workbook)
        out[key] = payload
    return out


def _load_reference_offer_map(reference_csv: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not reference_csv.exists():
        raise StatusError("EXTERNAL_MAPPING_STALE", f"reference csv missing: {reference_csv}")
    df = pd.read_csv(reference_csv, dtype=str, keep_default_na=False)
    if df.empty:
        raise StatusError("EXTERNAL_MAPPING_STALE", f"reference csv empty: {reference_csv}")

    required = {"store_code", "kaspi_offer_name", "effective_sku_key", "effective_size", "mapping_status", "identity_status"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise StatusError("EXTERNAL_MAPPING_STALE", f"reference csv missing columns: {', '.join(missing)}")

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for _, row in df.iterrows():
        store = str(row["store_code"] or "").strip().upper()
        offer = normalize_offer_name(row["kaspi_offer_name"])
        if not store or not offer:
            continue
        rec = {
            "sku_key": str(row.get("effective_sku_key") or "").strip(),
            "sku_id": str(row.get("effective_sku_key") or "").strip(),
            "my_size": str(row.get("effective_size") or "").strip().upper(),
            "kaspi_offer_name": str(row.get("kaspi_offer_name") or "").strip(),
            "mapping_status": str(row.get("mapping_status") or "").strip().lower(),
            "identity_status": str(row.get("identity_status") or "").strip().lower(),
            "source": "EXTERNAL_OFFER_NAME_EXACT",
        }
        grouped.setdefault((store, offer), []).append(rec)

    resolved: dict[tuple[str, str], dict[str, str]] = {}
    for key, rows in grouped.items():
        valid = [
            r
            for r in rows
            if r["sku_key"] and r["mapping_status"] != "deprecated" and r["identity_status"] in {"", "matched"}
        ]
        sku_keys = sorted({r["sku_key"] for r in valid})
        if len(sku_keys) != 1:
            continue
        first = valid[0]
        resolved[key] = {
            "sku_key": sku_keys[0],
            "sku_id": sku_keys[0],
            "my_size": first["my_size"],
            "kaspi_offer_name": first["kaspi_offer_name"],
            "source": first["source"],
        }
    return resolved


def _choose_fill(current: sqlite3.Row, candidate: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    updates: dict[str, str] = {}
    changed: list[str] = []
    for field in ("sku_key", "sku_id", "my_size", "kaspi_offer_name"):
        current_value = str(current[field] or "").strip()
        if current_value:
            continue
        new_value = str(candidate.get(field) or "").strip()
        if not new_value:
            continue
        updates[field] = new_value
        changed.append(field)
    return updates, changed


def _extract_size_from_text(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    tokens = [tok for tok in re.split(r"[^A-Z0-9]+", text) if tok]
    if not tokens:
        return ""

    size_tokens = [tok for tok in tokens if tok in SIZE_TOKENS]
    if size_tokens:
        long_hits = [tok for tok in size_tokens if len(tok) >= 2]
        if long_hits:
            uniq_long = sorted(set(long_hits))
            if len(uniq_long) == 1:
                return uniq_long[0]
            return ""
        # Single-letter sizes are too ambiguous in free text unless the tail token is a size marker.
        if tokens[-1] in {"S", "M", "L"}:
            return tokens[-1]
        return ""

    numeric_hits = sorted({tok for tok in tokens if re.fullmatch(r"4\d|5\d|6[0-2]", tok)})
    if len(numeric_hits) == 1:
        return numeric_hits[0]
    return ""


def _extract_size_from_sku_key(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    parts = [p for p in re.split(r"[^A-Z0-9]+", text) if p]
    for token in reversed(parts):
        if token in SIZE_TOKENS:
            return token
        if re.fullmatch(r"4\d|5\d|6[0-2]", token):
            return token
    return ""


def _load_order_entry_product_map(
    conn: sqlite3.Connection,
    *,
    stores: tuple[str, ...],
) -> dict[tuple[str, str], dict[str, str]]:
    if not stores:
        return {}
    rows = conn.execute(
        """
        SELECT
            UPPER(COALESCE(e.store_code,'')) AS store_code,
            COALESCE(e.product_id,'') AS product_id,
            COALESCE(o.sku_key,'') AS sku_key,
            COALESCE(o.my_size,'') AS my_size,
            COALESCE(o.kaspi_offer_name,'') AS kaspi_offer_name
        FROM fact_order_entries_kaspi e
        JOIN fact_orders_kaspi o
          ON o.order_id = e.order_id
         AND UPPER(COALESCE(o.store_code,'')) = UPPER(COALESCE(e.store_code,''))
        WHERE UPPER(COALESCE(e.store_code,'')) IN ({})
          AND COALESCE(e.product_id,'') <> ''
          AND COALESCE(o.sku_key,'') <> ''
        """.format(",".join(["?"] * len(stores))),
        stores,
    ).fetchall()

    grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        key = (str(row["store_code"] or "").strip().upper(), str(row["product_id"] or "").strip())
        if not key[0] or not key[1]:
            continue
        grouped.setdefault(key, []).append(row)

    out: dict[tuple[str, str], dict[str, str]] = {}
    for key, group in grouped.items():
        sku_keys = sorted({str(r["sku_key"] or "").strip() for r in group if str(r["sku_key"] or "").strip()})
        if len(sku_keys) != 1:
            continue
        sku_key = sku_keys[0]
        size_values = sorted({str(r["my_size"] or "").strip().upper() for r in group if str(r["my_size"] or "").strip()})
        offer_values = sorted({str(r["kaspi_offer_name"] or "").strip() for r in group if str(r["kaspi_offer_name"] or "").strip()})
        out[key] = {
            "sku_key": sku_key,
            "sku_id": sku_key,
            "my_size": size_values[0] if len(size_values) == 1 else "",
            "kaspi_offer_name": offer_values[0] if len(offer_values) == 1 else "",
            "source": "ORDER_ENTRY_PRODUCT_ID_UNIQUE",
        }
    return out


def _load_recent_order_product_ids(
    conn: sqlite3.Connection,
    *,
    stores: tuple[str, ...],
    start_day: date,
    as_of: date,
) -> dict[tuple[str, str], list[str]]:
    if not stores:
        return {}
    rows = conn.execute(
        """
        SELECT
            UPPER(COALESCE(o.store_code,'')) AS store_code,
            COALESCE(o.order_id,'') AS order_id,
            COALESCE(e.product_id,'') AS product_id
        FROM fact_orders_kaspi o
        LEFT JOIN fact_order_entries_kaspi e
          ON e.order_id = o.order_id
         AND UPPER(COALESCE(e.store_code,'')) = UPPER(COALESCE(o.store_code,''))
        WHERE date(o.created_at) BETWEEN ? AND ?
          AND UPPER(COALESCE(o.store_code,'')) IN ({})
        """.format(",".join(["?"] * len(stores))),
        (start_day.isoformat(), as_of.isoformat(), *stores),
    ).fetchall()
    out: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        store = str(row["store_code"] or "").strip().upper()
        order_id = str(row["order_id"] or "").strip()
        product_id = str(row["product_id"] or "").strip()
        if not store or not order_id or not product_id:
            continue
        out.setdefault((store, order_id), set()).add(product_id)
    return {k: sorted(v) for k, v in out.items()}


def backfill_recent_order_identity(
    *,
    db_path: Path,
    as_of: date,
    lookback_days: int,
    stores: tuple[str, ...],
    reference_csv: Path,
    crm_workbook: Path,
    output_root: Path,
    strict: bool,
    apply: bool,
    backup_root: Path,
) -> dict[str, Any]:
    if lookback_days <= 0:
        raise StatusError("IDENTITY_COVERAGE_FAIL", "lookback_days must be > 0")
    if not db_path.exists():
        raise StatusError("IDENTITY_COVERAGE_FAIL", f"db not found: {db_path}")

    start_day = as_of - timedelta(days=lookback_days - 1)
    offer_map = _load_reference_offer_map(reference_csv)
    crm_map = _load_crm_identity_map(crm_workbook)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        order_entry_product_map = _load_order_entry_product_map(conn, stores=stores)
        order_product_ids = _load_recent_order_product_ids(
            conn,
            stores=stores,
            start_day=start_day,
            as_of=as_of,
        )

        rows = conn.execute(
            """
            SELECT id, order_id, UPPER(COALESCE(store_code,'')) AS store_code,
                   COALESCE(sku_key,'') AS sku_key,
                   COALESCE(sku_id,'') AS sku_id,
                   COALESCE(my_size,'') AS my_size,
                   COALESCE(kaspi_offer_name,'') AS kaspi_offer_name,
                   COALESCE(size_source,'') AS size_source,
                   COALESCE(size_confidence,'') AS size_confidence,
                   COALESCE(created_at,'') AS created_at
            FROM fact_orders_kaspi
            WHERE date(created_at) BETWEEN ? AND ?
              AND UPPER(COALESCE(store_code,'')) IN ({})
            ORDER BY created_at, id
            """.format(",".join(["?"] * len(stores))),
            (start_day.isoformat(), as_of.isoformat(), *stores),
        ).fetchall()

        diffs: list[dict[str, str]] = []
        unresolved: list[dict[str, str]] = []
        apply_rows: list[tuple[str, str, str, str, str, str, int]] = []

        for row in rows:
            missing = [f for f in ("sku_key", "sku_id", "my_size", "kaspi_offer_name") if not str(row[f] or "").strip()]
            if not missing:
                continue

            order_id = str(row["order_id"] or "").strip()
            store_code = str(row["store_code"] or "").strip().upper()
            crm_key = f"{store_code}:{order_id}"
            candidate = crm_map.get(crm_key)
            source = ""
            reason = ""

            if candidate is not None:
                source = "CRM_ORDER_ID_EXACT"
            else:
                offer_name_norm = normalize_offer_name(row["kaspi_offer_name"])
                if offer_name_norm:
                    candidate = offer_map.get((store_code, offer_name_norm))
                    if candidate:
                        source = "EXTERNAL_OFFER_NAME_EXACT"
            if candidate is None:
                product_ids = order_product_ids.get((store_code, order_id), [])
                if len(product_ids) == 1:
                    candidate = order_entry_product_map.get((store_code, product_ids[0]))
                    if candidate:
                        source = "ORDER_ENTRY_PRODUCT_ID_UNIQUE"

            if candidate is None:
                reason = "no_deterministic_candidate"
            else:
                updates, changed = _choose_fill(row, candidate)
                if "my_size" not in updates:
                    size_candidate = (
                        _extract_size_from_text(str(candidate.get("my_size") or ""))
                        or _extract_size_from_text(str(candidate.get("kaspi_offer_name") or ""))
                        or _extract_size_from_text(str(row["kaspi_offer_name"] or ""))
                        or _extract_size_from_sku_key(updates.get("sku_key", str(row["sku_key"] or "")))
                    )
                    if size_candidate:
                        updates["my_size"] = size_candidate
                        if "my_size" not in changed:
                            changed.append("my_size")
                if not changed:
                    reason = "candidate_has_no_fill_for_missing_fields"
                else:
                    new_sku_key = updates.get("sku_key", str(row["sku_key"] or "").strip())
                    new_sku_id = updates.get("sku_id", str(row["sku_id"] or "").strip())
                    new_size = updates.get("my_size", str(row["my_size"] or "").strip())
                    new_offer = updates.get("kaspi_offer_name", str(row["kaspi_offer_name"] or "").strip())
                    new_size_source = str(row["size_source"] or "").strip() or source
                    new_size_conf = str(row["size_confidence"] or "").strip() or "1.0"

                    diffs.append(
                        {
                            "id": str(row["id"]),
                            "order_id": order_id,
                            "store_code": store_code,
                            "source": source,
                            "changed_fields": ",".join(changed),
                            "before_sku_key": str(row["sku_key"] or "").strip(),
                            "after_sku_key": new_sku_key,
                            "before_sku_id": str(row["sku_id"] or "").strip(),
                            "after_sku_id": new_sku_id,
                            "before_my_size": str(row["my_size"] or "").strip(),
                            "after_my_size": new_size,
                            "before_kaspi_offer_name": str(row["kaspi_offer_name"] or "").strip(),
                            "after_kaspi_offer_name": new_offer,
                        }
                    )
                    apply_rows.append(
                        (
                            new_sku_key,
                            new_sku_id,
                            new_size,
                            new_offer,
                            new_size_source,
                            new_size_conf,
                            int(row["id"]),
                        )
                    )

            if reason:
                unresolved.append(
                    {
                        "id": str(row["id"]),
                        "order_id": order_id,
                        "store_code": store_code,
                        "reason": reason,
                        "missing_fields": ",".join(missing),
                        "kaspi_offer_name": str(row["kaspi_offer_name"] or "").strip(),
                    }
                )

        backup_path = None
        if apply:
            if str(os.environ.get("ENABLE_DB_WRITE") or "").strip() != "1":
                raise StatusError("IDENTITY_COVERAGE_FAIL", "ENABLE_DB_WRITE=1 is required for --apply")
            backup_path = _backup_db(db_path.resolve(), backup_root.resolve())
            if apply_rows:
                conn.executemany(
                    """
                    UPDATE fact_orders_kaspi
                    SET sku_key=?, sku_id=?, my_size=?, kaspi_offer_name=?, size_source=?, size_confidence=?
                    WHERE id=?
                    """,
                    apply_rows,
                )
                conn.commit()
    finally:
        conn.close()

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    diff_csv = out_dir / "backfill_recent_order_identity_diff_fact_orders_kaspi.csv"
    unresolved_csv = out_dir / "backfill_recent_order_identity_unresolved.csv"
    summary_json = out_dir / "backfill_recent_order_identity_summary.json"
    summary_md = out_dir / "backfill_recent_order_identity_summary.md"
    apply_manifest = out_dir / "backfill_recent_order_identity_apply_manifest.json"

    pd.DataFrame(diffs).to_csv(diff_csv, index=False, encoding="utf-8")
    pd.DataFrame(unresolved).to_csv(unresolved_csv, index=False, encoding="utf-8")

    status = "PASS" if (not strict or len(unresolved) == 0) else "IDENTITY_COVERAGE_FAIL"
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "lookback_days": int(lookback_days),
        "stores": list(stores),
        "reference_csv": str(reference_csv.resolve()),
        "crm_workbook": str(crm_workbook.resolve()),
        "apply": bool(apply),
        "db_backup_path": str(backup_path) if backup_path else "",
        "updated_rows": int(len(diffs)),
        "unresolved_rows": int(len(unresolved)),
        "diff_csv": str(diff_csv.resolve()),
        "unresolved_csv": str(unresolved_csv.resolve()),
        "status": status,
        "error_code": "" if status == "PASS" else "IDENTITY_COVERAGE_FAIL",
    }
    write_json(summary_json, summary)
    summary_md.write_text(
        "\n".join(
            [
                "# Recent Order Identity Backfill",
                "",
                f"- as_of: `{as_of.isoformat()}`",
                f"- status: `{status}`",
                f"- apply: `{str(bool(apply)).lower()}`",
                f"- updated_rows: `{len(diffs)}`",
                f"- unresolved_rows: `{len(unresolved)}`",
                f"- diff_csv: `{diff_csv.resolve()}`",
                f"- unresolved_csv: `{unresolved_csv.resolve()}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if apply:
        write_json(
            apply_manifest,
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "as_of": as_of.isoformat(),
                "backup_path": str(backup_path) if backup_path else "",
                "updated_rows": int(len(diffs)),
                "diff_csv": str(diff_csv.resolve()),
                "summary_json": str(summary_json.resolve()),
            },
        )

    if strict and status != "PASS":
        raise StatusError(
            "IDENTITY_COVERAGE_FAIL",
            f"unresolved rows remain after deterministic backfill: {len(unresolved)}",
        )
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill recent order identity from deterministic sources")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--lookback-days", type=int, default=15)
    parser.add_argument("--stores", default=",".join(DEFAULT_ACTIVE_STORES))
    parser.add_argument("--reference-csv", type=Path, required=True)
    parser.add_argument("--crm-workbook", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    stores = tuple(s.strip().upper() for s in str(args.stores).split(",") if s.strip())
    try:
        summary = backfill_recent_order_identity(
            db_path=args.db,
            as_of=parse_iso_date(args.as_of, field="as_of"),
            lookback_days=int(args.lookback_days),
            stores=stores,
            reference_csv=args.reference_csv,
            crm_workbook=args.crm_workbook,
            output_root=args.output_root,
            strict=bool(args.strict),
            apply=bool(args.apply),
            backup_root=args.backup_root,
        )
    except StatusError as exc:
        print(f"status={exc.code}")
        print(f"error_code={exc.code}")
        print(f"message={exc.message}")
        return 1
    except Exception as exc:  # pragma: no cover
        print("status=FAIL")
        print("error_code=FAIL")
        print(f"message={exc}")
        return 1

    out_root = args.output_root.resolve() / summary["as_of"]
    print(f"backfill_summary_json={out_root / 'backfill_recent_order_identity_summary.json'}")
    print(f"backfill_diff_csv={out_root / 'backfill_recent_order_identity_diff_fact_orders_kaspi.csv'}")
    print(f"status={summary['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
