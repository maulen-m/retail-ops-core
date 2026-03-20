#!/usr/bin/env python3
"""Validate COGS realism against forensic archive priors."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    resolve_latest_dir,
)
from scripts.webui_db_gate_utils import resolve_effective_missing_in_db_orders


class CogsRealismError(RuntimeError):
    """Raised when strict COGS realism validation fails."""


DEFAULT_FORENSIC = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/"
    "Purchase_orders/vibe_code_PO/Sales_archive/v2_sales_archive/"
    "run_20260304_032257/v2_sales_archive_all_status_2025-06-06_to_2026-03-02.xlsx"
)
DEFAULT_FORENSIC_REFERENCE_MANIFEST = PROJECT_ROOT / "config" / "cogs_forensic_reference.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate COGS realism vs forensic priors.")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-03-06")
    parser.add_argument("--forensic-file", default=str(DEFAULT_FORENSIC))
    parser.add_argument("--forensic-reference-manifest", type=Path, default=DEFAULT_FORENSIC_REFERENCE_MANIFEST)
    parser.add_argument("--max-month-gap-pct", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _resolve_output_dir(output_dir: Path | None, *, truth_source: str, as_of: str) -> Path:
    if output_dir is not None:
        return output_dir
    if truth_source == "webui_archive":
        return PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / as_of
    return PROJECT_ROOT / "exports" / "validation" / "crm_north_star_restate" / "2026-03-06"


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


def _load_forensic(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise CogsRealismError(f"forensic file not found: {path}")
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=object)
    else:
        df = pd.read_excel(path, sheet_name="all_status", dtype=object)

    required = {"mapped_sku_key", "final_cogs_kzt"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise CogsRealismError(f"forensic schema drift; missing columns: {', '.join(missing)}")

    delivered_mask = pd.Series([False] * len(df))
    if "is_delivered_truth_row" in df.columns:
        delivered_mask = (
            pd.to_numeric(df["is_delivered_truth_row"], errors="coerce").fillna(0).astype(int) == 1
        )
    if "status_internal" in df.columns:
        delivered_mask = delivered_mask | (
            df["status_internal"].fillna("").astype(str).str.upper() == "DELIVERED"
        )

    date_col = "conclusion_sale_date"
    if date_col not in df.columns:
        date_col = "truth_sale_date" if "truth_sale_date" in df.columns else "transaction_date"
    if date_col not in df.columns:
        raise CogsRealismError(
            "forensic file missing sale date columns (expected one of: conclusion_sale_date, truth_sale_date, transaction_date)"
        )

    out = pd.DataFrame()
    out["sale_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype("string")
    out["sale_month"] = out["sale_date"].str.slice(0, 7)
    out["sku_key"] = df.get("mapped_sku_key", "").fillna("").astype(str).str.strip()
    out["net_rev_kzt"] = pd.to_numeric(df.get("net_rev_kzt", 0), errors="coerce").fillna(0.0)
    out["cogs_kzt"] = pd.to_numeric(df.get("final_cogs_kzt", 0), errors="coerce").fillna(0.0)
    out["is_delivered"] = delivered_mask.fillna(False)
    out = out[out["is_delivered"] & out["sale_date"].notna()].copy()
    return out


def _load_forensic_reference_manifest(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return {}
    return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}


def _evaluate_supersession(
    *,
    manifest: dict[str, object],
    manifest_path: Path | None,
    truth_source: str,
) -> tuple[bool, list[dict[str, object]], str | None]:
    truth_sources = manifest.get("truth_sources") if isinstance(manifest, dict) else None
    if not isinstance(truth_sources, dict):
        return False, [], None
    decision = truth_sources.get(truth_source)
    if not isinstance(decision, dict):
        return False, [], None
    if str(decision.get("decision") or "").upper() != "SUPERSEDED":
        return False, [], None

    required_reports = decision.get("required_reports")
    checks: list[dict[str, object]] = []
    if not isinstance(required_reports, dict) or not required_reports:
        return False, checks, "supersession decision missing required_reports"

    for name, meta in required_reports.items():
        if not isinstance(meta, dict):
            checks.append({"name": name, "ok": False, "reason": "invalid_manifest_entry"})
            continue
        path = Path(str(meta.get("path") or "")).expanduser()
        if not path.is_absolute() and manifest_path is not None:
            path = manifest_path.expanduser().resolve().parent / path
        expected_status = str(meta.get("status") or "PASS").upper()
        if not path.exists():
            checks.append({"name": name, "ok": False, "path": str(path), "reason": "missing"})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            checks.append({"name": name, "ok": False, "path": str(path), "reason": "invalid_json"})
            continue
        actual_status = str(payload.get("status") or "").upper()
        ok = actual_status == expected_status
        checks.append(
            {
                "name": name,
                "ok": ok,
                "path": str(path),
                "expected_status": expected_status,
                "actual_status": actual_status,
            }
        )

    return all(bool(check.get("ok")) for check in checks), checks, str(decision.get("reason") or "")


def _load_db_lines(
    *,
    db_path: Path,
    truth_source: str,
    ledger_root: Path | None,
    start: str,
    end: str,
    output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, object] | None, list[str]]:
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
        rows["sku_key"] = rows["sku_key"].fillna("").astype(str).replace({"": "__UNMAPPED__"})
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
        return rows, projection_meta, truth_errors

    conn = sqlite3.connect(str(db_path))
    try:
        rows = pd.read_sql_query(
            """
            SELECT
                date(sale_date) AS sale_date,
                substr(sale_date,1,7) AS sale_month,
                UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                COALESCE(units,0) AS units,
                COALESCE(net_rev_kzt,0) AS net_rev_kzt,
                COALESCE(cogs_kzt,0) AS cogs_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN date(?) AND date(?)
            """,
            conn,
            params=[start, end],
        )
    finally:
        conn.close()
    return rows, None, []


def validate_cogs_realism_vs_forensic(
    *,
    start: str,
    end: str,
    strict: bool,
    db_path: Path,
    truth_source: str = "db",
    ledger_root: Path | None = None,
    as_of: str = "2026-03-06",
    forensic_file: Path,
    forensic_reference_manifest: Path | None = DEFAULT_FORENSIC_REFERENCE_MANIFEST,
    max_month_gap_pct: float,
    output_dir: Path | None = None,
) -> dict[str, object]:
    output_dir = _resolve_output_dir(output_dir, truth_source=truth_source, as_of=as_of)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_payload = _load_forensic_reference_manifest(forensic_reference_manifest)
    superseded_ok, supersession_checks, supersession_reason = _evaluate_supersession(
        manifest=manifest_payload,
        manifest_path=forensic_reference_manifest,
        truth_source=truth_source,
    )

    try:
        db_lines, projection_meta, truth_errors = _load_db_lines(
            db_path=db_path,
            truth_source=truth_source,
            ledger_root=ledger_root,
            start=start,
            end=end,
            output_dir=output_dir,
        )
    except FileNotFoundError as exc:
        if not (truth_source == "webui_archive" and superseded_ok):
            raise CogsRealismError(f"webui truth projection unavailable: {exc}") from exc
        db_lines = pd.DataFrame(
            columns=["sale_date", "sale_month", "store_code", "sku_key", "units", "net_rev_kzt", "cogs_kzt"]
        )
        projection_meta = {"status": "skipped_missing_ledger_root_superseded"}
        truth_errors = []
    forensic_lines = _load_forensic(forensic_file)
    forensic_lines = forensic_lines[
        (forensic_lines["sale_date"] >= start) & (forensic_lines["sale_date"] <= end)
    ].copy()

    db_month = db_lines.groupby("sale_month", as_index=False).agg(
        db_net_rev_kzt=("net_rev_kzt", "sum"),
        db_cogs_kzt=("cogs_kzt", "sum"),
    )
    forensic_month = forensic_lines.groupby("sale_month", as_index=False).agg(
        forensic_net_rev_kzt=("net_rev_kzt", "sum"),
        forensic_cogs_kzt=("cogs_kzt", "sum"),
    )
    month = db_month.merge(forensic_month, on="sale_month", how="outer").fillna(0.0)
    month["cogs_gap_kzt"] = month["db_cogs_kzt"] - month["forensic_cogs_kzt"]
    month["net_rev_gap_kzt"] = month["db_net_rev_kzt"] - month["forensic_net_rev_kzt"]
    month["cogs_gap_pct"] = (
        month["cogs_gap_kzt"].abs() / month["forensic_cogs_kzt"].abs().replace({0.0: 1.0})
    )
    month["realism_ok"] = month["cogs_gap_pct"] <= float(max_month_gap_pct)
    month = month.sort_values("sale_month")

    db_sku = db_lines.groupby("sku_key", as_index=False).agg(
        db_units=("units", "sum"),
        db_net_rev_kzt=("net_rev_kzt", "sum"),
        db_cogs_kzt=("cogs_kzt", "sum"),
    )
    forensic_sku = forensic_lines.groupby("sku_key", as_index=False).agg(
        forensic_lines=("sku_key", "count"),
        forensic_net_rev_kzt=("net_rev_kzt", "sum"),
        forensic_cogs_kzt=("cogs_kzt", "sum"),
    )
    sku = db_sku.merge(forensic_sku, on="sku_key", how="outer").fillna(0.0)
    sku["cogs_gap_kzt"] = sku["db_cogs_kzt"] - sku["forensic_cogs_kzt"]
    sku = sku.sort_values("sku_key")

    profit_at_risk = month.copy()
    profit_at_risk["profit_at_risk_kzt"] = (
        profit_at_risk["forensic_cogs_kzt"] - profit_at_risk["db_cogs_kzt"]
    ).clip(lower=0.0)
    profit_at_risk = profit_at_risk[
        ["sale_month", "db_cogs_kzt", "forensic_cogs_kzt", "profit_at_risk_kzt", "cogs_gap_pct"]
    ]

    month_csv = output_dir / "cogs_realism_by_month.csv"
    sku_csv = output_dir / "cogs_realism_by_sku.csv"
    risk_csv = output_dir / "cogs_profit_at_risk.csv"
    scope_md = output_dir / "cogs_restatement_scope.md"
    report_json = output_dir / "cogs_realism_report.json"

    month.to_csv(month_csv, index=False, encoding="utf-8")
    sku.to_csv(sku_csv, index=False, encoding="utf-8")
    profit_at_risk.to_csv(risk_csv, index=False, encoding="utf-8")

    fail_months = int((~month["realism_ok"]).sum()) if not month.empty else 0
    forensic_comparison_status = "SUPERSEDED" if superseded_ok else "ACTIVE"
    status = (
        "PASS"
        if ((fail_months == 0) or superseded_ok) and not truth_errors
        else "FAIL"
    )
    payload: dict[str, object] = {
        "status": status,
        "strict": strict,
        "truth_source": truth_source,
        "truth_projection": projection_meta,
        "truth_errors": truth_errors,
        "forensic_comparison_status": forensic_comparison_status,
        "forensic_reference_manifest": (
            str(Path(forensic_reference_manifest).expanduser().resolve())
            if forensic_reference_manifest is not None and Path(forensic_reference_manifest).expanduser().exists()
            else None
        ),
        "supersession_reason": supersession_reason,
        "supersession_checks": supersession_checks,
        "period": {"start": start, "end": end},
        "max_month_gap_pct": float(max_month_gap_pct),
        "fail_months": fail_months,
        "forensic_file": str(forensic_file),
        "outputs": {
            "cogs_realism_by_month_csv": str(month_csv.resolve()),
            "cogs_realism_by_sku_csv": str(sku_csv.resolve()),
            "cogs_profit_at_risk_csv": str(risk_csv.resolve()),
            "cogs_restatement_scope_md": str(scope_md.resolve()),
            "cogs_realism_report_json": str(report_json.resolve()),
        },
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    scope_md.write_text(
        "\n".join(
            [
                "# COGS Restatement Scope",
                "",
                f"- period: `{start}`..`{end}`",
                f"- status: `{status}`",
                f"- truth_source: `{truth_source}`",
                f"- fail_months: `{fail_months}`",
                f"- forensic_comparison_status: `{forensic_comparison_status}`",
                f"- max_month_gap_pct: `{float(max_month_gap_pct)}`",
                f"- forensic_file: `{forensic_file}`",
                f"- truth_errors: `{len(truth_errors)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if strict and status != "PASS":
        raise CogsRealismError(
            f"COGS realism failed: fail_months={fail_months} truth_errors={len(truth_errors)}"
        )
    return payload


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = validate_cogs_realism_vs_forensic(
            start=args.start,
            end=args.end,
            strict=args.strict,
            db_path=Path(args.db_path),
            truth_source=str(args.truth_source),
            ledger_root=args.ledger_root,
            as_of=str(args.as_of),
            forensic_file=Path(args.forensic_file),
            forensic_reference_manifest=args.forensic_reference_manifest,
            max_month_gap_pct=float(args.max_month_gap_pct),
            output_dir=args.output_dir,
        )
    except CogsRealismError as exc:
        print(str(exc))
        return 1
    print(f"cogs_realism_report_json={payload['outputs']['cogs_realism_report_json']}")
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
