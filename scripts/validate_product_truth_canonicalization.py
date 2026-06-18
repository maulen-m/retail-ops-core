#!/usr/bin/env python3
"""Validate and materialize the May 28 product-truth canonicalization contract."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.manual_stock_count_manifest import (
    load_approved_manual_stock_manifest,
    manual_stock_overrides_by_sku_id,
)
from core.product_truth.rombik_kid30_alias import (
    AUTHORIZED_ROUTES as ROMBIK_KID30_AUTHORIZED_ROUTES,
    CANONICAL_SIZE as ROMBIK_KID30_CANONICAL_SIZE,
    CANONICAL_SKU_ID as ROMBIK_KID30_CANONICAL_SKU_ID,
    CANONICAL_SKU_KEY as ROMBIK_KID30_CANONICAL_SKU_KEY,
    EFFECTIVE_AT_ALMATY as ROMBIK_KID30_EFFECTIVE_AT_ALMATY,
    PHYSICAL_STOCK_POOL_UNITS as ROMBIK_KID30_PHYSICAL_STOCK_POOL_UNITS,
)
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "product_truth_canonicalization_2026_05_28.json"
SIZES = ("S", "M", "L", "XL", "2XL", "3XL", "4XL")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]


def _project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def _split_md_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _to_int(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    return int(float(text.replace(",", "")))


def _to_float(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    return float(text.replace(",", ""))


def _parse_size_from_sku_id(sku_id: str, fallback: str = "") -> str:
    text = (sku_id or "").strip()
    for size in sorted(SIZES, key=len, reverse=True):
        if text.endswith(f"_{size}"):
            return size
    fallback = (fallback or "").strip().upper()
    return fallback if fallback in SIZES else ""


def parse_line31_sales(path: Path) -> list[dict[str, Any]]:
    headers: list[str] | None = None
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_md_row(line)
        if len(cells) < 19:
            continue
        if cells[0] == "1" and cells[1] == "Date":
            headers = cells[1:]
            continue
        if headers is None or not cells[0].isdigit():
            continue
        values = cells[1 : 1 + len(headers)]
        if len(values) != len(headers):
            continue
        row = dict(zip(headers, values))
        if row.get("MODEL") != "LINE31" or not row.get("Date"):
            continue
        row["source_row"] = cells[0]
        row["quantity"] = _to_int(row.get("Quantity"))
        row["sell_price_kzt"] = _to_int(row.get("Sell_price_kzt"))
        row["total_price_kzt"] = _to_int(row.get("Total_price"))
        row["total_net_rev_kzt"] = _to_float(row.get("Total_net_rev"))
        row["size"] = row.get("MY_SIZE") or row.get("PROBABLE_SIZE") or _parse_size_from_sku_id(row.get("SKU_ID", ""))
        rows.append(row)
    return rows


def parse_line31_stock_anchor(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_md_row(line)
        if len(cells) < 12 or not cells[0].isdigit():
            continue
        if cells[0] in {"1", "2", "3", "4", "5", "14"}:
            continue
        sku_key = cells[4].strip()
        if not sku_key.startswith("CL_OF_ARC_WM_LINE31"):
            continue
        color = cells[3].strip()
        set_name = cells[1].strip()
        for index, size in enumerate(("S", "M", "L", "XL", "2XL", "3XL"), start=5):
            qty = _to_int(cells[index])
            rows.append(
                {
                    "source_row": cells[0],
                    "set_name": set_name,
                    "color": color,
                    "sku_key": sku_key,
                    "size": size,
                    "anchor_qty": qty,
                }
            )
    return rows


def parse_po1a_addback(
    path: Path,
    mapping: dict[str, str],
    quarantine_colors: set[str],
    reserve_colors: set[str] | None = None,
) -> list[dict[str, Any]]:
    reserve_colors = reserve_colors or set()
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            set_color = raw["set_color"]
            if set_color == "TOTAL":
                continue
            if set_color in mapping:
                status = "MAPPED_PO1A_ADD_BACK"
            elif set_color in reserve_colors:
                status = "PHYSICAL_NOT_FOR_SALE_RESERVE"
            else:
                status = "QUARANTINED_UNMAPPED_PO1A"
            if status.startswith("QUARANTINED") and set_color not in quarantine_colors:
                status = "QUARANTINED_UNEXPECTED_UNMAPPED_PO1A"
            for size_key, size in (("s", "S"), ("m", "M"), ("l", "L"), ("xl", "XL"), ("2xl", "2XL"), ("3xl", "3XL")):
                qty = _to_int(raw.get(size_key))
                if qty == 0:
                    continue
                rows.append(
                    {
                        "set_color": set_color,
                        "sku_key": mapping.get(set_color, ""),
                        "size": size,
                        "po1a_addback_qty": qty,
                        "mapping_status": status,
                        "offer_action_scope": raw.get("offer_action_scope", ""),
                    }
                )
    return rows


def _load_owner_override_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _owner_qty(rows: list[dict[str, str]], sku_key: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for row in rows:
        if row.get("sku_key") == sku_key:
            found[row["size"]] = _to_int(row.get("qty"))
    return found


def _load_line31_db_proxy_depletion(db_path: Path, anchor_date: str) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select order_id, store_code, created_at, actual_shipment_date, kaspi_status,
                   internal_status, kaspi_offer_name, sku_key, sku_id, my_size,
                   assigned_size, quantity, unit_price_kzt
            from fact_orders_kaspi
            where (sku_key like '%LINE31%' or sku_id like '%LINE31%' or kaspi_offer_name like '%LINE31%')
              and date(created_at) > date(?)
            order by created_at, order_id
            """,
            (anchor_date,),
        ).fetchall()
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        sku_id = row["sku_id"] or ""
        size = _parse_size_from_sku_id(sku_id, row["assigned_size"] or row["my_size"] or "")
        qty = _to_int(row["quantity"])
        internal_status = row["internal_status"] or ""
        shipped = bool(row["actual_shipment_date"]) and internal_status != "CANCELLED"
        completed = internal_status == "COMPLETED"
        open_reserved = internal_status in {"READY", "ACCEPTED"} and not row["actual_shipment_date"]
        out.append(
            {
                "order_id": row["order_id"],
                "store_code": row["store_code"],
                "created_at": row["created_at"],
                "ship_date": row["actual_shipment_date"] or "",
                "kaspi_status": row["kaspi_status"] or "",
                "internal_status": internal_status,
                "sku_key": row["sku_key"] or "",
                "sku_id": sku_id,
                "size": size,
                "quantity": qty,
                "unit_price_kzt": _to_float(row["unit_price_kzt"]),
                "physical_depletion_qty": qty if shipped else 0,
                "economic_depletion_qty": qty if completed else 0,
                "open_reserved_qty": qty if open_reserved else 0,
            }
        )
    return out


