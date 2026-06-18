#!/usr/bin/env python3
"""Build April 23 stock re-anchor full-window coverage-closure packet."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rebuild_april23_stock_reanchor_split_views import (  # noqa: E402
    ANCHOR_XLSX,
    CRM_WORKBOOK,
    DB_PATH,
    GOOGLE_CLOSEOUT_DIR,
    LIVE_WEBUI_CSV,
    MANUAL_WEBUI_CSV,
    WEBUI_CLOSEOUT,
    build_stock_views,
    file_evidence,
    load_anchor,
    load_shipped_deduction_ledger,
    load_status_change_sales_ledger,
    make_blockers,
    make_sources,
    make_summary,
    protected_boundary_sample,
    protected_boundary_stable,
    sha256_file,
    write_dataframe_csv,
    write_workbooks,
)

OLD_PACKET_DIR = PROJECT_ROOT / "exports/validation/april23_stock_reanchor_statusdate_rebuild_20260526_165900"
ACTIVE_STORES = ("STOREB", "ACMEWEAR", "UNIVERSAL")
OWNER_INACTIVE_STORES = ("11KZ", "MELVIS")
WINDOW_SINCE = "2026-04-24"
WINDOW_UNTIL = "2026-05-26"
INACTIVE_STORE_OLD_BLOCKER = "MANUAL_WEBUI_PRE_2026_05_05_AND_2026_05_26_OMITS_11KZ_MELVIS"
INACTIVE_STORE_DISCLOSURE = (
    "OWNER_CONFIRMED_11KZ_MELVIS_INACTIVE_NO_ORDERS_OR_SALES_SINCE_2026_04_01_NOT_BLOCKER"
)
MANUAL_RUN_MANIFEST = (
    PROJECT_ROOT
    / "exports/validation/webui_archive_autonomous_refresh_20260526/source_refresh_runs/"
    "webui_archive_autonomous_refresh_20260526_manual_import_20260301_to_20260526/run_manifest.json"
)
LIVE_RUN_MANIFEST = (
    PROJECT_ROOT
    / "exports/validation/webui_archive_autonomous_refresh_20260526/full_parse_runs/"
    "webui_archive_autonomous_refresh_20260526_live_all_enabled_20260505_to_20260525__full_parse/"
    "run_manifest.json"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sorted_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted(str(item).strip().upper() for item in values if str(item).strip())


def manifest_covers_window(manifest: dict[str, Any], *, stores: tuple[str, ...]) -> bool:
    target_stores = set(sorted_list(manifest.get("target_stores") or manifest.get("stores")))
    return (
        str(manifest.get("since", "")) <= WINDOW_SINCE
        and str(manifest.get("until", "")) >= WINDOW_UNTIL
        and set(stores).issubset(target_stores)
        and str(manifest.get("status", "PASS")).upper() in {"PASS", "OK", "TRUE"}
        and bool(manifest.get("ok", True))
    )


def summarize_csv_window(path: Path, *, date_column: str = "status_change_at") -> dict[str, Any]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
    if "store_code" not in frame.columns:
        return {"path": str(path.resolve()), "row_count": int(len(frame)), "error": "missing store_code column"}
    dates = pd.to_datetime(frame.get(date_column, ""), errors="coerce")
    active_mask = frame["store_code"].astype(str).str.upper().isin(ACTIVE_STORES)
    window_mask = (dates.dt.strftime("%Y-%m-%d") >= WINDOW_SINCE) & (dates.dt.strftime("%Y-%m-%d") <= WINDOW_UNTIL)
    active_window = frame[active_mask & window_mask].copy()
    by_store = {
        store: int((active_window["store_code"].astype(str).str.upper() == store).sum())
        for store in ACTIVE_STORES
    }
    status_col = frame["status_internal"].astype(str).str.upper() if "status_internal" in frame.columns else pd.Series([])
    delivered_mask = status_col.isin({"DELIVERED", "COMPLETED", "ВЫДАН", "ЗАВЕРШЕН"}) if not status_col.empty else pd.Series([False] * len(frame))
    missing_completed_status_change = int(
        (active_mask & window_mask & delivered_mask & frame[date_column].astype(str).str.strip().eq("")).sum()
    )
    return {
        "path": str(path.resolve()),
        "file": file_evidence(path),
        "row_count": int(len(frame)),
        "active_window_row_count": int(len(active_window)),
        "active_window_row_count_by_store": by_store,
        "all_active_stores_present_in_window": all(count > 0 for count in by_store.values()),
        "status_change_min": str(dates.min().date()) if dates.notna().any() else "",
        "status_change_max": str(dates.max().date()) if dates.notna().any() else "",
        "completed_rows_missing_status_change_at": missing_completed_status_change,
    }


def summarize_api_companion(api_dir: Path) -> dict[str, Any]:
    manifest_path = api_dir / "manifest.json"
    all_csv = api_dir / "ArchiveOrders_ALL_STORES.csv"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    results = manifest.get("results", []) if isinstance(manifest.get("results"), list) else []
    result_rows = []
    for result in results:
        result_rows.append(
            {
                "store_code": result.get("store_code", ""),
                "success": bool(result.get("success")),
                "windows_total": int(result.get("windows_total") or 0),
                "windows_ok": int(result.get("windows_ok") or 0),
                "orders_selected": int(result.get("orders_selected") or 0),
                "rows_exported": int(result.get("rows_exported") or 0),
                "entry_fetch_failures": int(result.get("entry_fetch_failures") or 0),
                "errors": result.get("errors", []),
            }
        )
    active_stores = set(ACTIVE_STORES)
    result_stores = {str(row["store_code"]).upper() for row in result_rows}
    result_ok = all(
        row["success"] and row["windows_total"] == row["windows_ok"] and row["entry_fetch_failures"] == 0
        for row in result_rows
    )
    csv_summary: dict[str, Any] = {}
    if all_csv.exists():
        csv_frame = pd.read_csv(all_csv, dtype=str, keep_default_na=False).fillna("")
        store_col = "store_code" if "store_code" in csv_frame.columns else "store"
        if store_col in csv_frame.columns:
            csv_summary = {
                "row_count": int(len(csv_frame)),
                "row_count_by_store": {
                    store: int((csv_frame[store_col].astype(str).str.upper() == store).sum())
                    for store in ACTIVE_STORES
                },
            }
    ok = (
        manifest_path.exists()
        and all_csv.exists()
        and str(manifest.get("since")) == WINDOW_SINCE
        and str(manifest.get("until")) == WINDOW_UNTIL
        and set(sorted_list(manifest.get("stores"))) == active_stores
        and str(manifest.get("date_mode")) == "creationDate"
        and bool(manifest.get("fetch_entries")) is True
        and active_stores.issubset(result_stores)
        and result_ok
    )
    return {
        "role": "API companion evidence for order/SKU/line-item identity only; does not replace WebUI status_change_at truth",
        "ok": ok,
        "api_dir": str(api_dir.resolve()),
        "manifest": file_evidence(manifest_path) if manifest_path.exists() else None,
        "all_stores_csv": file_evidence(all_csv) if all_csv.exists() else None,
        "manifest_core": {
            "since": manifest.get("since"),
            "until": manifest.get("until"),
            "stores": manifest.get("stores", []),
            "date_mode": manifest.get("date_mode"),
            "fetch_entries": manifest.get("fetch_entries"),
            "strict": manifest.get("strict"),
        },
        "results": result_rows,
        "csv_summary": csv_summary,
    }


def relabel_inactive_store_coverage_notes(status_ledger: pd.DataFrame) -> pd.DataFrame:
    out = status_ledger.copy()
    replacements = {
        "manual_webui_only_storeb_acmewear_universal_omits_store-d_store-c": (
            "manual_webui_active_store_scope_owner_confirmed_store-d_store-c_inactive_not_blocker"
        ),
        "manual_webui_2026-05-26_storeb_acmewear_universal_omits_store-d_store-c": (
            "manual_webui_2026_05_26_active_store_scope_owner_confirmed_store-d_store-c_inactive_not_blocker"
        ),
    }
    if "coverage_note" in out.columns:
        out["coverage_note"] = out["coverage_note"].replace(replacements)
    return out


def remove_retained_blocker(frame: pd.DataFrame, blocker: str) -> pd.DataFrame:
    out = frame.copy()
    if "retained_blockers" not in out.columns:
        return out

    def clean(value: Any) -> str:
        parts = [part.strip() for part in str(value or "").split(";")]
        return "; ".join(part for part in parts if part and part != blocker)

    out["retained_blockers"] = out["retained_blockers"].map(clean)
    return out


def build_delta(old_packet_dir: Path, new_summary: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    old_summary = pd.read_csv(old_packet_dir / "summary.csv", dtype=str, keep_default_na=False)
    for _, new_row in new_summary.iterrows():
        metric = str(new_row["metric"])
        old_match = old_summary[old_summary["metric"] == metric]
        old_value = float(old_match.iloc[0]["value"]) if not old_match.empty else 0.0
        new_value = float(new_row["value"])
        rows.append(
            {
                "scope": "TOTAL",
                "family": "",
                "sku_key": "",
                "my_size": "",
                "metric": metric,
                "old_value": old_value,
                "new_value": new_value,
                "delta": new_value - old_value,
            }
        )

    comparisons = [
        (
            "PHYSICAL_WAREHOUSE_STOCK_ESTIMATE",
            "physical_warehouse_stock_estimate_by_sku_size.csv",
            "estimated_warehouse_on_hand_qty",
        ),
        (
            "ECONOMIC_FINAL_SALES_STOCK",
            "economic_final_sales_stock_by_sku_size.csv",
            "estimated_final_sales_stock_qty",
        ),
        (
            "INVENTORY_ON_DELIVERY_EXPOSURE",
            "inventory_on_delivery_exposure_by_sku_size.csv",
            "on_delivery_exposure_qty",
        ),
        (
            "MISSING_SHIPPED_SOURCE_GAP",
            "inventory_on_delivery_exposure_by_sku_size.csv",
            "missing_shipped_source_gap_qty",
        ),
    ]
    for view, filename, value_col in comparisons:
        old_frame = pd.read_csv(old_packet_dir / filename, dtype=str, keep_default_na=False)
        new_frame = pd.read_csv(output_dir / filename, dtype=str, keep_default_na=False)
        keys = ["family", "sku_key", "my_size"]
        merged = old_frame[keys + [value_col]].rename(columns={value_col: "old_value"}).merge(
            new_frame[keys + [value_col]].rename(columns={value_col: "new_value"}),
            on=keys,
            how="outer",
        )
        for _, row in merged.iterrows():
            old_value = float(row.get("old_value") or 0)
            new_value = float(row.get("new_value") or 0)
            rows.append(
                {
                    "scope": "SKU_SIZE",
                    "family": row.get("family", ""),
                    "sku_key": row.get("sku_key", ""),
                    "my_size": row.get("my_size", ""),
                    "metric": f"{view}.{value_col}",
                    "old_value": old_value,
                    "new_value": new_value,
                    "delta": new_value - old_value,
                }
            )

    old_blockers = pd.read_csv(old_packet_dir / "retained_blockers.csv", dtype=str, keep_default_na=False)
    new_blockers = pd.read_csv(output_dir / "retained_blockers.csv", dtype=str, keep_default_na=False)
    for blocker in [
        INACTIVE_STORE_OLD_BLOCKER,
        "MISSING_SHIPPED_SOURCE_FOR_SOME_DELIVERED_ROWS",
        "NO_CONFIRMED_POST_ANCHOR_INBOUND_SOURCE",
        "NO_RETURN_QC_ACCEPTANCE_SOURCE",
        "CHILD_BUNDLE_COMPONENT_STOCK_SPLIT_NOT_PROVEN",
        "SIZE_SOURCE_MISMATCH_SKU_ID_VS_ASSIGNED_SIZE",
    ]:
        old_count = int((old_blockers["blocker"] == blocker).sum())
        new_count = int((new_blockers["blocker"] == blocker).sum())
        rows.append(
            {
                "scope": "BLOCKER_COUNT",
                "family": "",
                "sku_key": "",
                "my_size": "",
                "metric": blocker,
                "old_value": old_count,
                "new_value": new_count,
                "delta": new_count - old_count,
            }
        )
    return pd.DataFrame(rows)


def write_owner_clarification(path: Path) -> None:
    text = f"""# Owner Inactive-Store Scope Clarification

