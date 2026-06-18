#!/usr/bin/env python3
"""Materialize Merchant Cabinet pricelist rows as copied-temp offer availability only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.parsers.kaspi_parser import extract_sku_from_article

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
CONTRACT_VERSION = "MERCHANT_CABINET_PRICELIST_OFFER_AVAILABILITY_COPIED_TEMP_V1"
ALLOWED_STORES = {"STOREB", "ACMEWEAR", "UNIVERSAL"}
ALLOWED_STATES = {"ACTIVE", "ARCHIVE"}
SIZE_TOKEN_RE = r"(XS|S|M|L|XL|2XL|3XL|4XL|5XL)"
REQUIRED_COLUMNS = {
    "store_code",
    "sale_state",
    "source_file",
    "source_file_sha256",
    "excel_row",
    "sku",
    "model",
    "brand",
    "price",
    "pp1",
    "pp2",
    "pp3",
    "pp4",
    "pp5",
    "preorder",
    "positive_on_hand_units_pp1_pp5",
    "positive_preorder_units",
}


class OfferAvailabilityMaterializationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _refuse_unsafe_apply(db_path: Path, apply: bool) -> None:
    if not apply:
        return
    resolved = db_path.expanduser().resolve()
    if resolved == DEFAULT_DB.resolve():
        raise OfferAvailabilityMaterializationError("refusing to write production db/app.db")
    if os.environ.get("ENABLE_MERCHANT_CABINET_OFFER_AVAILABILITY_WRITE") != "1":
        raise OfferAvailabilityMaterializationError(
            "ENABLE_MERCHANT_CABINET_OFFER_AVAILABILITY_WRITE=1 is required with --apply"
        )
    if not any("evidence" in part for part in resolved.parts):
        raise OfferAvailabilityMaterializationError(
            "copied-temp apply requires DB path under an evidence folder"
        )


def _table_stat(conn: sqlite3.Connection, table: str, date_col: str | None = None) -> dict[str, Any]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return {"exists": False, "count": 0, "max_date": None}
    count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
    max_date = None
    if date_col:
        max_date = conn.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()[0]
    return {"exists": True, "count": count, "max_date": max_date}


def _open_stock_high_count(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exception_queue'"
    ).fetchone()
    if not exists:
        return 0
    cols = {row[1] for row in conn.execute("PRAGMA table_info(exception_queue)").fetchall()}
    if not {"domain", "severity", "status"}.issubset(cols):
        return 0
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM exception_queue
            WHERE domain='STOCK' AND severity='HIGH' AND status='OPEN'
            """
        ).fetchone()[0]
        or 0
    )


def _parse_pp(value: Any, *, column: str, row_number: int) -> int:
    text = str(value or "").strip().lower()
    if text in {"", "no", "none", "null", "nan"}:
        return 0
    try:
        number = float(text)
    except ValueError as exc:
        raise OfferAvailabilityMaterializationError(
            f"row {row_number} {column} is not a nonnegative integer or blank/no: {value!r}"
        ) from exc
    if number < 0 or not number.is_integer():
        raise OfferAvailabilityMaterializationError(
            f"row {row_number} {column} must be a nonnegative integer"
        )
    return int(number)


def _pricelist_identity_rejection_reason(kaspi_article: Any) -> str | None:
    """Fail closed on parser features not accepted for the Agent917 stock packet."""
    article = str(kaspi_article or "").strip().upper()
    if not article:
        return "blank sku"
    if re.match(r"^\d+_", article):
        return "numeric offer id without canonical article identity"
    if re.match(r"^(SUIT|LINE)-\d{2}-(LS|TS)-ST-", article):
        return "compact bundle alias requires separate owner/source contract"
    if article.startswith("LOSINA "):
        return "free-text losina alias requires separate owner/source contract"
    if re.search(rf"_{SIZE_TOKEN_RE}_[0-9]{{1,3}}_[0-9]+$", article):
        return "size variant alias requires explicit identity mapping"
    return None


