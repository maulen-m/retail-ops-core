#!/usr/bin/env python3
"""
Export Kaspi ARCHIVE orders for a historical date range across stores.

Design goals:
- Fail-closed by default (strict mode)
- Deterministic output layout for replay/audit
- Efficient extraction using API windows (Kaspi API max 14-day creationDate span)
- Optional line-item enrichment via order entries endpoint
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv

# Ensure repo root imports when invoked from anywhere
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import (  # noqa: E402
    KaspiAPIClient,
    KaspiAuthError,
    STORE_TOKEN_MAP,
)
from scripts.export_api_orders import EXCEL_COLUMNS, order_to_rows  # noqa: E402


WINDOW_DAYS = 14
PAGE_SIZE = 100
MAX_PAGES = 1000


@dataclass
class StoreResult:
    store_code: str
    success: bool
    date_mode: str
    windows_total: int
    windows_ok: int
    orders_raw: int
    orders_dedup: int
    orders_selected: int
    rows_exported: int
    entry_fetch_failures: int
    status_change_missing_completed: int
    status_change_hydration_attempted: int
    status_change_hydration_success: int
    status_change_hydration_skipped_after_probe: int
    output_dir: str
    errors: List[str]


DATE_MODE_CREATION = "creationDate"
DATE_MODE_STATUS_CHANGE = "statusChangeDate"
DATE_MODE_CHOICES = (DATE_MODE_CREATION, DATE_MODE_STATUS_CHANGE)
COMPLETED_STATUS = "COMPLETED"


def now_kz_iso() -> str:
    # Keep timezone explicit in text; no tz dependency required.
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_windows(start: date, end: date, days: int = WINDOW_DAYS) -> List[Tuple[date, date]]:
    if end < start:
        raise ValueError("end date must be >= start date")
    if days < 1:
        raise ValueError("window days must be >= 1")
    windows: List[Tuple[date, date]] = []
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=days - 1), end)
        windows.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return windows


def _timestamp_to_iso(ts: Any) -> str:
    if ts in (None, ""):
        return ""
    try:
        v = int(ts)
        if v > 10_000_000_000:  # ms
            dt = datetime.fromtimestamp(v / 1000)
        else:
            dt = datetime.fromtimestamp(v)
        return dt.isoformat(timespec="seconds")
    except Exception:
        return str(ts)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _timestamp_to_date(ts: Any) -> Optional[date]:
    if ts in (None, ""):
        return None
    try:
        v = int(ts)
        if v > 10_000_000_000:  # ms
            return datetime.fromtimestamp(v / 1000).date()
        return datetime.fromtimestamp(v).date()
    except Exception:
        return None


def _extract_order_from_response(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and row.get("attributes"):
                    return row
        if payload.get("attributes"):
            return payload
    return None


def _copy_status_change_date(order: Dict[str, Any], detail_order: Optional[Dict[str, Any]]) -> bool:
    if not detail_order:
        return False
    detail_attrs = detail_order.get("attributes", {}) or {}
    status_change = detail_attrs.get("statusChangeDate")
    if status_change in (None, ""):
        return False
    attrs = order.setdefault("attributes", {}) or {}
    attrs["statusChangeDate"] = status_change
    order["attributes"] = attrs
    return True


def _order_matches_date_mode(order: Dict[str, Any], mode: str, since: date, until: date) -> bool:
    attrs = order.get("attributes", {}) or {}
    if mode == DATE_MODE_STATUS_CHANGE:
        target_date = _timestamp_to_date(attrs.get("statusChangeDate"))
    else:
        target_date = _timestamp_to_date(attrs.get("creationDate"))
    if not target_date:
        return False
    return since <= target_date <= until


def _hydrate_missing_status_change_dates(
    orders: List[Dict[str, Any]],
    fetch_order_detail: Callable[[str, str], Optional[Dict[str, Any]]],
    max_workers: int = 8,
    probe_limit: int = 25,
) -> Dict[str, int]:
    missing_indices: List[int] = []
    for idx, order in enumerate(orders):
        attrs = order.get("attributes", {}) or {}
        if attrs.get("statusChangeDate") in (None, ""):
            missing_indices.append(idx)

    stats = {
        "attempted": 0,
        "hydrated": 0,
        "skipped_after_probe": 0,
    }
    if not missing_indices:
        return stats

    def _fetch_and_apply(idx: int) -> bool:
        order = orders[idx]
        attrs = order.get("attributes", {}) or {}
        order_id = str(order.get("id") or "")
        order_code = str(attrs.get("code") or "")
        detail_order = fetch_order_detail(order_id, order_code)
        return _copy_status_change_date(order, detail_order)

    probe_hits = 0
    probe_count = min(len(missing_indices), max(0, int(probe_limit)))
    for idx in missing_indices[:probe_count]:
        stats["attempted"] += 1
        if _fetch_and_apply(idx):
            stats["hydrated"] += 1
            probe_hits += 1

    remaining = missing_indices[probe_count:]
    if remaining and probe_count > 0 and probe_hits == 0:
        stats["skipped_after_probe"] = len(remaining)
        return stats

    max_workers = max(1, int(max_workers))
    if max_workers == 1:
        for idx in remaining:
            stats["attempted"] += 1
            if _fetch_and_apply(idx):
                stats["hydrated"] += 1
        return stats

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fut_map = {pool.submit(_fetch_and_apply, idx): idx for idx in remaining}
        for fut in as_completed(fut_map):
            stats["attempted"] += 1
            if fut.result():
                stats["hydrated"] += 1
    return stats


def _flatten_order(order: Dict[str, Any], store_code: str) -> Dict[str, Any]:
    attrs = order.get("attributes", {}) or {}
    delivery = attrs.get("kaspiDelivery", {}) or {}
    customer = attrs.get("customer", {}) or {}
    rel = order.get("relationships", {}) or {}
    entries_rel = ((rel.get("entries") or {}).get("data") or []) if isinstance(rel, dict) else []

    phone = customer.get("cellPhone") or ""
    if phone:
        phone = "".join(ch for ch in str(phone) if ch.isdigit())

    return {
        "store_code": store_code,
        "order_id": order.get("id") or "",
        "order_type": order.get("type") or "",
        "order_code": attrs.get("code") or "",
        "state": attrs.get("state") or "",
        "status": attrs.get("status") or "",
        "creation_date": _timestamp_to_iso(attrs.get("creationDate")),
        "status_change_date": _timestamp_to_iso(attrs.get("statusChangeDate")),
        "planned_courier_date": _timestamp_to_iso(delivery.get("courierTransmissionPlanningDate")),
        "courier_transmission_date": _timestamp_to_iso(delivery.get("courierTransmissionDate")),
        "total_price": attrs.get("totalPrice"),
        "delivery_cost_for_seller": attrs.get("deliveryCostForSeller"),
        "delivery_cost": attrs.get("deliveryCost"),
        "delivery_cost_compensation": delivery.get("deliveryCostCompensation"),
        "delivery_mode": attrs.get("deliveryMode") or "",
        "payment_mode": attrs.get("paymentMode") or "",
        "assembled": attrs.get("assembled"),
        "is_kaspi_delivery": attrs.get("isKaspiDelivery"),
        "signature_required": attrs.get("signatureRequired"),
        "pre_order": attrs.get("preOrder"),
        "customer_phone": phone,
        "entry_refs_count": len(entries_rel),
        "entry_refs": ";".join(str((e or {}).get("id") or "") for e in entries_rel),
    }


def _fetch_orders_window(
    client: KaspiAPIClient,
    store_code: str,
    since: str,
    until: str,
    retries: int,
    retry_sleep: float,
) -> List[Dict[str, Any]]:
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            orders: List[Dict[str, Any]] = []
            page = 0
            while page < MAX_PAGES:
                resp = client.list_orders(
                    state="ARCHIVE",
                    since=since,
                    until=until,
                    page_number=page,
                    page_size=PAGE_SIZE,
                )
                if not resp.success:
                    raise RuntimeError(
                        f"list_orders failed store={store_code} since={since} until={until} "
                        f"page={page}: {resp.error}"
                    )

                data = []
                if isinstance(resp.data, dict):
                    data = resp.data.get("data", []) or []
                if not data:
                    break

                orders.extend(data)
                if len(data) < PAGE_SIZE:
                    break
                page += 1

            return orders
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= retries:
                break
            time.sleep(retry_sleep * (2 ** (attempt - 1)))

    raise RuntimeError(last_error or "unknown window fetch error")


def _fetch_order_detail_with_retry(
    client: KaspiAPIClient,
    order_id: str,
    order_code: str,
    retries: int,
    retry_sleep: float,
) -> Optional[Dict[str, Any]]:
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.get_order_by_id(order_id) if order_id else client.get_order(order_code)
            if not resp.success:
                raise RuntimeError(resp.error or "order detail request failed")
            detail_order = _extract_order_from_response(resp.data)
            return detail_order
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= retries:
                break
            time.sleep(retry_sleep * (2 ** (attempt - 1)))

    raise RuntimeError(last_error or "unknown order detail fetch error")


def _fetch_entries_with_retry(
    client: KaspiAPIClient,
    order_id: str,
    order_code: str,
    retries: int,
    retry_sleep: float,
) -> List[Dict[str, Any]]:
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            if order_id:
                resp = client.get_order_entries_by_id(order_id)
            else:
                resp = client.get_order_entries(order_code)

            if not resp.success:
                raise RuntimeError(resp.error or "entries request failed")
            if isinstance(resp.data, dict):
                return resp.data.get("data", []) or []
            return []
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= retries:
                break
            time.sleep(retry_sleep * (2 ** (attempt - 1)))

    raise RuntimeError(last_error or "unknown entries fetch error")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(_json_dumps(row))
            f.write("\n")


def _write_windows_csv(path: Path, windows: List[Dict[str, Any]]) -> None:
    cols = [
        "window_index",
        "since",
        "until",
        "orders_fetched",
        "status",
        "error",
        "duration_sec",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in windows:
            w.writerow({k: row.get(k, "") for k in cols})


def _build_methods_report(path: Path) -> None:
    content = f"""# Kaspi Archive Extraction Methods Report

