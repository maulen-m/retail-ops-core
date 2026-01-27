from __future__ import annotations

from typing import Iterable

from .pricelist_models import Catalog, Offer, Availability, CityPrice


class ValidationError(ValueError):
    """Raised when pricelist data fails validation."""


def _require_text(value: str, field: str) -> None:
    if value is None or not str(value).strip():
        raise ValidationError(f"Missing required field: {field}")


def _require_int(value: int, field: str) -> None:
    if not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")


def _validate_availability(avail: Availability) -> None:
    _require_text(avail.store_id, "availability.store_id")
    _require_int(avail.stock_count, "availability.stock_count")
    if avail.stock_count < 0:
        raise ValidationError("availability.stock_count must be >= 0")
    if avail.pre_order is not None:
        _require_int(avail.pre_order, "availability.pre_order")
        if not 1 <= avail.pre_order <= 30:
            raise ValidationError("availability.pre_order must be in 1..30")


def _validate_price(price: int) -> None:
    _require_int(price, "price")
    if price < 0:
        raise ValidationError("price must be >= 0")


def _validate_cityprices(cityprices: Iterable[CityPrice]) -> None:
    for cp in cityprices:
        _require_text(cp.city_id, "cityprice.city_id")
        _validate_price(cp.price)
        if cp.old_price is not None:
            _validate_price(cp.old_price)


def _validate_offer(offer: Offer) -> None:
    _require_text(offer.sku, "offer.sku")
    _require_text(offer.model, "offer.model")
    _require_text(offer.brand, "offer.brand")

    if offer.price is None and not offer.cityprices:
        raise ValidationError("offer requires price or cityprices")
    if offer.price is not None and offer.cityprices:
        raise ValidationError("offer cannot have both price and cityprices")
    if offer.price is not None:
        _validate_price(offer.price)
    if offer.cityprices:
        _validate_cityprices(offer.cityprices)

    if not offer.availabilities:
        raise ValidationError("offer must include at least one availability")
    for avail in offer.availabilities:
        _validate_availability(avail)


def validate_catalog(catalog: Catalog) -> None:
    _require_text(catalog.company, "catalog.company")
    _require_text(catalog.merchant_id, "catalog.merchant_id")
    if not catalog.offers:
        raise ValidationError("catalog must include at least one offer")

    seen = set()
    for offer in catalog.offers:
        _validate_offer(offer)
        if offer.sku in seen:
            raise ValidationError(f"Duplicate SKU in catalog: {offer.sku}")
        seen.add(offer.sku)
