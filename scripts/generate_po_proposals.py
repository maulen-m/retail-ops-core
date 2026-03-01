#!/usr/bin/env python3
"""Generate deterministic PO proposal artifacts with capital-protection fields."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "po"
DEFAULT_RULES_DOC = PROJECT_ROOT / "docs" / "inventory" / "Master_Inventory_Rules_v8.md"

ROIC_FULL_PCT = 20.0
ROIC_FLAG_PCT = 10.0
DEFAULT_NEW_SKU_CAP_PCT = 20.0


def _load_new_sku_cap_pct(rules_doc_path: Path) -> float:
    if not rules_doc_path.exists():
        return DEFAULT_NEW_SKU_CAP_PCT
    text = rules_doc_path.read_text(encoding="utf-8")
    marker = "Max_new_SKU_capital_pct"
    for line in text.splitlines():
        if marker not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        for part in parts:
            cleaned = part.replace("%", "").strip()
            try:
                value = float(cleaned)
            except ValueError:
                continue
            if value > 0:
                return value
    return DEFAULT_NEW_SKU_CAP_PCT


def _roic_action(roic_pct: float) -> str:
    if roic_pct >= ROIC_FULL_PCT:
        return "ORDER_FULL"
    if roic_pct >= ROIC_FLAG_PCT:
        return "ORDER_WITH_FLAG"
    return "REVIEW_REQUIRED"


def _exit_horizon(qty: float, d30: float) -> int | None:
    if d30 <= 0:
        return None
    return int(math.ceil(max(0.0, qty) / d30))


def _exit_path(*, horizon_days: int | None, d30: float) -> str:
    if d30 <= 0 or horizon_days is None:
        return "NO_DEMAND_EXIT_REQUIRED"
    if horizon_days <= 45:
        return "STANDARD_SELL_THROUGH"
    if horizon_days <= 90:
        return "MONITOR_AND_REPRICE"
    return "LIQUIDATION_PLAN_REQUIRED"


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# PO Proposals",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- proposal_count: `{report['proposal_count']}`",
        f"- total_capital_at_risk_kzt: `{report['total_capital_at_risk_kzt']:.2f}`",
        "",
        "| store | sku_key | qty | roic_pct | roic_action | capital_at_risk_kzt | share_pct | is_new | exit_path |",
        "|---|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for row in report["lines"]:
        lines.append(
            "| {store_code} | {sku_key} | {suggested_order_qty} | {roic_monthly_pct:.2f} | {roic_action} | "
            "{capital_at_risk_kzt:.2f} | {capital_share_pct:.2f} | {is_new_sku} | {exit_path} |".format(**row)
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def generate_po_proposals(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path,
    strict: bool,
    rules_doc_path: Path = DEFAULT_RULES_DOC,
) -> dict[str, Any]:
    errors: list[str] = []
    if not db_path.exists():
        errors.append(f"db not found: {db_path.resolve()}")

    rows: list[sqlite3.Row] = []
    if not errors:
        conn = sqlite3.connect(str(db_path.resolve()))
        conn.row_factory = sqlite3.Row
        try:
            table_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_sku_metrics'"
            ).fetchone()
            if table_exists is None:
                errors.append("missing table: fact_sku_metrics")
            else:
                rows = conn.execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            computed_at,
                            sku_key,
                            UPPER(TRIM(COALESCE(store_code, 'UNKNOWN'))) AS store_code,
                            COALESCE(status, '') AS status,
                            CAST(COALESCE(suggested_order_qty, 0) AS REAL) AS suggested_order_qty,
                            CAST(COALESCE(roic_monthly, 0) AS REAL) AS roic_monthly_pct,
                            CAST(COALESCE(k_avg, 0) AS REAL) AS k_avg_kzt,
                            CAST(COALESCE(avg_cogs, 0) AS REAL) AS unit_cost_kzt,
                            CAST(COALESCE(avg_profit, 0) AS REAL) AS avg_profit_kzt,
                            CAST(COALESCE(d30, 0) AS REAL) AS d30,
                            CAST(COALESCE(days_with_sales, 0) AS INTEGER) AS days_with_sales,
                            ROW_NUMBER() OVER (
                                PARTITION BY UPPER(TRIM(COALESCE(store_code, 'UNKNOWN'))), sku_key
                                ORDER BY datetime(COALESCE(computed_at, '1970-01-01 00:00:00')) DESC, id DESC
                            ) AS rn
                        FROM fact_sku_metrics
                        WHERE COALESCE(suggested_order_qty, 0) > 0
                    )
                    SELECT
                        sku_key,
                        store_code,
                        status,
                        suggested_order_qty,
                        roic_monthly_pct,
                        k_avg_kzt,
                        unit_cost_kzt,
                        avg_profit_kzt,
                        d30,
                        days_with_sales
                    FROM ranked
                    WHERE rn = 1
                    ORDER BY roic_monthly_pct DESC, sku_key ASC
                    """
                ).fetchall()
        finally:
            conn.close()

    if not rows and not errors:
        errors.append("no proposal candidates found in fact_sku_metrics")

    new_sku_cap_pct = _load_new_sku_cap_pct(rules_doc_path.resolve())
    proposals: list[dict[str, Any]] = []
    for row in rows:
        sku_key = str(row["sku_key"] or "").strip()
        if not sku_key:
            errors.append("encountered empty sku_key in fact_sku_metrics")
            continue
        qty = float(row["suggested_order_qty"] or 0.0)
        unit_cost = float(row["unit_cost_kzt"] or 0.0)
        if qty <= 0:
            continue
        if unit_cost <= 0:
            errors.append(f"missing unit cost for sku={sku_key} store={row['store_code']}")
            continue
        d30 = float(row["d30"] or 0.0)
        avg_profit = float(row["avg_profit_kzt"] or 0.0)
        k_avg = float(row["k_avg_kzt"] or 0.0)
        if avg_profit > 0 and d30 > 0 and k_avg > 0:
            roic_pct = round(((avg_profit * d30 * 30.0) / k_avg) * 100.0, 2)
            roic_source = "rules_formula"
        else:
            roic_pct = round(float(row["roic_monthly_pct"] or 0.0), 2)
            roic_source = "fact_sku_metrics"
        action = _roic_action(roic_pct)
        horizon = _exit_horizon(qty, d30)
        is_new = int(row["days_with_sales"] or 0) <= 0
        proposals.append(
            {
                "store_code": str(row["store_code"] or "UNKNOWN").upper(),
                "sku_key": sku_key,
                "status": str(row["status"] or "").strip(),
                "suggested_order_qty": int(round(qty)),
                "unit_cost_kzt": round(unit_cost, 2),
                "capital_at_risk_kzt": round(qty * unit_cost, 2),
                "roic_monthly_pct": roic_pct,
                "roic_source": roic_source,
                "roic_action": action,
                "requires_human_review": action == "REVIEW_REQUIRED",
                "d30": round(d30, 4),
                "k_avg_kzt": round(k_avg, 2),
                "days_with_sales": int(row["days_with_sales"] or 0),
                "is_new_sku": bool(is_new),
                "new_sku_cap_limit_pct": round(new_sku_cap_pct, 2),
                "exit_horizon_days": horizon,
                "exit_path": _exit_path(horizon_days=horizon, d30=d30),
            }
        )

    total_capital = round(sum(float(row["capital_at_risk_kzt"]) for row in proposals), 2)
    for row in proposals:
        share = (float(row["capital_at_risk_kzt"]) / total_capital * 100.0) if total_capital > 0 else 0.0
        row["capital_share_pct"] = round(share, 2)
        row["new_sku_cap_compliant"] = (not row["is_new_sku"]) or (share <= new_sku_cap_pct + 1e-9)

    ok = len(errors) == 0 and len(proposals) > 0
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "db_path": str(db_path.resolve()),
        "rules_doc_path": str(rules_doc_path.resolve()),
        "roic_thresholds_pct": {
            "order_full": ROIC_FULL_PCT,
            "order_with_flag": ROIC_FLAG_PCT,
        },
        "new_sku_cap_pct": new_sku_cap_pct,
        "proposal_count": len(proposals),
        "total_capital_at_risk_kzt": total_capital,
        "lines": proposals,
        "errors": errors,
    }
    json_path = out_dir / "po_proposals.json"
    md_path = out_dir / "po_proposals.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("po proposal generation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate PO proposals with capital-protection fields")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--rules-doc", type=Path, default=DEFAULT_RULES_DOC)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = generate_po_proposals(
        db_path=args.db,
        as_of=str(args.as_of),
        output_root=args.output_root,
        strict=bool(args.strict),
        rules_doc_path=args.rules_doc,
    )
    print(f"po_proposals_json={report['json_path']}")
    print(f"po_proposals_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
