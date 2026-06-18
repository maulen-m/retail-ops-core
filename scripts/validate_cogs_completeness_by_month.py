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

CHILDSUM_CNY_KZT = 72.55808287
USD_KZT = 514.0
DLV = 2.66
UNIT_COGS_COPIED_TEMP_SOURCE = "owner_approved_unit_cogs_copied_temp"
CHILDSUM_COGS_COPIED_TEMP_SOURCE = "childsum_component_formula_copied_temp"


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
    parser.add_argument(
        "--unit-cogs-evidence-csv",
        type=Path,
        default=None,
        help=(
            "Optional copied-temp-only unit COGS evidence CSV. "
            "Rows must include sku_key, approved_unit_cogs_kzt, copied_temp_only=true, "
            "and production_write_authorized=false."
        ),
    )
    parser.add_argument(
        "--childsum-cogs-evidence-csv",
        type=Path,
        default=None,
        help=(
            "Optional copied-temp-only ChildSum component COGS evidence CSV. "
            "Rows must include child_sku_key, component_key, component_base_cost_cny, "
            "component_weight_kg, copied_temp_only=true, and production_write_authorized=false."
        ),
    )
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


def _normalize_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


def _parse_evidence_bool(value: object, *, column: str, row_number: int, path: Path) -> bool:
    if isinstance(value, bool):
        return value
    text = "" if value is None or pd.isna(value) else str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise CogsCompletenessError(
        f"{path}: row {row_number} has invalid {column}; expected explicit true/false"
    )


def _load_unit_cogs_evidence(unit_cogs_evidence_csv: Path) -> pd.DataFrame:
    path = unit_cogs_evidence_csv.expanduser()
    if not path.exists():
        raise CogsCompletenessError(f"unit COGS evidence CSV not found: {path}")

    evidence = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {
        "sku_key",
        "approved_unit_cogs_kzt",
        "copied_temp_only",
        "production_write_authorized",
    }
    missing = sorted(required - set(evidence.columns))
    if missing:
        raise CogsCompletenessError(
            f"{path}: unit COGS evidence missing required columns: {', '.join(missing)}"
        )
    if evidence.empty:
        raise CogsCompletenessError(f"{path}: unit COGS evidence is empty")

    records: list[dict[str, object]] = []
    for idx, row in evidence.iterrows():
        row_number = int(idx) + 2
        sku_key = str(row.get("sku_key", "")).strip()
        sku_key_norm = _normalize_key(sku_key)
        if not sku_key_norm:
            raise CogsCompletenessError(f"{path}: row {row_number} missing sku_key")

        unit_cogs = pd.to_numeric(row.get("approved_unit_cogs_kzt"), errors="coerce")
        if pd.isna(unit_cogs) or float(unit_cogs) <= 0:
            raise CogsCompletenessError(
                f"{path}: row {row_number} approved_unit_cogs_kzt must be positive"
            )

        if not _parse_evidence_bool(
            row.get("copied_temp_only"),
            column="copied_temp_only",
            row_number=row_number,
            path=path,
        ):
            raise CogsCompletenessError(
                f"{path}: row {row_number} requires copied_temp_only=true"
            )
        if _parse_evidence_bool(
            row.get("production_write_authorized"),
            column="production_write_authorized",
            row_number=row_number,
            path=path,
        ):
            raise CogsCompletenessError(
                f"{path}: row {row_number} requires production_write_authorized=false"
            )

        order_id = str(row.get("order_id", "")).strip() if "order_id" in evidence.columns else ""
        order_id_norm = _normalize_key(order_id)
        scope = "order_sku" if order_id_norm else "sku"
        records.append(
            {
                "scope": scope,
                "order_id": order_id,
                "order_id_norm": order_id_norm,
                "sku_key": sku_key,
                "sku_key_norm": sku_key_norm,
                "approved_unit_cogs_kzt": float(unit_cogs),
                "source_parent_sku": str(row.get("source_parent_sku", "")).strip(),
                "decision_basis": str(row.get("decision_basis", "")).strip(),
            }
        )

    loaded = pd.DataFrame(records)
    exact_dupes = loaded[loaded["scope"] == "order_sku"].duplicated(
        ["order_id_norm", "sku_key_norm"],
        keep=False,
    )
    sku_dupes = loaded[loaded["scope"] == "sku"].duplicated(["sku_key_norm"], keep=False)
    if exact_dupes.any() or sku_dupes.any():
        raise CogsCompletenessError(f"{path}: ambiguous duplicate unit COGS evidence rows")
    return loaded


