from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .pricelist_models import Availability, Catalog, Offer
from .validators import validate_catalog
from .xml_renderer import render_catalog_xml


@dataclass
class GenerationResult:
    catalog_path: Path
    diff_report_path: Path
    offer_count: int


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _load_pricelist_config(config_path: Path, store_code: str) -> dict:
    data = _load_yaml(config_path)
    defaults = data.get("defaults", {})
    stores = data.get("stores", {})
    store_cfg = stores.get(store_code, {})
    if not store_cfg:
        raise ValueError(f"Missing store config for {store_code}")

    return {
        "company": store_cfg.get("company") or store_code,
        "merchant_id": store_cfg.get("merchant_id"),
        "warehouses": store_cfg.get("warehouses", []),
        "default_brand": store_cfg.get("brand") or defaults.get("brand"),
        "preorder_days": store_cfg.get("preorder_days") or defaults.get("preorder_days"),
        "stock_allocation": store_cfg.get("stock_allocation") or defaults.get("stock_allocation"),
    }


def _get_latest_snapshot_date(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT MAX(snapshot_date) as max_date FROM fact_inventory_snapshot_size"
    ).fetchone()
    if not row or not row[0]:
        raise ValueError("No inventory snapshot date found in fact_inventory_snapshot_size")
    return str(row[0])


def _allocate_stock(total_stock: int, warehouses: list[str], allocation: str | None) -> list[int]:
    if len(warehouses) <= 1:
        return [total_stock]
    if not allocation:
        raise ValueError("stock_allocation must be set when multiple warehouses are configured")
    if allocation == "copy":
        return [total_stock for _ in warehouses]
    if allocation == "split_even":
        base = total_stock // len(warehouses)
        remainder = total_stock % len(warehouses)
        return [base + (1 if idx < remainder else 0) for idx in range(len(warehouses))]
    raise ValueError(f"Unknown stock_allocation: {allocation}")


def _build_offers(
    conn: sqlite3.Connection,
    snapshot_date: str,
    store_code: str,
    cfg: dict,
) -> list[Offer]:
    sku_cols = _table_columns(conn, "dim_sku")
    size_cols = _table_columns(conn, "dim_sku_size")

    has_brand = "brand" in sku_cols
    has_price = "kaspi_price_kzt" in sku_cols
    has_active_sku = "active_flag" in sku_cols
    has_active_size = "active_flag" in size_cols

    select_brand = "d.brand" if has_brand else "NULL as brand"
    select_price = "d.kaspi_price_kzt" if has_price else "NULL as kaspi_price_kzt"
    select_active_sku = "d.active_flag" if has_active_sku else "1 as sku_active"
    select_active_size = "s.active_flag" if has_active_size else "1 as size_active"

    rows = conn.execute(
        f"""
        SELECT
            s.sku_id,
            s.sku_key,
            s.my_size,
            d.model,
            {select_brand},
            {select_price},
            d.avg_sell_price_kzt_used as avg_price,
            {select_active_sku},
            {select_active_size},
            COALESCE(inv.current_stock, 0) as current_stock,
            COALESCE(inv.inbound_stock, 0) as inbound_stock
        FROM dim_sku_size s
        JOIN dim_sku d ON d.sku_key = s.sku_key
        LEFT JOIN (
            SELECT sku_id, SUM(current_stock) as current_stock, SUM(inbound_stock) as inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
            GROUP BY sku_id
        ) inv ON inv.sku_id = s.sku_id
        """,
        (snapshot_date,),
    ).fetchall()

    offers = []
    missing_fields: list[str] = []
    warehouses = cfg.get("warehouses") or []
    if not warehouses:
        raise ValueError("warehouses list is required in pricelist config")

    for row in rows:
        sku_id, sku_key, my_size, model, brand, kaspi_price, avg_price, sku_active, size_active, current_stock, inbound_stock = row
        if int(sku_active) == 0 or int(size_active) == 0:
            continue

        if not model:
            missing_fields.append(f"{sku_id}: missing model")
            continue

        effective_brand = brand or cfg.get("default_brand")
        if not effective_brand:
            missing_fields.append(f"{sku_id}: missing brand")
            continue

        price = None
        if kaspi_price is not None and float(kaspi_price) > 0:
            price = int(float(kaspi_price))
        elif avg_price is not None and float(avg_price) > 0:
            price = int(float(avg_price))

        if price is None:
            missing_fields.append(f"{sku_id}: missing price")
            continue

        total_stock = int(current_stock or 0)
        inbound_total = int(inbound_stock or 0)
        pre_order = None
        if total_stock <= 0 and inbound_total > 0:
            pre_order = cfg.get("preorder_days")
            if pre_order:
                pre_order = min(int(pre_order), 30)

        allocation = cfg.get("stock_allocation")
        per_warehouse = _allocate_stock(total_stock, warehouses, allocation)
        availabilities = []
        for idx, store_id in enumerate(warehouses):
            stock_count = per_warehouse[idx]
            available = stock_count > 0 or pre_order is not None
            availabilities.append(
                Availability(
                    available=available,
                    store_id=store_id,
                    stock_count=stock_count,
                    pre_order=pre_order,
                )
            )

        offers.append(
            Offer(
                sku=str(sku_id),
                model=str(model),
                brand=str(effective_brand),
                price=price,
                availabilities=availabilities,
            )
        )

    if missing_fields:
        raise ValueError("Missing required fields: " + "; ".join(missing_fields))

    return offers


