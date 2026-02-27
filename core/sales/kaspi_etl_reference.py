"""External sales reference adapter for Kaspi ArchiveOrders exports."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
import glob
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import warnings

import pandas as pd


REQUIRED_ARCHIVE_COLS = {
    "№ заказа",
    "Дата изменения статуса",
    "Статус",
    "Количество",
    "Сумма",
    "Склад передачи КД",
}

DELIVERED_STATUSES = {"ВЫДАН", "DELIVERED", "COMPLETED"}

DEFAULT_STORE_MAP = {
    # Known warehouse aliases; DB inference can override.
    "30137883_PP1": "ACMEWEAR",
    "30000001_PP1": "UNIVERSAL",
    "30000002_PP1": "STOREB",
}


def _to_number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return 0.0
    text = text.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_archive_frames(archive_dir: Path) -> tuple[pd.DataFrame, list[Path]]:
    files = sorted(
        Path(match).resolve()
        for match in glob.glob(str(archive_dir / "**" / "ArchiveOrders*.xlsx"), recursive=True)
        if Path(match).is_file() and not Path(match).name.startswith("~$")
    )
    if not files:
        raise FileNotFoundError(f"No ArchiveOrders*.xlsx files found under: {archive_dir}")

    frames: list[pd.DataFrame] = []
    for path in files:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Workbook contains no default style, apply openpyxl's default",
                category=UserWarning,
            )
            df = pd.read_excel(path, dtype=str)
        if not REQUIRED_ARCHIVE_COLS.issubset(set(df.columns)):
            continue
        slim = df.copy()
        slim["source_file"] = str(path)
        frames.append(slim)
    if not frames:
        raise RuntimeError("ArchiveOrders files found, but none contained required columns")
    return pd.concat(frames, ignore_index=True), files


def _resolve_store_map_from_db(
    *,
    df: pd.DataFrame,
    db_path: Path | None,
    explicit_map: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {k.upper(): v.upper() for k, v in DEFAULT_STORE_MAP.items()}
    if explicit_map:
        mapping.update({k.upper(): v.upper() for k, v in explicit_map.items()})

    unresolved: list[str] = []
    if db_path is None or not db_path.exists():
        for warehouse in sorted(set(df["kd_warehouse"].astype(str).str.upper())):
            if warehouse not in mapping:
                unresolved.append(warehouse)
        return mapping, unresolved

    conn = sqlite3.connect(str(db_path))
    try:
        has_fact_orders = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not has_fact_orders:
            for warehouse in sorted(set(df["kd_warehouse"].astype(str).str.upper())):
                if warehouse not in mapping:
                    unresolved.append(warehouse)
            return mapping, unresolved

        for warehouse, group in df.groupby("kd_warehouse"):
            warehouse_norm = str(warehouse or "").strip().upper()
            if not warehouse_norm or warehouse_norm in mapping:
                continue
            order_ids = sorted({str(v).strip() for v in group["order_id"].tolist() if str(v).strip()})
            if not order_ids:
                unresolved.append(warehouse_norm)
                continue
            counter: Counter[str] = Counter()
            chunk_size = 500
            for i in range(0, len(order_ids), chunk_size):
                chunk = order_ids[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT UPPER(COALESCE(store_code, '')) AS store_code, COUNT(*) AS c
                    FROM fact_orders_kaspi
                    WHERE CAST(order_id AS TEXT) IN ({placeholders})
                    GROUP BY UPPER(COALESCE(store_code, ''))
                    """,
                    tuple(chunk),
                ).fetchall()
                for store_code, count in rows:
                    code = str(store_code or "").strip().upper()
                    if code and code != "UNKNOWN":
                        counter[code] += int(count or 0)
            if counter:
                mapping[warehouse_norm] = counter.most_common(1)[0][0]
            else:
                unresolved.append(warehouse_norm)
    finally:
        conn.close()

    return mapping, sorted(set(unresolved))


