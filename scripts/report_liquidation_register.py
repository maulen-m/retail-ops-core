#!/usr/bin/env python3
"""Build the G-LIQ-01 fresh liquidation register and A-E segment map."""

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

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "liquidation_register.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "liquidation_register"

SEGMENTS = {
    "A": "A_COUNT_GATED",
    "B": "B_ZERO_VELOCITY",
    "C": "C_SLOW_HIGH_COVER",
    "D": "D_SIZE_MISALLOCATED",
    "E": "E_STRATEGIC_NO_ACTION",
}

REGISTER_COLUMNS = [
    "sku_key",
    "segment_code",
    "segment",
    "segment_reason",
    "stock_units",
    "snapshot_size_rows",
    "positive_size_rows",
    "negative_size_rows",
    "goods_basis_kzt_known_cogs",
    "missing_cogs_positive_size_rows",
    "delivered_30d_units",
    "non_cancelled_30d_units",
    "delivered_90d_units",
    "june_non_cancelled_units",
    "days_cover_30d",
    "prior_canonical_tranche1",
    "tranche_sizing_allowed",
    "hold_reason",
]

SEGMENT_COLUMNS = [
    "sku_key",
    "segment_code",
    "segment",
    "segment_reason",
    "stock_units",
    "goods_basis_kzt_known_cogs",
    "delivered_30d_units",
    "june_non_cancelled_units",
    "days_cover_30d",
    "prior_canonical_tranche1",
    "tranche_sizing_allowed",
    "hold_reason",
]