def _empty_unit_cogs_applied() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "order_id",
            "sale_date",
            "store_code",
            "sku_key",
            "units",
            "approved_unit_cogs_kzt",
            "resolved_cogs_kzt",
            "cogs_source",
            "evidence_scope",
            "source_parent_sku",
            "decision_basis",
        ]
    )


def _load_childsum_cogs_evidence(childsum_cogs_evidence_csv: Path) -> pd.DataFrame:
    path = childsum_cogs_evidence_csv.expanduser()
    if not path.exists():
        raise CogsCompletenessError(f"ChildSum COGS evidence CSV not found: {path}")

    evidence = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {
        "child_sku_key",
        "component_key",
        "component_base_cost_cny",
        "component_weight_kg",
        "copied_temp_only",
        "production_write_authorized",
    }
    missing = sorted(required - set(evidence.columns))
    if missing:
        raise CogsCompletenessError(
            f"{path}: ChildSum COGS evidence missing required columns: {', '.join(missing)}"
        )
    if evidence.empty:
        raise CogsCompletenessError(f"{path}: ChildSum COGS evidence is empty")

    records: list[dict[str, object]] = []
    for idx, row in evidence.iterrows():
        row_number = int(idx) + 2
        child_sku_key = str(row.get("child_sku_key", "")).strip()
        child_sku_key_norm = _normalize_key(child_sku_key)
        if not child_sku_key_norm:
            raise CogsCompletenessError(f"{path}: row {row_number} missing child_sku_key")

        component_key = str(row.get("component_key", "")).strip()
        component_key_norm = _normalize_key(component_key)
        if not component_key_norm:
            raise CogsCompletenessError(f"{path}: row {row_number} missing component_key")

        base_cost_cny = pd.to_numeric(row.get("component_base_cost_cny"), errors="coerce")
        weight_kg = pd.to_numeric(row.get("component_weight_kg"), errors="coerce")
        if pd.isna(base_cost_cny) or float(base_cost_cny) <= 0:
            raise CogsCompletenessError(
                f"{path}: row {row_number} component_base_cost_cny must be positive"
            )
        if pd.isna(weight_kg) or float(weight_kg) <= 0:
            raise CogsCompletenessError(
                f"{path}: row {row_number} component_weight_kg must be positive"
            )

        if not _parse_evidence_bool(
            row.get("copied_temp_only"),
            column="copied_temp_only",
            row_number=row_number,
            path=path,
        ):
            raise CogsCompletenessError(
                f"{path}: row {row_number} requires copied_temp_only=true"
            )
        if _parse_evidence_bool(
            row.get("production_write_authorized"),
            column="production_write_authorized",
            row_number=row_number,
            path=path,
        ):
            raise CogsCompletenessError(
                f"{path}: row {row_number} requires production_write_authorized=false"
            )

        order_id = str(row.get("order_id", "")).strip() if "order_id" in evidence.columns else ""
        order_id_norm = _normalize_key(order_id)
        scope = "order_sku" if order_id_norm else "sku"
        records.append(
            {
                "scope": scope,
                "order_id": order_id,
                "order_id_norm": order_id_norm,
                "child_sku_key": child_sku_key,
                "child_sku_key_norm": child_sku_key_norm,
                "component_key": component_key,
                "component_key_norm": component_key_norm,
                "component_base_cost_cny": float(base_cost_cny),
                "component_weight_kg": float(weight_kg),
                "component_source_sku": str(row.get("component_source_sku", "")).strip(),
                "decision_basis": str(row.get("decision_basis", "")).strip(),
            }
        )

    loaded = pd.DataFrame(records)
    duplicate_components = loaded.duplicated(
        ["scope", "order_id_norm", "child_sku_key_norm", "component_key_norm"],
        keep=False,
    )
    if duplicate_components.any():
        raise CogsCompletenessError(f"{path}: duplicate ChildSum component evidence rows")

    group_sizes = loaded.groupby(
        ["scope", "order_id_norm", "child_sku_key_norm"],
        dropna=False,
    )["component_key_norm"].nunique()
    if (group_sizes < 2).any():
        raise CogsCompletenessError(
            f"{path}: ChildSum evidence requires at least two components per child bundle"
        )
    return loaded


