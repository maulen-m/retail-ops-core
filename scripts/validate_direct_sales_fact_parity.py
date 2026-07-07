#!/usr/bin/env python3
"""Validate Phase 1 direct feeder shadow rows against the CRM workbook lane."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CRM = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "decommission" / "crm_excel_shadow"

sys.path.insert(0, str(PROJECT_ROOT))

from core.ingest.sales_ingest import normalize_store_code, resolve_sales_identity_detail  # noqa: E402
from core.utils.sku_normalize import normalize_sku_key, normalize_size  # noqa: E402
from scripts.feed_fact_orders_kaspi_to_sales_fact_v2 import (  # noqa: E402
    SHADOW_COLUMNS,
    UNMAPPED_COLUMNS,
    _clean_text,
    _connect_readonly,
    _date_text,
    _parse_date,
    _table_exists,
    _to_float,
    _to_int,
)


BASELINE_COLUMNS = [
    "source_lane",
    "order_id",
    "order_date",
    "planned_shipment_date",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "kaspi_offer_name",
    "quantity",
    "sell_price_kzt",
    "delivery_fee",
    "net_rev",
    "status",
    "return_flag",
    "logical_dedupe_key",
    "db_unique_key",
]

ROW_DIFF_COLUMNS = [
    "severity",
    "diff_type",
    "order_id",
    "store_code",
    "kaspi_offer_name",
    "sku_key",
    "sku_id",
    "my_size",
    "field",
    "crm_value",
    "direct_value",
    "match_key_type",
]

DATE_BASIS_COLUMNS = [
    "order_id",
    "store_code",
    "kaspi_offer_name",
    "sku_key",
    "sku_id",
    "my_size",
    "crm_order_date",
    "direct_order_date",
    "explained_by",
]


HEADER_ALIASES = {
    "order_id": ["orderid", "order_id", "№ заказа"],
    "order_date": ["date", "order_date", "дата поступления заказа"],
    "planned_shipment_date": ["planned_shipping_date", "плановая дата передачи курьеру"],
    "kaspi_offer_name": ["kaspi_offer_name", "название товара в kaspi магазине"],
    "sku_id": ["sku_id", "skuid"],
    "sku_key": ["sku_key", "skukey"],
    "my_size": ["my_size", "mysize", "size"],
    "quantity": ["quantity", "qty", "количество"],
    "sell_price_kzt": ["sell_price_kzt", "price", "цена", "сумма"],
    "total_price": ["total_price", "totalprice"],
    "store_name": ["store_name", "storename", "store"],
    "return_flag": ["return", "return_flag"],
    "status": ["status"],
    "net_rev": ["total_net_rev", "net_rev"],
    "delivery_fee": ["delivery_fee_kzt", "delivery_fee"],
    "delivery_fee_seller": ["delivery_fee_seller", "стоимость доставки для продавца"],
    "delivery_fee_buyer": ["delivery_fee_buyer", "стоимость доставки для покупателя"],
    "product_type": ["product_type"],
}


def _canonical_header(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _header_indexes(headers: list[Any]) -> dict[str, int]:
    normalized = [_canonical_header(header).replace("_", " ") for header in headers]
    indexes: dict[str, int] = {}
    for target, aliases in HEADER_ALIASES.items():
        alias_norm = {_canonical_header(alias).replace("_", " ") for alias in aliases}
        for idx, header in enumerate(normalized):
            if header in alias_norm:
                indexes[target] = idx
                break
    return indexes


def _cell(row: tuple[Any, ...], indexes: dict[str, int], key: str) -> Any:
    idx = indexes.get(key)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _truthy(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "returned", "return", "возврат"}


def _num_text(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    if float(number).is_integer():
        return str(int(number))
    return str(number)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _numbers_equal(left: Any, right: Any) -> bool:
    return _decimal(left) == _decimal(right)


def _primary_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("order_id") or ""),
        str(row.get("store_code") or ""),
        str(row.get("kaspi_offer_name") or ""),
        str(row.get("sku_key") or ""),
        str(row.get("my_size") or ""),
    )


def _fallback_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("order_id") or ""),
        str(row.get("store_code") or ""),
        str(row.get("kaspi_offer_name") or ""),
        str(row.get("sku_id") or ""),
    )


def _key_text(key: tuple[Any, ...]) -> str:
    return "|".join(str(part or "") for part in key)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _resolve_workbook_identity(
    conn: sqlite3.Connection,
    *,
    sku_id: str | None,
    sku_key: str | None,
    my_size: str | None,
    product_type: str | None,
    kaspi_offer_name: str,
    store_code: str,
) -> tuple[str | None, str | None, str | None]:
    normalized_key = normalize_sku_key(sku_key) if sku_key else None
    normalized_size = normalize_size(my_size, product_type=product_type) if my_size else None
    resolution = resolve_sales_identity_detail(
        conn,
        sku_id,
        normalized_key,
        normalized_size,
        kaspi_offer_name,
        store_code,
    )
    return resolution.sku_key, resolution.sku_id, resolution.my_size


def load_crm_baseline_rows(
    conn: sqlite3.Connection,
    *,
    crm_file: Path,
    sheet_name: str,
    from_date: str,
    to_date: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    start = _parse_date(from_date)
    end = _parse_date(to_date)
    if not start or not end:
        raise ValueError("from-date and to-date must be YYYY-MM-DD")

    wb = load_workbook(crm_file, read_only=True, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"sheet not found: {sheet_name}")
        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)
        headers = next(rows_iter)
        indexes = _header_indexes(list(headers))
        required = {"order_id", "order_date", "kaspi_offer_name", "quantity"}
        missing = sorted(required - set(indexes))
        if missing:
            raise ValueError(f"CRM workbook missing required headers: {missing}")

        baseline: list[dict[str, Any]] = []
        unmapped: list[dict[str, Any]] = []
        for row in rows_iter:
            order_date = _parse_date(_cell(row, indexes, "order_date"))
            if not order_date or order_date < start or order_date > end:
                continue
            order_id = _clean_text(_cell(row, indexes, "order_id")) or ""
            kaspi_offer_name = _clean_text(_cell(row, indexes, "kaspi_offer_name")) or ""
            if not order_id or not kaspi_offer_name:
                continue
            store_code = normalize_store_code(_clean_text(_cell(row, indexes, "store_name")) or "UNIVERSAL")
            sku_id = _clean_text(_cell(row, indexes, "sku_id"))
            sku_key = _clean_text(_cell(row, indexes, "sku_key"))
            my_size = _clean_text(_cell(row, indexes, "my_size"))
            product_type = _clean_text(_cell(row, indexes, "product_type"))
            resolved_key, resolved_id, resolved_size = _resolve_workbook_identity(
                conn,
                sku_id=sku_id,
                sku_key=sku_key,
                my_size=my_size,
                product_type=product_type,
                kaspi_offer_name=kaspi_offer_name,
                store_code=store_code,
            )
            if not resolved_key or not resolved_id or not resolved_size:
                unmapped.append(
                    {
                        "run_id": "",
                        "source_lane": "crm_baseline",
                        "reason": "unresolved_identity",
                        "source_row_id": "",
                        "order_id": order_id,
                        "store_code": store_code,
                        "line_identity_key": "",
                        "kaspi_offer_name": kaspi_offer_name,
                        "source_sku_key": sku_key or "",
                        "source_sku_id": sku_id or "",
                        "assigned_size": "",
                        "my_size": my_size or "",
                        "final_my_size": resolved_size or "",
                        "size_source": "CRM_MY_SIZE",
                        "created_date": "",
                        "planned_shipment_date": _date_text(_cell(row, indexes, "planned_shipment_date")),
                        "actual_shipment_date": "",
                        "status_updated_date": "",
                    }
                )
                continue
            quantity = _to_int(_cell(row, indexes, "quantity"), 1) or 1
            sell_price = _to_float(_cell(row, indexes, "sell_price_kzt"))
            if sell_price is None:
                total_price = _to_float(_cell(row, indexes, "total_price"))
                if total_price is not None and quantity:
                    sell_price = total_price / quantity
            seller_fee = _to_float(_cell(row, indexes, "delivery_fee_seller"))
            legacy_fee = _to_float(_cell(row, indexes, "delivery_fee"))
            buyer_fee = _to_float(_cell(row, indexes, "delivery_fee_buyer"))
            delivery_fee = seller_fee if seller_fee is not None else legacy_fee
            if delivery_fee is None:
                delivery_fee = buyer_fee
            return_flag = 1 if _truthy(_cell(row, indexes, "return_flag")) else 0
            status = "RETURNED" if return_flag else "DELIVERED"
            out = {
                "source_lane": "crm_baseline",
                "order_id": order_id,
                "order_date": order_date.isoformat(),
                "planned_shipment_date": _date_text(_cell(row, indexes, "planned_shipment_date")),
                "store_code": store_code,
                "sku_key": resolved_key,
                "sku_id": resolved_id,
                "my_size": resolved_size,
                "kaspi_offer_name": kaspi_offer_name,
                "quantity": quantity,
                "sell_price_kzt": _num_text(sell_price),
                "delivery_fee": _num_text(delivery_fee),
                "net_rev": _num_text(_cell(row, indexes, "net_rev")),
                "status": status,
                "return_flag": return_flag,
            }
            out["logical_dedupe_key"] = _key_text(_primary_key(out))
            out["db_unique_key"] = _key_text(_fallback_key(out))
            baseline.append(out)
        baseline.sort(key=lambda r: (r["order_date"], r["order_id"], r["store_code"], r["kaspi_offer_name"], r["sku_id"]))
        return baseline, unmapped
    finally:
        wb.close()


def _sales_fact_count(conn: sqlite3.Connection, from_date: str, to_date: str) -> int:
    if not _table_exists(conn, "sales_fact_v2"):
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM sales_fact_v2 WHERE order_date BETWEEN ? AND ?",
        (from_date, to_date),
    ).fetchone()
    return int(row["c"] or 0)


def _index_rows(rows: list[dict[str, Any]], key_func) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    indexed: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for idx, row in enumerate(rows):
        row["_row_index"] = str(idx)
        indexed[key_func(row)].append(row)
    return indexed


def _row_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": row.get("order_id", ""),
        "store_code": row.get("store_code", ""),
        "kaspi_offer_name": row.get("kaspi_offer_name", ""),
        "sku_key": row.get("sku_key", ""),
        "sku_id": row.get("sku_id", ""),
        "my_size": row.get("my_size", ""),
    }


def _diff_row(
    *,
    severity: str,
    diff_type: str,
    row: dict[str, Any],
    field: str = "",
    crm_value: Any = "",
    direct_value: Any = "",
    match_key_type: str = "",
) -> dict[str, Any]:
    out = {
        "severity": severity,
        "diff_type": diff_type,
        **_row_identity(row),
        "field": field,
        "crm_value": crm_value,
        "direct_value": direct_value,
        "match_key_type": match_key_type,
    }
    return out


def _classify_date_basis_diff(crm_row: dict[str, Any], direct_row: dict[str, Any]) -> str | None:
    crm_date = _parse_date(crm_row.get("order_date"))
    direct_date = _parse_date(direct_row.get("order_date"))
    if crm_date == direct_date:
        return None
    explanations = []
    for column in (
        "planned_shipment_date",
        "created_date",
        "source_order_date",
        "actual_shipment_date",
        "courier_transmission_date",
        "status_updated_date",
    ):
        candidate = _parse_date(direct_row.get(column))
        if candidate and candidate == crm_date:
            explanations.append(f"crm_date_matches_{column}")
    if explanations:
        known = ""
        known_dates = {date(2026, 7, 4), date(2026, 7, 5)}
        if crm_date in known_dates or direct_date in known_dates:
            known = "known_2026_07_04_07_05:"
        return known + ",".join(explanations)
    return None


def compare_rows(
    *,
    crm_rows: list[dict[str, Any]],
    direct_rows: list[dict[str, Any]],
    direct_unmapped: list[dict[str, Any]],
    crm_unmapped: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    date_basis_rows: list[dict[str, Any]] = []
    matched_direct_indexes: set[str] = set()
    matched = 0

    direct_primary = _index_rows(direct_rows, _primary_key)
    direct_fallback = _index_rows(direct_rows, _fallback_key)

    for key, rows in direct_primary.items():
        if len(rows) > 1:
            diffs.append(
                _diff_row(
                    severity="RED",
                    diff_type="duplicate_direct_logical_key",
                    row=rows[0],
                    field="logical_dedupe_key",
                    direct_value=_key_text(key),
                )
            )
    for key, rows in direct_fallback.items():
        if len(rows) > 1:
            diffs.append(
                _diff_row(
                    severity="RED",
                    diff_type="duplicate_direct_db_unique_key",
                    row=rows[0],
                    field="db_unique_key",
                    direct_value=_key_text(key),
                )
            )

    for crm_row in crm_rows:
        direct_row = None
        match_key_type = "primary"
        primary_matches = direct_primary.get(_primary_key(crm_row), [])
        for candidate in primary_matches:
            if candidate.get("_row_index") not in matched_direct_indexes:
                direct_row = candidate
                break
        if direct_row is None:
            match_key_type = "fallback"
            fallback_matches = direct_fallback.get(_fallback_key(crm_row), [])
            for candidate in fallback_matches:
                if candidate.get("_row_index") not in matched_direct_indexes:
                    direct_row = candidate
                    break
        if direct_row is None:
            diffs.append(
                _diff_row(
                    severity="RED",
                    diff_type="missing_direct_row",
                    row=crm_row,
                    field="key",
                    crm_value=crm_row.get("logical_dedupe_key"),
                    direct_value="",
                    match_key_type="none",
                )
            )
            continue

        matched += 1
        matched_direct_indexes.add(str(direct_row["_row_index"]))
        field_mismatches = []
        if _to_int(crm_row.get("quantity"), 0) != _to_int(direct_row.get("quantity"), 0):
            field_mismatches.append(("quantity", crm_row.get("quantity"), direct_row.get("quantity")))
        if not _numbers_equal(crm_row.get("sell_price_kzt"), direct_row.get("sell_price_kzt")):
            field_mismatches.append(("sell_price_kzt", crm_row.get("sell_price_kzt"), direct_row.get("sell_price_kzt")))
        if str(crm_row.get("status") or "").upper() != str(direct_row.get("status") or "").upper():
            field_mismatches.append(("status", crm_row.get("status"), direct_row.get("status")))
        if str(crm_row.get("my_size") or "") != str(direct_row.get("my_size") or ""):
            field_mismatches.append(("my_size", crm_row.get("my_size"), direct_row.get("my_size")))
        if str(crm_row.get("sku_key") or "") != str(direct_row.get("sku_key") or ""):
            field_mismatches.append(("sku_key", crm_row.get("sku_key"), direct_row.get("sku_key")))
        if str(crm_row.get("sku_id") or "") != str(direct_row.get("sku_id") or ""):
            field_mismatches.append(("sku_id", crm_row.get("sku_id"), direct_row.get("sku_id")))

        date_explanation = _classify_date_basis_diff(crm_row, direct_row)
        same_date = _parse_date(crm_row.get("order_date")) == _parse_date(direct_row.get("order_date"))
        if field_mismatches:
            for field, crm_value, direct_value in field_mismatches:
                diffs.append(
                    _diff_row(
                        severity="RED",
                        diff_type="field_mismatch",
                        row=crm_row,
                        field=field,
                        crm_value=crm_value,
                        direct_value=direct_value,
                        match_key_type=match_key_type,
                    )
                )
            if not same_date:
                diffs.append(
                    _diff_row(
                        severity="RED",
                        diff_type="date_mismatch_with_field_mismatch",
                        row=crm_row,
                        field="order_date",
                        crm_value=crm_row.get("order_date"),
                        direct_value=direct_row.get("order_date"),
                        match_key_type=match_key_type,
                    )
                )
        elif not same_date:
            if date_explanation:
                date_basis_rows.append(
                    {
                        **_row_identity(crm_row),
                        "crm_order_date": crm_row.get("order_date"),
                        "direct_order_date": direct_row.get("order_date"),
                        "explained_by": date_explanation,
                    }
                )
            else:
                diffs.append(
                    _diff_row(
                        severity="RED",
                        diff_type="unclassified_date_mismatch",
                        row=crm_row,
                        field="order_date",
                        crm_value=crm_row.get("order_date"),
                        direct_value=direct_row.get("order_date"),
                        match_key_type=match_key_type,
                    )
                )

    for direct_row in direct_rows:
        if str(direct_row.get("_row_index")) in matched_direct_indexes:
            continue
        diffs.append(
            _diff_row(
                severity="RED",
                diff_type="extra_direct_row",
                row=direct_row,
                field="key",
                crm_value="",
                direct_value=direct_row.get("logical_dedupe_key", ""),
                match_key_type="none",
            )
        )

    crm_unmapped_keys = {
        (row.get("order_id", ""), row.get("store_code", ""), row.get("kaspi_offer_name", ""))
        for row in crm_unmapped
    }
    for row in direct_unmapped:
        key = (row.get("order_id", ""), row.get("store_code", ""), row.get("kaspi_offer_name", ""))
        if key not in crm_unmapped_keys:
            diffs.append(
                _diff_row(
                    severity="RED",
                    diff_type="unmapped_regression",
                    row=row,
                    field="reason",
                    crm_value="",
                    direct_value=row.get("reason", ""),
                    match_key_type="unmapped_key",
                )
            )

    summary_counts = {
        "matched": matched,
        "true_mismatches": len([row for row in diffs if row["severity"] == "RED"]),
        "date_basis_classified": len(date_basis_rows),
    }
    return diffs, date_basis_rows, summary_counts


def _load_direct_rows(path: Path) -> list[dict[str, Any]]:
    rows = _read_csv(path)
    normalized = []
    for row in rows:
        out = {column: row.get(column, "") for column in SHADOW_COLUMNS}
        if not out.get("logical_dedupe_key"):
            out["logical_dedupe_key"] = _key_text(_primary_key(out))
        if not out.get("db_unique_key"):
            out["db_unique_key"] = _key_text(_fallback_key(out))
        normalized.append(out)
    return normalized


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Direct Sales Fact Parity Summary",
        "",
        f"Gate: {summary['verdict']}",
        "",
        f"- window: {summary['from_date']}..{summary['to_date']}",
        f"- baseline_rows: {summary['baseline_rows']}",
        f"- shadow_rows: {summary['shadow_rows']}",
        f"- sales_fact_v2_rows: {summary['sales_fact_v2_rows']}",
        f"- matched: {summary['matched']}",
        f"- date_basis_classified: {summary['date_basis_classified']}",
        f"- unmapped: {summary['unmapped']}",
        f"- missing_size: {summary['missing_size']}",
        f"- true_mismatches: {summary['true_mismatches']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_parity(
    *,
    db_path: Path,
    crm_file: Path,
    crm_sheet: str,
    direct_shadow: Path,
    from_date: str,
    to_date: str,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    direct_rows = _load_direct_rows(direct_shadow)
    source_unmapped_path = direct_shadow.parent / "unmapped_rows.csv"
    direct_unmapped = _read_csv(source_unmapped_path)

    with _connect_readonly(db_path) as conn:
        crm_rows, crm_unmapped = load_crm_baseline_rows(
            conn,
            crm_file=crm_file,
            sheet_name=crm_sheet,
            from_date=from_date,
            to_date=to_date,
        )
        sales_fact_rows = _sales_fact_count(conn, from_date, to_date)

    diffs, date_basis_rows, counts = compare_rows(
        crm_rows=crm_rows,
        direct_rows=direct_rows,
        direct_unmapped=direct_unmapped,
        crm_unmapped=crm_unmapped,
    )

    all_unmapped = []
    for row in crm_unmapped:
        out = {column: row.get(column, "") for column in UNMAPPED_COLUMNS}
        all_unmapped.append(out)
    for row in direct_unmapped:
        out = {column: row.get(column, "") for column in UNMAPPED_COLUMNS}
        all_unmapped.append(out)

    missing_size = sum(1 for row in all_unmapped if row.get("reason") == "missing_size")
    if counts["true_mismatches"] > 0 or not crm_rows or not direct_rows:
        verdict = "RED"
    elif date_basis_rows:
        verdict = "GREEN_WITH_DATE_BASIS_DIFF"
    else:
        verdict = "GREEN"

    summary = {
        "verdict": verdict,
        "from_date": from_date,
        "to_date": to_date,
        "baseline_rows": len(crm_rows),
        "shadow_rows": len(direct_rows),
        "sales_fact_v2_rows": sales_fact_rows,
        "matched": counts["matched"],
        "date_basis_classified": len(date_basis_rows),
        "unmapped": len(all_unmapped),
        "missing_size": missing_size,
        "true_mismatches": counts["true_mismatches"],
        "diff_breakdown": dict(Counter(row["diff_type"] for row in diffs)),
    }

    target_shadow = out_dir / "direct_feeder_shadow_rows.csv"
    if direct_shadow.resolve() != target_shadow.resolve():
        shutil.copyfile(direct_shadow, target_shadow)
    else:
        _write_csv(target_shadow, direct_rows, SHADOW_COLUMNS)
    _write_csv(out_dir / "crm_baseline_rows.csv", crm_rows, BASELINE_COLUMNS)
    _write_csv(out_dir / "row_diff.csv", diffs, ROW_DIFF_COLUMNS)
    _write_csv(out_dir / "date_basis_diff.csv", date_basis_rows, DATE_BASIS_COLUMNS)
    _write_csv(out_dir / "unmapped_rows.csv", all_unmapped, UNMAPPED_COLUMNS)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_summary_md(out_dir / "summary.md", summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--crm-sheet", default=DEFAULT_SHEET)
    parser.add_argument("--direct-shadow", type=Path, required=True)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir or DEFAULT_OUTPUT_ROOT / date.today().isoformat() / "manual_parity"
    summary = validate_parity(
        db_path=args.db,
        crm_file=args.crm_file,
        crm_sheet=args.crm_sheet,
        direct_shadow=args.direct_shadow,
        from_date=args.from_date,
        to_date=args.to_date,
        out_dir=out_dir,
    )
    print(json.dumps({**summary, "out_dir": str(out_dir)}, sort_keys=True))
    return 0 if summary["verdict"] in {"GREEN", "GREEN_WITH_DATE_BASIS_DIFF"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