def build_line31_stock_preview(
    anchor_rows: list[dict[str, Any]],
    po1a_rows: list[dict[str, Any]],
    depletion_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    color_by_sku = {row["sku_key"]: row["color"] for row in anchor_rows}
    set_by_sku = {row["sku_key"]: row["set_name"] for row in anchor_rows}

    for row in anchor_rows:
        key = (row["sku_key"], row["size"])
        by_key[key] = {
            "sku_key": row["sku_key"],
            "color": row["color"],
            "set_name": row["set_name"],
            "size": row["size"],
            "anchor_qty": row["anchor_qty"],
            "po1a_mapped_addback_qty": 0,
            "physical_depletion_qty": 0,
            "economic_depletion_qty": 0,
            "open_reserved_qty": 0,
            "po1a_quarantined_qty": 0,
            "mapping_status": "MAPPED_LINE31_SKU",
        }

    for row in po1a_rows:
        if row["mapping_status"] == "MAPPED_PO1A_ADD_BACK":
            key = (row["sku_key"], row["size"])
            by_key.setdefault(
                key,
                {
                    "sku_key": row["sku_key"],
                    "color": color_by_sku.get(row["sku_key"], row["set_color"]),
                    "set_name": set_by_sku.get(row["sku_key"], row["set_color"]),
                    "size": row["size"],
                    "anchor_qty": 0,
                    "po1a_mapped_addback_qty": 0,
                    "physical_depletion_qty": 0,
                    "economic_depletion_qty": 0,
                    "open_reserved_qty": 0,
                    "po1a_quarantined_qty": 0,
                    "mapping_status": "MAPPED_LINE31_SKU_PO1A_ONLY",
                },
            )
            by_key[key]["po1a_mapped_addback_qty"] += row["po1a_addback_qty"]
        elif row["mapping_status"].startswith("PHYSICAL_NOT_FOR_SALE_RESERVE"):
            key = (f"PHYSICAL_NOT_FOR_SALE_RESERVE::{row['set_color']}", row["size"])
            by_key[key] = {
                "sku_key": "",
                "color": row["set_color"],
                "set_name": row["set_color"],
                "size": row["size"],
                "anchor_qty": 0,
                "po1a_mapped_addback_qty": 0,
                "physical_depletion_qty": 0,
                "economic_depletion_qty": 0,
                "open_reserved_qty": 0,
                "po1a_quarantined_qty": 0,
                "physical_not_for_sale_reserve_qty": row["po1a_addback_qty"],
                "mapping_status": row["mapping_status"],
            }
        else:
            key = (f"UNMAPPED_PO1A_QUARANTINE::{row['set_color']}", row["size"])
            by_key[key] = {
                "sku_key": "",
                "color": row["set_color"],
                "set_name": row["set_color"],
                "size": row["size"],
                "anchor_qty": 0,
                "po1a_mapped_addback_qty": 0,
                "physical_depletion_qty": 0,
                "economic_depletion_qty": 0,
                "open_reserved_qty": 0,
                "po1a_quarantined_qty": row["po1a_addback_qty"],
                "physical_not_for_sale_reserve_qty": 0,
                "mapping_status": row["mapping_status"],
            }

    for row in depletion_rows:
        if not row["sku_key"] or not row["size"]:
            continue
        key = (row["sku_key"], row["size"])
        if key not in by_key:
            by_key[key] = {
                "sku_key": row["sku_key"],
                "color": color_by_sku.get(row["sku_key"], ""),
                "set_name": set_by_sku.get(row["sku_key"], "DB_PROXY_ONLY_LINE31_SKU"),
                "size": row["size"],
                "anchor_qty": 0,
                "po1a_mapped_addback_qty": 0,
                "physical_depletion_qty": 0,
                "economic_depletion_qty": 0,
                "open_reserved_qty": 0,
                "po1a_quarantined_qty": 0,
                "mapping_status": "DB_PROXY_DEPLETION_NOT_IN_ANCHOR_TABLE",
            }
        by_key[key]["physical_depletion_qty"] += row["physical_depletion_qty"]
        by_key[key]["economic_depletion_qty"] += row["economic_depletion_qty"]
        by_key[key]["open_reserved_qty"] += row["open_reserved_qty"]

    preview: list[dict[str, Any]] = []
    for row in by_key.values():
        reserve_qty = row.get("physical_not_for_sale_reserve_qty", 0)
        physical = row["anchor_qty"] + row["po1a_mapped_addback_qty"] + reserve_qty - row["physical_depletion_qty"]
        economic = row["anchor_qty"] + row["po1a_mapped_addback_qty"] + reserve_qty - row["economic_depletion_qty"]
        available = physical - row["open_reserved_qty"]
        out = dict(row)
        out["estimated_physical_warehouse_qty"] = physical
        out["estimated_available_after_open_reserved_qty"] = available
        out["estimated_economic_final_sales_stock_qty"] = economic
        out["confidence"] = "MEDIUM" if row["mapping_status"].startswith("MAPPED") else "LOW"
        if row["mapping_status"].startswith("MAPPED"):
            out["blockers"] = "WEBUI_STATUS_CHANGE_REPLAY_STILL_REQUIRED"
        elif row["mapping_status"].startswith("PHYSICAL_NOT_FOR_SALE_RESERVE"):
            out["blockers"] = "NOT_FOR_SALE_RESERVE_NOT_LIVE_ROUTE_BLOCKER"
        else:
            out["blockers"] = "PO1A_COLOR_OFFER_SKU_MAPPING_NOT_SOURCE_PROVEN"
        preview.append(out)
    return sorted(preview, key=lambda r: (r["mapping_status"], r["sku_key"], r["color"], SIZES.index(r["size"]) if r["size"] in SIZES else 99))


def validate_config(config_path: Path = DEFAULT_CONFIG, *, strict: bool = False) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    config = _read_json(config_path)
    metrics: dict[str, Any] = {}

    contract_doc = _project_path(config["contract_doc"])
    if not contract_doc.exists():
        errors.append(f"contract_doc missing: {contract_doc}")

    owner_rows = _load_owner_override_rows(_project_path(config["owner_stock_override_csv"]))
    identities = config["product_identities"]

    rush = identities["RUSH31"]
    if rush["identity_class"] != "INDEPENDENT_PRODUCT":
        errors.append("RUSH31 must be INDEPENDENT_PRODUCT")
    if "LINE61_CHILD" not in rush["forbidden_identity_classes"] or "LINE31" not in rush["forbidden_identity_classes"]:
        errors.append("RUSH31 forbidden identity classes must include LINE61_CHILD and LINE31")
    if rush["campaign_id"] != "2794142" or rush["kaspi_offer_id"] != "165486887" or rush["product_sku"] != "21282790b":
        errors.append("RUSH31 offer/campaign/product_sku identity drifted")
    rush_owner = _owner_qty(owner_rows, rush["canonical_sku_key"])
    if rush_owner != {k: int(v) for k, v in rush["owner_stock_by_size"].items()}:
        errors.append(f"RUSH31 owner override mismatch: {rush_owner}")
    if sum(rush_owner.values()) != 290:
        errors.append("RUSH31 owner stock total must be 290")
    rush_authority = rush.get("inventory_authority", {})
    if rush_authority.get("pricelist_pp_stock_is_inventory_truth") is not False:
        errors.append("RUSH31 PP/pricelist stock must be non-authoritative inventory evidence")
    if rush_authority.get("canonical_owner_physical_stock_total") != 290:
        errors.append("RUSH31 owner physical stock must remain canonical over pricelist PP stock")

    suit_owner = _owner_qty(owner_rows, identities["LINE61"]["canonical_sku_key"])
    if suit_owner != identities["LINE61"]["owner_override_by_size"]:
        errors.append(f"LINE61 owner override mismatch: {suit_owner}")

    beli_owner = _owner_qty(owner_rows, identities["LINE51"]["canonical_sku_key"])
    if beli_owner.get("4XL") != 0:
        errors.append("LINE51 WHITE 4XL override must be 0")

    print_owner = _owner_qty(owner_rows, identities["LINE52"]["canonical_sku_key"])
    if print_owner != identities["LINE52"]["owner_stock_by_size"]:
        errors.append(f"LINE52 owner override mismatch: {print_owner}")
    if sum(print_owner.values()) != 298:
        errors.append("LINE52 owner stock total must be 298")

    rombik_alias = identities["ROMBIK_KID30_ALIAS"]
    if rombik_alias["status"] != "OWNER_APPROVED":
        errors.append("ROMBIK_KID30_ALIAS must be OWNER_APPROVED")
    if rombik_alias["effective_at_almaty"] != ROMBIK_KID30_EFFECTIVE_AT_ALMATY.isoformat():
        errors.append("ROMBIK_KID30_ALIAS effective timestamp drifted")
    if rombik_alias["canonical_sku_key"] != ROMBIK_KID30_CANONICAL_SKU_KEY:
        errors.append("ROMBIK_KID30_ALIAS canonical_sku_key drifted")
    if rombik_alias["canonical_size"] != ROMBIK_KID30_CANONICAL_SIZE:
        errors.append("ROMBIK_KID30_ALIAS canonical_size must remain 30")
    if rombik_alias["canonical_stock_pool_id"] != ROMBIK_KID30_CANONICAL_SKU_ID:
        errors.append("ROMBIK_KID30_ALIAS stock pool must be CL_NEW-CLO_KID_ROMBIK_BLACK_30")
    if rombik_alias["physical_stock_pool_units"] != ROMBIK_KID30_PHYSICAL_STOCK_POOL_UNITS:
        errors.append("ROMBIK_KID30_ALIAS physical pool units must remain 93")
    if set(rombik_alias["authorized_routes"].keys()) != set(ROMBIK_KID30_AUTHORIZED_ROUTES.keys()):
        errors.append("ROMBIK_KID30_ALIAS authorized route set drifted")
    route_split_total = sum(int(route["stock_to_expose_per_store"]) for route in rombik_alias["authorized_routes"].values())
    if route_split_total != ROMBIK_KID30_PHYSICAL_STOCK_POOL_UNITS:
        errors.append("ROMBIK_KID30_ALIAS route exposure must total 93 per store")
    if sorted(rombik_alias["explicitly_unchanged_product_codes"]) != ["143893497", "147855005"]:
        errors.append("ROMBIK_KID30_ALIAS must preserve 164/170 product-code neighbors")
    if "future_only" not in rombik_alias["historical_order_policy"]:
        errors.append("ROMBIK_KID30_ALIAS historical policy must be future-only")

    manual_manifest = load_approved_manual_stock_manifest()
    manual_overrides = manual_stock_overrides_by_sku_id(manual_manifest)
    kid30_manual = manual_overrides.get(ROMBIK_KID30_CANONICAL_SKU_ID)
    if kid30_manual is None:
        errors.append("Manual stock manifest must include Rombik kid30 pool")
    elif kid30_manual.quantity != ROMBIK_KID30_PHYSICAL_STOCK_POOL_UNITS:
        errors.append(f"Rombik kid30 manual stock must remain 93, got {kid30_manual.quantity}")
    kid_s_manual = manual_overrides.get("CL_NEW-CLO_KID_ROMBIK_BLACK_S")
    men_s_manual = manual_overrides.get("CL_NEW-CLO_MEN_ROMBIK_BLACK_S")
    if not kid_s_manual or not men_s_manual or kid_s_manual is not men_s_manual or kid_s_manual.quantity != 74:
        errors.append("Rombik shared S men/kids pool must remain one 74-unit alias pool")

    line31 = identities["LINE31"]
    sales_rows = parse_line31_sales(Path(line31["sales_source"]))
    sales_qty = sum(row["quantity"] for row in sales_rows)
    price_counter = Counter(row["sell_price_kzt"] for row in sales_rows)
    gross = sum(row["total_price_kzt"] for row in sales_rows)
    net = sum(row["total_net_rev_kzt"] for row in sales_rows)
    if not sales_rows:
        errors.append("LINE31 sales parser found zero rows")
    if 0 in price_counter:
        errors.append(f"LINE31 sales parser produced zero sell price: {dict(price_counter)}")
    if int(line31["required_sell_price_kzt"]) not in price_counter:
        errors.append("LINE31 sales source must include 16,990 KZT sell-price evidence")

    anchor_rows = parse_line31_stock_anchor(Path(line31["stock_anchor_source"]))
    anchor_total = sum(row["anchor_qty"] for row in anchor_rows)
    if anchor_total != 139:
        errors.append(f"LINE31 April 13 anchor total expected 139, got {anchor_total}")

    po1a_rows = parse_po1a_addback(
        Path(line31["po1a_arrived_quantities_csv"]),
        dict(line31["po1a_color_mapping"]),
        set(line31.get("po1a_quarantine_colors", [])),
        set(line31.get("po1a_physical_not_for_sale_reserve_colors", [])),
    )
    po1a_total = sum(row["po1a_addback_qty"] for row in po1a_rows)
    po1a_mapped = sum(row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"] == "MAPPED_PO1A_ADD_BACK")
    po1a_reserve = sum(
        row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"] == "PHYSICAL_NOT_FOR_SALE_RESERVE"
    )
    po1a_quarantine = sum(row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"].startswith("QUARANTINED"))
    if po1a_total != line31["po1a_total_sets"]:
        errors.append(f"PO1A total expected {line31['po1a_total_sets']}, got {po1a_total}")
    if po1a_mapped != line31["po1a_mapped_addback_sets"]:
        errors.append(f"PO1A mapped expected {line31['po1a_mapped_addback_sets']}, got {po1a_mapped}")
    if po1a_reserve != line31["po1a_physical_not_for_sale_reserve_sets"]:
        errors.append(
            f"PO1A physical not-for-sale reserve expected {line31['po1a_physical_not_for_sale_reserve_sets']}, got {po1a_reserve}"
        )
    if po1a_quarantine != line31["po1a_quarantined_sets"]:
        errors.append(f"PO1A quarantine expected {line31['po1a_quarantined_sets']}, got {po1a_quarantine}")
    ignored_routes = line31.get("ignored_sellable_route_evidence", [])
    ignored_urls = {route.get("url") for route in ignored_routes}
    if "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-wb-l-sinii-l-162287320/" not in ignored_urls:
        errors.append("LINE31 Whale Blue incorrect single-size URL must be ignored for sellable-route proof")

    gift = config["gift_bag_cogs"]
    if gift["gift_bag_cost_cny_per_unit"] != 3 or float(gift["gift_bag_weight_kg_per_unit"]) != 0.10:
        errors.append("gift-bag COGS must be 3 CNY and 0.10 kg")
    if gift["kaspi_customer_copy_auto_include"] is not False:
        errors.append("Kaspi customer-facing copy must not auto-include gift bag")
    if gift.get("review_only_export_surfaces_must_opt_in") is not True:
        errors.append("review-only inventory/capital/export surfaces must opt into gift-bag COGS")

    pricelist_authority = config.get("pricelist_stock_non_authority", {})
    if pricelist_authority.get("pp_columns_inventory_authority") is not False:
        errors.append("pricelist PP columns must be explicitly non-authoritative for inventory truth")
    forbidden_use = pricelist_authority.get("forbidden_use", "")
    if "PHYSICAL_INVENTORY_TRUTH" not in forbidden_use or "REORDER_QTY" not in forbidden_use:
        errors.append("pricelist non-authority forbidden_use must block physical stock and reorder qty")

    trm = config["trm_opportunity_detector"]
    if trm["marketing_aggregate_attribution_must_remain_separate_from_order_identity"] is not True:
        errors.append("TRM attribution must stay separate from order identity")
    if trm["routes"]["Line61_TRM"]["current_rule"] != "HOLD_ENABLED_AND_MONITOR":
        errors.append("Line61 TRM rule must hold/monitor")
    if trm["routes"]["LINE51_TRM"]["current_rule"] != "DRY_RUN_REENABLE_CANDIDATE_ONLY":
        errors.append("LINE51 TRM must remain dry-run candidate only")

    metrics.update(
        {
            "rush31_owner_total": sum(rush_owner.values()),
            "line31_sales_rows": len(sales_rows),
            "line31_sales_qty": sales_qty,
            "line31_sell_price_distribution": dict(price_counter),
            "line31_gross_revenue_kzt": gross,
            "line31_net_revenue_kzt": round(net, 4),
            "line31_anchor_total_sets": anchor_total,
            "line31_po1a_total_sets": po1a_total,
            "line31_po1a_mapped_sets": po1a_mapped,
            "line31_po1a_physical_not_for_sale_reserve_sets": po1a_reserve,
            "line31_po1a_quarantined_sets": po1a_quarantine,
            "rombik_kid30_physical_stock_pool_units": ROMBIK_KID30_PHYSICAL_STOCK_POOL_UNITS,
            "rombik_kid30_route_split_total_per_store": route_split_total,
            "rombik_kid30_authorized_product_codes": sorted(rombik_alias["authorized_routes"].keys()),
        }
    )
    return ValidationResult(ok=not errors, errors=errors, warnings=warnings, metrics=metrics)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def materialize_wave(config_path: Path, output_root: Path, run_id: str | None = None) -> dict[str, Any]:
    config = _read_json(config_path)
    line31 = config["product_identities"]["LINE31"]
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out = output_root / f"product_truth_canonicalization_wave_{run_id}"
    out.mkdir(parents=True, exist_ok=True)

    sales_rows = parse_line31_sales(Path(line31["sales_source"]))
    anchor_rows = parse_line31_stock_anchor(Path(line31["stock_anchor_source"]))
    po1a_rows = parse_po1a_addback(
        Path(line31["po1a_arrived_quantities_csv"]),
        dict(line31["po1a_color_mapping"]),
        set(line31.get("po1a_quarantine_colors", [])),
        set(line31.get("po1a_physical_not_for_sale_reserve_colors", [])),
    )
    depletion_rows = _load_line31_db_proxy_depletion(PROJECT_ROOT / "db" / "app.db", line31["anchor_date"])
    stock_preview = build_line31_stock_preview(anchor_rows, po1a_rows, depletion_rows)

    sales_csv = out / "repaired_line31_sales_rows.csv"
    stock_csv = out / "repaired_line31_stock_preview.csv"
    _write_csv(sales_csv, sales_rows)
    _write_csv(stock_csv, stock_preview)

    sales_qty = sum(row["quantity"] for row in sales_rows)
    gross = sum(row["total_price_kzt"] for row in sales_rows)
    net = sum(row["total_net_rev_kzt"] for row in sales_rows)
    price_counter = Counter(row["sell_price_kzt"] for row in sales_rows)
    anchor_total = sum(row["anchor_qty"] for row in anchor_rows)
    po1a_mapped = sum(row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"] == "MAPPED_PO1A_ADD_BACK")
    po1a_reserve = sum(
        row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"] == "PHYSICAL_NOT_FOR_SALE_RESERVE"
    )
    po1a_quarantine = sum(row["po1a_addback_qty"] for row in po1a_rows if row["mapping_status"].startswith("QUARANTINED"))
    physical_depletion = sum(row["physical_depletion_qty"] for row in depletion_rows)
    economic_depletion = sum(row["economic_depletion_qty"] for row in depletion_rows)
    open_reserved = sum(row["open_reserved_qty"] for row in depletion_rows)
    physical_qty = anchor_total + po1a_mapped + po1a_reserve - physical_depletion
    available_qty = physical_qty - open_reserved
    economic_qty = anchor_total + po1a_mapped + po1a_reserve - economic_depletion

    proof_md = out / "repaired_line31_sales_stock_proof.md"
    proof_md.write_text(
        f"""# Repaired LINE31 Sales And Stock Proof

Gate: YELLOW_REPAIRED_LINE31_PROOF_WITH_DB_PROXY_DEPLETION

## Corrected Historical Sales Parse

- Sales source: `{line31['sales_source']}`
- Parsed LINE31 rows: `{len(sales_rows)}`
- Parsed quantity: `{sales_qty}`
- Sell price distribution: `{dict(price_counter)}` KZT
- Gross revenue: `{gross}` KZT
- Net revenue from source rows: `{net:.4f}` KZT

The repaired parser reads the Markdown sheet matrix and preserves the source
`Sell_price_kzt` field. The prior `{{0: 51}}` / gross `0` result is superseded
by this row-level parse.

## Stock Preview Basis

- April 13 LINE31 anchor source: `{line31['stock_anchor_source']}`
- April 13 full-set anchor total: `{anchor_total}` sets
- PO-1A source: `{line31['po1a_arrived_quantities_csv']}`
- PO-1A mapped addback: `{po1a_mapped}` sets
- PO-1A physical not-for-sale reserve: `{po1a_reserve}` sets
- PO-1A quarantined/unmapped: `{po1a_quarantine}` sets
- DB proxy physical shipped depletion after anchor: `{physical_depletion}` sets
- DB proxy economic completed depletion after anchor: `{economic_depletion}` sets
- DB proxy open reserved exposure after anchor: `{open_reserved}` sets

## Planning Preview Totals

| Metric | Qty |
| --- | ---: |
| Physical warehouse estimate | {physical_qty} |
| Available after open reserved exposure | {available_qty} |
| Economic final-sales stock estimate | {economic_qty} |
| PO-1A physical not-for-sale reserve | {po1a_reserve} |
| PO-1A unmapped quarantine | {po1a_quarantine} |

## Required Retained Blockers

- `WEBUI_STATUS_CHANGE_REPLAY_STILL_REQUIRED`: DB proxy depletion is useful but
  is not a final WebUI status-change ledger.
- `PHYSICAL_NOT_FOR_SALE_RESERVE`: Bean Paste Pink, Pomelo Pink, Eggplant
  Purple, and Whale Blue PO-1A units are physical reserve/non-live stock.
- `NO_LIVE_STOCK_OR_PRICE_ACTION_AUTHORIZED`: this proof is local evidence only.
""",
        encoding="utf-8",
    )

    summaries = {
        "rush31_canonical_identity_patch_summary.md": """# RUSH31 Canonical Identity Patch Summary

RUSH31 is canonicalized as independent product route `CL_NC_MEN_RUSH-31_BLACK`,
offer `165486887`, campaign `2794142`, product SKU `21282790b`, owner stock
total `290`. It must not be automatically classified as `LINE61_CHILD`, LINE31, or
LINE31S. Historical stale classifications are preserved only as superseded
evidence.
""",
        "owner_stock_override_integration_summary.md": """# Owner Stock Override Integration Summary

The owner override doc and CSV are validated as machine-readable planning truth.
Focused validation checks RUSH31, LINE61, LINE51 4XL zero, LINE52, and the LINE31
exception stack. No production stock, DB, or workbook surface was changed.
""",
        "gift_bag_cogs_contract_patch_summary.md": """# Gift-Bag COGS Contract Patch Summary

Internal COGS planning now requires `3 CNY` plus `0.10 kg` gift-bag weight effect
for current ACMEWEAR/Kaspi and near-term Instagram economics. Customer-facing
Kaspi copy does not automatically mention the gift bag.
""",
        "trm_opportunity_detector_contract_summary.md": """# TRM Opportunity Detector Contract Summary

Line61 TRM campaign `2629982` is a hold-and-monitor route: no cap lift while
spend is far below cap, and any bid test requires fresh preflight plus exact
owner approval. LINE51 TRM campaign `2690256` is a dry-run re-enable candidate
only. Marketing aggregate attribution must remain separate from API/order-level
product identity.
""",
        "retained_blockers.md": """# Retained Blockers

- `WEBUI_STATUS_CHANGE_REPLAY_STILL_REQUIRED`
- `PO1A_COLOR_OFFER_SKU_MAPPING_NOT_SOURCE_PROVEN`
- `RUSH31_LIVE_MAPPING_PREFLIGHT_REQUIRED_BEFORE_ANY_EXTERNAL_CHANGE`
- `GIFT_BAG_COGS_NEEDS_DOWNSTREAM_ECONOMICS_ADOPTION`
- `TRM_LIVE_ACTION_REQUIRES_EXACT_OWNER_APPROVAL`
- `DIRTY_REPO_PRODUCTION_PREFLIGHT_BLOCKED`
""",
        "next_live_preflight_recommendations.md": """# Next Live-Preflight Recommendations

Do not execute these in this lane.

1. RUSH31: read-only Kaspi/Web_automation preflight for offer `165486887`,
   campaign `2794142`, product SKU `21282790b`, current price, stock, bid,
   budget, and offer state.
2. LINE31: replace DB proxy depletion with WebUI status-change and shipping ledger
   replay before any production stock claim.
3. Gift-bag COGS: add downstream economics adoption only after reviewing each
   current COGS materializer/report surface.
4. Line61 TRM/LINE51 TRM: fresh read-only Marketing and stock/pricelist preflight
   before any exact owner approval phrase is used.
""",
    }
    for filename, text in summaries.items():
        (out / filename).write_text(text, encoding="utf-8")

    closeout = out / "canonicalization_closeout.md"
    closeout.write_text(
        f"""# Product Truth Canonicalization Wave Closeout

Gate: YELLOW

Generated: `{datetime.now().isoformat(timespec='seconds')}`

## Outputs

- `repaired_line31_sales_stock_proof.md`
- `repaired_line31_sales_rows.csv`
- `repaired_line31_stock_preview.csv`
- `rush31_canonical_identity_patch_summary.md`
- `owner_stock_override_integration_summary.md`
- `gift_bag_cogs_contract_patch_summary.md`
- `trm_opportunity_detector_contract_summary.md`
- `retained_blockers.md`
- `next_live_preflight_recommendations.md`

## Key Totals

- LINE31 historical sales rows: `{len(sales_rows)}`
- LINE31 historical sales quantity: `{sales_qty}`
- LINE31 historical gross revenue: `{gross}` KZT
- LINE31 April 13 anchor: `{anchor_total}` sets
- PO-1A mapped addback: `{po1a_mapped}` sets
- PO-1A physical not-for-sale reserve: `{po1a_reserve}` sets
- PO-1A quarantine: `{po1a_quarantine}` sets
- Physical warehouse estimate: `{physical_qty}` sets
- Available after open reserved exposure: `{available_qty}` sets
- Economic final-sales stock estimate: `{economic_qty}` sets

## Boundary

No production DB writes, workbook writes, source-pointer writes, scheduler
changes, Web_automation live writes, Kaspi/API/WebUI/Meta/CRM mutations,
campaign bid/budget/state changes, price changes, stock changes, supplier
messages, payment, PO commitment, owner publication, production preflight, or
production apply were authorized or performed.
""",
        encoding="utf-8",
    )

    manifest = {
        "gate": "YELLOW",
        "output_dir": str(out),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": str(config_path),
        "metrics": {
            "line31_sales_rows": len(sales_rows),
            "line31_sales_qty": sales_qty,
            "line31_gross_revenue_kzt": gross,
            "line31_net_revenue_kzt": round(net, 4),
            "line31_anchor_total_sets": anchor_total,
            "line31_po1a_mapped_sets": po1a_mapped,
            "line31_po1a_physical_not_for_sale_reserve_sets": po1a_reserve,
            "line31_po1a_quarantined_sets": po1a_quarantine,
            "line31_physical_depletion_db_proxy": physical_depletion,
            "line31_economic_depletion_db_proxy": economic_depletion,
            "line31_open_reserved_db_proxy": open_reserved,
            "line31_physical_warehouse_estimate": physical_qty,
            "line31_available_after_open_reserved": available_qty,
            "line31_economic_final_sales_stock_estimate": economic_qty,
        },
    }
    (out / "canonicalization_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--materialize-wave", action="store_true")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "exports" / "validation")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)

    result = validate_config(args.config, strict=args.strict)
    payload: dict[str, Any] = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "metrics": result.metrics,
    }
    if result.ok and args.materialize_wave:
        payload["materialized"] = materialize_wave(args.config, args.output_root, args.run_id)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("OK" if result.ok else "FAILED")
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        for warning in result.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
