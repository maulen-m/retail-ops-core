from pathlib import Path

from core.integrations.kaspi_pricelist.pricelist_models import (
    Availability,
    Catalog,
    CityPrice,
    Offer,
)
from core.integrations.kaspi_pricelist.xml_renderer import render_catalog_xml


def test_render_xml_matches_golden():
    catalog = Catalog(
        company="TestCo",
        merchant_id="123",
        offers=[
            Offer(
                sku="SKU1",
                model="Model A",
                brand="BrandA",
                price=10000,
                availabilities=[
                    Availability(available=True, store_id="PP1", stock_count=5, pre_order=3)
                ],
            ),
            Offer(
                sku="SKU2",
                model="Model B",
                brand="BrandB",
                cityprices=[CityPrice(city_id="750000000", price=11000)],
                availabilities=[
                    Availability(available=False, store_id="PP1", stock_count=0)
                ],
            ),
        ],
    )
    xml = render_catalog_xml(catalog, date_str="2026-01-27")
    expected = Path("tests/fixtures/kaspi_pricelist/golden_catalog.xml").read_text(encoding="utf-8")
    assert xml.strip() == expected.strip()


def test_render_xml_escapes_text():
    catalog = Catalog(
        company="TestCo",
        merchant_id="123",
        offers=[
            Offer(
                sku="SKU1",
                model="Model & Co <Test>",
                brand="Brand \"X\"",
                price=10000,
                availabilities=[Availability(available=True, store_id="PP1", stock_count=1)],
            )
        ],
    )
    xml = render_catalog_xml(catalog, date_str="2026-01-27")
    assert "&amp;" in xml
    assert "&lt;Test&gt;" in xml
    assert "Brand \"X\"" in xml
