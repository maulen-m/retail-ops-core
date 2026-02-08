#!/usr/bin/env python3
"""
Generate single-truth business insides snapshot from paid capital + delivered sales.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.paid_capital_truth import compute_paid_capital_truth
from core.config.business_params import get_fx_rates
from core.calc.economics import calc_cogs

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BANK = PROJECT_ROOT / "config" / "bank_accounts.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"


def _parse_as_of(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    return date.fromisoformat(str(value))


def _fmt_kzt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.2f}"


def _ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [sep, _fmt_row(headers), sep]
    out.extend(_fmt_row(r) for r in rows)
    out.append(sep)
    return "\n".join(out)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        str(row[0]): {
            "cogs_kzt": float(row[1] or 0.0),
            "base_cost_cny": float(row[2] or 0.0),
            "weight_kg": float(row[3] or 0.0),
        }
        for row in rows
    }


def compute_sales_metrics(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | date | None = None,
    last_7_days: int = 7,
    last_30_days: int = 30,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    start_30 = as_of_date - timedelta(days=max(1, int(last_30_days)) - 1)
    start_7 = as_of_date - timedelta(days=max(1, int(last_7_days)) - 1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "sales_fact_v2"):
            raise RuntimeError("sales_fact_v2 table missing")

        dim_costs = _load_dim_sku_costs(conn)
        fx_rates = get_fx_rates(as_of_date, db_path=db_path)
        rows = conn.execute(
            """
            SELECT order_date, sku_key, quantity, cogs, net_rev
            FROM sales_fact_v2
            WHERE date(order_date) BETWEEN ? AND ?
              AND UPPER(COALESCE(status, '')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0
            ORDER BY order_date
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    by_date: dict[str, dict[str, float]] = {}
    fallback_rows = 0
    unresolved_rows = 0
    unresolved_skus: set[str] = set()
    total_rows = 0

    for row in rows:
        total_rows += 1
        day = str(row["order_date"])
        qty = float(row["quantity"] or 0.0)
        net_rev = float(row["net_rev"] or 0.0)
        cogs_raw = float(row["cogs"] or 0.0)
        sku_key = str(row["sku_key"] or "").strip()

        cogs_line = cogs_raw
        if cogs_line <= 0:
            meta = dim_costs.get(sku_key, {})
            cogs_unit = float(meta.get("cogs_kzt") or 0.0)
            if cogs_unit <= 0 and float(meta.get("base_cost_cny") or 0.0) > 0:
                cogs_unit = float(
                    calc_cogs(
                        float(meta.get("base_cost_cny") or 0.0),
                        float(meta.get("weight_kg") or 0.0),
                        cny_kzt=float(fx_rates.cny_kzt),
                        volumetric_factor=float(fx_rates.dlv_rate_usd_kg),
                        freight_rate=float(fx_rates.usd_kzt),
                    )
                )
            if cogs_unit > 0 and qty > 0:
                cogs_line = round(cogs_unit * qty, 2)
                fallback_rows += 1
            else:
                cogs_line = 0.0
                unresolved_rows += 1
                if sku_key:
                    unresolved_skus.add(sku_key)

        day_row = by_date.setdefault(day, {"net_rev_kzt": 0.0, "cogs_kzt": 0.0, "profit_kzt": 0.0})
        day_row["net_rev_kzt"] += net_rev
        day_row["cogs_kzt"] += cogs_line
        day_row["profit_kzt"] += net_rev - cogs_line

    for day_row in by_date.values():
        day_row["net_rev_kzt"] = round(day_row["net_rev_kzt"], 2)
        day_row["cogs_kzt"] = round(day_row["cogs_kzt"], 2)
        day_row["profit_kzt"] = round(day_row["profit_kzt"], 2)

    last_7_list: list[dict[str, Any]] = []
    for i in range(max(1, int(last_7_days))):
        day = (start_7 + timedelta(days=i)).isoformat()
        if day in by_date:
            item = {"date": day, **by_date[day]}
        else:
            item = {"date": day, "net_rev_kzt": None, "cogs_kzt": None, "profit_kzt": None}
        last_7_list.append(item)

    window_30_days = [
        (start_30 + timedelta(days=i)).isoformat() for i in range(max(1, int(last_30_days)))
    ]
    series_30_net = [by_date[d]["net_rev_kzt"] for d in window_30_days if d in by_date]
    series_30_cogs = [by_date[d]["cogs_kzt"] for d in window_30_days if d in by_date]
    series_30_profit = [by_date[d]["profit_kzt"] for d in window_30_days if d in by_date]

    series_7_net = [r["net_rev_kzt"] for r in last_7_list if r["net_rev_kzt"] is not None]
    series_7_cogs = [r["cogs_kzt"] for r in last_7_list if r["cogs_kzt"] is not None]
    series_7_profit = [r["profit_kzt"] for r in last_7_list if r["profit_kzt"] is not None]

    def _avg(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    return {
        "as_of_date": as_of_date.isoformat(),
        "last_7_days": last_7_list,
        "avg_30d_net_rev_kzt": _avg(series_30_net),
        "avg_30d_cogs_kzt": _avg(series_30_cogs),
        "avg_30d_profit_kzt": _avg(series_30_profit),
        "avg_7d_net_rev_kzt": _avg(series_7_net),
        "avg_7d_cogs_kzt": _avg(series_7_cogs),
        "avg_7d_profit_kzt": _avg(series_7_profit),
        "fallback_rows": fallback_rows,
        "unresolved_rows": unresolved_rows,
        "unresolved_sku_count": len(unresolved_skus),
        "total_rows": total_rows,
        "cogs_fallback_coverage_pct": round((fallback_rows / total_rows * 100.0), 2) if total_rows else 0.0,
    }


def _external_reference_check(
    *,
    external_sales_csv: Path | None,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    if external_sales_csv is None:
        return {"status": "skipped", "reason": "no external csv provided"}
    if not external_sales_csv.exists():
        return {"status": "missing", "path": str(external_sales_csv)}

    try:
        df = pd.read_csv(external_sales_csv)
    except Exception as exc:
        return {"status": "error", "path": str(external_sales_csv), "error": str(exc)}

    needed = {"sale_date", "total_net_rev_kzt", "total_cogs_kzt"}
    if not needed.issubset(set(df.columns)):
        return {
            "status": "error",
            "path": str(external_sales_csv),
            "error": f"missing columns: {sorted(needed - set(df.columns))}",
        }

    grouped = (
        df.groupby("sale_date", dropna=True)[["total_net_rev_kzt", "total_cogs_kzt"]]
        .sum()
        .reset_index()
    )
    ext_map = {
        str(row["sale_date"]): (
            float(row["total_net_rev_kzt"] or 0.0),
            float(row["total_cogs_kzt"] or 0.0),
        )
        for _, row in grouped.iterrows()
    }
    local_map = {
        row["date"]: (float(row["net_rev_kzt"] or 0.0), float(row["cogs_kzt"] or 0.0))
        for row in metrics["last_7_days"]
        if row["net_rev_kzt"] is not None and row["cogs_kzt"] is not None
    }
    overlap = sorted(set(ext_map.keys()) & set(local_map.keys()))
    if not overlap:
        return {"status": "ok", "path": str(external_sales_csv), "matched_days": 0}

    max_net = 0.0
    max_cogs = 0.0
    for day in overlap:
        ext_net, ext_cogs = ext_map[day]
        loc_net, loc_cogs = local_map[day]
        max_net = max(max_net, abs(ext_net - loc_net))
        max_cogs = max(max_cogs, abs(ext_cogs - loc_cogs))
    return {
        "status": "ok",
        "path": str(external_sales_csv),
        "matched_days": len(overlap),
        "max_abs_diff_net_rev_kzt": round(max_net, 2),
        "max_abs_diff_cogs_kzt": round(max_cogs, 2),
    }


def _render_markdown(
    *,
    generated_at: datetime,
    as_of_date: str,
    capital: dict[str, Any],
    sales_metrics: dict[str, Any],
    external_check: dict[str, Any],
) -> str:
    capital_rows = [
        ["Cash (actual, bank_accounts.yaml)", _fmt_kzt(capital["cash_actual_kzt"])],
        ["Inventory on-hand paid", _fmt_kzt(capital["inventory_on_hand_paid_kzt"])],
        ["Inventory inbound paid", _fmt_kzt(capital["inventory_inbound_paid_kzt"])],
        ["Inventory on-delivery paid", _fmt_kzt(capital["inventory_on_delivery_paid_kzt"])],
        ["Total capital (paid truth)", _fmt_kzt(capital["total_capital_paid_kzt"])],
        ["Inbound unpaid obligations", _fmt_kzt(capital["inbound_unpaid_obligations_kzt"])],
        [
            "Capital + unpaid inbound",
            _fmt_kzt(capital["total_capital_paid_kzt"] + capital["inbound_unpaid_obligations_kzt"]),
        ],
    ]
    perf_rows = [
        ["Avg 30d Net Rev", _fmt_kzt(sales_metrics["avg_30d_net_rev_kzt"])],
        ["Avg 30d COGS", _fmt_kzt(sales_metrics["avg_30d_cogs_kzt"])],
        ["Avg 30d Profit", _fmt_kzt(sales_metrics["avg_30d_profit_kzt"])],
        ["Avg 7d Net Rev", _fmt_kzt(sales_metrics["avg_7d_net_rev_kzt"])],
        ["Avg 7d COGS", _fmt_kzt(sales_metrics["avg_7d_cogs_kzt"])],
        ["Avg 7d Profit", _fmt_kzt(sales_metrics["avg_7d_profit_kzt"])],
    ]
    daily_rows = [
        [
            row["date"],
            _fmt_kzt(row["net_rev_kzt"]),
            _fmt_kzt(row["cogs_kzt"]),
            _fmt_kzt(row["profit_kzt"]),
        ]
        for row in sales_metrics["last_7_days"]
    ]

    lines = [
        "# Business Insides Snapshot",
        "",
        f"- Generated at: `{generated_at.strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- As of date: `{as_of_date}`",
        f"- Paid-capital snapshot date: `{capital.get('snapshot_date')}`",
        f"- Bank snapshot date: `{capital.get('bank_as_of_date')}`",
        "",
        "## Capital Snapshot (KZT)",
        "",
        "```text",
        _ascii_table(["Metric", "Value KZT"], capital_rows),
        "```",
        "",
        "## Performance Metrics (KZT)",
        "",
        "```text",
        _ascii_table(["Metric", "Value KZT"], perf_rows),
        "```",
        "",
        "## Last 7 Days Values (KZT)",
        "",
        "```text",
        _ascii_table(["Date", "Net Rev", "COGS", "Profit"], daily_rows),
        "```",
        "",
        "## Data Quality",
        "",
        f"- Sales source: `sales_fact_v2` (`DELIVERED`, `return_flag=0`).",
        f"- COGS fallback rows: `{sales_metrics['fallback_rows']}/{sales_metrics['total_rows']}` "
        f"({sales_metrics['cogs_fallback_coverage_pct']:.2f}%).",
        f"- Unresolved COGS rows: `{sales_metrics['unresolved_rows']}`.",
        f"- Unresolved SKU count: `{sales_metrics['unresolved_sku_count']}`.",
        "",
        "## External Reference Check",
        "",
        f"- Status: `{external_check.get('status')}`",
        f"- Details: `{external_check}`",
        "",
    ]
    return "\n".join(lines)


def generate_business_insides(
    *,
    db_path: Path = DEFAULT_DB,
    bank_accounts_path: Path = DEFAULT_BANK,
    as_of: str | date | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    external_sales_csv: Path | None = None,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    generated_at = datetime.now()
    capital = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank_accounts_path,
        as_of=as_of_date,
    )
    sales_metrics = compute_sales_metrics(db_path=db_path, as_of=as_of_date)
    external_check = _external_reference_check(
        external_sales_csv=external_sales_csv,
        metrics=sales_metrics,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = output_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    snapshot_name = f"BUSINESS_INSIDES_{as_of_date.isoformat()}.md"
    snapshot_path = snapshots_dir / snapshot_name
    latest_path = output_dir / snapshot_name
    content = _render_markdown(
        generated_at=generated_at,
        as_of_date=as_of_date.isoformat(),
        capital=capital,
        sales_metrics=sales_metrics,
        external_check=external_check,
    )
    snapshot_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")

    return {
        "as_of_date": as_of_date.isoformat(),
        "snapshot_path": str(snapshot_path),
        "latest_path": str(latest_path),
        "capital": capital,
        "performance": {
            "avg_30d_net_rev_kzt": sales_metrics["avg_30d_net_rev_kzt"],
            "avg_30d_cogs_kzt": sales_metrics["avg_30d_cogs_kzt"],
            "avg_30d_profit_kzt": sales_metrics["avg_30d_profit_kzt"],
            "avg_7d_net_rev_kzt": sales_metrics["avg_7d_net_rev_kzt"],
            "avg_7d_cogs_kzt": sales_metrics["avg_7d_cogs_kzt"],
            "avg_7d_profit_kzt": sales_metrics["avg_7d_profit_kzt"],
        },
        "last_7_days": sales_metrics["last_7_days"],
        "fallback_rows": sales_metrics["fallback_rows"],
        "total_rows": sales_metrics["total_rows"],
        "unresolved_rows": sales_metrics["unresolved_rows"],
        "unresolved_sku_count": sales_metrics["unresolved_sku_count"],
        "external_check": external_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate business insides snapshot markdown")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--bank-accounts", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--external-sales-csv", type=Path, default=None)
    args = parser.parse_args()

    result = generate_business_insides(
        db_path=args.db,
        bank_accounts_path=args.bank_accounts,
        as_of=args.as_of,
        output_dir=args.output_dir,
        external_sales_csv=args.external_sales_csv,
    )
    print(f"snapshot_path={result['snapshot_path']}")
    print(f"latest_path={result['latest_path']}")
    print(f"avg_7d_net_rev_kzt={result['performance']['avg_7d_net_rev_kzt']:.2f}")
    print(f"avg_7d_profit_kzt={result['performance']['avg_7d_profit_kzt']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
