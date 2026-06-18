"""Effective-dated Rombik kid size-30 alias decision."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone, timedelta
from typing import Any


EFFECTIVE_AT_ALMATY = datetime(2026, 6, 3, 10, 9, 14, tzinfo=timezone(timedelta(hours=5)))
CANONICAL_SKU_KEY = "CL_NEW-CLO_KID_ROMBIK_BLACK"
CANONICAL_SIZE = "30"
CANONICAL_SKU_ID = f"{CANONICAL_SKU_KEY}_{CANONICAL_SIZE}"
CANONICAL_STOCK_POOL_ID = CANONICAL_SKU_ID
PHYSICAL_STOCK_POOL_UNITS = 93
AUTHORIZED_ROUTES = {
    "135222379": {"public_height_label": "152", "stock_to_expose_per_store": 47},
    "128541983": {"public_height_label": "158", "stock_to_expose_per_store": 46},
}


def _normalize_event_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EFFECTIVE_AT_ALMATY.tzinfo)
    return dt.astimezone(EFFECTIVE_AT_ALMATY.tzinfo)


def is_effective_at(value: Any) -> bool:
    dt = _normalize_event_at(value)
    return bool(dt and dt >= EFFECTIVE_AT_ALMATY)


def extract_authorized_product_code(*values: Any) -> str:
    blob = " ".join(str(v or "") for v in values)
    if not blob:
        return ""
    for code in AUTHORIZED_ROUTES:
        if re.search(rf"(?<!\d){re.escape(code)}(?!\d)", blob):
            return code
    return ""


def apply_rombik_kid30_alias(
    *,
    sku_key: str | None,
    sku_id: str | None,
    my_size: str | None,
    event_at: Any,
    kaspi_article: str | None = None,
    kaspi_offer_name: str | None = None,
) -> dict[str, str | None]:
    """Return canonical identity for the owner-approved 152/158 alias routes.

    The rule is future-only from EFFECTIVE_AT_ALMATY and product-code scoped. It
    intentionally does not remap neighboring Rombik kids S routes such as
    143893497/164 or 147855005/170.
    """
    out = {"sku_key": sku_key, "sku_id": sku_id, "my_size": my_size}
    if not is_effective_at(event_at):
        return out
    key = str(sku_key or "").strip()
    size = str(my_size or "").strip().upper()
    if key != CANONICAL_SKU_KEY or size != "S":
        return out
    code = extract_authorized_product_code(kaspi_article, sku_id, kaspi_offer_name)
    if not code:
        return out
    out.update({"sku_key": CANONICAL_SKU_KEY, "sku_id": CANONICAL_SKU_ID, "my_size": CANONICAL_SIZE})
    return out

