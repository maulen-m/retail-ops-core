#!/usr/bin/env python3
"""Validate shipped truth parity (API vs CRM vs waybill) with fail-closed policy."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Callable, Iterable

import pandas as pd
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from core.integrations.kaspi_api_client import KaspiAPIClient, KaspiAuthError, STORE_TOKEN_MAP

ALMATY_TZ = ZoneInfo("Asia/Almaty")
ORDER_ID_RE = re.compile(r"(\d{6,})")

STORE_CODE_TO_CRM = {
    "UNIVERSAL": "Universal",
    "ACMEWEAR": "AcmeWear",
    "11KZ": "11KZ",
    "MELVIS": "Store-C",
    "STOREB": "STORE-B",
}
CRM_CODE_TO_NAME = {
    "30137883_PP1": "AcmeWear",
    "30000001_PP1": "Universal",
    "30290083_PP1": "11KZ",
    "30000002_PP1": "STORE-B",
    "30362323_PP1": "Store-C",
}
CRM_NAME_TO_STORE_CODE = {value: key for key, value in STORE_CODE_TO_CRM.items()}
CANCELLED_DB_STATUSES = {"CANCELLED", "RETURNED", "RETURNING", "CANCELLING"}
CANCELLED_TEXT_TOKENS = ("cancel", "отмен", "возврат", "возвращ")
DEFAULT_CRM_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_ARCHIVE_ROOT = PROJECT_ROOT / "excel_ui" / "Archive"
DEFAULT_WAYBILL_FALLBACK_DIR = PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "waybills"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "shipped_truth_crm_waybill"
API_WINDOW_DAYS = 14
API_PAGE_SIZE = 100


@dataclass(frozen=True)
class ApiOrderRow:
    ship_date: date
    store_code: str
    store_name: str
    order_id: str
    api_state: str
    api_status: str
    state_bucket: str
    is_cancelled_final: bool


ApiFetcher = Callable[[date, str], pd.DataFrame]


@dataclass(frozen=True)
class DbOrderSnapshot:
    internal_status: str
    courier_transmission_date: str


def _normalize_order_id(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _normalize_store_name(value: Any) -> str:
    if value is None or pd.isna(value):
        return "UNKNOWN"
    text = str(value).strip()
    if text in CRM_CODE_TO_NAME:
        return CRM_CODE_TO_NAME[text]
    if text.upper() in STORE_CODE_TO_CRM:
        return STORE_CODE_TO_CRM[text.upper()]
    return text


def _parse_datetime_any(value: Any) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$", text):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    else:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed


def _parse_planned_date(row: pd.Series) -> date | None:
    for col in ("PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"):
        if col not in row:
            continue
        parsed = _parse_datetime_any(row[col])
        if parsed is not None:
            return parsed.date()
    return None


def _contains_cancel_token(value: str) -> bool:
    low = value.lower()
    return any(token in low for token in CANCELLED_TEXT_TOKENS)


def _parse_ts_ms_to_date(value: Any) -> date | None:
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=ALMATY_TZ).date()
    except Exception:
        return None


def _is_api_cancelled(attrs: dict[str, Any]) -> bool:
    state = str(attrs.get("state") or "").strip().upper()
    if state in CANCELLED_DB_STATUSES:
        return True
    status = str(attrs.get("status") or "").strip().lower()
    return _contains_cancel_token(status)


def _date_windows(start: date, end: date, days: int) -> list[tuple[date, date]]:
    if end < start:
        return []
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        win_end = min(end, cursor + timedelta(days=max(1, days) - 1))
        windows.append((cursor, win_end))
        cursor = win_end + timedelta(days=1)
    return windows


def _fetch_orders_window(
    client: KaspiAPIClient,
    *,
    state_bucket: str,
    since: date,
    until: date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 0
    while True:
        resp = client.list_orders(
            state=state_bucket,
            since=since.isoformat(),
            until=until.isoformat(),
            page_number=page,
            page_size=API_PAGE_SIZE,
        )
        if not resp.success:
            raise RuntimeError(
                f"list_orders failed state={state_bucket} since={since.isoformat()} until={until.isoformat()} error={resp.error}"
            )
        payload = resp.data if isinstance(resp.data, dict) else {}
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if not data:
            break
        rows.extend(data)
        if len(data) < API_PAGE_SIZE:
            break
        page += 1
    return rows


def _dedup_api_rows(rows: list[ApiOrderRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "ship_date",
                "store_code",
                "store_name",
                "order_id",
                "api_state",
                "api_status",
                "state_bucket",
                "is_cancelled_final",
            ]
        )

    df = pd.DataFrame([row.__dict__ for row in rows])
    return (
        df.groupby(["store_code", "store_name", "order_id"], as_index=False)
        .agg(
            ship_date=("ship_date", "max"),
            api_state=("api_state", "last"),
            api_status=("api_status", "last"),
            state_bucket=("state_bucket", lambda values: ",".join(sorted(set(values)))),
            is_cancelled_final=("is_cancelled_final", "max"),
        )
    )


def _collect_api_shipped_rows(since_iso: str, include_ship_day: Callable[[date], bool]) -> list[ApiOrderRow]:
    rows: list[ApiOrderRow] = []
    auth_ready_stores = 0
    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
        except KaspiAuthError:
            continue
        auth_ready_stores += 1
        for state_bucket in ("KASPI_DELIVERY", "ARCHIVE"):
            orders = client.list_all_orders(
                state=state_bucket,
                since=since_iso,
                include_orders="user",
            )

            for order in orders:
                attrs = order.get("attributes", {}) or {}
                delivery = attrs.get("kaspiDelivery", {}) or {}
                ship_day = _parse_ts_ms_to_date(delivery.get("courierTransmissionDate"))
                if ship_day is None or not include_ship_day(ship_day):
                    continue
                order_id = _normalize_order_id(attrs.get("code"))
                if not order_id:
                    continue
                rows.append(
                    ApiOrderRow(
                        ship_date=ship_day,
                        store_code=store_code,
                        store_name=STORE_CODE_TO_CRM.get(store_code, store_code),
                        order_id=order_id,
                        api_state=str(attrs.get("state") or "").strip(),
                        api_status=str(attrs.get("status") or "").strip(),
                        state_bucket=state_bucket,
                        is_cancelled_final=_is_api_cancelled(attrs),
                    )
                )

    if auth_ready_stores == 0:
        raise RuntimeError("No Kaspi API tokens configured for shipped truth validation")

    return rows


def fetch_api_shipped_for_day(day: date, since_iso: str) -> pd.DataFrame:
    rows = _collect_api_shipped_rows(since_iso, lambda ship_day: ship_day == day)
    return _dedup_api_rows(rows)


def fetch_api_shipped_for_range(
    *,
    since: date,
    until: date,
    lookback_days: int = 7,
) -> pd.DataFrame:
    if until < since:
        raise RuntimeError("until date must be >= since date")
    rows: list[ApiOrderRow] = []
    auth_ready_stores = 0
    fetch_start = since - timedelta(days=max(0, int(lookback_days)))
    windows = _date_windows(fetch_start, until, API_WINDOW_DAYS)
    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
        except KaspiAuthError:
            continue
        auth_ready_stores += 1

        for state_bucket in ("KASPI_DELIVERY", "ARCHIVE"):
            for win_since, win_until in windows:
                orders = _fetch_orders_window(
                    client,
                    state_bucket=state_bucket,
                    since=win_since,
                    until=win_until,
                )
                for order in orders:
                    attrs = order.get("attributes", {}) or {}
                    delivery = attrs.get("kaspiDelivery", {}) or {}
                    ship_day = _parse_ts_ms_to_date(delivery.get("courierTransmissionDate"))
                    if ship_day is None or ship_day < since or ship_day > until:
                        continue
                    order_id = _normalize_order_id(attrs.get("code"))
                    if not order_id:
                        continue
                    rows.append(
                        ApiOrderRow(
                            ship_date=ship_day,
                            store_code=store_code,
                            store_name=STORE_CODE_TO_CRM.get(store_code, store_code),
                            order_id=order_id,
                            api_state=str(attrs.get("state") or "").strip(),
                            api_status=str(attrs.get("status") or "").strip(),
                            state_bucket=state_bucket,
                            is_cancelled_final=_is_api_cancelled(attrs),
                        )
                    )

    if auth_ready_stores == 0:
        raise RuntimeError("No Kaspi API tokens configured for shipped truth validation")

    return _dedup_api_rows(rows)


def _read_db_order_snapshot_map(db_path: Path, order_ids: Iterable[str]) -> dict[str, DbOrderSnapshot]:
    ids = sorted({oid for oid in order_ids if oid})
    if not ids or not db_path.exists():
        return {}

    with sqlite3.connect(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return {}
        cols = {str(row[1]).lower() for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()}
        has_updated = "updated_at" in cols
        has_imported = "imported_at" in cols
        has_id = "id" in cols
        has_courier = "courier_transmission_date" in cols

        ts_expr = "'1970-01-01'"
        if has_updated and has_imported:
            ts_expr = "COALESCE(updated_at, imported_at, '1970-01-01')"
        elif has_updated:
            ts_expr = "COALESCE(updated_at, '1970-01-01')"
        elif has_imported:
            ts_expr = "COALESCE(imported_at, '1970-01-01')"

        id_expr = "id" if has_id else "rowid"
        courier_expr = "courier_transmission_date" if has_courier else "''"
        placeholders = ",".join(["?"] * len(ids))
        rows = conn.execute(
            f"""
            SELECT order_id, internal_status, {courier_expr} AS courier_transmission_date, {ts_expr} AS sort_ts, {id_expr} AS sort_id
            FROM fact_orders_kaspi
            WHERE order_id IN ({placeholders})
            ORDER BY
                order_id ASC,
                datetime(sort_ts) DESC,
                sort_id DESC
            """,
            ids,
        ).fetchall()
    snapshot_map: dict[str, DbOrderSnapshot] = {}
    for order_id, status, courier_transmission_date, *_ in rows:
        oid = str(order_id)
        if oid in snapshot_map:
            continue
        snapshot_map[oid] = DbOrderSnapshot(
            internal_status=str(status or "").upper().strip(),
            courier_transmission_date=str(courier_transmission_date or "").strip(),
        )
    return snapshot_map


def _load_crm_range(crm_path: Path, since: date, until: date, db_path: Path) -> pd.DataFrame:
    if not crm_path.exists():
        return pd.DataFrame(columns=["order_id", "store_name", "my_size", "is_cancelled", "planned_date"])

    raw = pd.read_excel(crm_path, sheet_name="SALES_KSP_CRM_1")
    rows: list[dict[str, Any]] = []
    for _, row in raw.iterrows():
        order_id = _normalize_order_id(row.get("OrderID") or row.get("№ заказа"))
        if not order_id:
            continue
        planned = _parse_planned_date(row)
        if planned is None or planned < since or planned > until:
            continue
        store_name = _normalize_store_name(row.get("STORE_NAME") or row.get("Склад передачи КД"))
        my_size = str(row.get("MY_SIZE") or "").strip()
        status_text = str(row.get("Статус") or row.get("Return") or "").strip()
        rows.append(
            {
                "order_id": order_id,
                "store_name": store_name,
                "my_size": my_size,
                "crm_status_text": status_text,
                "planned_date": planned,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["order_id", "store_name", "my_size", "is_cancelled", "planned_date"])

    df = pd.DataFrame(rows).drop_duplicates(subset=["order_id", "store_name", "planned_date"], keep="last")
    db_snapshot = _read_db_order_snapshot_map(db_path, df["order_id"].tolist())

    def classify_cancelled(order_id: str, status_text: str) -> bool:
        db_value = db_snapshot.get(order_id, DbOrderSnapshot("", "")).internal_status
        if db_value in CANCELLED_DB_STATUSES:
            return True
        return _contains_cancel_token(status_text)

    def classify_shipped_universe(order_id: str) -> bool:
        snap = db_snapshot.get(order_id)
        if snap is None:
            return False
        if snap.courier_transmission_date:
            return True
        return snap.internal_status in {
            "SHIPPED",
            "COMPLETED",
            "RETURNED",
            "RETURNING",
            "CANCELLED",
            "CANCELLING",
        }

    df["is_cancelled"] = [
        classify_cancelled(str(row.order_id), str(row.crm_status_text or ""))
        for row in df.itertuples(index=False)
    ]
    df["in_shipped_universe"] = [classify_shipped_universe(str(order_id)) for order_id in df["order_id"].astype(str)]
    return df


def _load_crm_for_day(crm_path: Path, day: date, db_path: Path) -> pd.DataFrame:
    df = _load_crm_range(crm_path, day, day, db_path)
    if df.empty:
        return pd.DataFrame(columns=["order_id", "store_name", "my_size", "is_cancelled", "in_shipped_universe"])
    return df[df["planned_date"] == day][["order_id", "store_name", "my_size", "is_cancelled", "in_shipped_universe"]].copy()


def _find_latest_archive_input_dir(archive_root: Path, day: date) -> Path | None:
    if not archive_root.exists():
        return None
    pattern = f"input_{day.isoformat()}_*"
    candidates = [p for p in archive_root.glob(pattern) if p.is_dir()]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def _extract_pdf_order_ids(waybill_dir: Path) -> set[str]:
    ids: set[str] = set()
    for pdf in sorted(waybill_dir.glob("*.pdf")):
        stem = pdf.stem.strip()
        if stem.isdigit():
            ids.add(stem)
            continue
        match = ORDER_ID_RE.search(pdf.name)
        if match:
            ids.add(str(match.group(1)))
    return ids


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["store", "order_id", "reason"])
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _within_shift_window(day: date, candidates: set[date], max_shift_days: int) -> bool:
    if max_shift_days <= 0 or not candidates:
        return False
    for candidate in candidates:
        if abs((candidate - day).days) <= max_shift_days:
            return True
    return False


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Shipped Truth CRM/Waybill Validation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- since: `{report['since']}`",
        f"- until: `{report['until']}`",
        f"- status: `{report['status']}`",
        f"- include_today_provisional: `{report['include_today_provisional']}`",
        f"- volatility_days: `{report['volatility_days']}`",
        f"- date_shift_tolerance_days: `{report['date_shift_tolerance_days']}`",
        f"- api_creation_lookback_days: `{report['api_creation_lookback_days']}`",
        f"- mismatch_threshold_pct: `{report['mismatch_threshold_pct']}`",
        f"- waybill_missing_threshold_pct: `{report['waybill_missing_threshold_pct']}`",
        f"- cancel_drift_threshold_pct: `{report['cancel_drift_threshold_pct']}`",
        "",
        "| day | store | api_primary | api_secondary | crm_expected | crm_all | waybill_ids | mismatch_pct | waybill_missing_pct | cancel_drift_pct | status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {day} | {store} | {api_primary} | {api_secondary} | {crm_expected} | {crm_all} | {waybill} | "
            "{mismatch:.2f} | {waybill_missing:.2f} | {cancel_drift:.2f} | {status} |".format(
                day=row["day"],
                store=row["store"],
                api_primary=row["api_primary"],
                api_secondary=row["api_secondary"],
                crm_expected=row["crm_expected"],
                crm_all=row["crm_all"],
                waybill=row["waybill_ids"],
                mismatch=row["mismatch_pct"],
                waybill_missing=row["waybill_missing_pct"],
                cancel_drift=row["cancel_drift_pct"],
                status="PASS" if row["ok"] else "FAIL",
            )
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_shipped_truth_crm_waybill(
    *,
    project_root: Path,
    since: str,
    until: str,
    strict: bool,
    output_root: Path,
    include_today_provisional: bool = True,
    volatility_days: int = 14,
    date_shift_tolerance_days: int = 1,
    mismatch_threshold_pct: float = 0.0,
    waybill_missing_threshold_pct: float = 2.0,
    cancel_drift_threshold_pct: float = 2.0,
    api_creation_lookback_days: int = 120,
    crm_path: Path = DEFAULT_CRM_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    waybill_fallback_dir: Path = DEFAULT_WAYBILL_FALLBACK_DIR,
    api_fetcher: ApiFetcher | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    since_date = date.fromisoformat(since)
    until_date = date.fromisoformat(until)
    if until_date < since_date:
        raise RuntimeError("until date must be >= since date")

    fetcher = api_fetcher or fetch_api_shipped_for_day
    today = datetime.now(ALMATY_TZ).date()
    out_dir = output_root.resolve() / f"{since_date.isoformat()}_to_{until_date.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    mismatch_csv_rows: list[dict[str, Any]] = []
    shifted_csv_rows: list[dict[str, Any]] = []
    waybill_missing_rows: list[dict[str, Any]] = []
    api_prefetch_df: pd.DataFrame | None = None
    api_prefetch_error: str | None = None
    detail_clients: dict[str, KaspiAPIClient] = {}
    detail_cache: dict[tuple[str, str], tuple[date | None, bool, bool]] = {}
    if api_fetcher is None:
        try:
            api_prefetch_df = fetch_api_shipped_for_range(
                since=since_date,
                until=until_date,
                lookback_days=max(0, int(api_creation_lookback_days)),
            )
        except Exception as exc:  # noqa: BLE001
            api_prefetch_error = str(exc)
            errors.append(f"api_prefetch_failed: {api_prefetch_error}")
            api_prefetch_df = pd.DataFrame(
                columns=["store_code", "store_name", "order_id", "is_cancelled_final", "api_state", "api_status", "ship_date"]
            )
    crm_range_df = _load_crm_range(crm_path.resolve(), since_date, until_date, db_path.resolve())
    fallback_waybill_ids = _extract_pdf_order_ids(waybill_fallback_dir.resolve())

    api_primary_day_map: dict[tuple[str, str], set[date]] = {}
    if api_prefetch_df is not None and not api_prefetch_df.empty:
        for row in api_prefetch_df.itertuples(index=False):
            if bool(getattr(row, "is_cancelled_final", False)):
                continue
            store_name = str(getattr(row, "store_name", "") or "")
            order_id = _normalize_order_id(getattr(row, "order_id", ""))
            ship_day = getattr(row, "ship_date", None)
            if not store_name or not order_id or not isinstance(ship_day, date):
                continue
            api_primary_day_map.setdefault((store_name, order_id), set()).add(ship_day)

    crm_expected_day_map: dict[tuple[str, str], set[date]] = {}
    if not crm_range_df.empty:
        crm_expected_rows = crm_range_df[~crm_range_df["is_cancelled"]].copy()
        for row in crm_expected_rows.itertuples(index=False):
            store_name = str(getattr(row, "store_name", "") or "")
            order_id = _normalize_order_id(getattr(row, "order_id", ""))
            planned_day = getattr(row, "planned_date", None)
            if not store_name or not order_id or not isinstance(planned_day, date):
                continue
            crm_expected_day_map.setdefault((store_name, order_id), set()).add(planned_day)

    day = since_date
    while day <= until_date:
        since_iso = max(day - timedelta(days=7), since_date).isoformat()
        if api_prefetch_df is not None:
            api_df = api_prefetch_df[api_prefetch_df["ship_date"] == day].copy()
        else:
            api_df = fetcher(day, since_iso)
        if api_df.empty:
            api_df = pd.DataFrame(
                columns=["store_code", "store_name", "order_id", "is_cancelled_final", "api_state", "api_status"]
            )

        crm_df = crm_range_df[crm_range_df["planned_date"] == day].copy()
        if not crm_df.empty:
            crm_df = crm_df[["order_id", "store_name", "my_size", "is_cancelled", "in_shipped_universe"]]
        else:
            crm_df = pd.DataFrame(columns=["order_id", "store_name", "my_size", "is_cancelled", "in_shipped_universe"])
        archive_input = _find_latest_archive_input_dir(archive_root.resolve(), day)
        waybill_ids = _extract_pdf_order_ids(archive_input / "waybills") if archive_input else set()
        if fallback_waybill_ids:
            waybill_ids |= fallback_waybill_ids

        stores = sorted(set(api_df.get("store_name", pd.Series(dtype=str)).dropna().tolist()) | set(crm_df.get("store_name", pd.Series(dtype=str)).dropna().tolist()))
        if not stores:
            stores = sorted(STORE_CODE_TO_CRM.values())

        for store in stores:
            api_store = api_df[api_df["store_name"] == store]
            crm_store = crm_df[crm_df["store_name"] == store]

            api_secondary = set(api_store["order_id"].astype(str))
            api_primary = set(api_store.loc[~api_store["is_cancelled_final"], "order_id"].astype(str))
            api_cancelled_ids = set(api_store.loc[api_store["is_cancelled_final"], "order_id"].astype(str))
            crm_all = set(crm_store["order_id"].astype(str))

            # Cancellation truth for shipped-universe orders follows API final status.
            # For orders outside the shipped API universe, use DB/CRM cancellation classification.
            crm_base_cancelled = set(
                crm_store.loc[crm_store["is_cancelled"], "order_id"].astype(str)
            )
            crm_unshipped_ids = set(crm_store.loc[~crm_store["in_shipped_universe"], "order_id"].astype(str))
            crm_base_cancelled |= crm_unshipped_ids
            crm_cancelled_effective = (crm_base_cancelled - api_secondary) | (api_cancelled_ids & crm_all)
            crm_expected = crm_all - crm_cancelled_effective

            # API detail fallback: some returned/completed orders are not surfaced by list-orders state buckets.
            # For orders expected by CRM but absent in API shipped set, verify by direct order-code lookup.
            detail_fallback_hits = 0
            store_code = CRM_NAME_TO_STORE_CODE.get(store, "")
            if api_fetcher is None and crm_expected:
                if store_code:
                    try:
                        detail_candidates = sorted(
                            order_id
                            for order_id in (crm_expected - api_secondary)
                            if not _within_shift_window(
                                day,
                                api_primary_day_map.get((store, order_id), set()),
                                int(date_shift_tolerance_days),
                            )
                        )
                        if detail_candidates and store_code not in detail_clients:
                            detail_clients[store_code] = KaspiAPIClient(store_code=store_code)
                        detail_client = detail_clients.get(store_code)
                        for order_id in detail_candidates:
                            assert detail_client is not None
                            cache_key = (store_code, order_id)
                            if cache_key in detail_cache:
                                ship_day, is_cancelled, has_waybill = detail_cache[cache_key]
                            else:
                                resp = detail_client.get_order(order_id)
                                ship_day = None
                                is_cancelled = False
                                has_waybill = False
                                if resp.success and isinstance(resp.data, dict):
                                    attrs = resp.data.get("attributes", {}) or {}
                                    delivery = attrs.get("kaspiDelivery", {}) or {}
                                    ship_day = _parse_ts_ms_to_date(delivery.get("courierTransmissionDate"))
                                    is_cancelled = _is_api_cancelled(attrs)
                                    has_waybill = bool(delivery.get("waybill") or delivery.get("waybillNumber"))
                                detail_cache[cache_key] = (ship_day, is_cancelled, has_waybill)
                            if ship_day == day:
                                detail_fallback_hits += 1
                                api_secondary.add(order_id)
                                if is_cancelled:
                                    api_cancelled_ids.add(order_id)
                                else:
                                    api_primary.add(order_id)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{day} {store}: api_detail_fallback_failed: {exc}")

            raw_miss_in_crm = sorted(api_primary - crm_expected)
            raw_miss_in_api = sorted(crm_expected - api_primary)
            shifted_from_api = sorted(
                oid
                for oid in raw_miss_in_crm
                if _within_shift_window(day, crm_expected_day_map.get((store, oid), set()), int(date_shift_tolerance_days))
            )
            shifted_from_crm = sorted(
                oid
                for oid in raw_miss_in_api
                if _within_shift_window(day, api_primary_day_map.get((store, oid), set()), int(date_shift_tolerance_days))
            )
            miss_in_crm = sorted(set(raw_miss_in_crm) - set(shifted_from_api))
            miss_in_api = sorted(set(raw_miss_in_api) - set(shifted_from_crm))
            waybill_missing = sorted(crm_expected - waybill_ids) if waybill_ids else []
            waybill_detail_resolved = 0
            if api_fetcher is None and waybill_missing and store_code:
                try:
                    if store_code not in detail_clients:
                        detail_clients[store_code] = KaspiAPIClient(store_code=store_code)
                    detail_client = detail_clients[store_code]
                    resolved_ids: set[str] = set()
                    for order_id in waybill_missing:
                        cache_key = (store_code, order_id)
                        if cache_key in detail_cache:
                            ship_day, _is_cancelled, has_waybill = detail_cache[cache_key]
                        else:
                            resp = detail_client.get_order(order_id)
                            ship_day = None
                            has_waybill = False
                            is_cancelled = False
                            if resp.success and isinstance(resp.data, dict):
                                attrs = resp.data.get("attributes", {}) or {}
                                delivery = attrs.get("kaspiDelivery", {}) or {}
                                ship_day = _parse_ts_ms_to_date(delivery.get("courierTransmissionDate"))
                                is_cancelled = _is_api_cancelled(attrs)
                                has_waybill = bool(delivery.get("waybill") or delivery.get("waybillNumber"))
                            detail_cache[cache_key] = (ship_day, is_cancelled, has_waybill)
                        if ship_day == day and has_waybill:
                            resolved_ids.add(order_id)
                    if resolved_ids:
                        waybill_detail_resolved = len(resolved_ids)
                        waybill_missing = sorted(set(waybill_missing) - resolved_ids)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{day} {store}: waybill_detail_fallback_failed: {exc}")

            denom = max(1, max(len(api_primary), len(crm_expected)))
            mismatch_pct = (len(miss_in_crm) + len(miss_in_api)) * 100.0 / float(denom)
            waybill_missing_pct = (
                (len(waybill_missing) * 100.0 / float(max(1, len(crm_expected)))) if waybill_ids and crm_expected else 0.0
            )
            api_cancelled = max(0, len(api_secondary) - len(api_primary))
            # Shipped-universe drift: do not count planned-day cancellations that never entered shipped API universe.
            crm_cancelled_ids = crm_cancelled_effective & api_secondary
            crm_cancelled = len(crm_cancelled_ids)
            cancel_drift_pct = abs(api_cancelled - crm_cancelled) * 100.0 / float(max(1, len(api_secondary)))

            volatility_floor = today - timedelta(days=max(0, int(volatility_days)))
            completed_day = day <= volatility_floor and not (include_today_provisional and day == today)
            checkable = completed_day and api_prefetch_error is None and (len(crm_all) > 0 or len(api_secondary) > 0)
            ok = True
            if checkable:
                if mismatch_pct > mismatch_threshold_pct:
                    ok = False
                    errors.append(
                        f"{day} {store}: mismatch_pct={mismatch_pct:.2f} exceeds threshold={mismatch_threshold_pct:.2f}"
                    )
                if waybill_ids and len(crm_expected) > 0 and waybill_missing_pct > waybill_missing_threshold_pct:
                    ok = False
                    errors.append(
                        f"{day} {store}: waybill_missing_pct={waybill_missing_pct:.2f} exceeds threshold={waybill_missing_threshold_pct:.2f}"
                    )
                if cancel_drift_pct > cancel_drift_threshold_pct:
                    ok = False
                    errors.append(
                        f"{day} {store}: cancel_drift_pct={cancel_drift_pct:.2f} exceeds threshold={cancel_drift_threshold_pct:.2f}"
                    )
            elif completed_day and api_prefetch_error is not None:
                ok = False

            rows.append(
                {
                    "day": day.isoformat(),
                    "store": store,
                    "api_primary": len(api_primary),
                    "api_secondary": len(api_secondary),
                    "api_cancelled": api_cancelled,
                    "crm_expected": len(crm_expected),
                    "crm_all": len(crm_all),
                    "crm_cancelled": crm_cancelled,
                    "waybill_ids": len(waybill_ids),
                    "mismatch_pct": round(mismatch_pct, 2),
                    "waybill_missing_pct": round(waybill_missing_pct, 2),
                    "cancel_drift_pct": round(cancel_drift_pct, 2),
                    "provisional": not completed_day,
                    "ok": ok,
                    "volatility_days": int(volatility_days),
                    "date_shift_tolerance_days": int(date_shift_tolerance_days),
                    "shifted_ids_count": int(len(shifted_from_api) + len(shifted_from_crm)),
                    "detail_fallback_hits": int(detail_fallback_hits),
                    "waybill_detail_resolved": int(waybill_detail_resolved),
                    "api_prefetch_error": api_prefetch_error or "",
                    "archive_input_dir": str(archive_input) if archive_input else "",
                    "waybill_fallback_dir": str(waybill_fallback_dir.resolve()),
                }
            )

            for order_id in miss_in_crm:
                mismatch_csv_rows.append(
                    {
                        "day": day.isoformat(),
                        "store": store,
                        "order_id": order_id,
                        "reason": "api_primary_missing_in_crm_expected",
                    }
                )
            for order_id in miss_in_api:
                mismatch_csv_rows.append(
                    {
                        "day": day.isoformat(),
                        "store": store,
                        "order_id": order_id,
                        "reason": "crm_expected_missing_in_api_primary",
                    }
                )
            for order_id in shifted_from_api:
                shifted_csv_rows.append(
                    {
                        "day": day.isoformat(),
                        "store": store,
                        "order_id": order_id,
                        "reason": "api_primary_shifted_to_adjacent_crm_day",
                    }
                )
            for order_id in shifted_from_crm:
                shifted_csv_rows.append(
                    {
                        "day": day.isoformat(),
                        "store": store,
                        "order_id": order_id,
                        "reason": "crm_expected_shifted_to_adjacent_api_day",
                    }
                )
            for order_id in waybill_missing:
                waybill_missing_rows.append(
                    {
                        "day": day.isoformat(),
                        "store": store,
                        "order_id": order_id,
                        "reason": "crm_expected_missing_waybill_pdf",
                    }
                )

        day += timedelta(days=1)

    status = "PASS" if not errors else "FAIL"
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project_root": str(root),
        "since": since,
        "until": until,
        "status": status,
        "ok": status == "PASS",
        "include_today_provisional": bool(include_today_provisional),
        "volatility_days": int(volatility_days),
        "date_shift_tolerance_days": int(date_shift_tolerance_days),
        "api_creation_lookback_days": int(api_creation_lookback_days),
        "mismatch_threshold_pct": float(mismatch_threshold_pct),
        "waybill_missing_threshold_pct": float(waybill_missing_threshold_pct),
        "cancel_drift_threshold_pct": float(cancel_drift_threshold_pct),
        "errors": errors,
        "rows": rows,
    }

    (out_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(_render_md(report), encoding="utf-8")
    pd.DataFrame(rows).to_csv(out_dir / "summary_by_day_store.csv", index=False, encoding="utf-8-sig")
    _write_csv(out_dir / "mismatch_ids.csv", mismatch_csv_rows)
    _write_csv(out_dir / "shifted_ids.csv", shifted_csv_rows)
    _write_csv(out_dir / "missing_waybill_ids.csv", waybill_missing_rows)

    report["json_path"] = str(out_dir / "summary.json")
    report["md_path"] = str(out_dir / "report.md")
    report["summary_csv"] = str(out_dir / "summary_by_day_store.csv")
    report["mismatch_csv"] = str(out_dir / "mismatch_ids.csv")
    report["shifted_csv"] = str(out_dir / "shifted_ids.csv")
    report["waybill_missing_csv"] = str(out_dir / "missing_waybill_ids.csv")

    if errors:
        exception_dir = root / "exports" / "exceptions" / until
        exception_dir.mkdir(parents=True, exist_ok=True)
        exception_payload = {
            "exception_type": "SHIPPED_TRUTH_CRM_WAYBILL_FAIL",
            "severity": "critical",
            "owner": "ops/daily-ops",
            "as_of": until,
            "status": "OPEN",
            "summary": "Shipped truth parity failed strict thresholds",
            "recommended_action": "Review mismatch_ids.csv and missing_waybill_ids.csv, remediate data/selection issues, rerun strict validator.",
            "evidence_paths": [
                str(out_dir / "summary.json"),
                str(out_dir / "report.md"),
                str(out_dir / "mismatch_ids.csv"),
                str(out_dir / "shifted_ids.csv"),
                str(out_dir / "missing_waybill_ids.csv"),
            ],
            "errors": errors,
        }
        (exception_dir / "shipped_truth_exception.json").write_text(
            json.dumps(exception_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (exception_dir / "shipped_truth_exception.md").write_text(
            "\n".join(
                [
                    "# Shipped Truth Exception",
                    "",
                    f"- type: `{exception_payload['exception_type']}`",
                    f"- severity: `{exception_payload['severity']}`",
                    f"- as_of: `{until}`",
                    "- status: `OPEN`",
                    "",
                    "## Errors",
                    *[f"- {err}" for err in errors],
                    "",
                    "## Evidence",
                    *[f"- `{path}`" for path in exception_payload["evidence_paths"]],
                    "",
                ]
            ),
            encoding="utf-8",
        )

    if strict and errors:
        raise RuntimeError("shipped truth CRM/waybill validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate shipped truth parity across API/CRM/waybills")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--waybill-fallback-dir", type=Path, default=DEFAULT_WAYBILL_FALLBACK_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-today-provisional", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--volatility-days", type=int, default=14)
    parser.add_argument("--date-shift-tolerance-days", type=int, default=1)
    parser.add_argument("--api-creation-lookback-days", type=int, default=120)
    parser.add_argument("--mismatch-threshold-pct", type=float, default=0.0)
    parser.add_argument("--waybill-missing-threshold-pct", type=float, default=2.0)
    parser.add_argument("--cancel-drift-threshold-pct", type=float, default=2.0)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_shipped_truth_crm_waybill(
        project_root=args.project_root,
        since=str(args.since),
        until=str(args.until),
        strict=False,
        output_root=args.output_root,
        include_today_provisional=bool(args.include_today_provisional),
        volatility_days=int(args.volatility_days),
        date_shift_tolerance_days=int(args.date_shift_tolerance_days),
        mismatch_threshold_pct=float(args.mismatch_threshold_pct),
        waybill_missing_threshold_pct=float(args.waybill_missing_threshold_pct),
        cancel_drift_threshold_pct=float(args.cancel_drift_threshold_pct),
        api_creation_lookback_days=int(args.api_creation_lookback_days),
        crm_path=args.crm_file,
        db_path=args.db,
        archive_root=args.archive_root,
        waybill_fallback_dir=args.waybill_fallback_dir,
    )
    print(f"shipped_truth_json={report['json_path']}")
    print(f"shipped_truth_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
