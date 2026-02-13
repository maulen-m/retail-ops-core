#!/usr/bin/env python3
"""Shared path and safety helpers for Kaspi ads worktree execution."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Production path must never be used by default in this worktree branch.
PROD_ADS_DB_PATH = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/"
    "Kaspi_marketing/db/kaspi_marketing.db"
)

# Safe default DB used by new ads scripts in worktree mode.
DEFAULT_WORKTREE_ADS_DB_PATH = PROJECT_ROOT / "db" / "kaspi_marketing_ads_wt.db"


def _env_get(env: Mapping[str, str] | Any | None, key: str) -> str | None:
    if env is None:
        return os.environ.get(key)
    if isinstance(env, Mapping):
        value = env.get(key)
        return None if value is None else str(value)
    getter = getattr(env, "get", None)
    if callable(getter):
        value = getter(key)
        return None if value is None else str(value)
    return None


def resolve_ads_db_path(
    *,
    ads_db_arg: Path | str | None,
    env: Mapping[str, str] | Any | None = None,
    default_path: Path | str = DEFAULT_WORKTREE_ADS_DB_PATH,
) -> Path:
    """Resolve ads DB path with precedence: CLI arg > env var > default."""
    candidate: Path
    if ads_db_arg:
        candidate = Path(ads_db_arg)
    else:
        env_value = _env_get(env, "KASPI_MARKETING_DB_PATH")
        if env_value:
            candidate = Path(env_value)
        else:
            candidate = Path(default_path)
    return candidate.expanduser().resolve()


def assert_ads_db_path_safe(
    *,
    ads_db_path: Path,
    prod_ads_db_path: Path = PROD_ADS_DB_PATH,
    env: Mapping[str, str] | Any | None = None,
) -> None:
    """Block production ads DB path unless ALLOW_PROD_ADS_DB=1 is explicitly set."""
    resolved = ads_db_path.expanduser().resolve()
    prod_resolved = prod_ads_db_path.expanduser().resolve()
    if resolved == prod_resolved and _env_get(env, "ALLOW_PROD_ADS_DB") != "1":
        raise RuntimeError(
            "Refusing to use production ads DB path. "
            "Set a separate --ads-db / KASPI_MARKETING_DB_PATH, "
            "or set ALLOW_PROD_ADS_DB=1 to override intentionally."
        )


def copy_ads_db_once(*, source_db: Path, dest_db: Path) -> dict[str, Any]:
    """Copy source DB to destination only when destination is missing/empty."""
    src = source_db.expanduser().resolve()
    dst = dest_db.expanduser().resolve()

    if src == dst:
        return {"copied": False, "reason": "same_path", "source": str(src), "dest": str(dst)}
    if not src.exists():
        return {"copied": False, "reason": "source_missing", "source": str(src), "dest": str(dst)}
    dst_existed = dst.exists()
    if dst_existed:
        try:
            if dst.stat().st_size > 0:
                return {"copied": False, "reason": "dest_exists", "source": str(src), "dest": str(dst)}
        except OSError:
            return {"copied": False, "reason": "dest_exists", "source": str(src), "dest": str(dst)}

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    reason = "dest_empty_replaced" if dst_existed else "copied"
    return {"copied": True, "reason": reason, "source": str(src), "dest": str(dst)}
