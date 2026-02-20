"""Runtime SQL guard that blocks raw sales-table reads in strict paths."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

DEFAULT_DISALLOWED_SALES_TABLES: tuple[str, ...] = (
    "fact_sales",
    "sales_fact_v2",
    "fact_sales_daily",
    "fact_sales_daily_size",
)

DEFAULT_ALLOWED_PUBLISHED_VIEWS: tuple[str, ...] = (
    "view_sales_line_truth",
    "view_sales_daily_truth",
)
DEFAULT_ALLOWED_INTERNAL_SOURCES: tuple[str, ...] = (
    "sales_v2",
    "sales_fact",
    "v2_bounds",
    "base_lines",
    "resolved_lines",
    "article_store_map",
    "article_any_map",
)


def _normalize_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def _build_authorizer(
    *,
    disallowed_tables: set[str],
    allowed_sources: set[str],
    allowed_internal_sources: set[str],
):
    def _authorizer(
        action_code: int,
        param1: str | None,
        _param2: str | None,
        _db_name: str | None,
        source_name: str | None,
    ) -> int:
        if action_code != sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK

        table_name = _normalize_name(param1)
        if table_name not in disallowed_tables:
            return sqlite3.SQLITE_OK

        source = _normalize_name(source_name)
        if source in allowed_sources:
            return sqlite3.SQLITE_OK
        if source in allowed_internal_sources:
            return sqlite3.SQLITE_OK

        return sqlite3.SQLITE_DENY

    return _authorizer


def install_sales_truth_query_guard(
    conn: sqlite3.Connection,
    *,
    disallowed_tables: Iterable[str] = DEFAULT_DISALLOWED_SALES_TABLES,
    allowed_sources: Iterable[str] = DEFAULT_ALLOWED_PUBLISHED_VIEWS,
    allowed_internal_sources: Iterable[str] = DEFAULT_ALLOWED_INTERNAL_SOURCES,
) -> None:
    """Install sqlite authorizer that blocks direct reads from raw sales tables."""
    disallowed = {_normalize_name(name) for name in disallowed_tables if str(name).strip()}
    allowed = {_normalize_name(name) for name in allowed_sources if str(name).strip()}
    allowed_internal = {
        _normalize_name(name) for name in allowed_internal_sources if str(name).strip()
    }
    conn.set_authorizer(
        _build_authorizer(
            disallowed_tables=disallowed,
            allowed_sources=allowed,
            allowed_internal_sources=allowed_internal,
        )
    )


def remove_sales_truth_query_guard(conn: sqlite3.Connection) -> None:
    """Remove sqlite authorizer guard from connection."""
    conn.set_authorizer(None)
