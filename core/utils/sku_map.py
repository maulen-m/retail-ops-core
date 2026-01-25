from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


DEFAULT_SKU_MAP_PATH = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Sku_Map_CRM_3.xlsx"
)

_SKU_MAP_CACHE: dict[str, dict[str, Optional[str]]] | None = None
_OFFER_OVERRIDES = [
    {
        "pattern": "podium_rash-32",
        "sku_key": "CL_OC_MEN_LINE52_BLACK",
        "my_size": None,
    },
]


def _normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = "_".join(text.split())
    return text


def extract_kaspi_name_core(offer_name: str) -> str:
    """
    Extract Kaspi_name_core from offer name.

    Mirrors the documented workflow in Phase_11_Daily_Kaspi_Workflow.md.
    """
    if not offer_name:
        return ""
    clean = str(offer_name)
    clean = re.sub(r"\s+\d+[-/]\d+.*$", "", clean)
    clean = re.sub(r"\s+[SMLX]{1,3}L?\s*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+\d+\s*$", "", clean)
    clean = re.sub(r"[^\w\s-]", "", clean, flags=re.UNICODE)
    clean = "_".join(clean.split()[:3])
    return clean or ""


def _load_sku_map(path: Path) -> dict[str, dict[str, Optional[str]]]:
    if not path.exists():
        return {}

    try:
        xls = pd.ExcelFile(path)
    except Exception:
        return {}

    sheet_name = "Sku_Map_CRM_01" if "Sku_Map_CRM_01" in xls.sheet_names else xls.sheet_names[0]
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return {}

    cols = {str(c).strip().lower(): c for c in df.columns}
    name_col = cols.get("kaspi_name_core")
    sku_key_col = cols.get("sku_key")
    size_col = cols.get("my_size")
    if not name_col or not sku_key_col:
        return {}

    mapping: dict[str, dict[str, Optional[str]]] = {}
    for _, row in df.iterrows():
        name_val = row.get(name_col)
        sku_key = row.get(sku_key_col)
        if pd.isna(name_val) or pd.isna(sku_key):
            continue
        key = _normalize_text(name_val)
        if not key:
            continue
        mapping[key] = {
            "sku_key": str(sku_key).strip(),
            "my_size": (str(row.get(size_col)).strip() if size_col and not pd.isna(row.get(size_col)) else None),
        }
    return mapping


def get_sku_map() -> dict[str, dict[str, Optional[str]]]:
    global _SKU_MAP_CACHE
    if _SKU_MAP_CACHE is not None:
        return _SKU_MAP_CACHE

    env_path = os.environ.get("AB_SKU_MAP_PATH") or os.environ.get("SKU_MAP_CRM_PATH")
    path = Path(env_path) if env_path else DEFAULT_SKU_MAP_PATH
    _SKU_MAP_CACHE = _load_sku_map(path)
    return _SKU_MAP_CACHE


def lookup_sku_from_offer(offer_name: str) -> Tuple[Optional[str], Optional[str]]:
    if not offer_name:
        return None, None
    normalized_offer = _normalize_text(offer_name)
    for override in _OFFER_OVERRIDES:
        pattern = override.get("pattern")
        if pattern and pattern in normalized_offer:
            return override.get("sku_key"), override.get("my_size")
    mapping = get_sku_map()
    if not mapping:
        return None, None
    core = extract_kaspi_name_core(offer_name)
    key = _normalize_text(core)
    entry = mapping.get(key)
    if entry:
        return entry.get("sku_key"), entry.get("my_size")
    return None, None
