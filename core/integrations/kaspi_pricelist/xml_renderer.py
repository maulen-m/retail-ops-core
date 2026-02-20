from __future__ import annotations

from datetime import date
from xml.etree import ElementTree as ET

from .pricelist_models import Catalog, Offer, Availability, CityPrice


def _availability_element(avail: Availability) -> ET.Element:
    attrs = {
        "available": "yes" if avail.available else "no",
        "storeId": str(avail.store_id),
    }
    if avail.pre_order is not None:
        attrs["preOrder"] = str(avail.pre_order)
    attrs["stockCount"] = str(avail.stock_count)
    return ET.Element("availability", attrs)


def _offer_element(offer: Offer) -> ET.Element:
    offer_el = ET.Element("offer", {"sku": str(offer.sku)})
    model_el = ET.SubElement(offer_el, "model")
    model_el.text = str(offer.model)
    brand_el = ET.SubElement(offer_el, "brand")
    brand_el.text = str(offer.brand)

    avail_el = ET.SubElement(offer_el, "availabilities")
    for avail in sorted(offer.availabilities, key=lambda a: str(a.store_id)):
        avail_el.append(_availability_element(avail))

    if offer.cityprices:
        cityprices_el = ET.SubElement(offer_el, "cityprices")
        for cp in offer.cityprices:
            city_el = ET.SubElement(cityprices_el, "cityprice", {"cityId": str(cp.city_id)})
            if cp.old_price is not None:
                city_el.set("oldprice", str(cp.old_price))
            city_el.text = str(cp.price)
    else:
        price_el = ET.SubElement(offer_el, "price")
        price_el.text = str(offer.price) if offer.price is not None else "0"

    return offer_el


def render_catalog_xml(catalog: Catalog, date_str: str | None = None) -> str:
    if not date_str:
        date_str = date.today().isoformat()

    root_attrs = {
        "date": date_str,
        "xmlns": "kaspiShopping",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "kaspiShopping http://kaspi.kz/kaspishopping.xsd",
    }
    root = ET.Element("kaspi_catalog", root_attrs)

    company_el = ET.SubElement(root, "company")
    company_el.text = str(catalog.company)
    merchant_el = ET.SubElement(root, "merchantid")
    merchant_el.text = str(catalog.merchant_id)

    offers_el = ET.SubElement(root, "offers")
    for offer in sorted(catalog.offers, key=lambda o: str(o.sku)):
        offers_el.append(_offer_element(offer))

    ET.indent(root, space="  ")
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")
