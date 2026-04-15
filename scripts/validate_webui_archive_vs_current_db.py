#!/usr/bin/env python3
"""Compare WebUI archive truth projection against the current DB chronology."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.north_star_workbook_utils import load_db_truth
from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    coerce_iso_date_string,
    load_status_ledger,
    resolve_latest_dir,
)

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-06"
)


class WebuiArchiveVsCurrentDBError(RuntimeError):
    """Raised when the WebUI-vs-current-DB comparison cannot be validated."""


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


def _agg_day_store(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["sale_date", "store_code", f"{prefix}_orders", f"{prefix}_units", f"{prefix}_net_rev_kzt"])
    return (
        df.groupby(["sale_date", "store_code"], as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            units=("units", "sum"),
            net_rev_kzt=("net_rev_kzt", "sum"),
        )
        .rename(
            columns={
                "orders": f"{prefix}_orders",
                "units": f"{prefix}_units",
                "net_rev_kzt": f"{prefix}_net_rev_kzt",
            }
        )
    )


def _fetch_db_rows_for_orders_any_date(*, db_path: Path, order_ids: list[str]) -> pd.DataFrame:
    if not order_ids:
        return pd.DataFrame(columns=["order_id", "sale_date", "store_code"])
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        frames: list[pd.DataFrame] = []
        for offset in range(0, len(order_ids), 900):
            chunk = order_ids[offset : offset + 900]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"""
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    date(sale_date) AS sale_date,
                    UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code
                FROM view_sales_line_truth
                WHERE CAST(order_id AS TEXT) IN ({placeholders})
            """
            frames.append(pd.read_sql_query(query, conn, params=chunk))
    finally:
        conn.close()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["order_id", "sale_date", "store_code"])


def _load_quarantine_order_ids(quarantine_csv: Path | None) -> set[str]:
    if quarantine_csv is None:
        return set()
    candidate = quarantine_csv.expanduser()
    if not candidate.exists():
        return set()
    df = pd.read_csv(candidate, dtype=object, keep_default_na=False)
    if "order_id" not in df.columns:
        return set()
    return {
        str(value).strip()
        for value in df["order_id"].tolist()
        if str(value or "").strip()
    }


def _iter_quarantine_csv_paths(output_dir: Path) -> list[Path]:
    candidates: list[Path] = [output_dir / "db_quarantine_candidates.csv"]
    validation_root = PROJECT_ROOT / "exports" / "validation"
    for folder_name in ["webui_archive_single_truth", "webui_shipped_authority_recon"]:
        folder = validation_root / folder_name
        if not folder.exists():
            continue
        for child in sorted(folder.iterdir(), reverse=True):
            candidate = child / "db_quarantine_candidates.csv"
            if candidate.exists():
                candidates.append(candidate)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _load_workbook_anchor_quarantine_pairs(db_path: Path) -> set[tuple[str, str]]:
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='fact_sales_workbook_anchor_quarantine'
            """
        ).fetchone()
        if row is None:
            return set()
        columns = {
            str(result[1]).strip()
            for result in conn.execute("PRAGMA table_info(fact_sales_workbook_anchor_quarantine)").fetchall()
        }
        if "order_id" not in columns:
            return set()
        store_expr = "UPPER(TRIM(COALESCE(store_code, 'UNKNOWN')))" if "store_code" in columns else "'UNKNOWN'"
        rows = conn.execute(
            f"""
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                {store_expr} AS store_code
            FROM fact_sales_workbook_anchor_quarantine
            """
        ).fetchall()
        return {
            (str(order_id).strip(), str(store_code).strip().upper())
            for order_id, store_code in rows
            if str(order_id or "").strip()
        }
    finally:
        conn.close()


def _resolve_quarantine_csv(quarantine_csv: Path | None, output_dir: Path) -> Path | None:
    if quarantine_csv is not None:
        return quarantine_csv
    for candidate in _iter_quarantine_csv_paths(output_dir):
        if candidate.exists():
            return candidate
    return None