Generated: {datetime.now().isoformat(timespec="seconds")}

Owner-confirmed truth for this April 23 stock re-anchor coverage-closure lane:

- As of `2026-05-26`, `11KZ` and `MELVIS` are fully inactive.
- Owner confirms `11KZ` and `MELVIS` have had no active orders or sales since `2026-04-01`.
- Missing broad WebUI ArchiveOrders coverage for `11KZ` and `MELVIS` after `2026-04-23` is therefore disclosed as an owner-confirmed inactive-store omission, not a sales-data blocker.
- Active sales stores for this rebuild scope are `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.

This clarification does not authorize production DB writes, workbook writes,
scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes,
Kaspi/API/WebUI mutations, stock/price/ad/cash/PO actions, owner publication,
production preflight, or production apply.
"""
    path.write_text(text, encoding="utf-8")


def write_closeout(
    path: Path,
    *,
    gate_color: str,
    summary: pd.DataFrame,
    blockers: pd.DataFrame,
    delta: pd.DataFrame,
    webui_ok: bool,
    api_ok: bool,
    boundary_stable: bool,
) -> None:
    summary_lines = "\n".join(
        f"- `{row.metric}` = `{float(row.value):g}` ({row.date_basis})"
        for row in summary.itertuples(index=False)
    )
    delta_lines = "\n".join(
        f"- `{row.metric}`: `{float(row.old_value):g}` -> `{float(row.new_value):g}` "
        f"(`{float(row.delta):+g}`)"
        for row in delta[delta["scope"] == "TOTAL"].itertuples(index=False)
    )
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers["blocker"].drop_duplicates().tolist()) or "- none"
    text = f"""# April 23 Stock Re-Anchor Full-Window Coverage Closure

Gate: **{gate_color}**

## Owner Scope Clarification
- `11KZ` and `MELVIS` are owner-confirmed inactive as of `2026-05-26` with no active orders or sales since `2026-04-01`.
- Missing broad WebUI ArchiveOrders coverage for those stores after `2026-04-23` is disclosed as an inactive-store omission, not a blocker.
- Active sales stores for this rebuild are `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.