def _empty_childsum_cogs_applied() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "order_id",
            "sale_date",
            "store_code",
            "sku_key",
            "units",
            "component_count",
            "component_base_cost_cny_sum",
            "component_weight_kg_sum",
            "approved_unit_cogs_kzt",
            "resolved_cogs_kzt",
            "cogs_source",
            "evidence_scope",
            "component_keys",
            "component_source_skus",
            "decision_basis",
        ]
    )


def _build_childsum_lookup(evidence: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, object]]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for (scope, order_id_norm, child_sku_key_norm), group in evidence.groupby(
        ["scope", "order_id_norm", "child_sku_key_norm"],
        dropna=False,
    ):
        base_sum = float(group["component_base_cost_cny"].sum())
        weight_sum = float(group["component_weight_kg"].sum())
        unit_cogs = round(
            (base_sum * CHILDSUM_CNY_KZT) + (weight_sum * USD_KZT * DLV),
            2,
        )
        grouped[(str(scope), str(order_id_norm), str(child_sku_key_norm))] = {
            "scope": str(scope),
            "order_id_norm": str(order_id_norm),
            "child_sku_key_norm": str(child_sku_key_norm),
            "component_count": int(group["component_key_norm"].nunique()),
            "component_base_cost_cny_sum": base_sum,
            "component_weight_kg_sum": weight_sum,
            "approved_unit_cogs_kzt": unit_cogs,
            "component_keys": ";".join(group["component_key"].astype(str).tolist()),
            "component_source_skus": ";".join(
                sorted(
                    {
                        value
                        for value in group["component_source_sku"].astype(str).tolist()
                        if value
                    }
                )
            ),
            "decision_basis": "; ".join(
                sorted(
                    {
                        value
                        for value in group["decision_basis"].astype(str).tolist()
                        if value
                    }
                )
            ),
        }
    return grouped