def _iter_chronology_authority_decision_paths(output_dir: Path) -> list[Path]:
    resolved_output_dir = output_dir.expanduser().resolve()
    candidates: list[Path] = []
    for candidate_dir in [resolved_output_dir, *list(resolved_output_dir.parents[:2])]:
        candidates.append(candidate_dir / "shipped_day_authority_decision.json")
    validation_root = PROJECT_ROOT / "exports" / "validation"
    for folder_name in ["webui_archive_single_truth", "webui_shipped_authority_recon"]:
        folder = validation_root / folder_name
        if not folder.exists():
            continue
        for child in sorted(folder.iterdir(), reverse=True):
            candidate = child / "shipped_day_authority_decision.json"
            if candidate.exists():
                candidates.append(candidate)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _load_chronology_authority_decision(output_dir: Path) -> str:
    for decision_path in _iter_chronology_authority_decision_paths(output_dir):
        if not decision_path.exists():
            continue
        try:
            payload = json.loads(decision_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        decision = str(payload.get("decision") or "").strip().upper()
        if decision:
            return decision
    return ""


def validate_webui_archive_vs_current_db(
    *,
    start: str,
    end: str,
    db_path: Path,
    ledger_root: Path | None,
    output_dir: Path,
    strict: bool,
    quarantine_csv: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_start = coerce_iso_date_string(start)
    normalized_end = coerce_iso_date_string(end)
    resolved_quarantine_csv = _resolve_quarantine_csv(quarantine_csv, output_dir)
    chronology_authority_decision = _load_chronology_authority_decision(output_dir)
    resolved_ledger_root = _resolve_ledger_root(ledger_root)
    webui_projection, projection_meta = build_webui_truth_projection(
        db_path=db_path.resolve(),
        ledger_run_root=resolved_ledger_root,
        start=normalized_start,
        end=normalized_end,
    )
    current_db = load_db_truth(db_path=db_path.resolve(), start=normalized_start, end=normalized_end)
    current_db = current_db[
        (current_db["sale_date"].astype(str) >= normalized_start)
        & (current_db["sale_date"].astype(str) <= normalized_end)
    ].copy()
    match_status = (
        webui_projection["db_match_status"]
        if "db_match_status" in webui_projection.columns
        else pd.Series(["MATCHED"] * len(webui_projection), index=webui_projection.index)
    )
    webui_matched = webui_projection[match_status == "MATCHED"].copy()

    by_day_store = _agg_day_store(webui_matched, "webui").merge(
        _agg_day_store(current_db, "db"),
        on=["sale_date", "store_code"],
        how="outer",
    ).fillna(0.0)
    by_day_store["orders_delta"] = by_day_store["webui_orders"] - by_day_store["db_orders"]
    by_day_store["units_delta"] = by_day_store["webui_units"] - by_day_store["db_units"]
    by_day_store["net_rev_delta_kzt"] = by_day_store["webui_net_rev_kzt"] - by_day_store["db_net_rev_kzt"]
    by_day_store = by_day_store.sort_values(["sale_date", "store_code"])

    db_orders = current_db[["order_id", "sale_date", "store_code"]].drop_duplicates()
    webui_orders = webui_matched[["order_id", "sale_date", "store_code"]].drop_duplicates()
    order_compare = webui_orders.merge(
        db_orders,
        on=["order_id"],
        how="outer",
        suffixes=("_webui", "_db"),
        indicator=True,
    )
    order_compare["classifier"] = order_compare["_merge"].map(
        {"left_only": "IN_WEBUI_ONLY", "right_only": "IN_DB_ONLY", "both": "BOTH"}
    ).astype(object)
    mismatch_mask = (
        (order_compare["classifier"] == "BOTH")
        & (
            (order_compare["sale_date_webui"] != order_compare["sale_date_db"])
            | (order_compare["store_code_webui"] != order_compare["store_code_db"])
        )
    )
    order_compare.loc[mismatch_mask, "classifier"] = "DATE_MISMATCH"

    webui_only_ids = sorted(order_compare.loc[order_compare["classifier"] == "IN_WEBUI_ONLY", "order_id"].dropna().astype(str).unique().tolist())
    db_any_date = _fetch_db_rows_for_orders_any_date(db_path=db_path.resolve(), order_ids=webui_only_ids)
    if not db_any_date.empty:
        outside_window_ids = set(
            db_any_date.loc[
                (db_any_date["sale_date"].astype(str) < normalized_start)
                | (db_any_date["sale_date"].astype(str) > normalized_end),
                "order_id",
            ]
            .dropna()
            .astype(str)
            .tolist()
        )
        drift_mask = (order_compare["classifier"] == "IN_WEBUI_ONLY") & order_compare["order_id"].astype(str).isin(outside_window_ids)
        order_compare.loc[drift_mask, "classifier"] = "DB_WINDOW_DRIFT_PREWINDOW"

    try:
        ledger, _ = load_status_ledger(resolved_ledger_root)
    except FileNotFoundError:
        ledger = pd.DataFrame(columns=["order_id", "returned_at"])
    ledger = ledger.reindex(columns=["order_id", "store_code", "delivered_at", "returned_at"], fill_value="").copy()
    returned_ids = set(
        ledger.loc[ledger["returned_at"].astype(str).str.strip() != "", "order_id"].dropna().astype(str).unique().tolist()
    )
    ledger_pairs = ledger.fillna("").copy()
    ledger_pairs["order_id"] = ledger_pairs["order_id"].astype(str).str.strip()
    ledger_pairs["store_code"] = ledger_pairs["store_code"].astype(str).str.strip().str.upper()
    delivered_postwindow_pairs = {
        (row.order_id, row.store_code)
        for row in ledger_pairs.itertuples(index=False)
        if str(row.delivered_at or "").strip() and str(row.delivered_at) > normalized_end
    }
    returned_only_mask = (order_compare["classifier"] == "IN_DB_ONLY") & order_compare["order_id"].astype(str).isin(returned_ids)
    order_compare.loc[returned_only_mask, "classifier"] = "DB_ONLY_RETURNED_IN_WEBUI"
    postwindow_membership = pd.Series(
        [
            (
                str(order_id).strip(),
                str(store_code).strip().upper(),
            )
            in delivered_postwindow_pairs
            for order_id, store_code in zip(order_compare["order_id"], order_compare["store_code_db"])
        ],
        index=order_compare.index,
    )
    postwindow_drift_mask = (
        (chronology_authority_decision == "CRM_REMAINS_CHRONOLOGY_AUTHORITY")
        & (order_compare["classifier"] == "IN_DB_ONLY")
        & postwindow_membership
    )
    order_compare.loc[postwindow_drift_mask, "classifier"] = "WEBUI_WINDOW_DRIFT_POSTWINDOW"
    quarantine_order_ids = _load_quarantine_order_ids(resolved_quarantine_csv)
    workbook_anchor_quarantine_pairs = _load_workbook_anchor_quarantine_pairs(db_path.resolve())
    quarantined_db_only_mask = (
        (order_compare["classifier"] == "IN_DB_ONLY")
        & order_compare["order_id"].astype(str).isin(quarantine_order_ids)
    )
    order_compare.loc[quarantined_db_only_mask, "classifier"] = "QUARANTINED_DB_ONLY"
    order_compare = order_compare.drop(columns=["_merge"]).sort_values(["classifier", "order_id"])

    missing_in_db_rows = webui_projection.loc[
        webui_projection["db_match_status"] == "MISSING_IN_DB",
        ["order_id", "store_code"],
    ].drop_duplicates()
    missing_in_db_ids = set(missing_in_db_rows["order_id"].dropna().astype(str).tolist())
    quarantined_missing_in_db_orders = len(missing_in_db_ids & quarantine_order_ids)
    workbook_anchor_quarantined_orders = 0
    if chronology_authority_decision == "CRM_REMAINS_CHRONOLOGY_AUTHORITY" and workbook_anchor_quarantine_pairs:
        workbook_anchor_quarantined_orders = len(
            {
                str(row.order_id).strip()
                for row in missing_in_db_rows.itertuples(index=False)
                if (
                    str(row.order_id).strip(),
                    str(row.store_code or "").strip().upper(),
                )
                in workbook_anchor_quarantine_pairs
            }
        )
    hard_missing_in_db_orders = max(
        0,
        int(projection_meta.get("missing_in_db_orders", 0))
        - int(quarantined_missing_in_db_orders + workbook_anchor_quarantined_orders),
    )
    chronology_delta_orders = int((order_compare["classifier"] == "DATE_MISMATCH").sum())
    hard_chronology_delta_orders = chronology_delta_orders
    if chronology_authority_decision == "CRM_REMAINS_CHRONOLOGY_AUTHORITY":
        hard_chronology_delta_orders = 0

    by_day_store_csv = output_dir / "webui_vs_db_by_day_store.csv"
    report_json = output_dir / "webui_vs_db_report.json"
    report_md = output_dir / "webui_vs_db_report.md"
    order_compare_csv = output_dir / "webui_vs_db_order_compare.csv"
    by_day_store.to_csv(by_day_store_csv, index=False, encoding="utf-8")
    order_compare.to_csv(order_compare_csv, index=False, encoding="utf-8")

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": (
            "PASS"
            if int(hard_missing_in_db_orders) == 0
            and int((order_compare["classifier"] == "IN_WEBUI_ONLY").sum()) == 0
            and int((order_compare["classifier"] == "IN_DB_ONLY").sum()) == 0
            and int(hard_chronology_delta_orders) == 0
            else "FAIL"
        ),
        "ok": (
            int(hard_missing_in_db_orders) == 0
            and int((order_compare["classifier"] == "IN_WEBUI_ONLY").sum()) == 0
            and int((order_compare["classifier"] == "IN_DB_ONLY").sum()) == 0
            and int(hard_chronology_delta_orders) == 0
        ),
        "strict": bool(strict),
        "period": {"start": normalized_start, "end": normalized_end},
        "ledger_root": str(resolved_ledger_root),
        "chronology_authority_decision": chronology_authority_decision or None,
        "projection_meta": projection_meta,
        "chronology_delta_orders": chronology_delta_orders,
        "hard_chronology_delta_orders": int(hard_chronology_delta_orders),
        "missing_in_db_orders": int(hard_missing_in_db_orders),
        "original_missing_in_db_orders": int(projection_meta.get("missing_in_db_orders", 0)),
        "db_only_orders": int((order_compare["classifier"] == "IN_DB_ONLY").sum()),
        "webui_only_orders": int((order_compare["classifier"] == "IN_WEBUI_ONLY").sum()),
        "window_drift_orders": int((order_compare["classifier"] == "DB_WINDOW_DRIFT_PREWINDOW").sum()),
        "postwindow_drift_orders": int((order_compare["classifier"] == "WEBUI_WINDOW_DRIFT_POSTWINDOW").sum()),
        "db_only_returned_orders": int((order_compare["classifier"] == "DB_ONLY_RETURNED_IN_WEBUI").sum()),
        "workbook_anchor_quarantined_orders": int(workbook_anchor_quarantined_orders),
        "quarantined_orders": int(
            quarantined_missing_in_db_orders
            + workbook_anchor_quarantined_orders
            + (order_compare["classifier"] == "QUARANTINED_DB_ONLY").sum()
        ),
        "outputs": {
            "webui_vs_db_by_day_store_csv": str(by_day_store_csv),
            "webui_vs_db_order_compare_csv": str(order_compare_csv),
            "webui_vs_db_report_json": str(report_json),
            "webui_vs_db_report_md": str(report_md),
            "quarantine_csv": str(resolved_quarantine_csv) if resolved_quarantine_csv is not None else None,
        },
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# WebUI vs Current DB",
                "",
                f"- status: `{report['status']}`",
                f"- chronology_delta_orders: `{report['chronology_delta_orders']}`",
                f"- hard_chronology_delta_orders: `{report['hard_chronology_delta_orders']}`",
                f"- db_only_orders: `{report['db_only_orders']}`",
                f"- webui_only_orders: `{report['webui_only_orders']}`",
                f"- window_drift_orders: `{report['window_drift_orders']}`",
                f"- postwindow_drift_orders: `{report['postwindow_drift_orders']}`",
                f"- db_only_returned_orders: `{report['db_only_returned_orders']}`",
                f"- workbook_anchor_quarantined_orders: `{report['workbook_anchor_quarantined_orders']}`",
                f"- quarantined_orders: `{report['quarantined_orders']}`",
                f"- missing_in_db_orders: `{report['missing_in_db_orders']}`",
                f"- original_missing_in_db_orders: `{report['original_missing_in_db_orders']}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if strict and not report["ok"]:
        raise WebuiArchiveVsCurrentDBError(
            f"webui vs current db failed: missing_in_db_orders={report['missing_in_db_orders']}"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate WebUI archive truth against current DB")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--db-path", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quarantine-csv", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_webui_archive_vs_current_db(
            start=str(args.start),
            end=str(args.end),
            db_path=args.db_path,
            ledger_root=args.ledger_root,
            output_dir=args.output_dir,
            strict=bool(args.strict),
            quarantine_csv=args.quarantine_csv,
        )
    except WebuiArchiveVsCurrentDBError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_CURRENT_DB_FAIL")
        print(f"message={exc}")
        return 1

    print(f"webui_vs_db_report_json={report['outputs']['webui_vs_db_report_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
