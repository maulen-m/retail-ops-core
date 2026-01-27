from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Availability:
    available: bool
    store_id: str
    stock_count: int
    pre_order: Optional[int] = None


@dataclass
class CityPrice:
    city_id: str
    price: int
    old_price: Optional[int] = None


@dataclass
class Offer:
    sku: str
    model: str
    brand: str
    availabilities: List[Availability] = field(default_factory=list)
    price: Optional[int] = None
    cityprices: Optional[List[CityPrice]] = None


@dataclass
class Catalog:
    company: str
    merchant_id: str
    offers: List[Offer] = field(default_factory=list)
