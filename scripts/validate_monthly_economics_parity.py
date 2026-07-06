#!/usr/bin/env python3
"""Fail-closed monthly economics parity: DB truth vs status-date mapped archive."""

from __future__ import annotations

import argparse
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAPPED_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "economics_parity"
DEFAULT_STATUSDATE_CUTOVER = "2026-02-27"
PROJECTION_SURFACE_TABLE = "monthly_sales_economics_statusdate_projection"
PROJECTION_EXCEPTION_TABLE = "monthly_sales_economics_statusdate_projection_exceptions"

PROJECTION_COLUMNS = [
    "order_id",
    "sale_date",
    "sale_month",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "units",
    "net_rev_kzt",
    "cogs_kzt",
    "profit_kzt",
    "cogs_source",
    "source_table",
    "db_source_sale_dates",
    "db_match_status",
    "match_key_kind",
    "archive_units",
    "archive_net_rev_kzt",
    "archive_line_rows",
    "archive_transaction_date_source",
    "archive_mapped_sku_key",
    "archive_mapped_sku_id",
    "archive_mapped_size",
    "db_line_reuse_count",
    "statusdate_projection_source",
]

PROJECTION_EXCEPTION_COLUMNS = [
    "exception_type",
    "order_id",
    "store_code",
    "sale_date",
    "sku_key",
    "sku_id",
    "my_size",
    "units",
    "net_rev_kzt",
    "details",
]


class ParityError(RuntimeError):
    """Raised when strict parity checks fail."""


def _month_end(month_key: str) -> date:
    year, month = month_key.split("-")
    y = int(year)
    m = int(month)
    return date(y, m, monthrange(y, m)[1])


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _normalize_identity(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"", "NAN", "NAN_NAN", "NONE", "NULL", "NA", "<NA>"}:
        return ""
    return text


def _first_nonblank(values: pd.Series) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _join_unique(values: pd.Series) -> str:
    out = sorted({str(value).strip() for value in values if str(value or "").strip()})
    return "|".join(out)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sqlite_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _resolve_mapped_csv(*, since: date, until: date, explicit: Path | None, mapped_root: Path) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
    else:
        path = (
            mapped_root.resolve()
            / f"{since.isoformat()}_to_{until.isoformat()}"
            / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
        )
    if not path.exists():
        raise ParityError(
            f"mapped archive csv missing: {path}. Run scripts/export_sales_archive_statusdate_mapped.py first."
        )
    return path