def _snapshot_id(row: pd.Series, *, snapshot_date: str) -> str:
    raw = "|".join(
        [
            CONTRACT_VERSION,
            snapshot_date,
            str(row["store_code"]),
            str(row["sale_state"]),
            str(row["source_file_sha256"]),
            str(row["excel_row"]),
            str(row["sku"]),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_rows(source_rows: Path, *, snapshot_date: str, source_manifest_id: str) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(source_rows, sep="\t", dtype=str, keep_default_na=False)
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise OfferAvailabilityMaterializationError(
            f"source rows missing required columns: {', '.join(missing)}"
        )

    parsed_rows: list[dict[str, Any]] = []
    unparsed_rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        row_number = int(idx) + 2
        store_code = str(row["store_code"]).strip()
        sale_state = str(row["sale_state"]).strip().upper()
        if store_code not in ALLOWED_STORES:
            raise OfferAvailabilityMaterializationError(f"row {row_number} invalid store_code={store_code!r}")
        if sale_state not in ALLOWED_STATES:
            raise OfferAvailabilityMaterializationError(f"row {row_number} invalid sale_state={sale_state!r}")

        identity_rejection_reason = _pricelist_identity_rejection_reason(row["sku"])
        if identity_rejection_reason:
            item = row.to_dict()
            item["unparsed_reason"] = identity_rejection_reason
            unparsed_rows.append(item)
            continue

        parsed = extract_sku_from_article(str(row["sku"]), str(row.get("model", "")))
        sku_key = str(parsed.get("sku_key") or "").strip()
        sku_id = str(parsed.get("sku_id") or "").strip()
        my_size = str(parsed.get("my_size") or "").strip()
        if not sku_key or not sku_id or not my_size or my_size.upper() == "UNPARSED":
            item = row.to_dict()
            item["unparsed_reason"] = "missing sku_key/sku_id/my_size from parser"
            unparsed_rows.append(item)
            continue

        pp_qty = sum(_parse_pp(row[col], column=col, row_number=row_number) for col in ("pp1", "pp2", "pp3", "pp4", "pp5"))
        available_qty = pp_qty if sale_state == "ACTIVE" else 0
        status = (
            "MERCHANT_CABINET_PRICELIST_ACTIVE_OFFER_AVAILABILITY_ONLY"
            if sale_state == "ACTIVE"
            else "MERCHANT_CABINET_PRICELIST_ARCHIVE_OFFER_AVAILABILITY_ONLY"
        )
        parsed_rows.append(
            {
                "snapshot_id": _snapshot_id(row, snapshot_date=snapshot_date),
                "snapshot_date": snapshot_date,
                "store_code": store_code,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "my_size": my_size,
                "offer_available_qty": available_qty,
                "physical_stock_qty": None,
                "status": status,
                "source_manifest_id": source_manifest_id,
                "sale_state": sale_state,
            }
        )

    return parsed_rows, pd.DataFrame(parsed_rows), pd.DataFrame(unparsed_rows)


def materialize(
    *,
    db_path: Path,
    source_normalized_rows: Path,
    source_sha256: str,
    snapshot_date: str,
    source_manifest_id: str,
    output_dir: Path,
    apply: bool = False,
) -> dict[str, Any]:
    db_path = db_path.expanduser()
    source_normalized_rows = source_normalized_rows.expanduser()
    output_dir = output_dir.expanduser()
    _refuse_unsafe_apply(db_path, apply)
    if _sha256(source_normalized_rows) != source_sha256:
        raise OfferAvailabilityMaterializationError("source_normalized_rows SHA-256 mismatch")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows, parsed_df, unparsed_df = _load_rows(
        source_normalized_rows,
        snapshot_date=snapshot_date,
        source_manifest_id=source_manifest_id,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        before_inventory = _table_stat(conn, "fact_inventory_snapshot_size", "snapshot_date")
        before_ledger = _table_stat(conn, "stock_ledger", "event_date")
        before_exceptions = _open_stock_high_count(conn)
        inserted_rows = 0
        if apply:
            with conn:
                conn.execute(
                    "DELETE FROM offer_availability_snapshot WHERE snapshot_date=? AND source_manifest_id=?",
                    (snapshot_date, source_manifest_id),
                )
                conn.executemany(
                    """
                    INSERT INTO offer_availability_snapshot (
                        snapshot_id, snapshot_date, store_code, sku_key, sku_id, my_size,
                        offer_available_qty, physical_stock_qty, status, source_manifest_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row["snapshot_id"],
                            row["snapshot_date"],
                            row["store_code"],
                            row["sku_key"],
                            row["sku_id"],
                            row["my_size"],
                            row["offer_available_qty"],
                            None,
                            row["status"],
                            row["source_manifest_id"],
                        )
                        for row in rows
                    ],
                )
                inserted_rows = len(rows)
        after_inventory = _table_stat(conn, "fact_inventory_snapshot_size", "snapshot_date")
        after_ledger = _table_stat(conn, "stock_ledger", "event_date")
        after_exceptions = _open_stock_high_count(conn)
    finally:
        conn.close()

    unparsed_path = output_dir / "merchant_cabinet_offer_availability_unparsed_rows.tsv"
    parsed_path = output_dir / "merchant_cabinet_offer_availability_parsed_rows.tsv"
    manifest_path = output_dir / "merchant_cabinet_offer_availability_manifest.json"
    unparsed_df.to_csv(unparsed_path, sep="\t", index=False)
    parsed_df.to_csv(parsed_path, sep="\t", index=False)

    by_store_state = (
        parsed_df.groupby(["store_code", "sale_state"], dropna=False)
        .size()
        .reset_index(name="insert_eligible_rows")
        .to_dict(orient="records")
        if not parsed_df.empty
        else []
    )
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "source_normalized_rows": str(source_normalized_rows.resolve()),
        "source_sha256": source_sha256,
        "snapshot_date": snapshot_date,
        "source_manifest_id": source_manifest_id,
        "mode": "apply" if apply else "dry-run",
        "copied_db": str(db_path.resolve()),
        "source_rows": int(len(parsed_df) + len(unparsed_df)),
        "parsed_identity_rows": int(len(parsed_df)),
        "unparsed_identity_rows": int(len(unparsed_df)),
        "inserted_rows": inserted_rows,
        "by_store_state": by_store_state,
        "offer_available_qty_total": int(parsed_df["offer_available_qty"].sum()) if not parsed_df.empty else 0,
        "identity_parser_policy": (
            "accepted copied-temp pricelist boundary; compact bundle aliases, free-text aliases, "
            "numeric offer-only ids, and size-variant aliases are retained in the unparsed sidecar"
        ),
        "physical_stock_qty_policy": "always NULL; Merchant Cabinet PP quantities are offer availability only",
        "current_stock_policy": "does not write fact_inventory_snapshot_size.current_stock or inbound_stock",
        "stock_ledger_policy": "does not write stock_ledger",
        "exception_policy": "does not close STOCK/HIGH/OPEN exceptions",
        "unchanged_physical_snapshot_before": before_inventory,
        "unchanged_physical_snapshot_after": after_inventory,
        "unchanged_stock_ledger_before": before_ledger,
        "unchanged_stock_ledger_after": after_ledger,
        "open_stock_high_exceptions_before": before_exceptions,
        "open_stock_high_exceptions_after": after_exceptions,
        "unparsed_rows_path": str(unparsed_path.resolve()),
        "parsed_rows_path": str(parsed_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize Merchant Cabinet offer availability on a copied DB only")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-normalized-rows", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--source-manifest-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        manifest = materialize(
            db_path=args.db,
            source_normalized_rows=args.source_normalized_rows,
            source_sha256=args.source_sha256,
            snapshot_date=args.snapshot_date,
            source_manifest_id=args.source_manifest_id,
            output_dir=args.output_dir,
            apply=args.apply,
        )
    except OfferAvailabilityMaterializationError as exc:
        payload = {"ok": False, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False) if args.json else f"ERROR: {exc}")
        return 1

    payload = {"ok": True, **manifest}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else f"OK: inserted_rows={manifest['inserted_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
