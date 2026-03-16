#!/usr/bin/env python3
"""COGS completeness validator for Jan-Feb owner-truth scope."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    resolve_latest_dir,
)
from scripts.webui_db_gate_utils import resolve_effective_missing_in_db_orders

USD_KZT = 514.0
DLV = 2.66


class CogsCompletenessError(RuntimeError):
    """Raised when strict COGS completeness fails."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate COGS completeness by month.")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-03-06")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _resolve_output_dir(output_dir: Path | None, *, truth_source: str, as_of: str) -> Path:
    if output_dir is not None:
        return output_dir
    if truth_source == "webui_archive":
        return PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / as_of
    return PROJECT_ROOT / "exports" / "validation" / "crm_north_star_rebuild" / "2026-03-05"


def _resolve_ledger_root(ledger_root: Path | None) -> Path:
    if ledger_root is None:
        return resolve_latest_dir(DEFAULT_LEDGER_ROOT)
    candidate = ledger_root.expanduser()
    if candidate.exists():
        return candidate.resolve()
    alt = DEFAULT_LEDGER_ROOT / candidate
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(f"ledger root not found: {ledger_root}")


def _load_lines(
    *,
    db_path: Path,
    truth_source: str,
    ledger_root: Path | None,
    start: str,
    end: str,
    output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, object] | None, list[str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        dim_sku = pd.read_sql_query(
            "SELECT sku_key, model, base_cost_cny, weight_kg FROM dim_sku",
            conn,
        )
        if truth_source == "webui_archive":
            resolved_ledger_root = _resolve_ledger_root(ledger_root)
            rows, projection_meta = build_webui_truth_projection(
                db_path=db_path.resolve(),
                ledger_run_root=resolved_ledger_root,
                start=start,
                end=end,
            )
            match_status = (
                rows["db_match_status"]
                if "db_match_status" in rows.columns
                else pd.Series(["MATCHED"] * len(rows), index=rows.index)
            )
            rows = rows[match_status == "MATCHED"].copy()
            rows["sale_month"] = rows["sale_date"].astype(str).str.slice(0, 7)
            lines = rows.merge(dim_sku, on="sku_key", how="left")
            truth_errors: list[str] = []
            if int((projection_meta or {}).get("projected_rows", 0)) == 0:
                truth_errors.append("webui truth projection contains 0 rows")
            effective_missing_in_db_orders, _ = resolve_effective_missing_in_db_orders(
                output_dir=output_dir,
                ledger_root=resolved_ledger_root,
                start=start,
                end=end,
                projection_meta=projection_meta,
            )
            if effective_missing_in_db_orders > 0:
                truth_errors.append(
                    f"webui truth projection has missing_in_db_orders={effective_missing_in_db_orders}"
                )
            return lines, projection_meta, truth_errors

        lines = pd.read_sql_query(
            """
            SELECT
                CAST(v.order_id AS TEXT) AS order_id,
                date(v.sale_date) AS sale_date,
                substr(v.sale_date, 1, 7) AS sale_month,
                v.store_code,
                COALESCE(v.sku_key, '') AS sku_key,
                COALESCE(v.units, 0) AS units,
                COALESCE(v.net_rev_kzt, 0) AS net_rev_kzt,
                v.cogs_kzt,
                COALESCE(v.cogs_source, 'unresolved') AS cogs_source,
                ds.model,
                ds.base_cost_cny,
                ds.weight_kg
            FROM view_sales_line_truth v
            LEFT JOIN dim_sku ds ON ds.sku_key = v.sku_key
            WHERE date(v.sale_date) BETWEEN date(?) AND date(?)
            """,
            conn,
            params=[start, end],
        )
    finally:
        conn.close()
    return lines, None, []


def validate_cogs_completeness_by_month(
    *,
    start: str,
    end: str,
    strict: bool,
    db_path: Path,
    truth_source: str = "db",
    ledger_root: Path | None = None,
    as_of: str = "2026-03-06",
    output_dir: Path | None = None,
) -> dict[str, object]:
    output_dir = _resolve_output_dir(output_dir, truth_source=truth_source, as_of=as_of)
    output_dir.mkdir(parents=True, exist_ok=True)
    lines, projection_meta, truth_errors = _load_lines(
        db_path=db_path,
        truth_source=truth_source,
        ledger_root=ledger_root,
        start=start,
        end=end,
        output_dir=output_dir,
    )

    if lines.empty:
        lines = pd.DataFrame(
            columns=[
                "order_id",
                "sale_date",
                "sale_month",
                "store_code",
                "sku_key",
                "units",
                "net_rev_kzt",
                "cogs_kzt",
                "cogs_source",
                "model",
                "base_cost_cny",
                "weight_kg",
            ]
        )

    lines["is_unresolved"] = (
        (lines["cogs_source"].fillna("unresolved").astype(str).str.lower() == "unresolved")
        | (lines["cogs_kzt"].isna())
        | (lines["cogs_kzt"].fillna(0) <= 0)
    )
    lines["base_cost_cny"] = pd.to_numeric(lines["base_cost_cny"], errors="coerce").fillna(0.0)
    lines["weight_kg"] = pd.to_numeric(lines["weight_kg"], errors="coerce").fillna(0.0)
    lines["units"] = pd.to_numeric(lines["units"], errors="coerce").fillna(0.0)
    lines["net_rev_kzt"] = pd.to_numeric(lines["net_rev_kzt"], errors="coerce").fillna(0.0)
    lines["cogs_kzt"] = pd.to_numeric(lines["cogs_kzt"], errors="coerce")
    lines["is_base_only"] = (
        lines["is_unresolved"]
        & (lines["base_cost_cny"] > 0)
        & (lines["weight_kg"] <= 0)
    )

    def classify_reason(row: pd.Series) -> str:
        if not row["is_unresolved"]:
            return "RESOLVED"
        if not row["sku_key"]:
            return "MISSING_SKU_KEY"
        if row["base_cost_cny"] <= 0 and row["weight_kg"] <= 0:
            return "MISSING_BASE_AND_WEIGHT"
        if row["base_cost_cny"] <= 0:
            return "MISSING_BASE_COST"
        if row["weight_kg"] <= 0:
            return "MISSING_WEIGHT"
        return "UNRESOLVED_OTHER"

    lines["unresolved_reason"] = lines.apply(classify_reason, axis=1)
    model_weight_ref = (
        lines[lines["weight_kg"] > 0]
        .groupby("model", dropna=True)["weight_kg"]
        .median()
        .to_dict()
    )
    base_only_lines = lines[lines["is_base_only"]].copy()
    base_only_lines["estimated_weight_kg"] = base_only_lines["model"].map(model_weight_ref).fillna(0.0)
    base_only_lines["estimated_missing_freight_kzt"] = (
        base_only_lines["units"].fillna(0.0)
        * base_only_lines["estimated_weight_kg"]
        * USD_KZT
        * DLV
    ).round(2)
    weight_drift = base_only_lines[
        [
            "order_id",
            "sale_date",
            "sale_month",
            "store_code",
            "sku_key",
            "units",
            "model",
            "estimated_weight_kg",
            "estimated_missing_freight_kzt",
        ]
    ].copy()

    monthly = (
        lines.groupby("sale_month", as_index=False)
        .agg(
            lines_total=("order_id", "count"),
            unresolved_lines=("is_unresolved", "sum"),
            base_only_lines=("is_base_only", "sum"),
        )
        .sort_values("sale_month")
    )
    monthly["unresolved_pct"] = (
        (monthly["unresolved_lines"] / monthly["lines_total"].replace({0: 1})) * 100.0
    ).round(4)

    unresolved = lines[lines["is_unresolved"]].copy()
    base_only = lines[lines["is_base_only"]].copy()

    month_csv = output_dir / "cogs_completeness_by_month.csv"
    unresolved_csv = output_dir / "cogs_unresolved_lines.csv"
    base_only_csv = output_dir / "cogs_base_only_lines.csv"
    drift_csv = output_dir / "weight_drift_impact_report.csv"
    report_md = output_dir / "cogs_completeness_report.md"
    report_json = output_dir / "cogs_completeness_report.json"

    monthly.to_csv(month_csv, index=False, encoding="utf-8")
    unresolved.to_csv(unresolved_csv, index=False, encoding="utf-8")
    base_only.to_csv(base_only_csv, index=False, encoding="utf-8")
    weight_drift.to_csv(drift_csv, index=False, encoding="utf-8")

    status = (
        "PASS"
        if int(unresolved["is_unresolved"].sum()) == 0 and not truth_errors
        else "FAIL"
    )
    payload: dict[str, object] = {
        "status": status,
        "strict": strict,
        "truth_source": truth_source,
        "truth_projection": projection_meta,
        "truth_errors": truth_errors,
        "period": {"start": start, "end": end},
        "unresolved_lines": int(unresolved["is_unresolved"].sum()),
        "base_only_lines": int(base_only["is_base_only"].sum()),
        "weight_drift_rows": len(weight_drift),
        "outputs": {
            "cogs_completeness_by_month_csv": str(month_csv.resolve()),
            "cogs_unresolved_lines_csv": str(unresolved_csv.resolve()),
            "cogs_base_only_lines_csv": str(base_only_csv.resolve()),
            "weight_drift_impact_report_csv": str(drift_csv.resolve()),
            "cogs_completeness_report_md": str(report_md.resolve()),
            "cogs_completeness_report_json": str(report_json.resolve()),
        },
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# COGS Completeness Report",
                "",
                f"- period: `{start}`..`{end}`",
                f"- status: `{status}`",
                f"- truth_source: `{truth_source}`",
                f"- unresolved_lines: `{payload['unresolved_lines']}`",
                f"- base_only_lines: `{payload['base_only_lines']}`",
                f"- weight_drift_rows: `{payload['weight_drift_rows']}`",
                f"- truth_errors: `{len(truth_errors)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if strict and status != "PASS":
        raise CogsCompletenessError(
            f"COGS completeness failed: unresolved_lines={payload['unresolved_lines']} truth_errors={len(truth_errors)}"
        )
    return payload


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = validate_cogs_completeness_by_month(
            start=args.start,
            end=args.end,
            strict=args.strict,
            db_path=Path(args.db_path),
            truth_source=str(args.truth_source),
            ledger_root=args.ledger_root,
            as_of=str(args.as_of),
            output_dir=args.output_dir,
        )
    except CogsCompletenessError as exc:
        print(str(exc))
        return 1
    print(f"cogs_completeness_report_json={payload['outputs']['cogs_completeness_report_json']}")
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