Generated: {now_kz_iso()}

## How Kaspi Web Archive Works (`https://kaspi.kz/mc/#/orders-new?status=ARCHIVED`)
- Archive section is UI-driven and date-filter based.
- Date inputs typically support 90-day interval selection in one export cycle.
- For long history, operator must execute multiple sequential period exports per store.
- With 5 stores and ~8 windows for this range, manual workload is ~40 exports + file hygiene.

## Methods Compared

### 1) Web UI manual export
- Pros: Native file shape, line-level parity with merchant view.
- Cons: High manual overhead, error-prone period tracking, browser/session fragility.

### 2) Web automation (Playwright)
- Pros: Can automate 90-day block clicking and downloads.
- Cons: Selector drift, profile/session lock issues, download handling complexity.

### 3) API-first archive extraction (implemented)
- Pros: Deterministic, restartable, auditable, fast enough for full history, fail-closed behavior.
- Cons: API creationDate window hard-limit (14 days) requires chunking logic.

## Implemented Efficiency Strategy
- Use API in 14-day windows (strict coverage, no gaps).
- Deduplicate globally by `(store_code, order_id)`.
- Default date cutoff mode is `statusChangeDate` for transaction-aligned exports.
- Hydrate missing `statusChangeDate` via order-detail fetch only for missing rows.
- Persist raw JSONL + normalized CSV/XLSX + manifests for replay.
- Optional per-order line enrichment via entries endpoint.
- Strict mode fails on any store/window failure.

