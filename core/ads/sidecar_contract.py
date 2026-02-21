from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
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
) -> dict[str, Any]:
    path = Path(ads_db_path).expanduser()
    if not path.exists():
        return {
            "ok": False,
            "reason": "missing",
            "path": str(path),
        }

    stat = path.stat()
    now = datetime.now(timezone.utc).timestamp()
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
    if age_hours > max_age_hours:
        return {
            "ok": False,
            "reason": "stale",
            "path": str(path),
            "age_hours": round(age_hours, 2),
            "max_age_hours": float(max_age_hours),
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
    }
