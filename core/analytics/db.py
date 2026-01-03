"""DB path resolution for analytics API."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.paths import data_path
from core.db import DEFAULT_DB_PATH


def resolve_db_path(explicit: Optional[Path] = None) -> Path:
    """
    Resolve DB path with DB_PATH and DATA_DIR/AB_DATA_DIR conventions.

    Priority:
      1) explicit path argument
      2) DB_PATH env var
      3) DATA_DIR/AB_DATA_DIR + db/app.db if it exists
      4) repo default db/app.db
    """
    if explicit:
        return Path(explicit).expanduser()

    env_path = os.environ.get("DB_PATH")
    if env_path:
        return Path(env_path).expanduser()

    data_db = data_path("db", "app.db")
    if data_db.exists():
        return data_db

    return DEFAULT_DB_PATH
