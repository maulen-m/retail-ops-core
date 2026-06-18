#!/usr/bin/env python3
"""Publish the G-MET-01 PPCH v1 report with denominator-consistent evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "ppch_v1_metric.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_met01_ppch_v1"

DENOMINATOR_COLUMNS = [
    "snapshot_date",
    "sku_id",
    "sku_key",
    "my_size",
    "current_stock",
    "cogs_kzt",
    "capital_kzt",
    "capitalized",
]

CONTRIBUTION_COLUMNS = [
    "sale_date",
    "store_code",
    "sku_key",
    "units",
    "net_rev_kzt",
    "cogs_kzt",
    "profit_kzt",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


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


def _resolve_project_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _as_float(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return float(str(value).strip() or "0")
    except ValueError:
        return 0.0


def _fmt_money(value: float) -> float:
    return round(float(value), 2)


def _fmt_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
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


def _latest_sales_date(conn: sqlite3.Connection, as_of_date: date) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(sale_date) AS sale_date
        FROM view_sales_line_truth
        WHERE date(sale_date) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    return str(row["sale_date"]) if row and row["sale_date"] else None


def _load_denominator_rows(conn: sqlite3.Connection, snapshot_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            f.snapshot_date,
            f.sku_id,
            f.sku_key,
            f.my_size,
            COALESCE(f.current_stock, 0) AS current_stock,
            COALESCE(d.cogs_kzt, 0) AS cogs_kzt
        FROM fact_inventory_snapshot_size f
        LEFT JOIN dim_sku d ON d.sku_key = f.sku_key
        WHERE f.snapshot_date = ?
          AND COALESCE(f.current_stock, 0) > 0
        ORDER BY f.sku_key, f.my_size, f.sku_id
        """,
        (snapshot_date,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        current_stock = _as_float(row["current_stock"])
        cogs = _as_float(row["cogs_kzt"])
        capitalized = cogs > 0 and current_stock > 0
        out.append(
            {
                "snapshot_date": row["snapshot_date"],
                "sku_id": row["sku_id"],
                "sku_key": row["sku_key"],
                "my_size": row["my_size"],
                "current_stock": int(current_stock),
                "cogs_kzt": _fmt_money(cogs),
                "capital_kzt": _fmt_money(current_stock * cogs) if capitalized else 0.0,
                "capitalized": capitalized,
            }
        )
    return out


def _load_contribution_rows(conn: sqlite3.Connection, start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            sale_date,
            store_code,
            sku_key,
            SUM(COALESCE(units, 0)) AS units,
            SUM(COALESCE(net_rev_kzt, 0)) AS net_rev_kzt,
            SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
            SUM(COALESCE(profit_kzt, 0)) AS profit_kzt
        FROM view_sales_line_truth
        WHERE date(sale_date) >= date(?)
          AND date(sale_date) <= date(?)
        GROUP BY sale_date, store_code, sku_key
        ORDER BY sale_date, store_code, sku_key
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    return [
        {
            "sale_date": row["sale_date"],
            "store_code": row["store_code"],
            "sku_key": row["sku_key"],
            "units": _fmt_money(_as_float(row["units"])),
            "net_rev_kzt": _fmt_money(_as_float(row["net_rev_kzt"])),
            "cogs_kzt": _fmt_money(_as_float(row["cogs_kzt"])),
            "profit_kzt": _fmt_money(_as_float(row["profit_kzt"])),
        }
        for row in rows
    ]


def _ads_cost(conn: sqlite3.Connection, start_date: date, end_date: date) -> float:
    if not _table_exists(conn, "ads_spend_sidecar_daily_sku"):
        return 0.0
    row = conn.execute(
        """
        SELECT SUM(COALESCE(ads_cost_kzt, 0)) AS ads_cost_kzt
        FROM ads_spend_sidecar_daily_sku
        WHERE date(date) >= date(?)
          AND date(date) <= date(?)
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchone()
    return _as_float(row["ads_cost_kzt"] if row else 0)


def _return_qc_count(conn: sqlite3.Connection, as_of_date: date) -> int:
    if not _table_exists(conn, "return_qc_event"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM return_qc_event
        WHERE qc_ts IS NULL OR date(qc_ts) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    return int(row["cnt"] or 0)


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-MET-01 PPCH v1 Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Period: `{report['period_start']}` to `{report['period_end']}`",
        f"Denominator basis: `{report['denominator_basis']}`",
        "",
        "## Headline",
        "",
        f"- headline_status: `{report['headline_status']}`",
        f"- ppch_v1_lower_pct_30d: `{report['ppch_v1']['lower_pct_30d']}`",
        f"- ppch_v1_mid_pct_30d: `{report['ppch_v1']['mid_pct_30d']}`",
        f"- ppch_v1_upper_pct_30d: `{report['ppch_v1']['upper_pct_30d']}`",
        f"- net_contribution_mid_kzt: `{report['net_contribution_mid_kzt']}`",
        f"- denominator_capital_hours: `{report['denominator_capital_hours']}`",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Measurement Blockers", ""])
    if report["measurement_blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["measurement_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Checks", "", "| check | status | details |", "|---|---:|---|"])
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.append("")
    return "\n".join(lines)


def build_ppch_v1_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    measurement_blockers: list[str] = []

    config_path = config_path.expanduser().resolve()
    if config_path.exists():
        config = _load_json(config_path)
        checks.append(_check(True, "config_present", str(config_path)))
    else:
        config = {}
        checks.append(_check(False, "config_present", f"missing: {config_path}"))
    checks.append(
        _check(
            config.get("contract_id") == "PPCH_V1_METRIC_V1" and config.get("gate_id") == "G-MET-01",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )

    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    db_path = _resolve_project_path(config.get("db_path", "db/app.db"))
    checks.append(_check(db_path.exists(), "db_present", str(db_path)))

    denominator_rows: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []
    latest_snapshot: str | None = None
    latest_sale_date: str | None = None
    ads_cost_kzt = 0.0
    return_qc_event_count = 0
    table_names = [
        "fact_inventory_snapshot_size",
        "dim_sku",
        "view_sales_line_truth",
        "return_qc_event",
    ]

    conn: sqlite3.Connection | None = None
    try:
        if db_path.exists():
            conn = _connect_readonly(db_path)
            checks.append(_check(True, "db_readonly_open", "mode=ro"))
            for table in table_names:
                checks.append(_check(_table_exists(conn, table), f"table_{table}_present", table))
            if _table_exists(conn, "fact_inventory_snapshot_size"):
                latest_snapshot = _latest_snapshot_date(conn, as_of_date)
            if _table_exists(conn, "view_sales_line_truth"):
                latest_sale_date = _latest_sales_date(conn, as_of_date)
            if latest_snapshot:
                denominator_rows = _load_denominator_rows(conn, latest_snapshot)
            latest_sale = _parse_date(latest_sale_date)
            if latest_sale is not None:
                period_start = latest_sale.replace(day=1)
                contribution_rows = _load_contribution_rows(conn, period_start, latest_sale)
                ads_cost_kzt = _ads_cost(conn, period_start, latest_sale)
            return_qc_event_count = _return_qc_count(conn, as_of_date)
    except sqlite3.Error as exc:
        checks.append(_check(False, "db_readonly_open", str(exc)))
    finally:
        if conn is not None:
            conn.close()

    snapshot_date = _parse_date(latest_snapshot)
    latest_sale = _parse_date(latest_sale_date)
    period_start = latest_sale.replace(day=1) if latest_sale is not None else as_of_date.replace(day=1)
    period_end = latest_sale or as_of_date
    observed_days = max((period_end - period_start).days + 1, 0)
    observed_hours = observed_days * 24

    snapshot_age_days = None if snapshot_date is None else (as_of_date - snapshot_date).days
    max_snapshot_age = int(config.get("max_denominator_snapshot_age_days") or 7)
    checks.append(
        _check(
            snapshot_age_days is not None and snapshot_age_days <= max_snapshot_age,
            "denominator_snapshot_fresh",
            f"age_days={snapshot_age_days} max_days={max_snapshot_age}",
        )
    )

    capitalized_rows = [row for row in denominator_rows if row["capitalized"]]
    denominator_capital_kzt = sum(_as_float(row["capital_kzt"]) for row in capitalized_rows)
    denominator_capital_hours = denominator_capital_kzt * observed_hours
    checks.append(_check(bool(denominator_rows), "denominator_rows_present", f"rows={len(denominator_rows)}"))
    checks.append(
        _check(
            denominator_capital_kzt > 0 and bool(capitalized_rows),
            "denominator_capital_positive",
            f"capitalized_rows={len(capitalized_rows)} capital_kzt={_fmt_money(denominator_capital_kzt)}",
        )
    )
    checks.append(_check(observed_hours > 0, "observed_hours_positive", f"observed_hours={observed_hours}"))
    checks.append(
        _check(
            bool(contribution_rows),
            "period_contribution_rows_present",
            f"rows={len(contribution_rows)} latest_sale_date={latest_sale_date}",
        )
    )

    denominator_basis = str(config.get("denominator_basis") or "")
    checks.append(
        _check(
            denominator_basis == "capitalized_rows_basis",
            "denominator_basis_pinned",
            f"denominator_basis={denominator_basis}",
        )
    )

    sales_profit_kzt = sum(_as_float(row["profit_kzt"]) for row in contribution_rows)
    sales_net_rev_kzt = sum(_as_float(row["net_rev_kzt"]) for row in contribution_rows)
    sales_cogs_kzt = sum(_as_float(row["cogs_kzt"]) for row in contribution_rows)
    sales_units = sum(_as_float(row["units"]) for row in contribution_rows)
    net_contribution_mid = sales_profit_kzt - ads_cost_kzt

    ppch_mid = None
    if denominator_capital_hours > 0:
        ppch_mid = 720.0 * net_contribution_mid / denominator_capital_hours * 100.0
    ppch = {
        "lower_pct_30d": _fmt_pct(ppch_mid),
        "mid_pct_30d": _fmt_pct(ppch_mid),
        "upper_pct_30d": _fmt_pct(ppch_mid),
        "confidence_basis": "known_input_only_no_invented_return_or_handling_loss",
    }
    checks.append(
        _check(
            ppch["lower_pct_30d"] is not None and ppch["mid_pct_30d"] is not None and ppch["upper_pct_30d"] is not None,
            "ppch_confidence_fields_present",
            f"lower={ppch['lower_pct_30d']} mid={ppch['mid_pct_30d']} upper={ppch['upper_pct_30d']}",
        )
    )

    for row in checks:
        if not row["ok"]:
            blockers.append(f"{row['check']}: {row['details']}")

    headline_policy = config.get("headline_policy") or {}
    if bool(headline_policy.get("green_requires_return_qc_event", True)) and return_qc_event_count <= 0:
        measurement_blockers.append("return_qc_event_count=0 so PPCH v1 is published as ARMED and v0.75 remains interim headline")

    if blockers:
        gate = "RED"
        headline_status = "blocked"
    elif measurement_blockers:
        gate = "ARMED"
        headline_status = "interim_v0.75_until_return_qc_measured"
    else:
        gate = "GREEN"
        headline_status = "ppch_v1_owner_headline_ready"

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    denominator_csv = output_root / "ppch_v1_denominator_snapshot.csv"
    contribution_csv = output_root / "ppch_v1_contribution_rows.csv"
    _write_csv(denominator_csv, denominator_rows, DENOMINATOR_COLUMNS)
    _write_csv(contribution_csv, contribution_rows, CONTRIBUTION_COLUMNS)

    report: dict[str, Any] = {
        "gate_id": "G-MET-01",
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.replace(microsecond=0).isoformat(),
        "config_path": str(config_path),
        "db_path": str(db_path),
        "period_policy": config.get("period", "month_to_latest_sales"),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "observed_days": observed_days,
        "observed_hours": observed_hours,
        "denominator_basis": denominator_basis,
        "denominator_snapshot_date": latest_snapshot or "",
        "denominator_snapshot_age_days": snapshot_age_days,
        "denominator_positive_rows": len(denominator_rows),
        "denominator_capitalized_rows": len(capitalized_rows),
        "denominator_excluded_positive_no_cogs_rows": len(denominator_rows) - len(capitalized_rows),
        "denominator_capital_kzt": _fmt_money(denominator_capital_kzt),
        "denominator_capital_hours": _fmt_money(denominator_capital_hours),
        "sales_units": _fmt_money(sales_units),
        "sales_net_rev_kzt": _fmt_money(sales_net_rev_kzt),
        "sales_cogs_kzt": _fmt_money(sales_cogs_kzt),
        "sales_profit_kzt": _fmt_money(sales_profit_kzt),
        "mapped_ads_cost_kzt": _fmt_money(ads_cost_kzt),
        "net_contribution_mid_kzt": _fmt_money(net_contribution_mid),
        "return_qc_event_count": return_qc_event_count,
        "headline_status": headline_status,
        "ppch_v1": ppch,
        "checks": checks,
        "blockers": blockers,
        "measurement_blockers": measurement_blockers,
        "artifacts": {
            "denominator_snapshot_csv": str(denominator_csv),
            "contribution_rows_csv": str(contribution_csv),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "ppch_v1_report.json"
    md_path = output_root / "ppch_v1_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_ppch_v1_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
        if report["measurement_blockers"]:
            print("Measurement blockers:")
            for blocker in report["measurement_blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
