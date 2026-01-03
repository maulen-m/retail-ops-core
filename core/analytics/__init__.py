"""Analytics helpers for the internal SaaS dashboard."""

from .db import resolve_db_path
from .views import ensure_sales_views
from .queries import (
    get_filters_options,
    get_last30_kpis,
    get_timeseries_monthly,
    get_calendar_daily,
    get_compare_summary,
)

__all__ = [
    "resolve_db_path",
    "ensure_sales_views",
    "get_filters_options",
    "get_last30_kpis",
    "get_timeseries_monthly",
    "get_calendar_daily",
    "get_compare_summary",
]
