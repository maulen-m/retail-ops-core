#!/usr/bin/env python3
"""Shared helpers for WebUI archive pack normalization and DB-backed truth projection."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Sequence

import pandas as pd
import yaml

from scripts.export_kaspi_archive_ui_history import WAREHOUSE_STORE_MAP
from scripts.north_star_workbook_utils import normalize_status_internal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORES_CONFIG = PROJECT_ROOT / "config" / "kaspi_stores.yaml"
DEFAULT_WEBUI_PACKS_ROOT = PROJECT_ROOT / "exports" / "webui_archive_packs"
DEFAULT_LEDGER_ROOT = PROJECT_ROOT / "exports" / "order_status_ledger"

PACK_REQUIRED_COLUMNS = {
    "№ заказа",
    "Дата поступления заказа",
    "Дата изменения статуса",
    "Статус",
    "Количество",
    "Сумма",
    "Склад передачи КД",
}

PACK_NORMALIZED_COLUMNS = [
    "pack_id",
    "store_code",
    "source_file",
    "source_file_sha256",
    "source_file_format",
    "source_row_number",
    "order_id",
    "created_at",
    "status_change_at",
    "status_raw",
    "status_internal",
    "quantity",
    "net_rev_kzt",
    "warehouse_code",
    "article",
    "kaspi_offer_name",
    "seller_system_name",
    "category",
    "pickup_or_delivery_address",
    "cancel_reason",
    "payment_mode",
    "delivery_mode",
    "courier_service",
    "planned_courier_at",
    "delivery_fee_buyer_kzt",
    "delivery_fee_seller_kzt",
    "transaction_signature_required",
    "status_change_required",
    "status_change_missing",
    "row_fingerprint",
    "window_since",
    "window_until",
]

LEDGER_COLUMNS = [
    "store_code",
    "order_id",
    "status_internal",
    "status_change_at",
    "created_at",
    "delivered_at",
    "returned_at",
    "source_pack_id",
    "source_file",
    "first_seen_pack",
    "last_seen_pack",
    "lineage_source_count",
    "row_fingerprint",
]

WINDOW_RE = re.compile(r"(?P<since>\d{4}-\d{2}-\d{2})_to_(?P<until>\d{4}-\d{2}-\d{2})")
ISO_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$")


def coerce_iso_date(value: str) -> date:
    text = str(value).strip()
    match = ISO_RE.match(text)
    if not match:
        raise ValueError(f"invalid iso date: {value}")
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    _, max_day = monthrange(year, month)
    if day > max_day:
        day = max_day
    return date(year, month, day)


def coerce_iso_date_string(value: str) -> str:
    return coerce_iso_date(value).isoformat()


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def parse_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return 0.0
        return float(value)
    text = str(value).replace(" ", "").replace(",", ".").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_store_code(value: Any, *, fallback: str | None = None) -> str:
    text = str(value or "").strip().upper()
    if text in WAREHOUSE_STORE_MAP:
        return WAREHOUSE_STORE_MAP[text]
    if text:
        return text
    return str(fallback or "").strip().upper()


def load_merchant_uid_store_map(stores_config: Path = DEFAULT_STORES_CONFIG) -> dict[str, str]:
    payload = yaml.safe_load(stores_config.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores", {}) or {}
    out: dict[str, str] = {}
    for store_code, meta in stores.items():
        merchant_uid = str((meta or {}).get("merchant_uid", "")).strip()
        if merchant_uid:
            out[merchant_uid] = str(store_code).strip().upper()
    return out


def normalize_warehouse_store_code(
    value: Any,
    *,
    fallback: str | None = None,
    merchant_uid_store_map: dict[str, str] | None = None,
) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return str(fallback or "").strip().upper()
    if text in WAREHOUSE_STORE_MAP:
        return WAREHOUSE_STORE_MAP[text]
    merchant_uid_match = re.match(r"^(?P<merchant_uid>\d+)(?:[_-].*)?$", text)
    if merchant_uid_match and merchant_uid_store_map:
        merchant_uid = merchant_uid_match.group("merchant_uid")
        mapped = str(merchant_uid_store_map.get(merchant_uid) or "").strip().upper()
        if mapped:
            return mapped
    return normalize_store_code(text, fallback=fallback)


def load_enabled_stores(stores_config: Path = DEFAULT_STORES_CONFIG) -> list[str]:
    payload = yaml.safe_load(stores_config.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores", {}) or {}
    out: list[str] = []
    for store_code, meta in stores.items():
        if bool(meta.get("sync_enabled", True)):
            out.append(str(store_code).strip().upper())
    return sorted(dict.fromkeys(out))


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def infer_window_from_path(path: Path) -> tuple[str | None, str | None]:
    for candidate in [path.name, *[part for part in path.parts if part]]:
        match = WINDOW_RE.search(candidate)
        if match:
            return match.group("since"), match.group("until")
    return None, None


def infer_store_code_from_path(path: Path) -> str | None:
    for part in reversed(path.parts):
        if part.startswith("store_"):
            store = part.replace("store_", "").strip().upper()
            if store:
                return store
    match = re.search(r"ArchiveOrders[_ ]+([A-Za-z0-9-]+)", path.stem, flags=re.IGNORECASE)
    if match:
        store = match.group(1).upper().replace("-", "_")
        if store != "ALL_STORES":
            return store
    return None


def _candidate_priority(path: Path) -> int:
    score = 0
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        score += 20
    if "raw" in {part.lower() for part in path.parts}:
        score += 10
    if "all_stores" in path.stem.lower():
        score -= 100
    return score


def find_webui_source_files(source_root: Path) -> list[Path]:
    if not source_root.exists():
        raise FileNotFoundError(f"source root not found: {source_root}")

    candidates = [
        path
        for path in source_root.rglob("ArchiveOrders*")
        if path.is_file() and path.suffix.lower() in {".xlsx", ".csv"}
    ]
    best_by_key: dict[tuple[str, str | None, str | None], Path] = {}
    for path in sorted(candidates):
        store = infer_store_code_from_path(path)
        if not store:
            continue
        window_since, window_until = infer_window_from_path(path)
        key = (store, window_since, window_until)
        current = best_by_key.get(key)
        if current is None or _candidate_priority(path) > _candidate_priority(current):
            best_by_key[key] = path.resolve()
    return [best_by_key[key] for key in sorted(best_by_key)]


def read_archive_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(path, dtype=str).fillna("")
    missing = sorted(PACK_REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"{path}: missing required columns: {', '.join(missing)}")
    return df.fillna("")


def normalize_source_file(
    *,
    path: Path,
    source_root: Path,
    pack_id: str,
    merchant_uid_store_map: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = read_archive_frame(path)
    store_hint = infer_store_code_from_path(path)
    warehouse_mapped = sorted(
        {
            normalize_warehouse_store_code(
                value,
                fallback=store_hint,
                merchant_uid_store_map=merchant_uid_store_map,
            )
            for value in df["Склад передачи КД"].tolist()
            if str(value or "").strip()
        }
    )
    store_code = warehouse_mapped[0] if len(warehouse_mapped) == 1 else (store_hint or "")
    if not store_code:
        raise ValueError(f"{path}: unable to infer store code")
    if warehouse_mapped and len(warehouse_mapped) > 1:
        raise ValueError(
            f"{path}: multiple warehouse-to-store mappings found: {', '.join(warehouse_mapped)}"
        )

    source_sha = compute_sha256(path)
    window_since, window_until = infer_window_from_path(path)
    rows: list[dict[str, Any]] = []
    delivered_rows = 0
    missing_status_change_date = 0
    for row_idx, row in enumerate(df.to_dict("records"), start=2):
        order_id = str(row.get("№ заказа") or "").strip()
        if not order_id:
            continue
        created_at = parse_date(row.get("Дата поступления заказа"))
        status_change_at = parse_date(row.get("Дата изменения статуса"))
        status_raw = str(row.get("Статус") or "").strip()
        status_internal = normalize_status_internal(status_raw)
        status_change_required = status_internal == "DELIVERED"
        status_change_missing = bool(status_change_required and not status_change_at)
        if status_change_required:
            delivered_rows += 1
        if status_change_missing:
            missing_status_change_date += 1
        norm_row = {
            "pack_id": pack_id,
            "store_code": store_code,
            "source_file": str(path.relative_to(source_root)),
            "source_file_sha256": source_sha,
            "source_file_format": path.suffix.lower().lstrip("."),
            "source_row_number": row_idx,
            "order_id": order_id,
            "created_at": created_at,
            "status_change_at": status_change_at,
            "status_raw": status_raw,
            "status_internal": status_internal,
            "quantity": parse_float(row.get("Количество")),
            "net_rev_kzt": parse_float(row.get("Сумма")),
            "warehouse_code": str(row.get("Склад передачи КД") or "").strip(),
            "article": str(row.get("Артикул") or "").strip(),
            "kaspi_offer_name": str(row.get("Название товара в Kaspi Магазине") or "").strip(),
            "seller_system_name": str(row.get("Название в системе продавца") or "").strip(),
            "category": str(row.get("Категория") or "").strip(),
            "pickup_or_delivery_address": str(row.get("Адрес самовывоза/доставки") or "").strip(),
            "cancel_reason": str(row.get("Причина отмены") or "").strip(),
            "payment_mode": str(row.get("Способ оплаты") or "").strip(),
            "delivery_mode": str(row.get("Способ доставки") or "").strip(),
            "courier_service": str(row.get("Курьерская служба") or "").strip(),
            "planned_courier_at": parse_date(row.get("Плановая дата передачи курьеру")),
            "delivery_fee_buyer_kzt": parse_float(row.get("Стоимость доставки для покупателя")),
            "delivery_fee_seller_kzt": parse_float(row.get("Стоимость доставки для продавца")),
            "transaction_signature_required": str(row.get("Требуется подписание") or "").strip(),
            "status_change_required": status_change_required,
            "status_change_missing": status_change_missing,
            "window_since": window_since,
            "window_until": window_until,
        }
        norm_row["row_fingerprint"] = hashlib.sha256(
            json.dumps(
                {
                    "store_code": norm_row["store_code"],
                    "order_id": norm_row["order_id"],
                    "created_at": norm_row["created_at"],
                    "status_change_at": norm_row["status_change_at"],
                    "status_internal": norm_row["status_internal"],
                    "quantity": norm_row["quantity"],
                    "net_rev_kzt": norm_row["net_rev_kzt"],
                    "article": norm_row["article"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        rows.append(norm_row)

    out = pd.DataFrame(rows, columns=PACK_NORMALIZED_COLUMNS)
    record = {
        "source_file": str(path.relative_to(source_root)),
        "absolute_source_file": str(path),
        "source_file_sha256": source_sha,
        "source_file_format": path.suffix.lower().lstrip("."),
        "store_code": store_code,
        "rows_total": int(len(df)),
        "rows_normalized": int(len(out)),
        "delivered_rows": int(delivered_rows),
        "delivered_missing_status_change_date": int(missing_status_change_date),
        "window_since": window_since,
        "window_until": window_until,
        "created_at_min": out["created_at"].dropna().min() if not out.empty else None,
        "created_at_max": out["created_at"].dropna().max() if not out.empty else None,
        "status_change_at_min": out["status_change_at"].dropna().min() if not out.empty else None,
        "status_change_at_max": out["status_change_at"].dropna().max() if not out.empty else None,
    }
    return out, record


def write_pack(
    *,
    source_root: Path,
    pack_id: str,
    output_root: Path = DEFAULT_WEBUI_PACKS_ROOT,
    stores_config: Path = DEFAULT_STORES_CONFIG,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    files = find_webui_source_files(source_root)
    enabled_stores = load_enabled_stores(stores_config)
    merchant_uid_store_map = load_merchant_uid_store_map(stores_config)
    pack_root = output_root.resolve() / pack_id
    pack_root.mkdir(parents=True, exist_ok=True)
    normalized_frames: list[pd.DataFrame] = []
    manifest_files: list[dict[str, Any]] = []
    stores_present: set[str] = set()
    for path in files:
        norm_df, record = normalize_source_file(
            path=path,
            source_root=source_root,
            pack_id=pack_id,
            merchant_uid_store_map=merchant_uid_store_map,
        )
        normalized_frames.append(norm_df)
        manifest_files.append(record)
        stores_present.add(str(record["store_code"]).upper())

    normalized = (
        pd.concat(normalized_frames, ignore_index=True)
        if normalized_frames
        else pd.DataFrame(columns=PACK_NORMALIZED_COLUMNS)
    )
    normalized = normalized.sort_values(
        ["store_code", "order_id", "status_change_at", "created_at", "source_file", "source_row_number"],
        na_position="last",
    ).reset_index(drop=True)
    normalized_csv = pack_root / "normalized_rows.csv"
    normalized.to_csv(normalized_csv, index=False, encoding="utf-8")

    missing_store_files = [store for store in enabled_stores if store not in stores_present]
    source_manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pack_id": pack_id,
        "source_root": str(source_root),
        "pack_root": str(pack_root),
        "enabled_stores": enabled_stores,
        "stores_present": sorted(stores_present),
        "missing_store_files": missing_store_files,
        "source_file_count": len(manifest_files),
        "total_rows": int(len(normalized)),
        "delivered_rows": int((normalized["status_internal"] == "DELIVERED").sum()) if not normalized.empty else 0,
        "delivered_missing_status_change_date": int(normalized["status_change_missing"].fillna(False).sum()) if not normalized.empty else 0,
        "files": manifest_files,
        "normalized_rows_csv": str(normalized_csv),
    }
    manifest_path = pack_root / "source_manifest.json"
    manifest_path.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "pack_root": pack_root,
        "source_manifest_path": manifest_path,
        "normalized_rows_csv": normalized_csv,
        "manifest": source_manifest,
        "normalized": normalized,
    }


def load_pack_manifest(pack_root: Path) -> dict[str, Any]:
    manifest_path = pack_root / "source_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing source_manifest.json in {pack_root}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_pack_rows(pack_root: Path) -> pd.DataFrame:
    normalized_csv = pack_root / "normalized_rows.csv"
    if not normalized_csv.exists():
        raise FileNotFoundError(f"missing normalized_rows.csv in {pack_root}")
    df = pd.read_csv(normalized_csv, dtype=object, keep_default_na=False)
    for col in {"quantity", "net_rev_kzt"}:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for col in {"status_change_required", "status_change_missing"}:
        if col in df.columns:
            df[col] = df[col].map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
    return df


def resolve_latest_dir(base_root: Path) -> Path:
    dirs = [path for path in base_root.iterdir() if path.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"no run directories found under {base_root}")
    return sorted(dirs, key=lambda path: path.name)[-1]


def build_status_ledger(
    *,
    pack_roots: Sequence[Path],
    run_id: str,
    output_root: Path = DEFAULT_LEDGER_ROOT,
) -> dict[str, Any]:
    lineage_frames: list[pd.DataFrame] = []
    pack_windows: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for pack_root in pack_roots:
        manifest = load_pack_manifest(pack_root)
        manifests.append(manifest)
        df = load_pack_rows(pack_root)
        if not df.empty:
            lineage_frames.append(df)
        for row in manifest.get("files", []):
            pack_windows.append(
                {
                    "pack_id": manifest.get("pack_id"),
                    "store_code": row.get("store_code"),
                    "window_since": row.get("window_since"),
                    "window_until": row.get("window_until"),
                    "source_file": row.get("source_file"),
                }
            )

    merged = (
        pd.concat(lineage_frames, ignore_index=True)
        if lineage_frames
        else pd.DataFrame(columns=PACK_NORMALIZED_COLUMNS)
    )
    if merged.empty:
        ledger = pd.DataFrame(columns=LEDGER_COLUMNS)
    else:
        merged = merged.sort_values(
            ["store_code", "order_id", "status_change_at", "created_at", "pack_id", "source_file", "source_row_number"],
            na_position="last",
        ).reset_index(drop=True)
        grouped = merged.groupby(["store_code", "order_id", "status_internal", "status_change_at"], dropna=False)
        ledger = grouped.agg(
            created_at=("created_at", "min"),
            source_pack_id=("pack_id", "min"),
            source_file=("source_file", "min"),
            first_seen_pack=("pack_id", "min"),
            last_seen_pack=("pack_id", "max"),
            lineage_source_count=("row_fingerprint", "count"),
            row_fingerprint=("row_fingerprint", "first"),
        ).reset_index()
        order_dates = merged.groupby(["store_code", "order_id"], dropna=False).agg(
            delivered_at=(
                "status_change_at",
                lambda values: max(
                    [str(v) for v, status in zip(values, merged.loc[values.index, "status_internal"]) if str(status) == "DELIVERED"],
                    default=None,
                ),
            ),
            returned_at=(
                "status_change_at",
                lambda values: max(
                    [str(v) for v, status in zip(values, merged.loc[values.index, "status_internal"]) if str(status) == "RETURNED"],
                    default=None,
                ),
            ),
        ).reset_index()
        ledger = ledger.merge(order_dates, on=["store_code", "order_id"], how="left")
        ledger = ledger[LEDGER_COLUMNS].sort_values(
            ["store_code", "order_id", "status_change_at", "status_internal"],
            na_position="last",
        ).reset_index(drop=True)

    run_root = output_root.resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    ledger_csv = run_root / "webui_status_ledger.csv"
    ledger.to_csv(ledger_csv, index=False, encoding="utf-8")
    continuity_report_json = run_root / "continuity_report.json"
    continuity_gaps_csv = run_root / "continuity_gaps.csv"
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": run_id,
        "pack_roots": [str(path.resolve()) for path in pack_roots],
        "pack_ids": [str(item.get("pack_id")) for item in manifests],
        "source_row_count": int(len(merged)),
        "ledger_row_count": int(len(ledger)),
        "ledger_sha256": compute_sha256(ledger_csv),
        "pack_windows": pack_windows,
        "webui_status_ledger_csv": str(ledger_csv),
        "continuity_report_json": str(continuity_report_json),
        "continuity_gaps_csv": str(continuity_gaps_csv),
    }
    manifest_path = run_root / "ledger_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "run_root": run_root,
        "ledger_manifest_path": manifest_path,
        "ledger_csv": ledger_csv,
        "manifest": manifest,
        "ledger": ledger,
    }


def load_status_ledger(run_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest_path = run_root / "ledger_manifest.json"
    ledger_csv = run_root / "webui_status_ledger.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing ledger_manifest.json in {run_root}")
    if not ledger_csv.exists():
        raise FileNotFoundError(f"missing webui_status_ledger.csv in {run_root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger = pd.read_csv(ledger_csv, dtype=object, keep_default_na=False)
    return ledger, manifest


def _merge_windows(intervals: Iterable[tuple[str, str]]) -> list[tuple[date, date]]:
    parsed: list[tuple[date, date]] = []
    for since, until in intervals:
        if not since or not until:
            continue
        parsed.append((coerce_iso_date(since), coerce_iso_date(until)))
    parsed.sort()
    if not parsed:
        return []
    merged = [parsed[0]]
    for cur_start, cur_end in parsed[1:]:
        last_start, last_end = merged[-1]
        if cur_start <= (last_end + timedelta(days=1)):
            merged[-1] = (last_start, max(last_end, cur_end))
        else:
            merged.append((cur_start, cur_end))
    return merged


def compute_continuity_gaps(
    *,
    pack_windows: Sequence[dict[str, Any]],
    enabled_stores: Sequence[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    start_date = coerce_iso_date(start)
    end_date = coerce_iso_date(end)
    rows: list[dict[str, Any]] = []
    for store in enabled_stores:
        intervals = _merge_windows(
            (str(item.get("window_since") or ""), str(item.get("window_until") or ""))
            for item in pack_windows
            if str(item.get("store_code") or "").upper() == str(store).upper()
        )
        cursor = start_date
        if not intervals:
            rows.append(
                {
                    "store_code": store,
                    "gap_start": start,
                    "gap_end": end,
                    "reason": "MISSING_STORE_WINDOWS",
                }
            )
            continue
        for interval_start, interval_end in intervals:
            if interval_end < start_date or interval_start > end_date:
                continue
            effective_start = max(interval_start, start_date)
            effective_end = min(interval_end, end_date)
            if effective_start > cursor:
                rows.append(
                    {
                        "store_code": store,
                        "gap_start": cursor.isoformat(),
                        "gap_end": (effective_start - timedelta(days=1)).isoformat(),
                        "reason": "UNION_WINDOW_GAP",
                    }
                )
            cursor = max(cursor, effective_end + timedelta(days=1))
        if cursor <= end_date:
            rows.append(
                {
                    "store_code": store,
                    "gap_start": cursor.isoformat(),
                    "gap_end": end,
                    "reason": "UNION_WINDOW_GAP",
                }
            )
    return pd.DataFrame(rows, columns=["store_code", "gap_start", "gap_end", "reason"])


def _fetch_db_rows_for_orders(db_path: Path, order_ids: list[str]) -> pd.DataFrame:
    if not order_ids:
        return pd.DataFrame(
            columns=[
                "order_id",
                "sale_date",
                "store_code",
                "sku_key",
                "sku_id",
                "units",
                "net_rev_kzt",
                "cogs_kzt",
                "cogs_source",
                "profit_kzt",
            ]
        )
    conn = sqlite3.connect(str(db_path))
    try:
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
                    CAST(COALESCE(units, 0) AS REAL) AS units,
                    CAST(COALESCE(net_rev_kzt, 0) AS REAL) AS net_rev_kzt,
                    CAST(COALESCE(cogs_kzt, 0) AS REAL) AS cogs_kzt,
                    COALESCE(cogs_source, 'unresolved') AS cogs_source,
                    CAST(COALESCE(profit_kzt, 0) AS REAL) AS profit_kzt
                FROM view_sales_line_truth
                WHERE CAST(order_id AS TEXT) IN ({placeholders})
            """
            frames.append(pd.read_sql_query(query, conn, params=chunk))
    finally:
        conn.close()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_webui_truth_projection(
    *,
    db_path: Path,
    ledger_run_root: Path,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized_start = coerce_iso_date_string(start)
    normalized_end = coerce_iso_date_string(end)
    ledger, manifest = load_status_ledger(ledger_run_root)
    delivered_orders = (
        ledger[["store_code", "order_id", "delivered_at", "returned_at", "first_seen_pack", "last_seen_pack"]]
        .drop_duplicates()
        .copy()
    )
    delivered_orders["delivered_at"] = delivered_orders["delivered_at"].replace({"": pd.NA})
    delivered_orders["returned_at"] = delivered_orders["returned_at"].replace({"": pd.NA})
    delivered_orders = delivered_orders[
        delivered_orders["delivered_at"].notna()
        & delivered_orders["returned_at"].isna()
        & (delivered_orders["delivered_at"] >= normalized_start)
        & (delivered_orders["delivered_at"] <= normalized_end)
    ].copy()

    db_rows = _fetch_db_rows_for_orders(
        db_path=db_path.resolve(),
        order_ids=sorted(delivered_orders["order_id"].dropna().astype(str).unique().tolist()),
    )
    if db_rows.empty:
        if delivered_orders.empty:
            projection = pd.DataFrame(
                columns=[
                    "order_id",
                    "sale_date",
                    "store_code",
                    "sku_key",
                    "sku_id",
                    "units",
                    "net_rev_kzt",
                    "cogs_kzt",
                    "cogs_source",
                    "profit_kzt",
                    "truth_source",
                    "webui_delivered_at",
                    "first_seen_pack",
                    "last_seen_pack",
                    "db_match_status",
                ]
            )
        else:
            projection = delivered_orders.copy()
            projection["sale_date"] = projection["delivered_at"]
            projection["sku_key"] = ""
            projection["sku_id"] = ""
            projection["units"] = 0.0
            projection["net_rev_kzt"] = 0.0
            projection["cogs_kzt"] = 0.0
            projection["cogs_source"] = "unresolved"
            projection["profit_kzt"] = 0.0
            projection["truth_source"] = "webui_archive"
            projection["webui_delivered_at"] = projection["delivered_at"]
            projection["db_match_status"] = "MISSING_IN_DB"
            projection = projection.drop(columns=["delivered_at", "returned_at"])
    else:
        projection = db_rows.merge(
            delivered_orders,
            on=["store_code", "order_id"],
            how="right",
            indicator=True,
        )
        projection["sale_date"] = projection["delivered_at"]
        projection["truth_source"] = "webui_archive"
        projection["webui_delivered_at"] = projection["delivered_at"]
        projection["db_match_status"] = projection["_merge"].map(
            {"both": "MATCHED", "right_only": "MISSING_IN_DB"}
        )
        projection = projection.drop(columns=["_merge", "delivered_at", "returned_at"])
        projection["units"] = pd.to_numeric(projection["units"], errors="coerce").fillna(0.0)
        projection["net_rev_kzt"] = pd.to_numeric(projection["net_rev_kzt"], errors="coerce").fillna(0.0)
        projection["cogs_kzt"] = pd.to_numeric(projection["cogs_kzt"], errors="coerce").fillna(0.0)
        projection["profit_kzt"] = pd.to_numeric(projection["profit_kzt"], errors="coerce").fillna(0.0)
        projection = projection.sort_values(["sale_date", "store_code", "order_id", "sku_key"], na_position="last")

    metadata = {
        "start": normalized_start,
        "end": normalized_end,
        "ledger_run_root": str(ledger_run_root.resolve()),
        "ledger_run_id": manifest.get("run_id"),
        "ledger_delivered_orders": int(len(delivered_orders)),
        "projected_rows": int(len(projection)),
        "projected_orders_matched": int(
            projection[projection["db_match_status"] == "MATCHED"]["order_id"].nunique()
        )
        if not projection.empty
        else 0,
        "missing_in_db_orders": int(
            projection[projection["db_match_status"] == "MISSING_IN_DB"]["order_id"].nunique()
        )
        if not projection.empty
        else int(len(delivered_orders)),
    }
    return projection, metadata


def build_webui_parity_csv(
    *,
    db_path: Path,
    ledger_run_root: Path,
    start: str,
    end: str,
    output_csv: Path,
) -> dict[str, Any]:
    projection, metadata = build_webui_truth_projection(
        db_path=db_path,
        ledger_run_root=ledger_run_root,
        start=start,
        end=end,
    )
    parity_df = projection.copy()
    if parity_df.empty:
        parity_df = pd.DataFrame(
            columns=[
                "transaction_date",
                "store_code",
                "order_id",
                "sku_key",
                "sku_id",
                "quantity",
                "net_rev_kzt",
                "status_internal",
                "return_flag",
                "transaction_date_source",
            ]
        )
    else:
        parity_df = pd.DataFrame(
            {
                "transaction_date": projection["sale_date"],
                "store_code": projection["store_code"],
                "order_id": projection["order_id"],
                "sku_key": projection["sku_key"],
                "sku_id": projection["sku_id"],
                "quantity": projection["units"],
                "net_rev_kzt": projection["net_rev_kzt"],
                "status_internal": "DELIVERED",
                "return_flag": 0,
                "transaction_date_source": "webui_status_ledger",
            }
        )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    parity_df.to_csv(output_csv, index=False, encoding="utf-8")
    metadata["output_csv"] = str(output_csv.resolve())
    return metadata