def _parse_existing_catalog(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    from xml.etree import ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()
    offers = {}
    for offer in root.findall(".//{*}offer"):
        sku = offer.attrib.get("sku")
        if not sku:
            continue
        price_el = offer.find("{*}price")
        cityprices_el = offer.find("{*}cityprices")
        price = None
        cityprices = []
        if price_el is not None and price_el.text:
            price = int(float(price_el.text))
        if cityprices_el is not None:
            for cp in cityprices_el.findall("{*}cityprice"):
                if cp.text:
                    cityprices.append((cp.attrib.get("cityId"), int(float(cp.text))))
        avail = {}
        for av in offer.findall(".//{*}availability"):
            store_id = av.attrib.get("storeId")
            if not store_id:
                continue
            stock = int(av.attrib.get("stockCount", "0"))
            pre = av.attrib.get("preOrder")
            pre_val = int(pre) if pre is not None else None
            avail[store_id] = (stock, pre_val)
        offers[sku] = {
            "price": price,
            "cityprices": cityprices,
            "availabilities": avail,
        }
    return offers


def _write_diff_report(
    old_offers: dict[str, dict[str, Any]],
    new_offers: dict[str, dict[str, Any]],
    report_path: Path,
) -> None:
    old_skus = set(old_offers.keys())
    new_skus = set(new_offers.keys())
    added = sorted(new_skus - old_skus)
    removed = sorted(old_skus - new_skus)

    changed_price = []
    changed_stock = []
    changed_preorder = []

    for sku in sorted(old_skus & new_skus):
        old = old_offers[sku]
        new = new_offers[sku]
        if old.get("price") != new.get("price") or old.get("cityprices") != new.get("cityprices"):
            changed_price.append(sku)
        if old.get("availabilities") != new.get("availabilities"):
            changed_stock.append(sku)
        for store_id, (stock, pre) in new.get("availabilities", {}).items():
            old_pre = old.get("availabilities", {}).get(store_id, (None, None))[1]
            if old_pre != pre:
                changed_preorder.append(sku)
                break

    lines = [
        "# Pricelist diff report",
        "",
        f"Added: {len(added)}",
        f"Removed: {len(removed)}",
        f"Price changes: {len(changed_price)}",
        f"Stock changes: {len(changed_stock)}",
        f"Preorder changes: {len(changed_preorder)}",
        "",
    ]
    if added:
        lines.append("## Added (sample)")
        lines.extend([f"- {sku}" for sku in added[:20]])
        lines.append("")
    if removed:
        lines.append("## Removed (sample)")
        lines.extend([f"- {sku}" for sku in removed[:20]])
        lines.append("")
    if changed_price:
        lines.append("## Price changes (sample)")
        lines.extend([f"- {sku}" for sku in changed_price[:20]])
        lines.append("")

    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def generate_pricelist(
    db_path: Path,
    store_code: str,
    config_path: Path,
    output_dir: Path,
    dry_run: bool = True,
    publish_path: Path | None = None,
) -> GenerationResult:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cfg = _load_pricelist_config(config_path, store_code)
        if not cfg.get("merchant_id"):
            # Try to pull merchant_id from kaspi_stores.yaml if available
            stores_cfg_path = Path(__file__).resolve().parents[3] / "config" / "kaspi_stores.yaml"
            if stores_cfg_path.exists():
                stores_cfg = _load_yaml(stores_cfg_path)
                merchant_id = stores_cfg.get("stores", {}).get(store_code, {}).get("merchant_uid")
                cfg["merchant_id"] = merchant_id
        if not cfg.get("merchant_id"):
            raise ValueError(f"merchant_id missing for {store_code}")

        snapshot_date = _get_latest_snapshot_date(conn)
        offers = _build_offers(conn, snapshot_date, store_code, cfg)
        catalog = Catalog(company=cfg["company"], merchant_id=str(cfg["merchant_id"]), offers=offers)
        validate_catalog(catalog)

        store_dir = output_dir / store_code
        store_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = store_dir / "kaspi_catalog.xml"
        diff_path = store_dir / "diff_report.md"

        old_offers = _parse_existing_catalog(catalog_path)

        xml = render_catalog_xml(catalog)
        catalog_path.write_text(xml, encoding="utf-8")

        new_offers = _parse_existing_catalog(catalog_path)
        _write_diff_report(old_offers, new_offers, diff_path)

        if publish_path:
            if dry_run:
                raise ValueError("dry_run=True cannot publish")
            publish_path.parent.mkdir(parents=True, exist_ok=True)
            publish_path.write_text(xml, encoding="utf-8")

        return GenerationResult(catalog_path=catalog_path, diff_report_path=diff_path, offer_count=len(offers))
    finally:
        conn.close()