## Source Coverage
- Active-store WebUI full-window coverage closed: `{webui_ok}`.
- API companion order/SKU evidence for the same active-store/full-window scope completed: `{api_ok}`.
- API evidence is not used as WebUI `Дата изменения статуса` / sale truth.

## Split Stock Views
{summary_lines}

## Delta vs 20260526_165900
{delta_lines}

See `delta_vs_20260526_165900.csv` for LINE61/LINE51 by-size deltas and blocker-count deltas.

## Retained Blockers
{blocker_lines}

## Protected Surfaces
- `db/app.db` unchanged during rebuild packet generation: `{boundary_stable}`.
- `excel_ui/SALES_KSP_CRM_V3.xlsx` unchanged during rebuild packet generation: `{boundary_stable}`.
- No production DB/workbook/scheduler/source-pointer/Web_automation/Kaspi/API/WebUI/external mutation was performed by this closure script.

## Date Vocabulary Guard
- Warehouse stock deducts by `ship_date`.
- Economic final-sales stock deducts only by WebUI `status_change_at` / `Дата изменения статуса` for delivered/completed rows.
- `order_intake_date` is retained as intake/demand context only and is not used as final sale truth.
"""
    path.write_text(text, encoding="utf-8")


def build_coverage_closure_packet(
    *,
    output_dir: Path,
    api_companion_dir: Path,
    old_packet_dir: Path,
    as_of: date,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    boundary_before = protected_boundary_sample()

    anchor_df = load_anchor(ANCHOR_XLSX)
    status_ledger = load_status_change_sales_ledger(
        MANUAL_WEBUI_CSV,
        LIVE_WEBUI_CSV,
        anchor_date=date(2026, 4, 23),
        as_of=as_of,
    )
    status_ledger = relabel_inactive_store_coverage_notes(status_ledger)
    shipped_ledger = load_shipped_deduction_ledger(
        DB_PATH,
        GOOGLE_CLOSEOUT_DIR,
        anchor_date=date(2026, 4, 23),
        as_of=as_of,
    )
    physical, economic, exposure, _base = build_stock_views(anchor_df, status_ledger, shipped_ledger)
    economic = remove_retained_blocker(economic, INACTIVE_STORE_OLD_BLOCKER)
    summary = make_summary(physical, economic, exposure)

    outputs = {
        "owner_inactive_store_scope_clarification": output_dir / "owner_inactive_store_scope_clarification.md",
        "source_coverage_closure_manifest": output_dir / "source_coverage_closure_manifest.json",
        "refreshed_or_reused_webui_archive_evidence_manifest": output_dir
        / "refreshed_or_reused_webui_archive_evidence_manifest.json",
        "api_companion_evidence_manifest": output_dir / "api_companion_evidence_manifest.json",
        "physical_warehouse_stock_estimate_by_sku_size": output_dir / "physical_warehouse_stock_estimate_by_sku_size.csv",
        "economic_final_sales_stock_by_sku_size": output_dir / "economic_final_sales_stock_by_sku_size.csv",
        "inventory_on_delivery_exposure_by_sku_size": output_dir / "inventory_on_delivery_exposure_by_sku_size.csv",
        "status_change_sales_ledger": output_dir / "status_change_sales_ledger.csv",
        "shipped_deduction_ledger": output_dir / "shipped_deduction_ledger.csv",
        "delta_vs_20260526_165900": output_dir / "delta_vs_20260526_165900.csv",
        "current_stock_valuation": output_dir / "current_stock_valuation.xlsx",
        "inventory_business_eval_tables": output_dir / "inventory_business_eval_tables.xlsx",
        "retained_blockers": output_dir / "retained_blockers.csv",
        "closeout": output_dir / "closeout.md",
        "summary": output_dir / "summary.csv",
        "source_evidence": output_dir / "source_evidence.csv",
    }

    write_dataframe_csv(physical, outputs["physical_warehouse_stock_estimate_by_sku_size"])
    write_dataframe_csv(economic, outputs["economic_final_sales_stock_by_sku_size"])
    write_dataframe_csv(exposure, outputs["inventory_on_delivery_exposure_by_sku_size"])
    write_dataframe_csv(status_ledger, outputs["status_change_sales_ledger"])
    write_dataframe_csv(shipped_ledger, outputs["shipped_deduction_ledger"])

    blockers = make_blockers(physical, economic, exposure)
    write_dataframe_csv(blockers, outputs["retained_blockers"])
    write_dataframe_csv(summary, outputs["summary"])
    sources = make_sources(
        {
            "anchor_workbook": ANCHOR_XLSX,
            "manual_webui_csv": MANUAL_WEBUI_CSV,
            "manual_webui_run_manifest": MANUAL_RUN_MANIFEST,
            "live_webui_csv": LIVE_WEBUI_CSV,
            "live_webui_run_manifest": LIVE_RUN_MANIFEST,
            "api_companion_manifest": api_companion_dir / "manifest.json",
            "webui_closeout": WEBUI_CLOSEOUT,
            "db_app_readonly": DB_PATH,
            "crm_workbook_protected_surface": CRM_WORKBOOK,
            "google_ops_closeout_salesraw_snapshot": GOOGLE_CLOSEOUT_DIR / "salesraw_snapshot.json",
        }
    )
    write_dataframe_csv(sources, outputs["source_evidence"])

    delta = build_delta(old_packet_dir, summary, output_dir)
    write_dataframe_csv(delta, outputs["delta_vs_20260526_165900"])

    write_owner_clarification(outputs["owner_inactive_store_scope_clarification"])

    manual_manifest = read_json(MANUAL_RUN_MANIFEST)
    live_manifest = read_json(LIVE_RUN_MANIFEST)
    webui_manifest = {
        "role": "WebUI ArchiveOrders source truth for status_change_at / Дата изменения статуса",
        "active_sales_stores": list(ACTIVE_STORES),
        "owner_confirmed_inactive_omissions": list(OWNER_INACTIVE_STORES),
        "window": {"since": WINDOW_SINCE, "until": WINDOW_UNTIL, "basis": "status_change_at"},
        "product_scope": "all_products",
        "manual_reused_full_window_source": {
            "run_manifest": file_evidence(MANUAL_RUN_MANIFEST),
            "manifest_core": {
                "run_id": manual_manifest.get("run_id"),
                "since": manual_manifest.get("since"),
                "until": manual_manifest.get("until"),
                "target_stores": manual_manifest.get("target_stores"),
                "omitted_enabled_stores": manual_manifest.get("omitted_enabled_stores"),
                "status": manual_manifest.get("status"),
                "pack_integrity_ok": manual_manifest.get("pack_integrity_ok"),
                "read_only": manual_manifest.get("read_only"),
            },
            "csv_summary": summarize_csv_window(MANUAL_WEBUI_CSV),
            "covers_active_store_full_window": manifest_covers_window(manual_manifest, stores=ACTIVE_STORES),
        },
        "live_overlap_reused_source": {
            "run_manifest": file_evidence(LIVE_RUN_MANIFEST),
            "manifest_core": {
                "run_id": live_manifest.get("run_id"),
                "since": live_manifest.get("since"),
                "until": live_manifest.get("until"),
                "target_stores": live_manifest.get("target_stores"),
                "status": live_manifest.get("status"),
                "pack_integrity_ok": live_manifest.get("pack_integrity_ok"),
            },
            "csv_summary": summarize_csv_window(LIVE_WEBUI_CSV),
            "covers_active_store_full_window": manifest_covers_window(live_manifest, stores=ACTIVE_STORES),
        },
    }
    webui_ok = bool(webui_manifest["manual_reused_full_window_source"]["covers_active_store_full_window"])
    webui_manifest["active_store_full_window_coverage_closed"] = webui_ok
    webui_manifest["inactive_store_omission_disclosure"] = INACTIVE_STORE_DISCLOSURE
    write_json(outputs["refreshed_or_reused_webui_archive_evidence_manifest"], webui_manifest)

    api_manifest = summarize_api_companion(api_companion_dir)
    write_json(outputs["api_companion_evidence_manifest"], api_manifest)
    api_ok = bool(api_manifest["ok"])

    write_workbooks(
        current_stock_xlsx=outputs["current_stock_valuation"],
        business_eval_xlsx=outputs["inventory_business_eval_tables"],
        physical=physical,
        exposure=exposure,
        economic=economic,
        status_ledger=status_ledger,
        shipped_ledger=shipped_ledger,
        blockers=blockers,
        sources=sources,
        summary=summary,
    )

    boundary_after = protected_boundary_sample()
    boundary_stable = protected_boundary_stable(boundary_before, boundary_after)
    gate_color = "RED" if not boundary_stable else ("YELLOW" if not webui_ok or not api_ok or not blockers.empty else "GREEN")

    write_closeout(
        outputs["closeout"],
        gate_color=gate_color,
        summary=summary,
        blockers=blockers,
        delta=delta,
        webui_ok=webui_ok,
        api_ok=api_ok,
        boundary_stable=boundary_stable,
    )

    closure_manifest = {
        "run_id": output_dir.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gate_color": gate_color,
        "scope": "copied-temp/read-only April 23 stock re-anchor full-window coverage closure",
        "active_sales_stores": list(ACTIVE_STORES),
        "owner_confirmed_inactive_stores": list(OWNER_INACTIVE_STORES),
        "inactive_store_disclosure": INACTIVE_STORE_DISCLOSURE,
        "window": {"since": WINDOW_SINCE, "until": WINDOW_UNTIL},
        "webui_active_store_full_window_coverage_closed": webui_ok,
        "api_companion_active_store_full_window_completed": api_ok,
        "api_status_truth_promotion": False,
        "date_vocabulary_guard": {
            "physical_warehouse_stock_date_basis": "ship_date",
            "economic_final_sales_stock_date_basis": "WebUI status_change_at / Дата изменения статуса",
            "order_intake_date_used_as_sale_truth": False,
        },
        "protected_boundary": {
            "before_generation": boundary_before,
            "after_generation": boundary_after,
            "stable": boundary_stable,
        },
        "summary": summary.to_dict(orient="records"),
        "retained_blocker_count": int(len(blockers)),
        "retained_blockers": sorted(blockers["blocker"].drop_duplicates().tolist()) if not blockers.empty else [],
        "source_manifests": {
            "webui": str(outputs["refreshed_or_reused_webui_archive_evidence_manifest"].resolve()),
            "api_companion": str(outputs["api_companion_evidence_manifest"].resolve()),
        },
        "outputs": {name: file_evidence(path) for name, path in outputs.items() if path.exists()},
        "not_authorized": [
            "production DB writes",
            "production workbook writes",
            "scheduler/LaunchAgent/cron changes",
            "source-pointer writes",
            "Web_automation writes",
            "Kaspi/API/WebUI mutations",
            "stock changes",
            "price changes",
            "ad changes",
            "cash movement",
            "PO commitment",
            "supplier payment",
            "owner publication",
            "production preflight",
            "production apply",
        ],
        "red_stopline_checks": {
            "protected_surface_drift_during_generation": not boundary_stable,
            "order_intake_date_used_as_final_sale_truth": False,
            "source_mutation": False,
            "secret_exposure": False,
        },
    }
    write_json(outputs["source_coverage_closure_manifest"], closure_manifest)

    return {
        "output_dir": str(output_dir.resolve()),
        "gate_color": gate_color,
        "summary": summary.to_dict(orient="records"),
        "retained_blocker_count": int(len(blockers)),
        "webui_active_store_full_window_coverage_closed": webui_ok,
        "api_companion_active_store_full_window_completed": api_ok,
        "protected_boundary_stable": boundary_stable,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-companion-dir", type=Path, required=True)
    parser.add_argument("--old-packet-dir", type=Path, default=OLD_PACKET_DIR)
    parser.add_argument("--as-of", default=WINDOW_UNTIL)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = build_coverage_closure_packet(
        output_dir=args.output_dir.expanduser().resolve(),
        api_companion_dir=args.api_companion_dir.expanduser().resolve(),
        old_packet_dir=args.old_packet_dir.expanduser().resolve(),
        as_of=date.fromisoformat(args.as_of),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