def build_reference_from_archive_dir(
    *,
    archive_dir: Path,
    as_of: date,
    include_as_of_day: bool,
    db_path: Path | None = None,
    explicit_store_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    raw_df, files = _load_archive_frames(archive_dir)
    raw_df = raw_df.copy()
    raw_df["status"] = raw_df["Статус"].astype(str).str.strip().str.upper()
    raw_df = raw_df[raw_df["status"].isin(DELIVERED_STATUSES)].copy()
    raw_df["order_id"] = raw_df["№ заказа"].astype(str).str.strip()
    raw_df["sale_date"] = raw_df["Дата изменения статуса"].apply(_to_iso_date)
    raw_df["quantity"] = raw_df["Количество"].apply(_to_number)
    raw_df["gross_rev_kzt"] = raw_df["Сумма"].apply(_to_number)
    raw_df["kd_warehouse"] = raw_df["Склад передачи КД"].astype(str).str.strip().str.upper()
    raw_df["article"] = raw_df.get("Артикул", "").astype(str).str.strip().str.upper()
    raw_df["offer_name"] = raw_df.get("Название товара в Kaspi Магазине", "").astype(str).str.strip()

    end_date = as_of.isoformat() if include_as_of_day else (as_of - timedelta(days=1)).isoformat()
    raw_df = raw_df[(raw_df["sale_date"].notna()) & (raw_df["sale_date"] <= end_date)].copy()
    raw_df = raw_df[raw_df["order_id"] != ""].copy()
    raw_df["quantity"] = raw_df["quantity"].apply(lambda v: float(v) if float(v) > 0 else 1.0)
    raw_df["gross_rev_kzt"] = raw_df["gross_rev_kzt"].apply(float)

    if raw_df.empty:
        return {
            "status": "missing",
            "reason": "no_delivered_rows_in_window",
            "files": [str(p) for p in files],
            "manifest": [],
            "lines": pd.DataFrame(),
            "daily_by_store": pd.DataFrame(),
            "daily_total": pd.DataFrame(),
            "unresolved_warehouses": [],
            "store_map": {},
        }

    raw_df["dedupe_key"] = raw_df[
        ["kd_warehouse", "order_id", "article", "offer_name", "sale_date", "quantity", "gross_rev_kzt"]
    ].astype(str).agg("|".join, axis=1)
    raw_df = raw_df.sort_values(["sale_date", "source_file"]).drop_duplicates("dedupe_key", keep="last")

    store_map, unresolved = _resolve_store_map_from_db(
        df=raw_df,
        db_path=db_path,
        explicit_map=explicit_store_map,
    )
    raw_df["store_code"] = raw_df["kd_warehouse"].map(store_map).fillna("UNKNOWN").astype(str).str.upper()

    raw_df["line_id"] = raw_df[
        ["store_code", "order_id", "article", "offer_name", "sale_date", "quantity", "gross_rev_kzt"]
    ].astype(str).agg("|".join, axis=1).apply(lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest())

    lines = raw_df[
        [
            "line_id",
            "sale_date",
            "store_code",
            "kd_warehouse",
            "order_id",
            "article",
            "offer_name",
            "quantity",
            "gross_rev_kzt",
            "source_file",
        ]
    ].copy()
    lines = lines.sort_values(["sale_date", "store_code", "order_id", "line_id"]).reset_index(drop=True)

    daily_by_store = (
        lines.groupby(["sale_date", "store_code"], dropna=False)
        .agg(
            units_delivered=("quantity", "sum"),
            gross_rev_kzt=("gross_rev_kzt", "sum"),
            orders_delivered=("order_id", "nunique"),
        )
        .reset_index()
        .sort_values(["sale_date", "store_code"])
        .reset_index(drop=True)
    )
    daily_total = (
        daily_by_store.groupby(["sale_date"], dropna=False)
        .agg(
            units_delivered=("units_delivered", "sum"),
            gross_rev_kzt=("gross_rev_kzt", "sum"),
            orders_delivered=("orders_delivered", "sum"),
        )
        .reset_index()
        .sort_values(["sale_date"])
        .reset_index(drop=True)
    )

    manifest = [
        {
            "path": str(path),
            "size_bytes": int(path.stat().st_size),
            "sha256": _file_sha256(path),
        }
        for path in files
    ]

    return {
        "status": "available",
        "reason": "ok",
        "files": [str(p) for p in files],
        "manifest": manifest,
        "lines": lines,
        "daily_by_store": daily_by_store,
        "daily_total": daily_total,
        "unresolved_warehouses": unresolved,
        "store_map": store_map,
    }


def load_reference_from_csv_dir(
    *,
    reference_dir: Path,
    as_of: date,
    include_as_of_day: bool,
) -> dict[str, Any]:
    ref_dir = reference_dir.resolve()
    lines_matches = sorted(ref_dir.glob("kaspi_etl_reference_delivered_lines_*.csv"))
    by_store_matches = sorted(ref_dir.glob("kaspi_etl_reference_delivered_daily_by_store_*.csv"))
    total_matches = sorted(ref_dir.glob("kaspi_etl_reference_delivered_daily_total_*.csv"))
    manifest_matches = sorted(ref_dir.glob("kaspi_etl_reference_manifest_*.json"))
    if not lines_matches or not by_store_matches:
        raise FileNotFoundError(f"Reference CSV set not found in: {ref_dir}")

    lines_path = lines_matches[-1]
    by_store_path = by_store_matches[-1]
    total_path = total_matches[-1] if total_matches else None
    manifest_path = manifest_matches[-1] if manifest_matches else None

    lines = pd.read_csv(lines_path, dtype=str)
    daily_by_store = pd.read_csv(by_store_path, dtype=str)
    daily_total = pd.read_csv(total_path, dtype=str) if total_path else pd.DataFrame()

    # Normalize known alias columns from sanitized oracle packs.
    if "store_code" not in lines.columns and "store_ref" in lines.columns:
        lines["store_code"] = lines["store_ref"]
    if "quantity" not in lines.columns and "qty" in lines.columns:
        lines["quantity"] = lines["qty"]
    if "gross_rev_kzt" not in lines.columns and "sell_price_kzt" in lines.columns:
        lines["gross_rev_kzt"] = lines["sell_price_kzt"]
    if "store_code" not in daily_by_store.columns and "store_ref" in daily_by_store.columns:
        daily_by_store["store_code"] = daily_by_store["store_ref"]
    if "units_delivered" not in daily_by_store.columns and "units" in daily_by_store.columns:
        daily_by_store["units_delivered"] = daily_by_store["units"]
    if "orders_delivered" not in daily_by_store.columns and "orders" in daily_by_store.columns:
        daily_by_store["orders_delivered"] = daily_by_store["orders"]

    for frame in (lines, daily_by_store, daily_total):
        if frame.empty:
            continue
        if "sale_date" not in frame.columns and "date" in frame.columns:
            frame["sale_date"] = frame["date"]
        frame["sale_date"] = frame["sale_date"].astype(str).str[:10]
        end_date = as_of.isoformat() if include_as_of_day else (as_of - timedelta(days=1)).isoformat()
        frame.drop(frame.index[frame["sale_date"] > end_date], inplace=True)

    for col in ("quantity", "gross_rev_kzt", "units_delivered", "orders_delivered"):
        if col in lines.columns:
            lines[col] = lines[col].apply(_to_number)
        if col in daily_by_store.columns:
            daily_by_store[col] = daily_by_store[col].apply(_to_number)
        if col in daily_total.columns:
            daily_total[col] = daily_total[col].apply(_to_number)

    manifest = {}
    if manifest_path and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    return {
        "status": "available",
        "reason": "ok",
        "files": [str(lines_path), str(by_store_path)] + ([str(total_path)] if total_path else []),
        "manifest": manifest,
        "lines": lines,
        "daily_by_store": daily_by_store,
        "daily_total": daily_total,
        "unresolved_warehouses": [],
        "store_map": {},
    }
