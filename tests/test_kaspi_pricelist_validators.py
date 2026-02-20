import pytest

from core.integrations.kaspi_pricelist.pricelist_models import (
    Availability,
    Catalog,
    CityPrice,
    Offer,
)
from core.integrations.kaspi_pricelist.validators import ValidationError, validate_catalog


def test_validate_requires_brand_and_model():
    offer = Offer(
        sku="SKU1",
        model="Model",
        brand=None,
        price=10000,
        availabilities=[Availability(available=True, store_id="PP1", stock_count=5)],
    )
    catalog = Catalog(company="Test", merchant_id="123", offers=[offer])
    with pytest.raises(ValidationError):
        validate_catalog(catalog)


def test_validate_preorder_range():
    offer = Offer(
        sku="SKU1",
        model="Model",
        brand="Brand",
        price=10000,
        availabilities=[Availability(available=True, store_id="PP1", stock_count=5, pre_order=31)],
    )
    catalog = Catalog(company="Test", merchant_id="123", offers=[offer])
    with pytest.raises(ValidationError):
        validate_catalog(catalog)


def test_validate_stock_non_negative():
    offer = Offer(
        sku="SKU1",
        model="Model",
        brand="Brand",
        price=10000,
        availabilities=[Availability(available=True, store_id="PP1", stock_count=-1)],
    )
    catalog = Catalog(company="Test", merchant_id="123", offers=[offer])
    with pytest.raises(ValidationError):
        validate_catalog(catalog)


def test_validate_price_and_cityprices_exclusive():
    offer = Offer(
        sku="SKU1",
        model="Model",
        brand="Brand",
        price=10000,
        cityprices=[CityPrice(city_id="750000000", price=11000)],
        availabilities=[Availability(available=True, store_id="PP1", stock_count=5)],
    )
    catalog = Catalog(company="Test", merchant_id="123", offers=[offer])
    with pytest.raises(ValidationError):
        validate_catalog(catalog)


def test_validate_sku_uniqueness():
    offer1 = Offer(
        sku="SKU1",
        model="Model",
        brand="Brand",
        price=10000,
        availabilities=[Availability(available=True, store_id="PP1", stock_count=5)],
    )
    offer2 = Offer(
        sku="SKU1",
        model="Model",
        brand="Brand",
        price=12000,
        availabilities=[Availability(available=True, store_id="PP2", stock_count=2)],
    )
    catalog = Catalog(company="Test", merchant_id="123", offers=[offer1, offer2])
    with pytest.raises(ValidationError):
        validate_catalog(catalog)


def test_validate_success():
    offer = Offer(
        sku="SKU1",
        model="Model",
        brand="Brand",
        price=10000,
        availabilities=[Availability(available=True, store_id="PP1", stock_count=5, pre_order=None)],
    )
    catalog = Catalog(company="Test", merchant_id="123", offers=[offer])
    validate_catalog(catalog)
