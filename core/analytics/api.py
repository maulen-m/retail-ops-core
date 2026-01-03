"""Minimal HTTP handler for analytics endpoints (no external deps)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Optional
from urllib.parse import parse_qs

from core.db import get_connection

from .db import resolve_db_path
from .queries import (
    get_calendar_daily,
    get_compare_summary,
    get_filters_options,
    get_last30_kpis,
    get_timeseries_monthly,
)


def _parse_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_bool(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.lower() in {"1", "true", "yes", "y"}


def _with_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    resolved = resolve_db_path(None if db_path is None else db_path)
    return get_connection(resolved)


def _extract_common_params(query: dict[str, list[str]]) -> dict[str, Any]:
    store_codes = _parse_list(query.get("store", [""])[0])
    sku_keys = _parse_list(query.get("sku", [""])[0])
    include_returns = _parse_bool(query.get("include_returns", [""])[0])
    return {
        "store_codes": store_codes or None,
        "sku_keys": sku_keys or None,
        "include_returns": include_returns,
    }


def handle_request(path: str, query_string: str, db_path: Optional[str] = None) -> tuple[int, dict]:
    """Pure handler for API endpoints. Returns (status_code, payload)."""
    query = parse_qs(query_string or "")
    common = _extract_common_params(query)

    try:
        with _with_db(db_path) as conn:
            if path == "/kpis/last30":
                payload = get_last30_kpis(
                    conn,
                    end_date=query.get("end_date", [None])[0],
                    **common,
                )
                return 200, payload
            if path == "/timeseries/monthly":
                payload = get_timeseries_monthly(
                    conn,
                    end_date=query.get("end_date", [None])[0],
                    **common,
                )
                return 200, payload
            if path == "/calendar/daily":
                payload = get_calendar_daily(
                    conn,
                    start_date=query.get("start_date", [None])[0],
                    end_date=query.get("end_date", [None])[0],
                    **common,
                )
                return 200, payload
            if path == "/compare/summary":
                payload = get_compare_summary(
                    conn,
                    start_date=query.get("start_date", [None])[0],
                    end_date=query.get("end_date", [None])[0],
                    **common,
                )
                return 200, payload
            if path == "/filters/options":
                payload = get_filters_options(conn)
                return 200, payload

        return 404, {"error": "Unknown endpoint"}
    except ValueError as exc:
        return 400, {"error": str(exc)}
    except RuntimeError as exc:
        return 422, {"error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        return 500, {"error": f"Unexpected error: {exc}"}


def json_response(status: int, payload: dict) -> bytes:
    """Serialize payload to JSON bytes."""
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return data
