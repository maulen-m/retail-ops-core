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
from core.sales import ensure_sales_truth_views

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
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _load_ads_daily(
    db_path: Path,
    start_date: date,
    end_date: date,
) -> tuple[dict[str, float], dict[str, float]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "ads_spend_sidecar_daily"):
            return {}, {
                "mapped_rows": 0.0,
                "unmapped_rows": 0.0,
                "mapped_cost_kzt": 0.0,
                "unmapped_cost_kzt": 0.0,
                "total_cost_kzt": 0.0,
                "mapping_coverage_pct": 0.0,
            }
        rows = conn.execute(
            """
            SELECT
                date,
                SUM(COALESCE(total_cost_kzt, 0)) AS total_cost_kzt,
                SUM(COALESCE(mapped_rows, 0)) AS mapped_rows,
                SUM(COALESCE(unmapped_rows, 0)) AS unmapped_rows,
                SUM(COALESCE(mapped_cost_kzt, 0)) AS mapped_cost_kzt,
                SUM(COALESCE(unmapped_cost_kzt, 0)) AS unmapped_cost_kzt
            FROM ads_spend_sidecar_daily
            WHERE date(date) BETWEEN ? AND ?
            GROUP BY date
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    by_date: dict[str, float] = {}
    totals = {
        "mapped_rows": 0.0,
        "unmapped_rows": 0.0,
        "mapped_cost_kzt": 0.0,
        "unmapped_cost_kzt": 0.0,
        "total_cost_kzt": 0.0,
        "mapping_coverage_pct": 0.0,
    }
    for row in rows:
        d = str(row["date"])
        cost = float(row["total_cost_kzt"] or 0.0)
        by_date[d] = round(cost, 2)
        totals["mapped_rows"] += float(row["mapped_rows"] or 0.0)
        totals["unmapped_rows"] += float(row["unmapped_rows"] or 0.0)
        totals["mapped_cost_kzt"] += float(row["mapped_cost_kzt"] or 0.0)
        totals["unmapped_cost_kzt"] += float(row["unmapped_cost_kzt"] or 0.0)
        totals["total_cost_kzt"] += cost
    total_rows = totals["mapped_rows"] + totals["unmapped_rows"]
    totals["mapping_coverage_pct"] = (
        round((totals["mapped_rows"] / total_rows) * 100.0, 2) if total_rows else 0.0
    )
    for key in ("mapped_cost_kzt", "unmapped_cost_kzt", "total_cost_kzt"):
        totals[key] = round(totals[key], 2)
    return by_date, totals


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
        ensure_sales_truth_views(conn)
        line_rows = conn.execute(
            """
            SELECT sale_date, sku_key, cogs_source
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()
        daily_rows = conn.execute(
            """
            SELECT
                sale_date,
                SUM(COALESCE(units, 0)) AS units_shipped,
                SUM(COALESCE(revenue_kzt, 0)) AS net_rev_kzt,
                SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
                SUM(COALESCE(profit_kzt, 0)) AS profit_kzt
            FROM view_sales_daily_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY sale_date
            ORDER BY sale_date
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

    for row in line_rows:
        total_rows += 1
        sku_key = str(row["sku_key"] or "").strip()
        cogs_source = str(row["cogs_source"] or "")
        if cogs_source in {"fact_sales_fallback", "dim_sku_fallback"}:
            fallback_rows += 1
        elif cogs_source == "unresolved":
            unresolved_rows += 1
            if sku_key:
                unresolved_skus.add(sku_key)

    for row in daily_rows:
        day = str(row["sale_date"])
        by_date[day] = {
            "units_shipped": round(float(row["units_shipped"] or 0.0), 2),
            "net_rev_kzt": round(float(row["net_rev_kzt"] or 0.0), 2),
            "cogs_kzt": round(float(row["cogs_kzt"] or 0.0), 2),
            "profit_kzt": round(float(row["profit_kzt"] or 0.0), 2),
        }

    ads_by_date, ads_totals = _load_ads_daily(db_path, start_30, as_of_date)
    for day, day_row in by_date.items():
        ads_cost = float(ads_by_date.get(day, 0.0))
        day_row["ads_spend_kzt"] = round(ads_cost, 2)
        day_row["profit_after_ads_kzt"] = round(day_row["profit_kzt"] - ads_cost, 2)

    last_7_list: list[dict[str, Any]] = []
    for i in range(max(1, int(last_7_days))):
        day = (start_7 + timedelta(days=i)).isoformat()
        if day in by_date:
            item = {"date": day, **by_date[day]}
        else:
            item = {
                "date": day,
                "units_shipped": None,
                "net_rev_kzt": None,
                "cogs_kzt": None,
                "profit_kzt": None,
                "ads_spend_kzt": round(float(ads_by_date.get(day, 0.0)), 2),
                "profit_after_ads_kzt": None,
            }
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
    series_30_ads = [by_date[d]["ads_spend_kzt"] for d in window_30_days if d in by_date]
    series_30_profit_after_ads = [by_date[d]["profit_after_ads_kzt"] for d in window_30_days if d in by_date]
    series_7_ads = [r["ads_spend_kzt"] for r in last_7_list if r["profit_kzt"] is not None]
    series_7_profit_after_ads = [r["profit_after_ads_kzt"] for r in last_7_list if r["profit_after_ads_kzt"] is not None]

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
        "avg_30d_ads_spend_kzt": _avg(series_30_ads),
        "avg_30d_profit_after_ads_kzt": _avg(series_30_profit_after_ads),
        "avg_7d_net_rev_kzt": _avg(series_7_net),
        "avg_7d_cogs_kzt": _avg(series_7_cogs),
        "avg_7d_profit_kzt": _avg(series_7_profit),
        "avg_7d_ads_spend_kzt": _avg(series_7_ads),
        "avg_7d_profit_after_ads_kzt": _avg(series_7_profit_after_ads),
        "fallback_rows": fallback_rows,
        "unresolved_rows": unresolved_rows,
        "unresolved_sku_count": len(unresolved_skus),
        "total_rows": total_rows,
        "cogs_fallback_coverage_pct": round((fallback_rows / total_rows * 100.0), 2) if total_rows else 0.0,
        "ads": ads_totals,
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
        ["Avg 30d Ads Spend", _fmt_kzt(sales_metrics["avg_30d_ads_spend_kzt"])],
        ["Avg 30d Profit After Ads", _fmt_kzt(sales_metrics["avg_30d_profit_after_ads_kzt"])],
        ["Avg 7d Net Rev", _fmt_kzt(sales_metrics["avg_7d_net_rev_kzt"])],
        ["Avg 7d COGS", _fmt_kzt(sales_metrics["avg_7d_cogs_kzt"])],
        ["Avg 7d Profit", _fmt_kzt(sales_metrics["avg_7d_profit_kzt"])],
        ["Avg 7d Ads Spend", _fmt_kzt(sales_metrics["avg_7d_ads_spend_kzt"])],
        ["Avg 7d Profit After Ads", _fmt_kzt(sales_metrics["avg_7d_profit_after_ads_kzt"])],
    ]
    daily_rows = [
        [
            row["date"],
            str(int(round(float(row["units_shipped"])))) if row["units_shipped"] is not None else "N/A",
            _fmt_kzt(row["net_rev_kzt"]),
            _fmt_kzt(row["cogs_kzt"]),
            _fmt_kzt(row["ads_spend_kzt"]),
            _fmt_kzt(row["profit_kzt"]),
            _fmt_kzt(row["profit_after_ads_kzt"]),
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
        _ascii_table(
            ["Date", "Units Shipped", "Net Rev", "COGS", "Ads Spend", "Profit", "Profit After Ads"],
            daily_rows,
        ),
        "```",
        "",
        "## Data Quality",
        "",
        f"- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).",
        f"- COGS fallback rows: `{sales_metrics['fallback_rows']}/{sales_metrics['total_rows']}` "
        f"({sales_metrics['cogs_fallback_coverage_pct']:.2f}%).",
        f"- Unresolved COGS rows: `{sales_metrics['unresolved_rows']}`.",
        f"- Unresolved SKU count: `{sales_metrics['unresolved_sku_count']}`.",
        f"- Ads mapping coverage: `{sales_metrics['ads'].get('mapping_coverage_pct', 0):.2f}%`.",
        f"- Ads mapped/unmapped cost: `{_fmt_kzt(sales_metrics['ads'].get('mapped_cost_kzt'))}` / "
        f"`{_fmt_kzt(sales_metrics['ads'].get('unmapped_cost_kzt'))}`.",
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
    strict_cogs: bool = False,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    generated_at = datetime.now()
    capital = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank_accounts_path,
        as_of=as_of_date,
    )
    sales_metrics = compute_sales_metrics(db_path=db_path, as_of=as_of_date)
    if strict_cogs and int(sales_metrics["unresolved_rows"]) > 0:
        raise RuntimeError(
            "Unresolved COGS rows detected in requested window: "
            f"rows={sales_metrics['unresolved_rows']}, "
            f"sku_count={sales_metrics['unresolved_sku_count']}"
        )
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
            "avg_30d_ads_spend_kzt": sales_metrics["avg_30d_ads_spend_kzt"],
            "avg_30d_profit_after_ads_kzt": sales_metrics["avg_30d_profit_after_ads_kzt"],
            "avg_7d_net_rev_kzt": sales_metrics["avg_7d_net_rev_kzt"],
            "avg_7d_cogs_kzt": sales_metrics["avg_7d_cogs_kzt"],
            "avg_7d_profit_kzt": sales_metrics["avg_7d_profit_kzt"],
            "avg_7d_ads_spend_kzt": sales_metrics["avg_7d_ads_spend_kzt"],
            "avg_7d_profit_after_ads_kzt": sales_metrics["avg_7d_profit_after_ads_kzt"],
        },
        "last_7_days": sales_metrics["last_7_days"],
        "fallback_rows": sales_metrics["fallback_rows"],
        "total_rows": sales_metrics["total_rows"],
        "unresolved_rows": sales_metrics["unresolved_rows"],
        "unresolved_sku_count": sales_metrics["unresolved_sku_count"],
        "ads": sales_metrics["ads"],
        "external_check": external_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate business insides snapshot markdown")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--bank-accounts", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--external-sales-csv", type=Path, default=None)
    parser.add_argument("--strict-cogs", action="store_true")
    args = parser.parse_args()

    result = generate_business_insides(
        db_path=args.db,
        bank_accounts_path=args.bank_accounts,
        as_of=args.as_of,
        output_dir=args.output_dir,
        external_sales_csv=args.external_sales_csv,
        strict_cogs=args.strict_cogs,
    )
    print(f"snapshot_path={result['snapshot_path']}")
    print(f"latest_path={result['latest_path']}")
    print(f"avg_7d_net_rev_kzt={result['performance']['avg_7d_net_rev_kzt']:.2f}")
    print(f"avg_7d_profit_kzt={result['performance']['avg_7d_profit_kzt']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