SIZE_COLUMNS = [
    "snapshot_date",
    "sku_id",
    "sku_key",
    "my_size",
    "current_stock",
    "inbound_stock",
    "dim_sku_present",
    "cogs_kzt",
    "stock_value_kzt_known_cogs",
    "delivered_30d_units",
    "delivered_90d_units",
    "june_non_cancelled_units",
    "size_zero_recent_movement",
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
    return PROJECT_ROOT / path


def _parse_as_of(value: str | None) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return 0


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fmt_number(value: float | int | None, *, digits: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _latest_snapshot_date(conn: sqlite3.Connection, as_of_date: date) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(snapshot_date) AS snapshot_date
        FROM fact_inventory_snapshot_size
        WHERE date(snapshot_date) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    return str(row["snapshot_date"]) if row and row["snapshot_date"] else None


def _load_snapshot_rows(conn: sqlite3.Connection, snapshot_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            f.snapshot_date,
            f.sku_id,
            f.sku_key,
            f.my_size,
            f.current_stock,
            f.inbound_stock,
            d.sku_key AS dim_sku_key,
            d.model,
            d.color,
            d.product_type,
            d.category,
            d.gender,
            d.active_flag,
            d.cogs_kzt
        FROM fact_inventory_snapshot_size f
        LEFT JOIN dim_sku d ON d.sku_key = f.sku_key
        WHERE f.snapshot_date = ?
        ORDER BY f.sku_key, f.my_size, f.sku_id
        """,
        (snapshot_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_sales_rows(conn: sqlite3.Connection, start_date: date, as_of_date: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sku_key, my_size, order_date, quantity, status
        FROM sales_fact_v2
        WHERE date(order_date) >= date(?)
          AND date(order_date) <= date(?)
        """,
        (start_date.isoformat(), as_of_date.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _new_family() -> dict[str, Any]:
    return {
        "sku_key": "",
        "stock_units": 0,
        "snapshot_size_rows": 0,
        "positive_size_rows": 0,
        "negative_size_rows": 0,
        "goods_basis_kzt_known_cogs": 0.0,
        "missing_cogs_positive_size_rows": 0,
        "delivered_30d_units": 0,
        "non_cancelled_30d_units": 0,
        "delivered_90d_units": 0,
        "june_non_cancelled_units": 0,
    }


def _status_is_delivered(status: str, delivered_statuses: set[str]) -> bool:
    return status.strip().upper() in delivered_statuses


def _status_is_non_cancelled(status: str, excluded_tokens: list[str]) -> bool:
    clean = status.strip().upper()
    return not any(token in clean for token in excluded_tokens)


def _aggregate_sales(
    sales_rows: list[dict[str, Any]],
    *,
    as_of_date: date,
    delivered_statuses: set[str],
    excluded_cancel_tokens: list[str],
    zero_velocity_window_days: int,
) -> tuple[dict[str, dict[str, int]], dict[tuple[str, str], dict[str, int]]]:
    family: dict[str, dict[str, int]] = {}
    size: dict[tuple[str, str], dict[str, int]] = {}
    start_30 = as_of_date - timedelta(days=max(zero_velocity_window_days, 1) - 1)
    start_90 = as_of_date - timedelta(days=89)
    start_month = as_of_date.replace(day=1)

    for row in sales_rows:
        order_date = _parse_date(row.get("order_date"))
        if order_date is None:
            continue
        sku_key = str(row.get("sku_key") or "").strip()
        my_size = str(row.get("my_size") or "").strip()
        if not sku_key:
            continue
        qty = _as_int(row.get("quantity"))
        status = str(row.get("status") or "")
        fam_bucket = family.setdefault(
            sku_key,
            {
                "delivered_30d_units": 0,
                "non_cancelled_30d_units": 0,
                "delivered_90d_units": 0,
                "june_non_cancelled_units": 0,
            },
        )
        size_bucket = size.setdefault(
            (sku_key, my_size),
            {
                "delivered_30d_units": 0,
                "delivered_90d_units": 0,
                "june_non_cancelled_units": 0,
            },
        )
        if order_date >= start_30 and _status_is_non_cancelled(status, excluded_cancel_tokens):
            fam_bucket["non_cancelled_30d_units"] += qty
        if order_date >= start_month and _status_is_non_cancelled(status, excluded_cancel_tokens):
            fam_bucket["june_non_cancelled_units"] += qty
            size_bucket["june_non_cancelled_units"] += qty
        if _status_is_delivered(status, delivered_statuses):
            if order_date >= start_30:
                fam_bucket["delivered_30d_units"] += qty
                size_bucket["delivered_30d_units"] += qty
            if order_date >= start_90:
                fam_bucket["delivered_90d_units"] += qty
                size_bucket["delivered_90d_units"] += qty
    return family, size


def _is_size_misallocated(
    *,
    size_rows: list[dict[str, Any]],
    size_sales: dict[tuple[str, str], dict[str, int]],
) -> bool:
    positive_sizes = [
        row
        for row in size_rows
        if _as_int(row.get("current_stock")) > 0
    ]
    if len(positive_sizes) < 2:
        return False
    sold_sizes = 0
    unsold_stock_sizes = 0
    for row in positive_sizes:
        key = (str(row.get("sku_key") or "").strip(), str(row.get("my_size") or "").strip())
        delivered_90d = (size_sales.get(key) or {}).get("delivered_90d_units", 0)
        if delivered_90d > 0:
            sold_sizes += 1
        else:
            unsold_stock_sizes += 1
    return sold_sizes > 0 and unsold_stock_sizes > 0


def _segment_family(
    family: dict[str, Any],
    *,
    size_rows: list[dict[str, Any]],
    size_sales: dict[tuple[str, str], dict[str, int]],
    config: dict[str, Any],
) -> tuple[str, str]:
    sku_key = str(family["sku_key"])
    count_gated = {str(v) for v in config.get("count_gated_sku_keys") or []}
    if sku_key in count_gated:
        return "A", "count-gated by owner/liquidation protocol"
    if int(family["delivered_30d_units"]) <= 0:
        return "B", "zero delivered units in the 30-day velocity window"
    days_cover = family.get("days_cover_30d")
    slow_cover_days = float(config.get("slow_cover_days") or 90)
    if days_cover is not None and float(days_cover) >= slow_cover_days:
        return "C", f"30-day cover {float(days_cover):.1f}d >= {slow_cover_days:.0f}d"
    if _is_size_misallocated(size_rows=size_rows, size_sales=size_sales):
        return "D", "positive stock includes size(s) with zero 90-day size-level movement"
    return "E", "recent movement does not meet liquidation criteria"


def _hold_reason(family: dict[str, Any], segment_code: str) -> str:
    reasons: list[str] = []
    if segment_code == "A":
        reasons.append("count_gated")
    if int(family["missing_cogs_positive_size_rows"]) > 0:
        reasons.append("missing_positive_stock_cogs")
    if int(family["negative_size_rows"]) > 0:
        reasons.append("negative_size_row_present")
    return ";".join(reasons)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-LIQ-01 Liquidation Register Report",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Snapshot date: `{report['latest_snapshot_date']}`",
        f"Snapshot age days: `{report['snapshot_age_days']}`",
        "",
        "## Summary",
        "",
        f"- snapshot_rows: `{report['snapshot_row_count']}`",
        f"- positive_stock_family_count: `{report['positive_stock_family_count']}`",
        f"- positive_stock_units: `{report['positive_stock_units']}`",
        f"- goods_basis_kzt_known_cogs: `{report['goods_basis_kzt_known_cogs']}`",
        f"- missing_cogs_positive_size_rows: `{report['missing_cogs_positive_size_rows']}`",
        f"- negative_snapshot_size_rows: `{report['negative_snapshot_size_rows']}`",
        f"- segment_counts: `{report['segment_counts']}`",
        "",
        "## Movement Watch",
        "",
        "| sku_key | stock_units | segment | june_non_cancelled_units | delivered_30d_units | days_cover_30d |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in report["movement_watch"]:
        lines.append(
            "| {sku_key} | {stock_units} | {segment} | {june_non_cancelled_units} | "
            "{delivered_30d_units} | {days_cover_30d} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | status | details |",
            "|---|---:|---|",
        ]
    )
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.append("")
    return "\n".join(lines)


def build_liquidation_register_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    config_path = config_path.resolve()
    if config_path.exists():
        config = _load_json(config_path)
        checks.append(_check(True, "config_present", str(config_path)))
    else:
        config = {}
        checks.append(_check(False, "config_present", f"missing: {config_path}"))
    checks.append(
        _check(
            config.get("contract_id") == "LIQUIDATION_REGISTER_V1" and config.get("gate_id") == "G-LIQ-01",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )

    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    db_path = _resolve_project_path(config.get("db_path", "db/app.db"))
    checks.append(_check(db_path.exists(), "db_present", str(db_path)))

    conn: sqlite3.Connection | None = None
    latest_snapshot = None
    snapshot_rows: list[dict[str, Any]] = []
    sales_rows: list[dict[str, Any]] = []
    try:
        if db_path.exists():
            conn = _connect_readonly(db_path)
            checks.append(_check(True, "db_readonly_open", "mode=ro"))
            for table_name in ("fact_inventory_snapshot_size", "sales_fact_v2", "dim_sku"):
                checks.append(_check(_table_exists(conn, table_name), f"table_{table_name}_present", table_name))
            if _table_exists(conn, "fact_inventory_snapshot_size"):
                latest_snapshot = _latest_snapshot_date(conn, as_of_date)
            checks.append(
                _check(
                    bool(latest_snapshot),
                    "latest_snapshot_present",
                    f"latest_snapshot={latest_snapshot or 'none'} as_of={as_of_date.isoformat()}",
                )
            )
            if latest_snapshot:
                snapshot_rows = _load_snapshot_rows(conn, latest_snapshot)
            if _table_exists(conn, "sales_fact_v2"):
                sales_start = as_of_date - timedelta(days=89)
                sales_rows = _load_sales_rows(conn, sales_start, as_of_date)
    except sqlite3.Error as exc:
        checks.append(_check(False, "db_readonly_open", str(exc)))
    finally:
        if conn is not None:
            conn.close()

    snapshot_date = _parse_date(latest_snapshot)
    snapshot_age_days = None
    if snapshot_date is not None:
        snapshot_age_days = (as_of_date - snapshot_date).days
    max_age_days = int(config.get("max_basis_age_days") or 2)
    checks.append(
        _check(
            snapshot_age_days is not None and snapshot_age_days <= max_age_days,
            "snapshot_basis_fresh",
            f"age_days={snapshot_age_days} max_days={max_age_days}",
        )
    )
    checks.append(_check(bool(snapshot_rows), "snapshot_rows_present", f"rows={len(snapshot_rows)}"))

    delivered_statuses = {str(v).upper() for v in config.get("delivered_statuses") or ["DELIVERED"]}
    excluded_tokens = [str(v).upper() for v in config.get("non_cancelled_excluded_status_tokens") or ["CANCEL"]]
    zero_velocity_window_days = int(config.get("zero_velocity_window_days") or 30)
    family_sales, size_sales = _aggregate_sales(
        sales_rows,
        as_of_date=as_of_date,
        delivered_statuses=delivered_statuses,
        excluded_cancel_tokens=excluded_tokens,
        zero_velocity_window_days=zero_velocity_window_days,
    )

    families: dict[str, dict[str, Any]] = {}
    rows_by_family: dict[str, list[dict[str, Any]]] = {}
    size_detail: list[dict[str, Any]] = []
    for row in snapshot_rows:
        sku_key = str(row.get("sku_key") or "").strip()
        if not sku_key:
            continue
        current_stock = _as_int(row.get("current_stock"))
        inbound_stock = _as_int(row.get("inbound_stock"))
        cogs = _as_float(row.get("cogs_kzt"))
        my_size = str(row.get("my_size") or "").strip()
        rows_by_family.setdefault(sku_key, []).append(row)
        family = families.setdefault(sku_key, _new_family())
        family["sku_key"] = sku_key
        family["snapshot_size_rows"] += 1
        if current_stock < 0:
            family["negative_size_rows"] += 1
        if current_stock > 0:
            family["stock_units"] += current_stock
            family["positive_size_rows"] += 1
            if cogs is None or cogs <= 0:
                family["missing_cogs_positive_size_rows"] += 1
            else:
                family["goods_basis_kzt_known_cogs"] += current_stock * cogs
        size_key = (sku_key, my_size)
        size_bucket = size_sales.get(size_key) or {}
        size_detail.append(
            {
                "snapshot_date": row.get("snapshot_date"),
                "sku_id": row.get("sku_id"),
                "sku_key": sku_key,
                "my_size": my_size,
                "current_stock": current_stock,
                "inbound_stock": inbound_stock,
                "dim_sku_present": bool(row.get("dim_sku_key")),
                "cogs_kzt": _fmt_number(cogs),
                "stock_value_kzt_known_cogs": _fmt_number(current_stock * cogs if cogs is not None and cogs > 0 else None),
                "delivered_30d_units": size_bucket.get("delivered_30d_units", 0),
                "delivered_90d_units": size_bucket.get("delivered_90d_units", 0),
                "june_non_cancelled_units": size_bucket.get("june_non_cancelled_units", 0),
                "size_zero_recent_movement": current_stock > 0 and size_bucket.get("delivered_90d_units", 0) == 0,
            }
        )

    canonical_tranche1 = {str(v) for v in config.get("canonical_tranche1_sku_keys") or []}
    register_rows: list[dict[str, Any]] = []
    segment_map_rows: list[dict[str, Any]] = []
    invalid_segment_rows: list[str] = []
    for sku_key, family in families.items():
        if int(family["stock_units"]) <= 0:
            continue
        sales_bucket = family_sales.get(sku_key) or {}
        for metric in (
            "delivered_30d_units",
            "non_cancelled_30d_units",
            "delivered_90d_units",
            "june_non_cancelled_units",
        ):
            family[metric] = int(sales_bucket.get(metric, 0))
        delivered_30d = int(family["delivered_30d_units"])
        family["days_cover_30d"] = round(float(family["stock_units"]) / (delivered_30d / 30.0), 2) if delivered_30d > 0 else None
        segment_code, reason = _segment_family(
            family,
            size_rows=rows_by_family.get(sku_key, []),
            size_sales=size_sales,
            config=config,
        )
        if segment_code not in SEGMENTS:
            invalid_segment_rows.append(sku_key)
        hold_reason = _hold_reason(family, segment_code)
        sizing_allowed = not hold_reason
        output_row = {
            "sku_key": sku_key,
            "segment_code": segment_code,
            "segment": SEGMENTS.get(segment_code, "INVALID"),
            "segment_reason": reason,
            "stock_units": int(family["stock_units"]),
            "snapshot_size_rows": int(family["snapshot_size_rows"]),
            "positive_size_rows": int(family["positive_size_rows"]),
            "negative_size_rows": int(family["negative_size_rows"]),
            "goods_basis_kzt_known_cogs": _fmt_number(float(family["goods_basis_kzt_known_cogs"])),
            "missing_cogs_positive_size_rows": int(family["missing_cogs_positive_size_rows"]),
            "delivered_30d_units": delivered_30d,
            "non_cancelled_30d_units": int(family["non_cancelled_30d_units"]),
            "delivered_90d_units": int(family["delivered_90d_units"]),
            "june_non_cancelled_units": int(family["june_non_cancelled_units"]),
            "days_cover_30d": _fmt_number(family["days_cover_30d"]),
            "prior_canonical_tranche1": sku_key in canonical_tranche1,
            "tranche_sizing_allowed": sizing_allowed,
            "hold_reason": hold_reason,
        }
        register_rows.append(output_row)
        segment_map_rows.append({col: output_row.get(col, "") for col in SEGMENT_COLUMNS})

    register_rows.sort(key=lambda row: (str(row["segment_code"]), -int(row["stock_units"]), str(row["sku_key"])))
    segment_map_rows.sort(key=lambda row: (str(row["segment_code"]), -int(row["stock_units"]), str(row["sku_key"])))
    size_detail.sort(key=lambda row: (str(row["sku_key"]), str(row["my_size"]), str(row["sku_id"])))

    positive_family_count = len(register_rows)
    checks.append(
        _check(
            positive_family_count > 0,
            "positive_stock_families_present",
            f"positive_stock_family_count={positive_family_count}",
        )
    )
    checks.append(
        _check(
            not invalid_segment_rows and len(segment_map_rows) == positive_family_count,
            "segment_map_complete",
            f"segment_rows={len(segment_map_rows)} positive_families={positive_family_count} invalid={len(invalid_segment_rows)}",
        )
    )

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    register_csv = output_root / "liquidation_register.csv"
    segment_csv = output_root / "liquidation_segment_map.csv"
    size_csv = output_root / "liquidation_size_detail.csv"
    _write_csv(register_csv, REGISTER_COLUMNS, register_rows)
    _write_csv(segment_csv, SEGMENT_COLUMNS, segment_map_rows)
    _write_csv(size_csv, SIZE_COLUMNS, size_detail)

    segment_counts: dict[str, int] = {}
    for row in segment_map_rows:
        segment_counts[str(row["segment"])] = segment_counts.get(str(row["segment"]), 0) + 1

    movement_watch_keys = [str(v) for v in config.get("movement_watch_sku_keys") or []]
    by_sku = {str(row["sku_key"]): row for row in register_rows}
    movement_watch: list[dict[str, Any]] = []
    for sku_key in movement_watch_keys:
        row = by_sku.get(sku_key)
        if row is None:
            sales_bucket = family_sales.get(sku_key) or {}
            row = {
                "sku_key": sku_key,
                "stock_units": 0,
                "segment": "NOT_IN_POSITIVE_STOCK_REGISTER",
                "june_non_cancelled_units": int(sales_bucket.get("june_non_cancelled_units", 0)),
                "delivered_30d_units": int(sales_bucket.get("delivered_30d_units", 0)),
                "days_cover_30d": "",
            }
        movement_watch.append(
            {
                "sku_key": row["sku_key"],
                "stock_units": row["stock_units"],
                "segment": row["segment"],
                "june_non_cancelled_units": row["june_non_cancelled_units"],
                "delivered_30d_units": row["delivered_30d_units"],
                "days_cover_30d": row["days_cover_30d"],
            }
        )

    no_failures = all(row["ok"] for row in checks)
    gate = "GREEN" if no_failures else "RED"
    report: dict[str, Any] = {
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.isoformat(),
        "gate": gate,
        "status": gate,
        "ok": gate == "GREEN",
        "config_path": str(config_path),
        "db_path": str(db_path),
        "latest_snapshot_date": latest_snapshot or "",
        "snapshot_age_days": snapshot_age_days,
        "max_basis_age_days": max_age_days,
        "snapshot_row_count": len(snapshot_rows),
        "sales_row_count_90d": len(sales_rows),
        "positive_stock_family_count": positive_family_count,
        "positive_stock_units": sum(int(row["stock_units"]) for row in register_rows),
        "goods_basis_kzt_known_cogs": _fmt_number(
            sum(float(str(row["goods_basis_kzt_known_cogs"] or 0)) for row in register_rows)
        ),
        "missing_cogs_positive_size_rows": sum(int(row["missing_cogs_positive_size_rows"]) for row in register_rows),
        "negative_snapshot_size_rows": sum(1 for row in snapshot_rows if _as_int(row.get("current_stock")) < 0),
        "segment_counts": segment_counts,
        "movement_watch": movement_watch,
        "checks": checks,
        "artifacts": {
            "liquidation_register_csv": str(register_csv),
            "liquidation_segment_map_csv": str(segment_csv),
            "liquidation_size_detail_csv": str(size_csv),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "liquidation_register_summary.json"
    md_path = output_root / "liquidation_register_summary.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the G-LIQ-01 liquidation register.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true", help="Return non-zero unless gate is GREEN.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    report = build_liquidation_register_report(
        config_path=Path(args.config),
        output_root=Path(args.output_dir),
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"ok: {report['ok']}")
        print(f"output_dir: {args.output_dir}")
    if args.strict and report["gate"] != "GREEN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
