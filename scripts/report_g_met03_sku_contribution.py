#!/usr/bin/env python3
"""Publish the G-MET-03 daily per-SKU contribution table."""

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

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "sku_contribution_daily.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_met03_sku_contribution"

CONTRIBUTION_COLUMNS = [
    "sale_date",
    "store_code",
    "sku_key",
    "units",
    "net_rev_kzt",
    "cogs_kzt",
    "profit_kzt",
    "mapped_ads_cost_kzt",
    "known_input_net_contribution_kzt",
    "expected_return_loss_kzt",
    "handling_cost_kzt",
    "input_completeness",
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


def _check(ok: bool, name: str, details: str) -> dict[str, Any]:
    return {"check": name, "ok": bool(ok), "details": details}


def _as_float(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return float(str(value).strip() or "0")
    except ValueError:
        return 0.0


def _fmt(value: float) -> float:
    return round(float(value), 2)


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


def _load_rows(conn: sqlite3.Connection, sale_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH sales AS (
            SELECT
                sale_date,
                store_code,
                sku_key,
                SUM(COALESCE(units, 0)) AS units,
                SUM(COALESCE(net_rev_kzt, 0)) AS net_rev_kzt,
                SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
                SUM(COALESCE(profit_kzt, 0)) AS profit_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) = date(?)
            GROUP BY sale_date, store_code, sku_key
        ),
        ads AS (
            SELECT
                date AS sale_date,
                store_code,
                sku_key,
                SUM(COALESCE(ads_cost_kzt, 0)) AS ads_cost_kzt
            FROM ads_spend_sidecar_daily_sku
            WHERE date(date) = date(?)
            GROUP BY date, store_code, sku_key
        )
        SELECT
            s.sale_date,
            s.store_code,
            s.sku_key,
            s.units,
            s.net_rev_kzt,
            s.cogs_kzt,
            s.profit_kzt,
            COALESCE(a.ads_cost_kzt, 0) AS mapped_ads_cost_kzt
        FROM sales s
        LEFT JOIN ads a
          ON a.sale_date = s.sale_date
         AND a.store_code = s.store_code
         AND a.sku_key = s.sku_key
        ORDER BY s.sale_date, s.store_code, s.sku_key
        """,
        (sale_date, sale_date),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        profit = _as_float(row["profit_kzt"])
        ads = _as_float(row["mapped_ads_cost_kzt"])
        out.append(
            {
                "sale_date": row["sale_date"],
                "store_code": row["store_code"],
                "sku_key": row["sku_key"],
                "units": _fmt(_as_float(row["units"])),
                "net_rev_kzt": _fmt(_as_float(row["net_rev_kzt"])),
                "cogs_kzt": _fmt(_as_float(row["cogs_kzt"])),
                "profit_kzt": _fmt(profit),
                "mapped_ads_cost_kzt": _fmt(ads),
                "known_input_net_contribution_kzt": _fmt(profit - ads),
                "expected_return_loss_kzt": "",
                "handling_cost_kzt": "",
                "input_completeness": "KNOWN_INPUTS_ONLY",
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-MET-03 Daily SKU Contribution",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Latest sales date: `{report['latest_sales_date']}`",
        "",
        "## Summary",
        "",
        f"- contribution_row_count: `{report['contribution_row_count']}`",
        f"- known_input_net_contribution_kzt: `{report['known_input_net_contribution_kzt']}`",
        f"- mapped_ads_cost_kzt: `{report['mapped_ads_cost_kzt']}`",
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


def build_sku_contribution_report(
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
            config.get("contract_id") == "SKU_CONTRIBUTION_DAILY_V1" and config.get("gate_id") == "G-MET-03",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )

    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    db_path = _resolve_project_path(config.get("db_path", "db/app.db"))
    checks.append(_check(db_path.exists(), "db_present", str(db_path)))

    rows: list[dict[str, Any]] = []
    latest_sales_date: str | None = None
    conn: sqlite3.Connection | None = None
    try:
        if db_path.exists():
            conn = _connect_readonly(db_path)
            checks.append(_check(True, "db_readonly_open", "mode=ro"))
            for table in ("view_sales_line_truth", "ads_spend_sidecar_daily_sku"):
                checks.append(_check(_table_exists(conn, table), f"table_{table}_present", table))
            if _table_exists(conn, "view_sales_line_truth"):
                latest_sales_date = _latest_sales_date(conn, as_of_date)
            if latest_sales_date and _table_exists(conn, "ads_spend_sidecar_daily_sku"):
                rows = _load_rows(conn, latest_sales_date)
    except sqlite3.Error as exc:
        checks.append(_check(False, "db_readonly_open", str(exc)))
    finally:
        if conn is not None:
            conn.close()

    latest_date = _parse_date(latest_sales_date)
    latest_sales_lag_days = None if latest_date is None else (as_of_date - latest_date).days
    max_lag_days = int(config.get("max_latest_sales_lag_days") or 2)
    checks.append(_check(latest_date is not None, "latest_sales_present", f"latest_sales_date={latest_sales_date}"))
    checks.append(
        _check(
            latest_sales_lag_days is not None and latest_sales_lag_days <= max_lag_days,
            "latest_sales_lag_within_limit",
            f"lag_days={latest_sales_lag_days} max_days={max_lag_days}",
        )
    )
    checks.append(_check(bool(rows), "contribution_rows_present", f"rows={len(rows)}"))

    if bool(config.get("require_expected_return_loss_source", True)):
        measurement_blockers.append("expected_return_loss_source_missing")
    if bool(config.get("require_handling_cost_source", True)):
        measurement_blockers.append("handling_cost_source_missing")

    for row in checks:
        if not row["ok"]:
            blockers.append(f"{row['check']}: {row['details']}")

    gate = "RED" if blockers else ("ARMED" if measurement_blockers else "GREEN")
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / "sku_contribution_daily.csv"
    spot_path = output_root / "sku_contribution_spot_check.csv"
    _write_csv(csv_path, rows, CONTRIBUTION_COLUMNS)
    spot_rows = sorted(rows, key=lambda row: abs(_as_float(row["known_input_net_contribution_kzt"])), reverse=True)[:5]
    _write_csv(spot_path, spot_rows, CONTRIBUTION_COLUMNS)

    known_input_net = sum(_as_float(row["known_input_net_contribution_kzt"]) for row in rows)
    mapped_ads = sum(_as_float(row["mapped_ads_cost_kzt"]) for row in rows)
    report: dict[str, Any] = {
        "gate_id": "G-MET-03",
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.replace(microsecond=0).isoformat(),
        "config_path": str(config_path),
        "db_path": str(db_path),
        "latest_sales_date": latest_sales_date or "",
        "latest_sales_lag_days": latest_sales_lag_days,
        "contribution_row_count": len(rows),
        "known_input_formula": config.get("known_input_formula", "profit_kzt - mapped_ads_cost_kzt"),
        "full_formula_target": config.get("full_formula_target", ""),
        "known_input_net_contribution_kzt": _fmt(known_input_net),
        "mapped_ads_cost_kzt": _fmt(mapped_ads),
        "checks": checks,
        "blockers": blockers,
        "measurement_blockers": measurement_blockers,
        "artifacts": {
            "sku_contribution_daily_csv": str(csv_path),
            "spot_check_csv": str(spot_path),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "sku_contribution_daily_report.json"
    md_path = output_root / "sku_contribution_daily_report.md"
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

    report = build_sku_contribution_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
