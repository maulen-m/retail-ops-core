from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

import pandas as pd

from core.utils.kaspi_dates import parse_kaspi_date

ORDER_ID_COLUMNS = ("OrderID", "№ заказа")
DATE_COLUMNS = ("Date",)
PLANNED_DATE_COLUMNS = ("PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру")
LINE_KEY_COLUMNS = (
    "KASPI_OFFER_NAME",
    "Название товара в Kaspi Магазине",
    "SKU_ID",
    "SKU_ID_KSP",
    "SKU_key",
    "Артикул",
    "Kaspi_name_core",
    "Quantity",
)


def _coerce_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _clean_order_id(value: Any) -> str:
    raw = _coerce_text(value)
    if raw.endswith(".0"):
        raw = raw[:-2]
    return raw if raw.isdigit() else ""


def _parse_batch_date(value: Any, fallback_target_date: date) -> date:
    parsed = parse_kaspi_date(value)
    return parsed or fallback_target_date


def _parse_planned_date(value: Any) -> Optional[date]:
    return parse_kaspi_date(value)


def _first_present(columns: Iterable[str], df: pd.DataFrame) -> Optional[str]:
    for name in columns:
        if name in df.columns:
            return name
    return None


def _is_blank_text(value: Any) -> bool:
    normalized = _coerce_text(value).lower()
    return normalized in ("", "nan", "none")


def _line_signature(row: pd.Series) -> str:
    parts = []
    for col in LINE_KEY_COLUMNS:
        if col not in row.index:
            continue
        value = _coerce_text(row.get(col))
        if value:
            parts.append(f"{col}={value}")
    return "|".join(parts) if parts else "__DEFAULT_SINGLE_LINE__"


def _planned_date_from_row(row: pd.Series) -> Optional[date]:
    for col in PLANNED_DATE_COLUMNS:
        if col not in row.index:
            continue
        parsed = _parse_planned_date(row.get(col))
        if parsed:
            return parsed
    return None


