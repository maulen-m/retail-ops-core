"""Canonical parser for DIM_SKU_light workbook sheets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


VALID_SKU_PREFIXES = ("CL_", "ELS_", "WB_")


def _norm_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    for ch in (" ", "_", "-", "/", "\\", "(", ")", "\t", "\n", "\r"):
        text = text.replace(ch, "")
    return text


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    normalized = {_norm_header(col): col for col in columns}
    for alias in aliases:
        key = _norm_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _to_bool(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    if text in {"1", "true", "yes", "y", "active"}:
        return True
    try:
        return float(text) > 0
    except ValueError:
        return False


def _is_valid_sku_key(value: str) -> bool:
    key = value.strip().upper()
    return any(key.startswith(prefix) for prefix in VALID_SKU_PREFIXES)


def _split_markdown_table_row(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text.startswith("|") or "|" not in text[1:]:
        return []
    cells = [cell.strip() for cell in text.strip("|").split("|")]
    if not cells or all(not cell or set(cell) <= {"-", ":", " "} for cell in cells):
        return []
    return cells


def _is_dim_sku_header(cells: list[str]) -> bool:
    normalized = {_norm_header(v) for v in cells}
    return "skukey" in normalized and "cny" in normalized and ("wtkg" in normalized or "weightkg" in normalized)


def _find_header_row(raw: pd.DataFrame) -> int:
    for idx in range(len(raw)):
        row_vals = [
            str(v).strip()
            for v in raw.iloc[idx].tolist()
            if v is not None and str(v).strip()
        ]
        if _is_dim_sku_header(row_vals):
            return idx
    raise RuntimeError("Failed to locate DIM_SKU_light header row")


def _extract_markdown_table(raw: pd.DataFrame) -> tuple[list[str], pd.DataFrame, int]:
    headers: list[str] | None = None
    header_idx = -1
    rows: list[tuple[int, list[str]]] = []

    for idx in range(len(raw)):
        row_cells: list[str] = []
        for value in raw.iloc[idx].tolist():
            cells = _split_markdown_table_row(value)
            if cells:
                row_cells = cells
                break

        if row_cells and _is_dim_sku_header(row_cells):
            headers = row_cells
            header_idx = idx
            rows = []
            continue
        if headers is None:
            continue
        if row_cells:
            if len(row_cells) == len(headers):
                rows.append((idx, row_cells))
            continue
        if rows:
            break

    if headers is None:
        raise RuntimeError("Failed to locate DIM_SKU_light header row")

    data = pd.DataFrame([cells for _, cells in rows], columns=headers)
    data["__source_row_index"] = [int(idx) + 1 for idx, _ in rows]
    return headers, data, header_idx


def parse_dim_sku_light(
    xlsx_path: Path,
    *,
    sheet_name: str = "DIM_SKU_light_v7",
    min_cny: float = 1.0,
    min_weight_kg: float = 0.1,
    max_weight_kg: float = 20.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, dtype=object)
    if raw.empty:
        return {}, {
            "source_xlsx": str(xlsx_path),
            "sheet_name": sheet_name,
            "header_row_index": 0,
            "rows_scanned": 0,
            "rows_valid": 0,
            "filtered_helper_rows": 0,
            "filtered_invalid_sku_rows": 0,
            "duplicate_sku_keys": 0,
            "selected_rows": 0,
            "source_format": "empty",
        }

    source_format = "tabular"
    try:
        header_idx = _find_header_row(raw)
        cols = [str(v).strip() if v is not None else f"col_{i}" for i, v in enumerate(raw.iloc[header_idx].tolist())]
        data = raw.iloc[header_idx + 1 :].copy()
        data.columns = cols
        data["__source_row_index"] = [int(idx) + 1 for idx in data.index]
    except RuntimeError as exc:
        if "Failed to locate DIM_SKU_light header row" not in str(exc):
            raise
        cols, data, header_idx = _extract_markdown_table(raw)
        source_format = "markdown_pipe_table"

    sku_col = _find_column(cols, ["SKU_key", "sku key", "sku"])
    cny_col = _find_column(cols, ["CNY", "base_cost_cny", "BaseCost_CNY"])
    weight_col = _find_column(cols, ["Wt (kg)", "Weight_kg", "weight_kg", "Weight"])
    avg_col = _find_column(cols, ["AvgPrc", "Avg Price", "avg_price"])
    active_col = _find_column(cols, ["Active", "Is_Active", "active_flag"])
    if not sku_col or not cny_col or not weight_col:
        raise RuntimeError("DIM_SKU_light missing required columns: SKU_key, CNY, Wt (kg)")

    candidates: dict[str, list[dict[str, Any]]] = {}
    filtered_helper_rows = 0
    filtered_invalid_sku_rows = 0
    rows_valid = 0
    for idx, row in data.iterrows():
        source_row_index = int(row.get("__source_row_index") or int(idx) + 1)
        sku_key = str(row.get(sku_col) or "").strip()
        if not sku_key or sku_key.upper() == "SKU_KEY":
            continue
        if not _is_valid_sku_key(sku_key):
            filtered_invalid_sku_rows += 1
            continue

        base_cost_cny = _to_float(row.get(cny_col))
        weight_kg = _to_float(row.get(weight_col))
        avg_price_kzt = _to_float(row.get(avg_col)) or 0.0
        if (
            base_cost_cny is None
            or weight_kg is None
            or base_cost_cny < float(min_cny)
            or weight_kg < float(min_weight_kg)
            or weight_kg > float(max_weight_kg)
        ):
            filtered_helper_rows += 1
            continue

        rows_valid += 1
        active_flag = 1 if _to_bool(row.get(active_col)) else 0 if active_col else 1
        entry = {
            "sku_key": sku_key,
            "base_cost_cny": float(base_cost_cny),
            "weight_kg": float(weight_kg),
            "avg_price_kzt": float(avg_price_kzt),
            "active_flag": int(active_flag),
            "source_row_index": source_row_index,
        }
        candidates.setdefault(sku_key, []).append(entry)

    out: dict[str, dict[str, Any]] = {}
    for sku_key, rows in candidates.items():
        best = max(
            rows,
            key=lambda r: (
                int(r["active_flag"]),
                1 if float(r["avg_price_kzt"]) > 0 else 0,
                float(r["base_cost_cny"]),
                float(r["weight_kg"]),
                -int(r["source_row_index"]),
            ),
        )
        out[sku_key] = best

    duplicate_sku_keys = sum(1 for rows in candidates.values() if len(rows) > 1)
    diagnostics = {
        "source_xlsx": str(xlsx_path),
        "sheet_name": sheet_name,
        "header_row_index": header_idx + 1,
        "rows_scanned": int(len(data)),
        "rows_valid": int(rows_valid),
        "filtered_helper_rows": int(filtered_helper_rows),
        "filtered_invalid_sku_rows": int(filtered_invalid_sku_rows),
        "duplicate_sku_keys": int(duplicate_sku_keys),
        "selected_rows": int(len(out)),
        "source_format": source_format,
    }
    return out, diagnostics
