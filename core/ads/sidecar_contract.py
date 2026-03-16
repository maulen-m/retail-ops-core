from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any

DEFAULT_ADS_DB = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/"
    "Kaspi_marketing/db/kaspi_marketing.db"
)


def resolve_ads_db_path(
    *,
    explicit: Path | None = None,
    env_var: str = "AB_ADS_DB_PATH",
    default_path: Path = DEFAULT_ADS_DB,
    require_exists: bool = False,
) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser()
    else:
        raw = os.environ.get(env_var, "").strip()
        path = Path(raw).expanduser() if raw else default_path
    if require_exists and not path.exists():
        raise RuntimeError(
            f"ads source db missing: {path} (set {env_var} or provide --ads-db)"
        )
    return path


def validate_ads_source(
    ads_db_path: Path,
    *,
    max_age_hours: float = 36.0,
    max_future_skew_seconds: float = 120.0,
    now_ts_override: float | None = None,
) -> dict[str, Any]:
    path = Path(ads_db_path).expanduser()
    if not path.exists():
        return {
            "ok": False,
            "reason": "missing",
            "path": str(path),
        }

    stat = path.stat()
    now = float(now_ts_override) if now_ts_override is not None else datetime.now(timezone.utc).timestamp()
    mtime = float(stat.st_mtime)
    skew = mtime - now
    if skew > max_future_skew_seconds:
        return {
            "ok": False,
            "reason": "future_mtime",
            "path": str(path),
            "future_skew_seconds": round(skew, 2),
        }

    age_hours = max(0.0, (now - mtime) / 3600.0)
    refresh_run = _latest_successful_refresh_run(path)
    refresh_age_hours = None
    if refresh_run is not None:
        refresh_finished_ts = float(refresh_run["finished_at_ts"])
        refresh_skew = refresh_finished_ts - now
        if refresh_skew <= max_future_skew_seconds:
            refresh_age_hours = max(0.0, (now - refresh_finished_ts) / 3600.0)
            if refresh_age_hours <= max_age_hours:
                return {
                    "ok": True,
                    "reason": "ok_refresh_run",
                    "path": str(path),
                    "age_hours": round(refresh_age_hours, 2),
                    "size_bytes": int(stat.st_size),
                    "freshness_source": "ads_source_refresh_runs.finished_at",
                    "refresh_run": {
                        "run_id": str(refresh_run["run_id"]),
                        "merchant_id": str(refresh_run["merchant_id"]),
                        "store_code": str(refresh_run["store_code"]),
                        "date_start": str(refresh_run["date_start"]),
                        "date_end": str(refresh_run["date_end"]),
                        "finished_at": str(refresh_run["finished_at"]),
                        "campaign_days_total": int(refresh_run["campaign_days_total"]),
                        "product_rows_total": int(refresh_run["product_rows_total"]),
                    },
                }
    if age_hours > max_age_hours:
        return {
            "ok": False,
            "reason": "stale",
            "path": str(path),
            "age_hours": round(age_hours, 2),
            "max_age_hours": float(max_age_hours),
            "freshness_source": "file_mtime",
            "latest_refresh_run_age_hours": (
                round(refresh_age_hours, 2) if refresh_age_hours is not None else None
            ),
        }

    if int(stat.st_size) <= 0:
        return {
            "ok": False,
            "reason": "empty",
            "path": str(path),
        }

    return {
        "ok": True,
        "reason": "ok",
        "path": str(path),
        "age_hours": round(age_hours, 2),
        "size_bytes": int(stat.st_size),
        "freshness_source": "file_mtime",
    }


def _latest_successful_refresh_run(ads_db_path: Path) -> dict[str, Any] | None:
    query = """
        SELECT
            run_id,
            merchant_id,
            store_code,
            date_start,
            date_end,
            finished_at,
            campaign_days_total,
            product_rows_total,
            strftime('%s', finished_at) AS finished_at_ts
        FROM ads_source_refresh_runs
        WHERE status = 'SUCCESS'
        ORDER BY datetime(finished_at) DESC
        LIMIT 1
    """
    try:
        with sqlite3.connect(ads_db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row["finished_at_ts"] is None:
        return None
    return dict(row)
