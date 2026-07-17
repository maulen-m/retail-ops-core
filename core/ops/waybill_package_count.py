"""Shared deterministic parcel-count rules for Kaspi waybill assembly."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


HEAVY_ITEMS = {
    "Костюм_мужской_Хус",
    "Line51",
    "Принт_5в1_черный",
    "Костюм_Ромбик_ДЕТСКИЙ",
    "Спортивный_3в1_детский_черный",
    "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
    "CL_NEW-CLO2_MEN_SUIT-51_BLACK_GREY",
    "CL_NK_MEN_LINE51_WHITE",
    "CL_OC_MEN_LINE52_BLACK",
}


def is_heavy_product(line: Mapping[str, Any]) -> bool:
    checks = [
        str(line.get("kaspi_name_core") or "").strip(),
        str(line.get("sku_key") or "").strip(),
        str(line.get("sku_id") or "").strip(),
    ]
    for value in checks:
        if not value:
            continue
        if value in HEAVY_ITEMS:
            return True
        if any(value.startswith(heavy) for heavy in HEAVY_ITEMS):
            return True
    return False


def calculate_package_count_from_lines(lines: Iterable[Mapping[str, Any]]) -> int:
    normalized = [dict(line) for line in lines]
    if not normalized:
        return 1
    quantities = [int(line.get("quantity") or 1) for line in normalized]
    if len(normalized) == 1:
        quantity = quantities[0]
        if quantity == 1:
            return 1
        return quantity if is_heavy_product(normalized[0]) or quantity > 3 else 1
    heavy_count = sum(1 for line in normalized if is_heavy_product(line))
    light_count = len(normalized) - heavy_count
    total_quantity = sum(quantities)
    if total_quantity <= 3 and heavy_count == 0:
        return 1
    return heavy_count + (1 if light_count > 0 else 0)
