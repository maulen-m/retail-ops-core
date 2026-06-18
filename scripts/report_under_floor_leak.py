#!/usr/bin/env python3
"""Report G-PRICE-03 under-floor sales leaks from read-only sales truth."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "under_floor_leak.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "under_floor_leak"

UNDER_FLOOR_COLUMNS = [
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "floor_sku_key",
    "floor_min_price_kzt",
    "floor_source",
    "floor_resolution_source",
    "gap_per_unit_kzt",
    "gap_total_kzt",
    "status",
    "kaspi_offer_name",
]

MISSING_FLOOR_COLUMNS = [
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "floor_sku_key",
    "floor_resolution_source",
    "status",
    "kaspi_offer_name",
]

MISSING_PRICE_COLUMNS = [
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "floor_sku_key",
    "floor_min_price_kzt",
    "floor_resolution_source",
    "status",
    "kaspi_offer_name",
]

BY_SKU_COLUMNS = [
    "sku_key",
    "floor_sku_key",
    "floor_min_price_kzt",
    "non_cancelled_rows",
    "non_cancelled_units",
    "under_floor_rows",
    "under_floor_units",
    "gap_total_kzt",
    "missing_floor_rows",
    "missing_price_rows",
    "min_sell_price_kzt",
    "stores",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _resolve_project_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _parse_as_of(value: str | None) -> date:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ).date()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if isinstance(parsed, datetime):
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ALMATY_TZ)
        return parsed.astimezone(ALMATY_TZ).date()
    return parsed


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    parsed = _as_float(value)
    if parsed is None:
        return 0
    return int(parsed)


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}"


def _status_is_non_cancelled(status: str, excluded_tokens: list[str]) -> bool:
    clean = status.strip().upper()
    return not any(token in clean for token in excluded_tokens)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _load_floor_rows(path: Path) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    rows: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        required = {"SKU_key", "Min_price_35pct"}
        missing = sorted(required - set(fieldnames))
        if missing:
            errors.append({"row": 0, "error": f"missing_columns:{','.join(missing)}"})
            return rows, fieldnames, errors
        for idx, row in enumerate(reader, start=2):
            sku_key = str(row.get("SKU_key") or "").strip()
            floor = _as_float(row.get("Min_price_35pct"))
            if not sku_key:
                errors.append({"row": idx, "error": "missing_sku_key"})
                continue
            if floor is None or floor <= 0:
                errors.append({"row": idx, "sku_key": sku_key, "error": "invalid_floor"})
                continue
            rows[sku_key] = {
                "sku_key": sku_key,
                "floor_min_price_kzt": float(floor),
                "floor_source": str(row.get("floor_source") or "").strip() or "floor_csv",
            }
    return rows, fieldnames, errors


def _alias_for(config: dict[str, Any], sku_key: str) -> tuple[str, str]:
    aliases = config.get("floor_aliases") or {}
    raw = aliases.get(sku_key)
    if raw is None:
        return sku_key, "exact"
    if isinstance(raw, str):
        return raw, "alias"
    if isinstance(raw, dict):
        target = str(raw.get("floor_sku_key") or "").strip()
        source = str(raw.get("source") or "alias").strip()
        return target or sku_key, f"alias:{source}"
    return sku_key, "exact"


def _load_sales_rows(conn: sqlite3.Connection, start_date: date, as_of_date: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            order_date,
            order_id,
            store_code,
            sku_key,
            sku_id,
            my_size,
            kaspi_offer_name,
            quantity,
            sell_price_kzt,
            status
        FROM sales_fact_v2
        WHERE date(order_date) >= date(?)
          AND date(order_date) <= date(?)
        ORDER BY date(order_date), store_code, sku_key, order_id, sku_id
        """,
        (start_date.isoformat(), as_of_date.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_sales_date(conn: sqlite3.Connection, as_of_date: date) -> date | None:
    row = conn.execute(
        """
        SELECT MAX(order_date) AS max_order_date
        FROM sales_fact_v2
        WHERE date(order_date) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    if not row or not row["max_order_date"]:
        return None
    return _parse_date(row["max_order_date"])


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-PRICE-03 Under-Floor Leak Report",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"As of: {report['as_of']}",
        f"Window: {report['window_start']}..{report['window_end']}",
        "",
        "## Summary",
        "",
        f"- total sales rows in window: {report['sales_row_count_total']}",
        f"- non-cancelled rows: {report['non_cancelled_row_count']}",
        f"- non-cancelled units: {report['non_cancelled_units']}",
        f"- under-floor rows: {report['under_floor_row_count']}",
        f"- under-floor units: {report['under_floor_units']}",
        f"- under-floor gap KZT: {report['under_floor_gap_kzt']}",
        f"- missing floor rows: {report['missing_floor_row_count']}",
        f"- missing price rows: {report['missing_price_row_count']}",
        f"- latest sales date: {report['latest_sales_date']}",
        f"- sales data lag days: {report['sales_data_lag_days']}",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- {mark} {check['check']}: {check['details']}")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    for name, path in report["artifacts"].items():
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    return "\n".join(lines)


def build_under_floor_leak_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    as_of_date = _parse_as_of(as_of)
    window_days = int(config.get("window_days") or 7)
    start_date = as_of_date - timedelta(days=max(window_days, 1) - 1)
    db_path = _resolve_project_path(config.get("db_path") or "db/app.db")
    floor_csv_path = _resolve_project_path(config.get("floor_csv_path") or "")
    excluded_tokens = [str(v).strip().upper() for v in (config.get("excluded_status_tokens") or ["CANCEL"]) if str(v).strip()]
    max_sales_lag_days = int(config.get("max_sales_data_lag_days") or 2)
    strict_missing_floor = bool(config.get("strict_missing_floor_blocks_green", True))
    strict_missing_price = bool(config.get("strict_missing_price_blocks_green", True))

    checks: list[dict[str, Any]] = []
    floor_rows: dict[str, dict[str, Any]] = {}
    floor_fieldnames: list[str] = []
    floor_errors: list[dict[str, Any]] = []
    if not floor_csv_path.exists():
        checks.append(_check(False, "floor_csv_present", str(floor_csv_path)))
    else:
        floor_rows, floor_fieldnames, floor_errors = _load_floor_rows(floor_csv_path)
        checks.append(_check(True, "floor_csv_present", str(floor_csv_path)))
    checks.append(
        _check(
            len(floor_rows) > 0 and not floor_errors,
            "floor_csv_valid",
            f"floor_rows={len(floor_rows)} errors={len(floor_errors)}",
            fieldnames=floor_fieldnames,
        )
    )

    sales_rows: list[dict[str, Any]] = []
    latest_sales: date | None = None
    if not db_path.exists():
        checks.append(_check(False, "db_path_present", str(db_path)))
    else:
        checks.append(_check(True, "db_path_present", str(db_path)))
        with _connect_readonly(db_path) as conn:
            checks.append(_check(_table_exists(conn, "sales_fact_v2"), "sales_fact_v2_present", "table exists"))
            if _table_exists(conn, "sales_fact_v2"):
                sales_rows = _load_sales_rows(conn, start_date, as_of_date)
                latest_sales = _latest_sales_date(conn, as_of_date)

    sales_lag_days: int | None = None
    if latest_sales is None:
        checks.append(_check(False, "sales_data_latest_date_present", "latest_sales_date missing"))
    else:
        sales_lag_days = max(0, (as_of_date - latest_sales).days)
        checks.append(
            _check(
                sales_lag_days <= max_sales_lag_days,
                "sales_data_fresh_enough",
                f"latest_sales_date={latest_sales.isoformat()} lag_days={sales_lag_days} max={max_sales_lag_days}",
            )
        )

    non_cancelled_rows: list[dict[str, Any]] = []
    under_floor_rows: list[dict[str, Any]] = []
    missing_floor_rows: list[dict[str, Any]] = []
    missing_price_rows: list[dict[str, Any]] = []
    by_sku: dict[tuple[str, str], dict[str, Any]] = {}

    for row in sales_rows:
        status = str(row.get("status") or "").strip()
        if not _status_is_non_cancelled(status, excluded_tokens):
            continue
        non_cancelled_rows.append(row)
        quantity = max(0, _as_int(row.get("quantity")))
        sku_key = str(row.get("sku_key") or "").strip()
        floor_sku_key, floor_resolution_source = _alias_for(config, sku_key)
        floor = floor_rows.get(floor_sku_key)
        sell_price = _as_float(row.get("sell_price_kzt"))
        bucket_key = (sku_key, floor_sku_key)
        bucket = by_sku.setdefault(
            bucket_key,
            {
                "sku_key": sku_key,
                "floor_sku_key": floor_sku_key,
                "floor_min_price_kzt": _fmt_money(floor["floor_min_price_kzt"]) if floor else "",
                "non_cancelled_rows": 0,
                "non_cancelled_units": 0,
                "under_floor_rows": 0,
                "under_floor_units": 0,
                "gap_total_kzt": 0.0,
                "missing_floor_rows": 0,
                "missing_price_rows": 0,
                "min_sell_price_kzt": None,
                "stores": set(),
            },
        )
        bucket["non_cancelled_rows"] += 1
        bucket["non_cancelled_units"] += quantity
        bucket["stores"].add(str(row.get("store_code") or "").strip())
        if sell_price is not None:
            current_min = bucket["min_sell_price_kzt"]
            bucket["min_sell_price_kzt"] = sell_price if current_min is None else min(float(current_min), sell_price)

        if floor is None:
            bucket["missing_floor_rows"] += 1
            missing_floor_rows.append(
                {
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "sell_price_kzt": _fmt_money(sell_price),
                    "floor_sku_key": floor_sku_key,
                    "floor_resolution_source": floor_resolution_source,
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )
            continue
        floor_min = float(floor["floor_min_price_kzt"])
        if sell_price is None:
            bucket["missing_price_rows"] += 1
            missing_price_rows.append(
                {
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "floor_sku_key": floor_sku_key,
                    "floor_min_price_kzt": _fmt_money(floor_min),
                    "floor_resolution_source": floor_resolution_source,
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )
            continue
        if sell_price < floor_min:
            gap_per_unit = floor_min - sell_price
            gap_total = gap_per_unit * quantity
            bucket["under_floor_rows"] += 1
            bucket["under_floor_units"] += quantity
            bucket["gap_total_kzt"] += gap_total
            under_floor_rows.append(
                {
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "sell_price_kzt": _fmt_money(sell_price),
                    "floor_sku_key": floor_sku_key,
                    "floor_min_price_kzt": _fmt_money(floor_min),
                    "floor_source": floor.get("floor_source", ""),
                    "floor_resolution_source": floor_resolution_source,
                    "gap_per_unit_kzt": _fmt_money(gap_per_unit),
                    "gap_total_kzt": _fmt_money(gap_total),
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )

    by_sku_rows: list[dict[str, Any]] = []
    for bucket in by_sku.values():
        by_sku_rows.append(
            {
                "sku_key": bucket["sku_key"],
                "floor_sku_key": bucket["floor_sku_key"],
                "floor_min_price_kzt": bucket["floor_min_price_kzt"],
                "non_cancelled_rows": bucket["non_cancelled_rows"],
                "non_cancelled_units": bucket["non_cancelled_units"],
                "under_floor_rows": bucket["under_floor_rows"],
                "under_floor_units": bucket["under_floor_units"],
                "gap_total_kzt": _fmt_money(float(bucket["gap_total_kzt"])),
                "missing_floor_rows": bucket["missing_floor_rows"],
                "missing_price_rows": bucket["missing_price_rows"],
                "min_sell_price_kzt": _fmt_money(bucket["min_sell_price_kzt"]),
                "stores": ";".join(sorted(v for v in bucket["stores"] if v)),
            }
        )
    by_sku_rows.sort(key=lambda row: (-int(row["under_floor_units"]), -int(row["missing_floor_rows"]), str(row["sku_key"])))
    under_floor_rows.sort(key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"])))
    missing_floor_rows.sort(key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"])))
    missing_price_rows.sort(key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"])))

    under_floor_units = sum(_as_int(row["quantity"]) for row in under_floor_rows)
    missing_floor_units = sum(_as_int(row["quantity"]) for row in missing_floor_rows)
    missing_price_units = sum(_as_int(row["quantity"]) for row in missing_price_rows)
    gap_total = sum(float(row["gap_total_kzt"] or 0) for row in under_floor_rows)
    non_cancelled_units = sum(max(0, _as_int(row.get("quantity"))) for row in non_cancelled_rows)

    checks.append(
        _check(
            under_floor_units == 0,
            "zero_under_floor_units",
            f"under_floor_rows={len(under_floor_rows)} under_floor_units={under_floor_units} gap_kzt={_fmt_money(gap_total)}",
        )
    )
    if strict_missing_floor:
        checks.append(
            _check(
                missing_floor_units == 0,
                "all_non_cancelled_rows_have_floor",
                f"missing_floor_rows={len(missing_floor_rows)} missing_floor_units={missing_floor_units}",
            )
        )
    if strict_missing_price:
        checks.append(
            _check(
                missing_price_units == 0,
                "all_non_cancelled_rows_have_sell_price",
                f"missing_price_rows={len(missing_price_rows)} missing_price_units={missing_price_units}",
            )
        )

    output_dir = output_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    under_floor_csv = output_dir / "under_floor_sales.csv"
    missing_floor_csv = output_dir / "missing_floor_sales.csv"
    missing_price_csv = output_dir / "missing_price_sales.csv"
    by_sku_csv = output_dir / "under_floor_by_sku.csv"
    _write_csv(under_floor_csv, UNDER_FLOOR_COLUMNS, under_floor_rows)
    _write_csv(missing_floor_csv, MISSING_FLOOR_COLUMNS, missing_floor_rows)
    _write_csv(missing_price_csv, MISSING_PRICE_COLUMNS, missing_price_rows)
    _write_csv(by_sku_csv, BY_SKU_COLUMNS, by_sku_rows)

    no_failures = all(row["ok"] for row in checks)
    gate = "GREEN" if no_failures else "RED"
    report: dict[str, Any] = {
        "generated_at": _now_almaty(),
        "as_of": as_of_date.isoformat(),
        "gate": gate,
        "status": gate,
        "ok": gate == "GREEN",
        "config_path": str(config_path.resolve()),
        "db_path": str(db_path),
        "db_open_mode": "ro",
        "sales_source_table": "sales_fact_v2",
        "floor_csv_path": str(floor_csv_path),
        "floor_version": str(config.get("floor_version") or ""),
        "floor_rows_loaded": len(floor_rows),
        "floor_errors": floor_errors,
        "floor_alias_count": len(config.get("floor_aliases") or {}),
        "window_days": window_days,
        "window_start": start_date.isoformat(),
        "window_end": as_of_date.isoformat(),
        "latest_sales_date": latest_sales.isoformat() if latest_sales else "",
        "sales_data_lag_days": sales_lag_days,
        "max_sales_data_lag_days": max_sales_lag_days,
        "sales_row_count_total": len(sales_rows),
        "non_cancelled_row_count": len(non_cancelled_rows),
        "non_cancelled_units": non_cancelled_units,
        "under_floor_row_count": len(under_floor_rows),
        "under_floor_units": under_floor_units,
        "under_floor_gap_kzt": _fmt_money(gap_total),
        "missing_floor_row_count": len(missing_floor_rows),
        "missing_floor_units": missing_floor_units,
        "missing_price_row_count": len(missing_price_rows),
        "missing_price_units": missing_price_units,
        "checks": checks,
        "artifacts": {
            "under_floor_sales_csv": str(under_floor_csv),
            "missing_floor_sales_csv": str(missing_floor_csv),
            "missing_price_sales_csv": str(missing_price_csv),
            "under_floor_by_sku_csv": str(by_sku_csv),
        },
        "production_db_written": False,
        "external_writes_performed": False,
        "forbidden_writes_performed": False,
    }
    json_path = output_dir / "under_floor_leak_report.json"
    md_path = output_dir / "under_floor_leak_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Report G-PRICE-03 under-floor leak status.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true", help="Return non-zero unless gate is GREEN.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_under_floor_leak_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"ok: {report['ok']}")
        print(f"under_floor_units: {report['under_floor_units']}")
        print(f"missing_floor_rows: {report['missing_floor_row_count']}")
        print(f"Report: {report['json_path']}")
    if args.strict and report["gate"] != "GREEN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