## Recommended Future Procedure (no scratch restart)
1. Run `scripts/export_kaspi_archive_history.py` with explicit `--since/--until`.
2. Keep `--strict` enabled.
3. Archive the output root with manifest + summary.
4. Mirror output to PO Sales_archive destination.
5. Re-run incrementally for new periods only.
"""
    path.write_text(content, encoding="utf-8")


def process_store(
    store_code: str,
    windows: List[Tuple[date, date]],
    since: date,
    until: date,
    out_root: Path,
    fetch_entries: bool,
    entry_workers: int,
    detail_workers: int,
    fetch_masterproduct: bool,
    date_mode: str,
    hydrate_missing_status_change_date: bool,
    require_status_change_date_for_completed: bool,
    retries: int,
    retry_sleep: float,
    strict: bool,
) -> StoreResult:
    store_dir = out_root / f"store_{store_code}"
    store_dir.mkdir(parents=True, exist_ok=True)

    errors: List[str] = []

    try:
        client = KaspiAPIClient(store_code=store_code)
    except KaspiAuthError as exc:
        msg = f"auth failed: {exc}"
        return StoreResult(
            store_code=store_code,
            success=False,
            date_mode=date_mode,
            windows_total=len(windows),
            windows_ok=0,
            orders_raw=0,
            orders_dedup=0,
            orders_selected=0,
            rows_exported=0,
            entry_fetch_failures=0,
            status_change_missing_completed=0,
            status_change_hydration_attempted=0,
            status_change_hydration_success=0,
            status_change_hydration_skipped_after_probe=0,
            output_dir=str(store_dir),
            errors=[msg],
        )

    windows_rows: List[Dict[str, Any]] = []
    raw_orders_lines: List[Dict[str, Any]] = []
    dedup: Dict[str, Dict[str, Any]] = {}

    for idx, (ws, we) in enumerate(windows, start=1):
        window_since = ws.isoformat()
        window_until = we.isoformat()
        started = time.time()
        status = "ok"
        error_msg = ""
        orders: List[Dict[str, Any]] = []

        try:
            orders = _fetch_orders_window(
                client=client,
                store_code=store_code,
                since=window_since,
                until=window_until,
                retries=retries,
                retry_sleep=retry_sleep,
            )
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_msg = str(exc)
            errors.append(f"window {window_since}..{window_until}: {error_msg}")
            if strict:
                windows_rows.append(
                    {
                        "window_index": idx,
                        "since": window_since,
                        "until": window_until,
                        "orders_fetched": 0,
                        "status": status,
                        "error": error_msg,
                        "duration_sec": round(time.time() - started, 3),
                    }
                )
                break

        duration = round(time.time() - started, 3)

        windows_rows.append(
            {
                "window_index": idx,
                "since": window_since,
                "until": window_until,
                "orders_fetched": len(orders),
                "status": status,
                "error": error_msg,
                "duration_sec": duration,
            }
        )

        for order in orders:
            attrs = order.get("attributes", {}) or {}
            key = str(order.get("id") or f"CODE::{attrs.get('code') or ''}")

            raw_orders_lines.append(
                {
                    "store_code": store_code,
                    "window_since": window_since,
                    "window_until": window_until,
                    "order": order,
                }
            )

            if key not in dedup:
                dedup[key] = order

    _write_windows_csv(store_dir / "windows.csv", windows_rows)
    _write_jsonl(store_dir / "archive_orders_api_raw.jsonl", raw_orders_lines)

    dedup_orders = list(dedup.values())
    _write_jsonl(
        store_dir / "archive_orders_dedup.jsonl",
        ({"store_code": store_code, "order": o} for o in dedup_orders),
    )

    status_hydration_stats = {
        "attempted": 0,
        "hydrated": 0,
        "skipped_after_probe": 0,
    }
    if date_mode == DATE_MODE_STATUS_CHANGE and hydrate_missing_status_change_date and dedup_orders:
        def _detail_fetcher(order_id: str, order_code: str) -> Optional[Dict[str, Any]]:
            try:
                return _fetch_order_detail_with_retry(
                    client=client,
                    order_id=order_id,
                    order_code=order_code,
                    retries=retries,
                    retry_sleep=retry_sleep,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"detail {order_code or order_id}: {exc}")
                return None

        status_hydration_stats = _hydrate_missing_status_change_dates(
            orders=dedup_orders,
            fetch_order_detail=_detail_fetcher,
            max_workers=detail_workers,
            probe_limit=25,
        )

    selected_orders = [o for o in dedup_orders if _order_matches_date_mode(o, date_mode, since, until)]

    missing_status_change_completed = 0
    if require_status_change_date_for_completed:
        for order in selected_orders:
            attrs = order.get("attributes", {}) or {}
            status = str(attrs.get("status") or "").upper()
            if status == COMPLETED_STATUS and attrs.get("statusChangeDate") in (None, ""):
                missing_status_change_completed += 1
                if missing_status_change_completed <= 50:
                    code = attrs.get("code") or order.get("id") or ""
                    errors.append(f"missing statusChangeDate for COMPLETED order {code}")

    flattened = [_flatten_order(o, store_code=store_code) for o in dedup_orders]
    df_flat = pd.DataFrame(flattened)
    df_flat.to_csv(store_dir / "archive_orders_flat.csv", index=False, encoding="utf-8")

    entry_failures = 0
    rows_export: List[Dict[str, Any]] = []
    raw_entries_lines: List[Dict[str, Any]] = []
    entries_by_key: Dict[str, List[Dict[str, Any]]] = {}

    if fetch_entries and selected_orders:
        # Masterproduct lookups add an extra API call per line-item and are kept
        # sequential for reliability. Fast path uses parallel entry fetching only.
        if fetch_masterproduct:
            for i, order in enumerate(selected_orders, start=1):
                attrs = order.get("attributes", {}) or {}
                order_id = str(order.get("id") or "")
                order_code = str(attrs.get("code") or "")
                key = str(order.get("id") or f"CODE::{order_code}")
                try:
                    entries = _fetch_entries_with_retry(
                        client=client,
                        order_id=order_id,
                        order_code=order_code,
                        retries=retries,
                        retry_sleep=retry_sleep,
                    )
                    entries_by_key[key] = entries
                    raw_entries_lines.append(
                        {
                            "store_code": store_code,
                            "order_id": order_id,
                            "order_code": order_code,
                            "entries": entries,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    entry_failures += 1
                    errors.append(f"entries {order_code or order_id}: {exc}")
                if i % 500 == 0:
                    print(
                        f"[{store_code}] entries progress {i}/{len(selected_orders)} "
                        f"(failures={entry_failures})"
                    )
        else:
            thread_local = threading.local()

            def _thread_client() -> KaspiAPIClient:
                c = getattr(thread_local, "client", None)
                if c is None:
                    c = KaspiAPIClient(store_code=store_code)
                    thread_local.client = c
                return c

            def _fetch_one(order: Dict[str, Any]) -> Tuple[str, str, str, List[Dict[str, Any]], Optional[str]]:
                attrs = order.get("attributes", {}) or {}
                order_id = str(order.get("id") or "")
                order_code = str(attrs.get("code") or "")
                key = str(order.get("id") or f"CODE::{order_code}")
                try:
                    entries = _fetch_entries_with_retry(
                        client=_thread_client(),
                        order_id=order_id,
                        order_code=order_code,
                        retries=retries,
                        retry_sleep=retry_sleep,
                    )
                    return key, order_id, order_code, entries, None
                except Exception as exc:  # noqa: BLE001
                    return key, order_id, order_code, [], str(exc)

            max_workers = max(1, int(entry_workers))
            with ThreadPoolExecutor(max_workers=max_workers) as entry_pool:
                fut_map = {entry_pool.submit(_fetch_one, order): order for order in selected_orders}
                processed = 0
                for fut in as_completed(fut_map):
                    key, order_id, order_code, entries, err = fut.result()
                    processed += 1
                    if err:
                        entry_failures += 1
                        errors.append(f"entries {order_code or order_id}: {err}")
                    else:
                        entries_by_key[key] = entries
                        raw_entries_lines.append(
                            {
                                "store_code": store_code,
                                "order_id": order_id,
                                "order_code": order_code,
                                "entries": entries,
                            }
                        )
                    if processed % 500 == 0:
                        print(
                            f"[{store_code}] entries progress {processed}/{len(selected_orders)} "
                            f"(failures={entry_failures}, workers={max_workers})"
                        )

        _write_jsonl(store_dir / "archive_order_entries_raw.jsonl", raw_entries_lines)

    for i, order in enumerate(selected_orders, start=1):
        attrs = order.get("attributes", {}) or {}
        order_code = str(attrs.get("code") or "")
        key = str(order.get("id") or f"CODE::{order_code}")
        entries = entries_by_key.get(key, []) if fetch_entries else []

        rows_export.extend(
            order_to_rows(
                order=order,
                entries=entries,
                store_code=store_code,
                client=client if (fetch_entries and fetch_masterproduct) else None,
            )
        )

        if i % 1000 == 0:
            print(f"[{store_code}] row build progress {i}/{len(selected_orders)}")

    # Ensure stable columns matching existing ArchiveOrders-style schema
    df_rows = pd.DataFrame(rows_export)
    for col in EXCEL_COLUMNS:
        if col not in df_rows.columns:
            df_rows[col] = ""
    df_rows = df_rows[EXCEL_COLUMNS]

    csv_name = f"ArchiveOrders_{store_code}.csv"
    xlsx_name = f"ArchiveOrders_{store_code}.xlsx"
    df_rows.to_csv(store_dir / csv_name, index=False, encoding="utf-8")
    df_rows.to_excel(store_dir / xlsx_name, index=False, engine="openpyxl")

    # Daily summary by status/date for quick checks
    date_col = "Дата изменения статуса"
    if date_col not in df_rows.columns:
        date_col = "Дата поступления заказа"
    summary = (
        df_rows.assign(_date=df_rows[date_col].astype(str).fillna(""))
        .groupby(["_date", "Статус"], dropna=False)
        .agg(rows=("№ заказа", "count"), gross_kzt=("Сумма", "sum"))
        .reset_index()
        .rename(columns={"_date": "date"})
        .sort_values(["date", "rows"], ascending=[True, False])
    )
    summary.to_csv(store_dir / "daily_status_summary.csv", index=False, encoding="utf-8")

    success = not errors
    windows_ok = sum(1 for w in windows_rows if w.get("status") == "ok")

    integrity_md = [
        f"# Store Integrity Report: {store_code}",
        "",
        f"- Generated: {now_kz_iso()}",
        f"- Date mode: {date_mode}",
        f"- Target period: {since.isoformat()} -> {until.isoformat()}",
        f"- Windows total: {len(windows)}",
        f"- Windows ok: {windows_ok}",
        f"- Raw orders (window sum): {len(raw_orders_lines)}",
        f"- Dedup orders: {len(dedup_orders)}",
        f"- Selected orders ({date_mode} in period): {len(selected_orders)}",
        f"- Export rows: {len(df_rows)}",
        f"- Entry fetch failures: {entry_failures}",
        f"- Status-change hydration attempted: {status_hydration_stats['attempted']}",
        f"- Status-change hydration success: {status_hydration_stats['hydrated']}",
        f"- Status-change hydration skipped after probe: {status_hydration_stats['skipped_after_probe']}",
        f"- Missing statusChangeDate for COMPLETED in selection: {missing_status_change_completed}",
        f"- Success: {success}",
    ]
    if errors:
        integrity_md.append("")
        integrity_md.append("## Errors")
        for err in errors[:200]:
            integrity_md.append(f"- {err}")
    (store_dir / "integrity_report.md").write_text("\n".join(integrity_md), encoding="utf-8")

    return StoreResult(
        store_code=store_code,
        success=success,
        date_mode=date_mode,
        windows_total=len(windows),
        windows_ok=windows_ok,
        orders_raw=len(raw_orders_lines),
        orders_dedup=len(dedup_orders),
        orders_selected=len(selected_orders),
        rows_exported=len(df_rows),
        entry_fetch_failures=entry_failures,
        status_change_missing_completed=missing_status_change_completed,
        status_change_hydration_attempted=status_hydration_stats["attempted"],
        status_change_hydration_success=status_hydration_stats["hydrated"],
        status_change_hydration_skipped_after_probe=status_hydration_stats["skipped_after_probe"],
        output_dir=str(store_dir),
        errors=errors,
    )


def append_journal(journal_path: Path, lines: List[str]) -> None:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line.rstrip("\n") + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Kaspi ARCHIVE history across stores")
    parser.add_argument("--since", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--stores",
        default=",".join(STORE_TOKEN_MAP.keys()),
        help="Comma-separated store codes",
    )
    parser.add_argument("--out-dir", default="", help="Output root directory")
    parser.add_argument(
        "--dotenv-path",
        default=str(PROJECT_ROOT / ".env"),
        help="Optional dotenv file for Kaspi API tokens; values are loaded but never printed",
    )
    parser.add_argument(
        "--copy-to",
        default="",
        help="Mirror output root into this directory (creates subfolder with output basename)",
    )
    parser.add_argument("--max-workers", type=int, default=2, help="Store-level parallel workers")
    parser.add_argument("--retries", type=int, default=3, help="Retries per API call block")
    parser.add_argument("--retry-sleep", type=float, default=0.6, help="Base retry backoff seconds")
    parser.add_argument("--entry-workers", type=int, default=8, help="Parallel workers per store for entries fetch")
    parser.add_argument(
        "--fetch-entries",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fetch order entries (line items) for each archive order",
    )
    parser.add_argument(
        "--fetch-masterproduct",
        action="store_true",
        help="Fetch masterproduct names (slower; many extra API calls)",
    )
    parser.add_argument(
        "--date-mode",
        choices=DATE_MODE_CHOICES,
        default=DATE_MODE_STATUS_CHANGE,
        help="Date cutoff mode for exported rows.",
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=8,
        help="Parallel workers for order-detail hydration when statusChangeDate is missing",
    )
    parser.add_argument(
        "--hydrate-missing-status-change-date",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Hydrate missing statusChangeDate from order details in statusChangeDate mode",
    )
    parser.add_argument(
        "--require-status-change-date-for-completed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail strict runs when COMPLETED orders in selection have missing statusChangeDate",
    )
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail closed on any store/window/entries failure",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan windows only")
    args = parser.parse_args()

    since = parse_date(args.since)
    until = parse_date(args.until)
    stores = [s.strip().upper() for s in args.stores.split(",") if s.strip()]
    dotenv_path = Path(str(args.dotenv_path)).expanduser()
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    invalid = [s for s in stores if s not in STORE_TOKEN_MAP]
    if invalid:
        print(f"ERROR: invalid store codes: {invalid}")
        return 2

    windows = date_windows(since, until, WINDOW_DAYS)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = PROJECT_ROOT / "exports" / f"kaspi_archive_history_{since.isoformat()}_to_{until.isoformat()}_{timestamp}"
    out_root = Path(args.out_dir).expanduser() if args.out_dir else default_out

    print("=" * 80)
    print("Kaspi ARCHIVE History Export")
    print("=" * 80)
    print(f"Generated: {now_kz_iso()}")
    print(f"Range: {since} -> {until}")
    print(f"Stores: {stores}")
    print(f"Windows: {len(windows)} x {WINDOW_DAYS}d(max)")
    print(f"Out root: {out_root}")
    print(f"Date mode: {args.date_mode}")
    print(f"Fetch entries: {args.fetch_entries}")
    print(f"Hydrate missing statusChangeDate: {args.hydrate_missing_status_change_date}")
    print(f"Require statusChangeDate for completed: {args.require_status_change_date_for_completed}")
    print(f"Strict mode: {args.strict}")

    if args.dry_run:
        print("\nDry-run window plan:")
        for idx, (ws, we) in enumerate(windows, start=1):
            print(f"  {idx:03d}: {ws} -> {we} ({(we - ws).days + 1}d)")
        return 0

    out_root.mkdir(parents=True, exist_ok=False)

    manifest: Dict[str, Any] = {
        "generated_at": now_kz_iso(),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "window_days": WINDOW_DAYS,
        "stores": stores,
        "fetch_entries": bool(args.fetch_entries),
        "fetch_masterproduct": bool(args.fetch_masterproduct),
        "date_mode": args.date_mode,
        "hydrate_missing_status_change_date": bool(args.hydrate_missing_status_change_date),
        "require_status_change_date_for_completed": bool(args.require_status_change_date_for_completed),
        "detail_workers": int(max(1, args.detail_workers)),
        "strict": bool(args.strict),
        "max_workers": int(max(1, args.max_workers)),
        "windows": [
            {
                "index": i + 1,
                "since": ws.isoformat(),
                "until": we.isoformat(),
                "days": (we - ws).days + 1,
            }
            for i, (ws, we) in enumerate(windows)
        ],
        "results": [],
    }

    _build_methods_report(out_root / "KASPI_ARCHIVE_EXTRACTION_METHODS_REPORT.md")

    journal_path = PROJECT_ROOT / "claude" / "journal.md"
    append_journal(
        journal_path,
        [
            f"[{now_kz_iso()}] START kaspi archive export: since={since} until={until} stores={','.join(stores)} out={out_root}",
            f"[{now_kz_iso()}] CONFIG strict={args.strict} fetch_entries={args.fetch_entries} fetch_masterproduct={args.fetch_masterproduct} max_workers={args.max_workers} entry_workers={args.entry_workers} detail_workers={args.detail_workers} date_mode={args.date_mode}",
        ],
    )

    results: List[StoreResult] = []

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as pool:
        future_map = {
            pool.submit(
                process_store,
                store,
                windows,
                since,
                until,
                out_root,
                args.fetch_entries,
                args.entry_workers,
                args.detail_workers,
                args.fetch_masterproduct,
                args.date_mode,
                args.hydrate_missing_status_change_date,
                args.require_status_change_date_for_completed,
                args.retries,
                args.retry_sleep,
                args.strict,
            ): store
            for store in stores
        }

        for future in as_completed(future_map):
            store = future_map[future]
            try:
                res = future.result()
            except Exception as exc:  # noqa: BLE001
                res = StoreResult(
                    store_code=store,
                    success=False,
                    date_mode=args.date_mode,
                    windows_total=len(windows),
                    windows_ok=0,
                    orders_raw=0,
                    orders_dedup=0,
                    orders_selected=0,
                    rows_exported=0,
                    entry_fetch_failures=0,
                    status_change_missing_completed=0,
                    status_change_hydration_attempted=0,
                    status_change_hydration_success=0,
                    status_change_hydration_skipped_after_probe=0,
                    output_dir=str(out_root / f"store_{store}"),
                    errors=[f"store worker crash: {exc}"],
                )
            results.append(res)
            print(
                f"[{res.store_code}] success={res.success} windows={res.windows_ok}/{res.windows_total} "
                f"orders={res.orders_dedup} selected={res.orders_selected} rows={res.rows_exported} "
                f"entry_failures={res.entry_fetch_failures} hydrated={res.status_change_hydration_success}/{res.status_change_hydration_attempted}"
            )

    results = sorted(results, key=lambda r: stores.index(r.store_code))

    manifest["results"] = [
        {
            "store_code": r.store_code,
            "success": r.success,
            "date_mode": r.date_mode,
            "windows_total": r.windows_total,
            "windows_ok": r.windows_ok,
            "orders_raw": r.orders_raw,
            "orders_dedup": r.orders_dedup,
            "orders_selected": r.orders_selected,
            "rows_exported": r.rows_exported,
            "entry_fetch_failures": r.entry_fetch_failures,
            "status_change_missing_completed": r.status_change_missing_completed,
            "status_change_hydration_attempted": r.status_change_hydration_attempted,
            "status_change_hydration_success": r.status_change_hydration_success,
            "status_change_hydration_skipped_after_probe": r.status_change_hydration_skipped_after_probe,
            "output_dir": r.output_dir,
            "errors": r.errors,
        }
        for r in results
    ]

    (out_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Combined rows artifact
    combined_frames: List[pd.DataFrame] = []
    for r in results:
        csv_path = Path(r.output_dir) / f"ArchiveOrders_{r.store_code}.csv"
        if csv_path.exists():
            combined_frames.append(pd.read_csv(csv_path, dtype=str, keep_default_na=False))

    if combined_frames:
        df_all = pd.concat(combined_frames, ignore_index=True)
        df_all.to_csv(out_root / "ArchiveOrders_ALL_STORES.csv", index=False, encoding="utf-8")
        df_all.to_excel(out_root / "ArchiveOrders_ALL_STORES.xlsx", index=False, engine="openpyxl")

    total_errors = sum(1 for r in results if not r.success)
    summary_lines = [
        "# Kaspi Archive Export Run Summary",
        "",
        f"- Generated: {now_kz_iso()}",
        f"- Range: `{since}` -> `{until}`",
        f"- Stores requested: `{', '.join(stores)}`",
        f"- Strict mode: `{args.strict}`",
        f"- Date mode: `{args.date_mode}`",
        f"- Fetch entries: `{args.fetch_entries}`",
        f"- Hydrate missing statusChangeDate: `{args.hydrate_missing_status_change_date}`",
        f"- Output root: `{out_root}`",
        "",
        "## Store Results",
        "",
        "| Store | Success | Windows OK/Total | Dedup Orders | Selected Orders | Export Rows | Hydrated/Attempted | Missing COMPLETED statusDate | Entry Failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        summary_lines.append(
            f"| {r.store_code} | {'YES' if r.success else 'NO'} | {r.windows_ok}/{r.windows_total} "
            f"| {r.orders_dedup} | {r.orders_selected} | {r.rows_exported} "
            f"| {r.status_change_hydration_success}/{r.status_change_hydration_attempted} "
            f"| {r.status_change_missing_completed} | {r.entry_fetch_failures} |"
        )

    if total_errors:
        summary_lines.extend(["", "## Errors"])
        for r in results:
            for err in r.errors[:100]:
                summary_lines.append(f"- [{r.store_code}] {err}")

    (out_root / "run_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    copied_to = ""
    if args.copy_to:
        copy_root = Path(args.copy_to).expanduser()
        copy_root.mkdir(parents=True, exist_ok=True)
        dst = copy_root / out_root.name
        if dst.exists():
            raise RuntimeError(f"copy destination already exists: {dst}")
        shutil.copytree(out_root, dst)
        copied_to = str(dst)
        print(f"Copied output pack to: {dst}")

    append_journal(
        journal_path,
        [
            f"[{now_kz_iso()}] DONE kaspi archive export: out={out_root} copied_to={copied_to or '-'}",
            f"[{now_kz_iso()}] RESULTS stores={len(results)} failed={total_errors} total_rows={sum(r.rows_exported for r in results)} total_orders={sum(r.orders_dedup for r in results)}",
        ],
    )

    if total_errors and args.strict:
        print("\nERROR: strict mode detected store/window failures. See run_summary.md")
        return 1

    print("\nDONE")
    print(f"Output root: {out_root}")
    if copied_to:
        print(f"Copied to:   {copied_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
