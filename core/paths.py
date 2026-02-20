"""
Helpers for resolving data paths with optional external data root.
"""
from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_data_root() -> Path:
    env_path = os.environ.get("AB_DATA_DIR") or os.environ.get("DATA_DIR")
    if env_path:
        return Path(env_path).expanduser()
    return PROJECT_ROOT


def data_path(*parts: str) -> Path:
    return get_data_root().joinpath(*parts)