def _apply_childsum_cogs_evidence(
    lines: pd.DataFrame,
    childsum_cogs_evidence_csv: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if childsum_cogs_evidence_csv is None:
        return lines, _empty_childsum_cogs_applied()

    evidence = _load_childsum_cogs_evidence(childsum_cogs_evidence_csv)
    if lines.empty:
        return lines, _empty_childsum_cogs_applied()

    lines = lines.copy()
    if "cogs_source" not in lines.columns:
        lines["cogs_source"] = "unresolved"
    lines["units"] = pd.to_numeric(lines["units"], errors="coerce").fillna(0.0)
    lines["cogs_kzt"] = pd.to_numeric(lines["cogs_kzt"], errors="coerce")

    lookup = _build_childsum_lookup(evidence)
    applied: list[dict[str, object]] = []
    unresolved_mask = (
        (lines["cogs_source"].fillna("unresolved").astype(str).str.lower() == "unresolved")
        | (lines["cogs_kzt"].isna())
        | (lines["cogs_kzt"].fillna(0) <= 0)
    )
    for idx, row in lines[unresolved_mask].iterrows():
        units = float(row.get("units") or 0.0)
        if units <= 0:
            continue

        order_id_norm = _normalize_key(row.get("order_id"))
        sku_key_norm = _normalize_key(row.get("sku_key"))
        if not sku_key_norm:
            continue

        exact_match = lookup.get(("order_sku", order_id_norm, sku_key_norm))
        sku_match = lookup.get(("sku", "", sku_key_norm))
        if exact_match is not None and sku_match is not None:
            exact_unit = float(exact_match["approved_unit_cogs_kzt"])
            sku_unit = float(sku_match["approved_unit_cogs_kzt"])
            if abs(exact_unit - sku_unit) > 0.0001:
                raise CogsCompletenessError(
                    f"conflicting ChildSum COGS evidence for order={row.get('order_id')} "
                    f"sku={row.get('sku_key')}"
                )
        match = exact_match if exact_match is not None else sku_match
        if match is None:
            continue

        unit_cogs = float(match["approved_unit_cogs_kzt"])
        resolved_cogs = round(unit_cogs * units, 2)
        lines.at[idx, "cogs_kzt"] = resolved_cogs
        lines.at[idx, "cogs_source"] = CHILDSUM_COGS_COPIED_TEMP_SOURCE
        applied.append(
            {
                "order_id": row.get("order_id"),
                "sale_date": row.get("sale_date"),
                "store_code": row.get("store_code"),
                "sku_key": row.get("sku_key"),
                "units": units,
                "component_count": match["component_count"],
                "component_base_cost_cny_sum": match["component_base_cost_cny_sum"],
                "component_weight_kg_sum": match["component_weight_kg_sum"],
                "approved_unit_cogs_kzt": unit_cogs,
                "resolved_cogs_kzt": resolved_cogs,
                "cogs_source": CHILDSUM_COGS_COPIED_TEMP_SOURCE,
                "evidence_scope": match["scope"],
                "component_keys": match["component_keys"],
                "component_source_skus": match["component_source_skus"],
                "decision_basis": match["decision_basis"],
            }
        )

    applied_df = pd.DataFrame(applied)
    if applied_df.empty:
        applied_df = _empty_childsum_cogs_applied()
    return lines, applied_df


def _apply_unit_cogs_evidence(
    lines: pd.DataFrame,
    unit_cogs_evidence_csv: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if unit_cogs_evidence_csv is None:
        return lines, _empty_unit_cogs_applied()

    evidence = _load_unit_cogs_evidence(unit_cogs_evidence_csv)
    if lines.empty:
        return lines, _empty_unit_cogs_applied()

    lines = lines.copy()
    if "cogs_source" not in lines.columns:
        lines["cogs_source"] = "unresolved"
    lines["units"] = pd.to_numeric(lines["units"], errors="coerce").fillna(0.0)
    lines["cogs_kzt"] = pd.to_numeric(lines["cogs_kzt"], errors="coerce")

    exact_lookup = {
        (str(row["order_id_norm"]), str(row["sku_key_norm"])): row
        for _, row in evidence[evidence["scope"] == "order_sku"].iterrows()
    }
    sku_lookup = {
        str(row["sku_key_norm"]): row
        for _, row in evidence[evidence["scope"] == "sku"].iterrows()
    }

    applied: list[dict[str, object]] = []
    unresolved_mask = (
        (lines["cogs_source"].fillna("unresolved").astype(str).str.lower() == "unresolved")
        | (lines["cogs_kzt"].isna())
        | (lines["cogs_kzt"].fillna(0) <= 0)
    )
    for idx, row in lines[unresolved_mask].iterrows():
        units = float(row.get("units") or 0.0)
        if units <= 0:
            continue

        order_id_norm = _normalize_key(row.get("order_id"))
        sku_key_norm = _normalize_key(row.get("sku_key"))
        if not sku_key_norm:
            continue

        exact_match = exact_lookup.get((order_id_norm, sku_key_norm))
        sku_match = sku_lookup.get(sku_key_norm)
        if exact_match is not None and sku_match is not None:
            exact_unit = float(exact_match["approved_unit_cogs_kzt"])
            sku_unit = float(sku_match["approved_unit_cogs_kzt"])
            if abs(exact_unit - sku_unit) > 0.0001:
                raise CogsCompletenessError(
                    f"conflicting unit COGS evidence for order={row.get('order_id')} "
                    f"sku={row.get('sku_key')}"
                )
        match = exact_match if exact_match is not None else sku_match
        if match is None:
            continue

        unit_cogs = float(match["approved_unit_cogs_kzt"])
        resolved_cogs = round(unit_cogs * units, 2)
        lines.at[idx, "cogs_kzt"] = resolved_cogs
        lines.at[idx, "cogs_source"] = UNIT_COGS_COPIED_TEMP_SOURCE
        applied.append(
            {
                "order_id": row.get("order_id"),
                "sale_date": row.get("sale_date"),
                "store_code": row.get("store_code"),
                "sku_key": row.get("sku_key"),
                "units": units,
                "approved_unit_cogs_kzt": unit_cogs,
                "resolved_cogs_kzt": resolved_cogs,
                "cogs_source": UNIT_COGS_COPIED_TEMP_SOURCE,
                "evidence_scope": match["scope"],
                "source_parent_sku": match["source_parent_sku"],
                "decision_basis": match["decision_basis"],
            }
        )

    applied_df = pd.DataFrame(applied)
    if applied_df.empty:
        applied_df = _empty_unit_cogs_applied()
    return lines, applied_df


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
    unit_cogs_evidence_csv: Path | None = None,
    childsum_cogs_evidence_csv: Path | None = None,
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

    lines["base_cost_cny"] = pd.to_numeric(lines["base_cost_cny"], errors="coerce").fillna(0.0)
    lines["weight_kg"] = pd.to_numeric(lines["weight_kg"], errors="coerce").fillna(0.0)
    lines["units"] = pd.to_numeric(lines["units"], errors="coerce").fillna(0.0)
    lines["net_rev_kzt"] = pd.to_numeric(lines["net_rev_kzt"], errors="coerce").fillna(0.0)
    lines["cogs_kzt"] = pd.to_numeric(lines["cogs_kzt"], errors="coerce")
    lines, childsum_cogs_applied = _apply_childsum_cogs_evidence(
        lines,
        childsum_cogs_evidence_csv,
    )
    lines, unit_cogs_applied = _apply_unit_cogs_evidence(lines, unit_cogs_evidence_csv)
    lines["is_unresolved"] = (
        (lines["cogs_source"].fillna("unresolved").astype(str).str.lower() == "unresolved")
        | (lines["cogs_kzt"].isna())
        | (lines["cogs_kzt"].fillna(0) <= 0)
    )
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
    unit_cogs_csv = output_dir / "cogs_unit_evidence_applied_lines.csv"
    childsum_cogs_csv = output_dir / "cogs_childsum_evidence_applied_lines.csv"
    report_md = output_dir / "cogs_completeness_report.md"
    report_json = output_dir / "cogs_completeness_report.json"

    monthly.to_csv(month_csv, index=False, encoding="utf-8")
    unresolved.to_csv(unresolved_csv, index=False, encoding="utf-8")
    base_only.to_csv(base_only_csv, index=False, encoding="utf-8")
    weight_drift.to_csv(drift_csv, index=False, encoding="utf-8")
    unit_cogs_applied.to_csv(unit_cogs_csv, index=False, encoding="utf-8")
    childsum_cogs_applied.to_csv(childsum_cogs_csv, index=False, encoding="utf-8")

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
        "unit_cogs_evidence_source_csv": (
            str(unit_cogs_evidence_csv.expanduser().resolve())
            if unit_cogs_evidence_csv is not None
            else None
        ),
        "childsum_cogs_evidence_source_csv": (
            str(childsum_cogs_evidence_csv.expanduser().resolve())
            if childsum_cogs_evidence_csv is not None
            else None
        ),
        "unit_cogs_evidence_applied_lines": len(unit_cogs_applied),
        "childsum_cogs_evidence_applied_lines": len(childsum_cogs_applied),
        "outputs": {
            "cogs_completeness_by_month_csv": str(month_csv.resolve()),
            "cogs_unresolved_lines_csv": str(unresolved_csv.resolve()),
            "cogs_base_only_lines_csv": str(base_only_csv.resolve()),
            "weight_drift_impact_report_csv": str(drift_csv.resolve()),
            "cogs_unit_evidence_applied_lines_csv": str(unit_cogs_csv.resolve()),
            "cogs_childsum_evidence_applied_lines_csv": str(childsum_cogs_csv.resolve()),
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
                f"- unit_cogs_evidence_applied_lines: `{payload['unit_cogs_evidence_applied_lines']}`",
                f"- childsum_cogs_evidence_applied_lines: `{payload['childsum_cogs_evidence_applied_lines']}`",
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
            unit_cogs_evidence_csv=args.unit_cogs_evidence_csv,
            childsum_cogs_evidence_csv=args.childsum_cogs_evidence_csv,
        )
    except CogsCompletenessError as exc:
        print(str(exc))
        return 1
    print(f"cogs_completeness_report_json={payload['outputs']['cogs_completeness_report_json']}")
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