def select_operational_crm_rows(
    df: pd.DataFrame,
    target_date: date,
    order_id_filter: Optional[set[str]] = None,
    allow_historical_fallback: bool = True,
    backfill_overdue_my_size_from_history: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Reduce CRM rows to the operational batch view for a target date.

    Rules:
    - If an order has rows on target_date, keep only target_date rows.
    - Otherwise keep rows from the latest Date <= target_date.
    - Within the chosen operational date slice, drop duplicate carry-forward
      copies of the same logical line, keeping the latest row.
    - Optionally backfill blank current-day MY_SIZE values for overdue rows from
      the latest prior CRM row of the same logical line.
    """
    stats = {
        "rows_in": int(len(df.index)),
        "rows_after_order_filter": 0,
        "rows_after_date_filter": 0,
        "orders_selected": 0,
        "selected_today_orders": 0,
        "selected_fallback_orders": 0,
        "orders_without_today_row_dropped": 0,
        "historical_rows_dropped": 0,
        "same_day_line_duplicates_dropped": 0,
        "overdue_my_size_backfilled_rows": 0,
    }

    if df.empty:
        return df.copy(), stats

    work = df.copy()
    work["_row_ordinal"] = range(len(work.index))

    order_col = _first_present(ORDER_ID_COLUMNS, work)
    if not order_col:
        return work.iloc[0:0].copy(), stats

    date_col = _first_present(DATE_COLUMNS, work)

    work["_order_id"] = work[order_col].map(_clean_order_id)
    work = work[work["_order_id"] != ""].copy()

    if order_id_filter is not None:
        work = work[work["_order_id"].isin(order_id_filter)].copy()
    stats["rows_after_order_filter"] = int(len(work.index))
    if work.empty:
        return work, stats

    if date_col:
        work["_batch_date"] = work[date_col].map(lambda value: _parse_batch_date(value, target_date))
    else:
        work["_batch_date"] = target_date
    work["_planned_date"] = work.apply(_planned_date_from_row, axis=1)
    work["_line_key"] = work.apply(_line_signature, axis=1)
    work["_my_size_backfilled"] = False

    work = work[work["_batch_date"] <= target_date].copy()
    stats["rows_after_date_filter"] = int(len(work.index))
    if work.empty:
        return work, stats

    selected_dates: dict[str, date] = {}
    selected_today_orders = 0
    selected_fallback_orders = 0
    for order_id, group in work.groupby("_order_id"):
        dates = set(group["_batch_date"].tolist())
        if target_date in dates:
            selected_dates[order_id] = target_date
            selected_today_orders += 1
        elif allow_historical_fallback:
            selected_dates[order_id] = max(dates)
            selected_fallback_orders += 1
        else:
            stats["orders_without_today_row_dropped"] += 1

    stats["orders_selected"] = len(selected_dates)
    stats["selected_today_orders"] = selected_today_orders
    stats["selected_fallback_orders"] = selected_fallback_orders

    work["_selected_batch_date"] = work["_order_id"].map(selected_dates)
    history_source = work.copy()
    before_history_drop = len(work.index)
    work = work[work["_batch_date"] == work["_selected_batch_date"]].copy()
    stats["historical_rows_dropped"] = before_history_drop - len(work.index)

    if backfill_overdue_my_size_from_history and "MY_SIZE" in work.columns:
        prior_rows = history_source[
            (history_source["_batch_date"] < target_date)
            & (~history_source["MY_SIZE"].map(_is_blank_text))
        ].copy()
        if not prior_rows.empty:
            prior_rows = prior_rows.sort_values(
                ["_order_id", "_line_key", "_batch_date", "_row_ordinal"]
            )
            latest_sizes: dict[tuple[str, str], str] = {}
            for _, prior_row in prior_rows.iterrows():
                latest_sizes[(prior_row["_order_id"], prior_row["_line_key"])] = _coerce_text(
                    prior_row.get("MY_SIZE")
                )

            for idx, row in work.iterrows():
                if row.get("_batch_date") != target_date:
                    continue
                if not _is_blank_text(row.get("MY_SIZE")):
                    continue
                planned_date = row.get("_planned_date")
                if not planned_date or planned_date >= target_date:
                    continue
                recovered_size = latest_sizes.get((row["_order_id"], row["_line_key"]), "")
                if not recovered_size:
                    continue
                work.at[idx, "MY_SIZE"] = recovered_size
                work.at[idx, "_my_size_backfilled"] = True
                stats["overdue_my_size_backfilled_rows"] += 1

    before_line_dedupe = len(work.index)
    work = work.sort_values(["_order_id", "_batch_date", "_row_ordinal"]).drop_duplicates(
        subset=["_order_id", "_line_key"],
        keep="last",
    )
    stats["same_day_line_duplicates_dropped"] = before_line_dedupe - len(work.index)

    work = work.sort_values(["_order_id", "_row_ordinal"]).reset_index(drop=True)
    return work, stats


def select_operational_crm_rows_with_targeted_fallback(
    df: pd.DataFrame,
    target_date: date,
    order_id_filter: Optional[set[str]] = None,
    historical_fallback_order_ids: Optional[set[str]] = None,
    backfill_overdue_my_size_from_history: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Reduce CRM rows to the operational batch view with narrow historical fallback.

    This keeps the default fail-closed behavior for the workbook's current-day
    operational slice, then selectively re-adds only explicitly approved order
    IDs from their latest historical rows. It avoids broad historical fallback
    that can pull in large stale backlogs.
    """
    primary, stats = select_operational_crm_rows(
        df,
        target_date=target_date,
        order_id_filter=order_id_filter,
        allow_historical_fallback=False,
        backfill_overdue_my_size_from_history=backfill_overdue_my_size_from_history,
    )

    requested_fallback_ids = {str(order_id).strip() for order_id in historical_fallback_order_ids or set() if str(order_id).strip()}
    if order_id_filter is not None:
        requested_fallback_ids &= {str(order_id).strip() for order_id in order_id_filter if str(order_id).strip()}

    primary_selected_ids = set(primary["_order_id"].tolist()) if "_order_id" in primary.columns else set()
    fallback_ids = requested_fallback_ids - primary_selected_ids

    stats["targeted_fallback_orders_requested"] = len(requested_fallback_ids)
    stats["targeted_fallback_orders_selected"] = 0
    stats["targeted_fallback_rows_added"] = 0

    if not fallback_ids:
        return primary, stats

    fallback, fallback_stats = select_operational_crm_rows(
        df,
        target_date=target_date,
        order_id_filter=fallback_ids,
        allow_historical_fallback=True,
        backfill_overdue_my_size_from_history=backfill_overdue_my_size_from_history,
    )
    if fallback.empty:
        return primary, stats

    combined = pd.concat([primary, fallback], ignore_index=True, sort=False)
    if "_order_id" in combined.columns and "_line_key" in combined.columns:
        combined = combined.sort_values(["_order_id", "_batch_date", "_row_ordinal"]).drop_duplicates(
            subset=["_order_id", "_line_key"],
            keep="last",
        )
    combined = combined.sort_values(["_order_id", "_row_ordinal"]).reset_index(drop=True)

    stats["orders_selected"] += int(fallback_stats.get("orders_selected", 0))
    stats["selected_fallback_orders"] += int(fallback_stats.get("orders_selected", 0))
    stats["targeted_fallback_orders_selected"] = int(fallback_stats.get("orders_selected", 0))
    stats["targeted_fallback_rows_added"] = int(len(fallback.index))
    return combined, stats
