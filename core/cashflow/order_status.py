"""Canonical order status normalization for cashflow mapping."""
from __future__ import annotations

COMPLETED_INTERNAL = {"COMPLETED"}
CANCELLED_INTERNAL = {"CANCELLED", "RETURNED"}
ON_DELIVERY_INTERNAL = {"SHIPPED"}
READY_INTERNAL = {"READY"}

COMPLETED_RU = {"завершен", "выдан", "архив", "archive"}
CANCELLED_RU = {"отменен", "возврат", "возвращен"}
ON_DELIVERY_RU = {"передан курьеру"}


def normalize_order_status(
    internal_status: str | None,
    kaspi_status: str | None,
    config: dict | None = None,
) -> str:
    internal = (internal_status or "").strip().upper()
    if internal in COMPLETED_INTERNAL:
        return "COMPLETED"
    if internal in CANCELLED_INTERNAL:
        return "CANCELLED"
    if internal in ON_DELIVERY_INTERNAL:
        return "ON_DELIVERY"
    if internal in READY_INTERNAL:
        return "READY"

    kaspi_raw = (kaspi_status or "").strip()
    kaspi_norm = kaspi_raw.lower()
    if kaspi_norm in COMPLETED_RU:
        return "COMPLETED"
    if kaspi_norm in CANCELLED_RU:
        return "CANCELLED"
    if kaspi_norm in ON_DELIVERY_RU:
        return "ON_DELIVERY"

    status_filters = (config or {}).get("status_filters", {})
    for _, info in status_filters.items():
        if info.get("russian") == kaspi_raw:
            mapped = (info.get("internal") or "").upper()
            if mapped in COMPLETED_INTERNAL:
                return "COMPLETED"
            if mapped in CANCELLED_INTERNAL:
                return "CANCELLED"
            if mapped in ON_DELIVERY_INTERNAL:
                return "ON_DELIVERY"
            if mapped in READY_INTERNAL:
                return "READY"
            return mapped

    return internal if internal else "NEW"