def _load_archive_monthly(*, mapped_csv: Path, since: date, until: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(mapped_csv, dtype=str, keep_default_na=False)
    if df.empty:
        raise ParityError("mapped archive csv contains 0 rows")

    required_cols = {
        "transaction_date",
        "store_code",
        "order_id",
        "quantity",
        "net_rev_kzt",
        "status_internal",
        "return_flag",
        "transaction_date_source",
        "mapped_sku_key",
        "mapped_sku_id",
        "mapped_size",
    }
    missing = sorted(required_cols - set(df.columns))
    if missing:
        raise ParityError(f"mapped archive csv missing columns: {', '.join(missing)}")

    tx = pd.to_datetime(df["transaction_date"], errors="coerce")
    mask_range = (tx.dt.date >= since) & (tx.dt.date <= until)
    df = df[mask_range].copy()
    if df.empty:
        raise ParityError("mapped archive has 0 rows in requested range")

    delivered = (
        df["status_internal"].astype(str).str.upper().eq("DELIVERED")
        & pd.to_numeric(df["return_flag"], errors="coerce").fillna(0).astype(int).eq(0)
    )
    df = df[delivered].copy()
    if df.empty:
        raise ParityError("mapped archive has 0 delivered rows in requested range")

    df["sale_month"] = pd.to_datetime(df["transaction_date"], errors="coerce").dt.to_period("M").astype(str)
    df["store_code"] = df["store_code"].astype(str).str.upper()
    df["units"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0.0)
    df["net_rev_kzt"] = pd.to_numeric(df["net_rev_kzt"], errors="coerce").fillna(0.0)
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["mapped_sku_key"] = df["mapped_sku_key"].astype(str).str.strip()
    df["mapped_sku_id"] = df["mapped_sku_id"].astype(str).str.strip()
    df["mapped_size"] = df["mapped_size"].astype(str).str.strip()

    monthly_archive = (
        df.groupby(["sale_month", "store_code"], dropna=False)
        .agg(
            archive_units=("units", "sum"),
            archive_net_rev_kzt=("net_rev_kzt", "sum"),
            archive_orders=("order_id", "nunique"),
            archive_rows=("order_id", "count"),
            status_date_rows=(
                "transaction_date_source",
                lambda s: int(s.isin(["status_change_date", "ui_override_status_date"]).sum()),
            ),
            fallback_rows=(
                "transaction_date_source",
                lambda s: int((s == "creation_date_fallback").sum()),
            ),
        )
        .reset_index()
        .sort_values(["sale_month", "store_code"])
        .reset_index(drop=True)
    )
    monthly_archive["status_date_coverage"] = monthly_archive.apply(
        lambda r: (float(r["status_date_rows"]) / float(r["archive_rows"])) if float(r["archive_rows"]) > 0 else 0.0,
        axis=1,
    )

    return monthly_archive, df


def _fetch_db_rows_for_projection(conn: sqlite3.Connection, order_ids: list[str]) -> pd.DataFrame:
    if not order_ids:
        return pd.DataFrame(
            columns=[
                "order_id",
                "sale_date",
                "store_code",
                "sku_key",
                "sku_id",
                "my_size",
                "units",
                "net_rev_kzt",
                "cogs_kzt",
                "profit_kzt",
                "cogs_source",
                "source_table",
            ]
        )

    frames: list[pd.DataFrame] = []
    chunk_size = 900
    for offset in range(0, len(order_ids), chunk_size):
        chunk = order_ids[offset : offset + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        query = f"""
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                date(sale_date) AS sale_date,
                UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                COALESCE(sku_key, '') AS sku_key,
                COALESCE(sku_id, '') AS sku_id,
                COALESCE(my_size, '') AS my_size,
                CAST(COALESCE(units, 0) AS REAL) AS units,
                CAST(COALESCE(net_rev_kzt, 0) AS REAL) AS net_rev_kzt,
                CAST(COALESCE(cogs_kzt, 0) AS REAL) AS cogs_kzt,
                CAST(COALESCE(profit_kzt, 0) AS REAL) AS profit_kzt,
                COALESCE(cogs_source, 'unresolved') AS cogs_source,
                COALESCE(source_table, 'view_sales_line_truth') AS source_table
            FROM view_sales_line_truth
            WHERE CAST(order_id AS TEXT) IN ({placeholders})
        """
        frames.append(pd.read_sql_query(query, conn, params=chunk))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _unique_lookup(records: list[dict[str, Any]], key_fields: tuple[str, ...]) -> tuple[dict[tuple[str, ...], dict[str, Any]], set[tuple[str, ...]]]:
    lookup: dict[tuple[str, ...], dict[str, Any]] = {}
    ambiguous: set[tuple[str, ...]] = set()
    for record in records:
        key = tuple(str(record.get(field, "") or "") for field in key_fields)
        if any(not part for part in key):
            continue
        if key in lookup:
            ambiguous.add(key)
            lookup.pop(key, None)
            continue
        if key in ambiguous:
            continue
        lookup[key] = record
    return lookup, ambiguous


def _empty_projection() -> pd.DataFrame:
    return pd.DataFrame(columns=PROJECTION_COLUMNS)


def _empty_projection_exceptions() -> pd.DataFrame:
    return pd.DataFrame(columns=PROJECTION_EXCEPTION_COLUMNS)


def build_monthly_sales_economics_statusdate_projection(
    *,
    conn: sqlite3.Connection,
    delivered_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if delivered_rows.empty:
        metadata = {
            "projection_surface_table": PROJECTION_SURFACE_TABLE,
            "projection_exception_table": PROJECTION_EXCEPTION_TABLE,
            "archive_anchor_rows": 0,
            "projected_rows": 0,
            "matched_rows": 0,
            "missing_in_db_rows": 0,
            "duplicate_db_line_match_rows": 0,
            "unmatched_db_line_rows": 0,
        }
        return _empty_projection(), _empty_projection_exceptions(), metadata

    anchors = delivered_rows.copy()
    anchors["sale_date"] = pd.to_datetime(anchors["transaction_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    anchors["sale_month"] = pd.to_datetime(anchors["transaction_date"], errors="coerce").dt.to_period("M").astype(str)
    anchors["order_id"] = anchors["order_id"].astype(str).str.strip()
    anchors["store_code"] = anchors["store_code"].astype(str).str.strip().str.upper()
    anchors["mapped_sku_key"] = anchors["mapped_sku_key"].astype(str).str.strip()
    anchors["mapped_sku_id"] = anchors["mapped_sku_id"].astype(str).str.strip()
    anchors["mapped_size"] = anchors["mapped_size"].astype(str).str.strip()
    anchors["mapped_sku_key_norm"] = anchors["mapped_sku_key"].map(_normalize_identity)
    anchors["mapped_sku_id_norm"] = anchors["mapped_sku_id"].map(_normalize_identity)
    anchors["mapped_size_norm"] = anchors["mapped_size"].map(_normalize_identity)

    archive_anchor_rows = (
        anchors.groupby(
            [
                "order_id",
                "store_code",
                "sale_date",
                "sale_month",
                "mapped_sku_key_norm",
                "mapped_sku_id_norm",
                "mapped_size_norm",
            ],
            dropna=False,
        )
        .agg(
            archive_mapped_sku_key=("mapped_sku_key", _first_nonblank),
            archive_mapped_sku_id=("mapped_sku_id", _first_nonblank),
            archive_mapped_size=("mapped_size", _first_nonblank),
            archive_units=("units", "sum"),
            archive_net_rev_kzt=("net_rev_kzt", "sum"),
            archive_line_rows=("order_id", "count"),
            archive_transaction_date_source=("transaction_date_source", _join_unique),
        )
        .reset_index()
    )
    archive_anchor_rows["has_line_identity"] = archive_anchor_rows.apply(
        lambda row: bool(row["mapped_sku_id_norm"])
        or bool(row["mapped_sku_key_norm"] and row["mapped_size_norm"]),
        axis=1,
    )
    order_stores_with_line_identity = {
        (str(row["order_id"]), str(row["store_code"]))
        for row in archive_anchor_rows[archive_anchor_rows["has_line_identity"]].to_dict("records")
    }

    db_rows = _fetch_db_rows_for_projection(
        conn,
        sorted(archive_anchor_rows["order_id"].dropna().astype(str).unique().tolist()),
    )
    if db_rows.empty:
        db_lines = pd.DataFrame()
        db_order_lines = pd.DataFrame()
    else:
        for col in ["units", "net_rev_kzt", "cogs_kzt", "profit_kzt"]:
            db_rows[col] = pd.to_numeric(db_rows[col], errors="coerce").fillna(0.0)
        db_rows["order_id"] = db_rows["order_id"].astype(str).str.strip()
        db_rows["store_code"] = db_rows["store_code"].astype(str).str.strip().str.upper()
        db_rows["sku_key"] = db_rows["sku_key"].astype(str).str.strip()
        db_rows["sku_id"] = db_rows["sku_id"].astype(str).str.strip()
        db_rows["my_size"] = db_rows["my_size"].astype(str).str.strip()
        db_rows["sku_key_norm"] = db_rows["sku_key"].map(_normalize_identity)
        db_rows["sku_id_norm"] = db_rows["sku_id"].map(_normalize_identity)
        db_rows["my_size_norm"] = db_rows["my_size"].map(_normalize_identity)
        db_order_lines = (
            db_rows.groupby(["order_id", "store_code"], dropna=False)
            .agg(
                sku_key=("sku_key", _join_unique),
                sku_id=("sku_id", _join_unique),
                my_size=("my_size", _join_unique),
                units=("units", "sum"),
                net_rev_kzt=("net_rev_kzt", "sum"),
                cogs_kzt=("cogs_kzt", "sum"),
                profit_kzt=("profit_kzt", "sum"),
                cogs_source=("cogs_source", _join_unique),
                source_table=("source_table", _join_unique),
                db_source_sale_dates=("sale_date", _join_unique),
                db_row_count=("order_id", "count"),
            )
            .reset_index()
        )
        db_order_lines["db_line_id"] = db_order_lines.apply(
            lambda row: "|".join([str(row["order_id"]), str(row["store_code"]), "__ORDER__"]),
            axis=1,
        )
        db_lines = (
            db_rows.groupby(
                ["order_id", "store_code", "sku_key_norm", "sku_id_norm", "my_size_norm"],
                dropna=False,
            )
            .agg(
                sku_key=("sku_key", _first_nonblank),
                sku_id=("sku_id", _first_nonblank),
                my_size=("my_size", _first_nonblank),
                units=("units", "sum"),
                net_rev_kzt=("net_rev_kzt", "sum"),
                cogs_kzt=("cogs_kzt", "sum"),
                profit_kzt=("profit_kzt", "sum"),
                cogs_source=("cogs_source", _join_unique),
                source_table=("source_table", _join_unique),
                db_source_sale_dates=("sale_date", _join_unique),
                db_row_count=("order_id", "count"),
            )
            .reset_index()
        )
        db_lines["db_line_id"] = db_lines.apply(
            lambda row: "|".join(
                [
                    str(row["order_id"]),
                    str(row["store_code"]),
                    str(row["sku_id_norm"]),
                    str(row["sku_key_norm"]),
                    str(row["my_size_norm"]),
                ]
            ),
            axis=1,
        )

    db_records = db_lines.to_dict("records") if not db_lines.empty else []
    sku_id_lookup, ambiguous_sku_id = _unique_lookup(db_records, ("order_id", "store_code", "sku_id_norm"))
    sku_size_lookup, ambiguous_sku_size = _unique_lookup(
        db_records,
        ("order_id", "store_code", "sku_key_norm", "my_size_norm"),
    )
    order_lookup, ambiguous_order = _unique_lookup(
        db_order_lines.to_dict("records") if not db_order_lines.empty else [],
        ("order_id", "store_code"),
    )

    projection_records: list[dict[str, Any]] = []
    exception_records: list[dict[str, Any]] = []
    matched_db_line_ids: list[str] = []
    matched_order_store_keys: set[tuple[str, str]] = set()

    for anchor in archive_anchor_rows.to_dict("records"):
        sku_id_key = (
            str(anchor["order_id"]),
            str(anchor["store_code"]),
            str(anchor["mapped_sku_id_norm"]),
        )
        sku_size_key = (
            str(anchor["order_id"]),
            str(anchor["store_code"]),
            str(anchor["mapped_sku_key_norm"]),
            str(anchor["mapped_size_norm"]),
        )
        db_record: dict[str, Any] | None = None
        match_key_kind = ""
        if anchor["mapped_sku_id_norm"]:
            if sku_id_key in ambiguous_sku_id:
                match_key_kind = "ambiguous_sku_id"
            else:
                db_record = sku_id_lookup.get(sku_id_key)
                if db_record is not None:
                    match_key_kind = "sku_id"
        if db_record is None and anchor["mapped_sku_key_norm"] and anchor["mapped_size_norm"]:
            if sku_size_key in ambiguous_sku_size:
                match_key_kind = match_key_kind or "ambiguous_sku_key_size"
            else:
                db_record = sku_size_lookup.get(sku_size_key)
                if db_record is not None:
                    match_key_kind = "sku_key_size"
        if (
            db_record is None
            and not bool(anchor["has_line_identity"])
            and (str(anchor["order_id"]), str(anchor["store_code"])) not in order_stores_with_line_identity
        ):
            order_key = (str(anchor["order_id"]), str(anchor["store_code"]))
            if order_key in ambiguous_order:
                match_key_kind = match_key_kind or "ambiguous_order_store"
            else:
                db_record = order_lookup.get(order_key)
                if db_record is not None:
                    match_key_kind = "order_store_missing_archive_identity"

        if db_record is None:
            status = "MISSING_IN_DB"
            if match_key_kind.startswith("ambiguous"):
                status = "AMBIGUOUS_DB_LINE_MATCH"
            exception_records.append(
                {
                    "exception_type": status,
                    "order_id": anchor["order_id"],
                    "store_code": anchor["store_code"],
                    "sale_date": anchor["sale_date"],
                    "sku_key": anchor["archive_mapped_sku_key"],
                    "sku_id": anchor["archive_mapped_sku_id"],
                    "my_size": anchor["archive_mapped_size"],
                    "units": float(anchor["archive_units"]),
                    "net_rev_kzt": float(anchor["archive_net_rev_kzt"]),
                    "details": match_key_kind or "no view_sales_line_truth identity match",
                }
            )
            projection_records.append(
                {
                    "order_id": anchor["order_id"],
                    "sale_date": anchor["sale_date"],
                    "sale_month": anchor["sale_month"],
                    "store_code": anchor["store_code"],
                    "sku_key": anchor["archive_mapped_sku_key"],
                    "sku_id": anchor["archive_mapped_sku_id"],
                    "my_size": anchor["archive_mapped_size"],
                    "units": 0.0,
                    "net_rev_kzt": 0.0,
                    "cogs_kzt": 0.0,
                    "profit_kzt": 0.0,
                    "cogs_source": "unresolved",
                    "source_table": "",
                    "db_source_sale_dates": "",
                    "db_match_status": status,
                    "match_key_kind": match_key_kind,
                    "archive_units": float(anchor["archive_units"]),
                    "archive_net_rev_kzt": float(anchor["archive_net_rev_kzt"]),
                    "archive_line_rows": int(anchor["archive_line_rows"]),
                    "archive_transaction_date_source": anchor["archive_transaction_date_source"],
                    "archive_mapped_sku_key": anchor["archive_mapped_sku_key"],
                    "archive_mapped_sku_id": anchor["archive_mapped_sku_id"],
                    "archive_mapped_size": anchor["archive_mapped_size"],
                    "db_line_reuse_count": 0,
                    "statusdate_projection_source": "mapped_archive_statusdate",
                }
            )
            continue

        matched_db_line_ids.append(str(db_record["db_line_id"]))
        if match_key_kind == "order_store_missing_archive_identity":
            matched_order_store_keys.add((str(db_record["order_id"]), str(db_record["store_code"])))
        projection_records.append(
            {
                "order_id": anchor["order_id"],
                "sale_date": anchor["sale_date"],
                "sale_month": anchor["sale_month"],
                "store_code": anchor["store_code"],
                "sku_key": db_record["sku_key"],
                "sku_id": db_record["sku_id"],
                "my_size": db_record["my_size"],
                "units": float(db_record["units"]),
                "net_rev_kzt": float(db_record["net_rev_kzt"]),
                "cogs_kzt": float(db_record["cogs_kzt"]),
                "profit_kzt": float(db_record["profit_kzt"]),
                "cogs_source": db_record["cogs_source"],
                "source_table": db_record["source_table"],
                "db_source_sale_dates": db_record["db_source_sale_dates"],
                "db_match_status": "MATCHED",
                "match_key_kind": match_key_kind,
                "archive_units": float(anchor["archive_units"]),
                "archive_net_rev_kzt": float(anchor["archive_net_rev_kzt"]),
                "archive_line_rows": int(anchor["archive_line_rows"]),
                "archive_transaction_date_source": anchor["archive_transaction_date_source"],
                "archive_mapped_sku_key": anchor["archive_mapped_sku_key"],
                "archive_mapped_sku_id": anchor["archive_mapped_sku_id"],
                "archive_mapped_size": anchor["archive_mapped_size"],
                "db_line_reuse_count": 1,
                "statusdate_projection_source": "mapped_archive_statusdate",
                "_db_line_id": str(db_record["db_line_id"]),
            }
        )

    reuse_counts = Counter(matched_db_line_ids)
    for record in projection_records:
        db_line_id = str(record.pop("_db_line_id", "") or "")
        if db_line_id:
            reuse_count = int(reuse_counts[db_line_id])
            record["db_line_reuse_count"] = reuse_count
            if reuse_count > 1:
                record["db_match_status"] = "DUPLICATE_DB_LINE_MATCH"
                exception_records.append(
                    {
                        "exception_type": "DUPLICATE_DB_LINE_MATCH",
                        "order_id": record["order_id"],
                        "store_code": record["store_code"],
                        "sale_date": record["sale_date"],
                        "sku_key": record["sku_key"],
                        "sku_id": record["sku_id"],
                        "my_size": record["my_size"],
                        "units": record["units"],
                        "net_rev_kzt": record["net_rev_kzt"],
                        "details": f"db_line_reuse_count={reuse_count}",
                    }
                )

    matched_unique_db_line_ids = {str(line_id) for line_id in matched_db_line_ids}
    if db_records:
        for db_record in db_records:
            if str(db_record["db_line_id"]) in matched_unique_db_line_ids:
                continue
            if (str(db_record["order_id"]), str(db_record["store_code"])) in matched_order_store_keys:
                continue
            exception_records.append(
                {
                    "exception_type": "DB_LINE_WITHOUT_STATUSDATE_ANCHOR",
                    "order_id": db_record["order_id"],
                    "store_code": db_record["store_code"],
                    "sale_date": db_record["db_source_sale_dates"],
                    "sku_key": db_record["sku_key"],
                    "sku_id": db_record["sku_id"],
                    "my_size": db_record["my_size"],
                    "units": float(db_record["units"]),
                    "net_rev_kzt": float(db_record["net_rev_kzt"]),
                    "details": "view_sales_line_truth line for archive order did not match mapped archive identity",
                }
            )

    projection = pd.DataFrame(projection_records, columns=PROJECTION_COLUMNS)
    exceptions = pd.DataFrame(exception_records, columns=PROJECTION_EXCEPTION_COLUMNS)
    metadata = {
        "projection_surface_table": PROJECTION_SURFACE_TABLE,
        "projection_exception_table": PROJECTION_EXCEPTION_TABLE,
        "archive_anchor_rows": int(len(archive_anchor_rows)),
        "projected_rows": int(len(projection)),
        "matched_rows": int((projection["db_match_status"] == "MATCHED").sum()) if not projection.empty else 0,
        "missing_in_db_rows": int((projection["db_match_status"] == "MISSING_IN_DB").sum()) if not projection.empty else 0,
        "duplicate_db_line_match_rows": int((projection["db_match_status"] == "DUPLICATE_DB_LINE_MATCH").sum())
        if not projection.empty
        else 0,
        "order_store_identity_fallback_rows": int(
            (projection["match_key_kind"] == "order_store_missing_archive_identity").sum()
        )
        if not projection.empty
        else 0,
        "unmatched_db_line_rows": int((exceptions["exception_type"] == "DB_LINE_WITHOUT_STATUSDATE_ANCHOR").sum())
        if not exceptions.empty
        else 0,
    }
    return projection, exceptions, metadata


def _create_temp_projection_table(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame) -> None:
    conn.execute(f"DROP TABLE IF EXISTS temp.{_quote_identifier(table_name)}")
    column_sql = ", ".join(f"{_quote_identifier(col)} TEXT" for col in df.columns)
    conn.execute(f"CREATE TEMP TABLE {_quote_identifier(table_name)} ({column_sql})")
    if df.empty:
        return
    columns = list(df.columns)
    column_names = ", ".join(_quote_identifier(col) for col in columns)
    placeholders = ", ".join(["?"] * len(columns))
    conn.executemany(
        f"INSERT INTO {_quote_identifier(table_name)} ({column_names}) VALUES ({placeholders})",
        [tuple(_sqlite_scalar(value) for value in row) for row in df.itertuples(index=False, name=None)],
    )


def _materialize_temp_projection_surface(
    conn: sqlite3.Connection,
    projection: pd.DataFrame,
    exceptions: pd.DataFrame,
) -> None:
    _create_temp_projection_table(conn, PROJECTION_SURFACE_TABLE, projection)
    _create_temp_projection_table(conn, PROJECTION_EXCEPTION_TABLE, exceptions)


def _load_db_monthly(
    *,
    db_path: Path,
    since: date,
    until: date,
    delivered_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not db_path.exists():
        raise ParityError(f"db not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_sales_truth_views(conn)
        projection, exceptions, projection_meta = build_monthly_sales_economics_statusdate_projection(
            conn=conn,
            delivered_rows=delivered_rows,
        )
        _materialize_temp_projection_surface(conn, projection, exceptions)
        rows = conn.execute(
            """
            SELECT
                sale_month AS sale_month,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                SUM(CAST(COALESCE(units, 0) AS REAL)) AS db_units,
                SUM(CAST(COALESCE(net_rev_kzt, 0) AS REAL)) AS db_net_rev_kzt,
                SUM(CAST(COALESCE(cogs_kzt, 0) AS REAL)) AS db_cogs_kzt,
                SUM(CAST(COALESCE(profit_kzt, 0) AS REAL)) AS db_profit_kzt,
                COUNT(DISTINCT CAST(order_id AS TEXT)) AS db_orders
            FROM temp.monthly_sales_economics_statusdate_projection
            WHERE date(sale_date) BETWEEN ? AND ?
              AND db_match_status = 'MATCHED'
            GROUP BY sale_month, UPPER(COALESCE(store_code, 'UNKNOWN'))
            ORDER BY 1, 2
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(
            columns=[
                "sale_month",
                "store_code",
                "db_units",
                "db_net_rev_kzt",
                "db_cogs_kzt",
                "db_profit_kzt",
                "db_orders",
            ]
        ), projection, exceptions, projection_meta

    df = pd.DataFrame([dict(r) for r in rows])
    numeric_cols = ["db_units", "db_net_rev_kzt", "db_cogs_kzt", "db_profit_kzt", "db_orders"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df, projection, exceptions, projection_meta


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Monthly Economics Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- range: `{report['since']} -> {report['until']}`",
        f"- status: `{report['status']}`",
        f"- strict: `{str(report['strict']).lower()}`",
        f"- tolerance_pct: `{report['tolerance_pct']}`",
        f"- db_projection_surface: `{report['db_projection_surface']}`",
        f"- db_projection_matched_rows: `{report['db_projection_meta']['matched_rows']}`",
        f"- db_projection_exceptions: `{report['db_projection_exception_count']}`",
        f"- decision_grade_mismatches: `{report['decision_grade_mismatch_count']}`",
        f"- provisional_month_store_pairs: `{report['provisional_pair_count']}`",
        "",
        "| sale_month | store_code | archive_units | db_units | archive_net_rev | db_net_rev | decision_grade | db_exceeds_archive |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['sale_month']}` | `{row['store_code']}` | {row['archive_units']:.2f} | {row['db_units']:.2f} | "
            f"{row['archive_net_rev_kzt']:.2f} | {row['db_net_rev_kzt']:.2f} | "
            f"{str(row['decision_grade']).lower()} | {str(row['db_exceeds_archive']).lower()} |"
        )

    if report["decision_grade_mismatches"]:
        lines.extend(["", "## Decision-Grade Mismatches", ""])
        for msg in report["decision_grade_mismatches"]:
            lines.append(f"- {msg}")

    if report["notes"]:
        lines.extend(["", "## Notes", ""])
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def validate_monthly_economics_parity(
    *,
    since: date,
    until: date,
    db_path: Path,
    mapped_csv: Path,
    output_root: Path,
    strict: bool,
    tolerance_pct: float,
    statusdate_cutover: date,
) -> dict[str, Any]:
    if until < since:
        raise ParityError("until must be >= since")
    if tolerance_pct < 0:
        raise ParityError("tolerance_pct must be >= 0")

    monthly_archive, delivered_rows = _load_archive_monthly(
        mapped_csv=mapped_csv,
        since=since,
        until=until,
    )
    monthly_db, db_projection, db_projection_exceptions, db_projection_meta = _load_db_monthly(
        db_path=db_path,
        since=since,
        until=until,
        delivered_rows=delivered_rows,
    )

    merged = monthly_archive.merge(monthly_db, on=["sale_month", "store_code"], how="outer").fillna(0)
    merged = merged.sort_values(["sale_month", "store_code"]).reset_index(drop=True)

    decision_grade_mismatches: list[str] = []
    rows: list[dict[str, Any]] = []
    notes: list[str] = []

    provisional_pairs = 0
    for _, row in merged.iterrows():
        sale_month = str(row["sale_month"])
        store_code = str(row["store_code"]).upper()
        archive_units = _safe_float(row.get("archive_units"))
        archive_net_rev = _safe_float(row.get("archive_net_rev_kzt"))
        db_units = _safe_float(row.get("db_units"))
        db_net_rev = _safe_float(row.get("db_net_rev_kzt"))

        fallback_rows = int(round(_safe_float(row.get("fallback_rows"))))
        archive_rows = int(round(_safe_float(row.get("archive_rows"))))
        status_date_coverage = _safe_float(row.get("status_date_coverage"))

        month_end = _month_end(sale_month)
        closed_month = month_end < until
        month_is_pre_cutover = month_end < statusdate_cutover

        decision_grade = bool(closed_month and not month_is_pre_cutover and fallback_rows == 0)
        if not decision_grade:
            provisional_pairs += 1

        units_threshold = archive_units * (1.0 + tolerance_pct)
        rev_threshold = archive_net_rev * (1.0 + tolerance_pct)
        units_exceeds = db_units > units_threshold + 1e-9
        rev_exceeds = db_net_rev > rev_threshold + 1.0
        db_exceeds = bool(units_exceeds or rev_exceeds)

        if decision_grade and db_exceeds:
            decision_grade_mismatches.append(
                f"{sale_month} {store_code}: db_units={db_units:.2f} archive_units={archive_units:.2f} "
                f"db_net_rev={db_net_rev:.2f} archive_net_rev={archive_net_rev:.2f}"
            )

        rows.append(
            {
                "sale_month": sale_month,
                "store_code": store_code,
                "archive_units": archive_units,
                "archive_net_rev_kzt": archive_net_rev,
                "archive_orders": int(round(_safe_float(row.get("archive_orders")))),
                "archive_rows": archive_rows,
                "status_date_rows": int(round(_safe_float(row.get("status_date_rows")))),
                "fallback_rows": fallback_rows,
                "status_date_coverage": status_date_coverage,
                "db_units": db_units,
                "db_net_rev_kzt": db_net_rev,
                "db_cogs_kzt": _safe_float(row.get("db_cogs_kzt")),
                "db_profit_kzt": _safe_float(row.get("db_profit_kzt")),
                "db_orders": int(round(_safe_float(row.get("db_orders")))),
                "closed_month": closed_month,
                "month_pre_cutover": month_is_pre_cutover,
                "decision_grade": decision_grade,
                "db_exceeds_archive": db_exceeds,
                "units_diff": db_units - archive_units,
                "net_rev_diff_kzt": db_net_rev - archive_net_rev,
            }
        )

    if provisional_pairs > 0:
        notes.append(
            f"{provisional_pairs} month/store pairs are provisional (pre-cutover or creation-date fallback present)."
        )
    notes.append(
        f"statusdate_cutover={statusdate_cutover.isoformat()} (months ending before this are provisional by contract)."
    )
    notes.append(
        f"db monthly totals use {PROJECTION_SURFACE_TABLE}; projection sale_date is mapped archive transaction_date."
    )
    fallback_rows = int(db_projection_meta.get("order_store_identity_fallback_rows", 0) or 0)
    if fallback_rows > 0:
        notes.append(
            f"{fallback_rows} projection rows used order/store fallback because mapped archive line identity was blank."
        )
    exception_count = int(len(db_projection_exceptions))
    if exception_count > 0:
        notes.append(
            f"{exception_count} status-date projection exception rows emitted; inspect {PROJECTION_EXCEPTION_TABLE} CSV."
        )

    range_dir = output_root.resolve() / f"{since.isoformat()}_to_{until.isoformat()}"
    range_dir.mkdir(parents=True, exist_ok=True)

    monthly_archive_csv = range_dir / "monthly_archive.csv"
    monthly_db_csv = range_dir / "monthly_db.csv"
    db_projection_csv = range_dir / "db_statusdate_projection.csv"
    db_projection_exceptions_csv = range_dir / "db_statusdate_projection_exceptions.csv"
    diffs_csv = range_dir / "diffs_by_month.csv"
    summary_json = range_dir / "summary.json"
    report_md = range_dir / "report.md"

    monthly_archive.to_csv(monthly_archive_csv, index=False, encoding="utf-8")
    monthly_db.to_csv(monthly_db_csv, index=False, encoding="utf-8")
    db_projection.to_csv(db_projection_csv, index=False, encoding="utf-8")
    db_projection_exceptions.to_csv(db_projection_exceptions_csv, index=False, encoding="utf-8")
    pd.DataFrame(rows).to_csv(diffs_csv, index=False, encoding="utf-8")

    status = "PASS" if not decision_grade_mismatches else "FAIL"
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "strict": bool(strict),
        "status": status,
        "tolerance_pct": float(tolerance_pct),
        "statusdate_cutover": statusdate_cutover.isoformat(),
        "db_projection_surface": PROJECTION_SURFACE_TABLE,
        "db_projection_exception_surface": PROJECTION_EXCEPTION_TABLE,
        "db_projection_meta": db_projection_meta,
        "db_projection_exception_count": exception_count,
        "decision_grade_mismatch_count": len(decision_grade_mismatches),
        "decision_grade_mismatches": decision_grade_mismatches,
        "provisional_pair_count": provisional_pairs,
        "notes": notes,
        "mapped_csv": str(mapped_csv.resolve()),
        "monthly_archive_csv": str(monthly_archive_csv.resolve()),
        "monthly_db_csv": str(monthly_db_csv.resolve()),
        "db_projection_csv": str(db_projection_csv.resolve()),
        "db_projection_exceptions_csv": str(db_projection_exceptions_csv.resolve()),
        "diffs_by_month_csv": str(diffs_csv.resolve()),
        "summary_json": str(summary_json.resolve()),
        "report_md": str(report_md.resolve()),
        "rows": rows,
        "archive_delivered_rows": int(len(delivered_rows)),
    }

    summary_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_md(report), encoding="utf-8")

    if strict and status != "PASS":
        raise ParityError("monthly economics parity failed on decision-grade month(s)")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate monthly economics parity (DB vs mapped archive)")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--mapped-csv", type=Path, default=None)
    parser.add_argument("--mapped-root", type=Path, default=DEFAULT_MAPPED_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--tolerance-pct", type=float, default=0.005)
    parser.add_argument("--statusdate-cutover", default=DEFAULT_STATUSDATE_CUTOVER)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    since = date.fromisoformat(args.since)
    until = date.fromisoformat(args.until)
    mapped_csv = _resolve_mapped_csv(
        since=since,
        until=until,
        explicit=args.mapped_csv,
        mapped_root=args.mapped_root,
    )

    report = validate_monthly_economics_parity(
        since=since,
        until=until,
        db_path=args.db,
        mapped_csv=mapped_csv,
        output_root=args.output_root,
        strict=bool(args.strict),
        tolerance_pct=float(args.tolerance_pct),
        statusdate_cutover=date.fromisoformat(args.statusdate_cutover),
    )

    print(f"monthly_economics_parity_summary_json={report['summary_json']}")
    print(f"monthly_economics_parity_report_md={report['report_md']}")
    print(f"monthly_db_csv={report['monthly_db_csv']}")
    print(f"monthly_archive_csv={report['monthly_archive_csv']}")
    print(f"diffs_by_month_csv={report['diffs_by_month_csv']}")
    print(f"status={report['status']}")
    return 0 if report["status"] == "PASS" else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
