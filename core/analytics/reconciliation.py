"""Helpers for reconciling sales sources."""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd


def _to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def compare_sales_frames(
    crm_df: pd.DataFrame,
    fact_df: pd.DataFrame,
    *,
    crm_date_col: str = "order_date",
    fact_date_col: str = "order_date",
) -> dict:
    """
    Compare CRM vs Fact_Sales aggregated totals.

    Expects:
      crm_df columns: order_date, units, net_rev_line, order_id, sku_id
      fact_df columns: order_date, units, net_rev_line, order_id, sku_id
    """
    crm = crm_df.copy()
    fact = fact_df.copy()

    crm[crm_date_col] = _to_date(crm[crm_date_col])
    fact[fact_date_col] = _to_date(fact[fact_date_col])

    crm["units"] = _coerce_numeric(crm["units"]).fillna(0)
    fact["units"] = _coerce_numeric(fact["units"]).fillna(0)

    crm["net_rev_line"] = _coerce_numeric(crm["net_rev_line"]).fillna(0)
    fact["net_rev_line"] = _coerce_numeric(fact["net_rev_line"]).fillna(0)

    crm_by_date = (
        crm.groupby(crm_date_col)
        .agg(units=("units", "sum"), net_rev=("net_rev_line", "sum"))
        .reset_index()
        .rename(columns={crm_date_col: "date", "net_rev": "crm_net_rev"})
    )
    fact_by_date = (
        fact.groupby(fact_date_col)
        .agg(units=("units", "sum"), net_rev=("net_rev_line", "sum"))
        .reset_index()
        .rename(columns={fact_date_col: "date", "net_rev": "fact_net_rev"})
    )

    merged = crm_by_date.merge(fact_by_date, on="date", how="outer").fillna(0)
    merged["delta_units"] = merged["units_x"] - merged["units_y"]
    merged["delta_net_rev"] = merged["crm_net_rev"] - merged["fact_net_rev"]
    merged = merged.rename(columns={"units_x": "crm_units", "units_y": "fact_units"})

    def key_set(df: pd.DataFrame) -> set[tuple[str, str]]:
        if "order_id" not in df.columns or "sku_id" not in df.columns:
            return set()
        return set(zip(df["order_id"].astype(str), df["sku_id"].astype(str)))

    crm_keys = key_set(crm)
    fact_keys = key_set(fact)

    crm_dates = crm[crm_date_col].dropna()
    fact_dates = fact[fact_date_col].dropna()

    summary = {
        "crm_rows": int(len(crm)),
        "fact_rows": int(len(fact)),
        "crm_units": float(crm["units"].sum()),
        "fact_units": float(fact["units"].sum()),
        "crm_net_rev": float(crm["net_rev_line"].sum()),
        "fact_net_rev": float(fact["net_rev_line"].sum()),
        "missing_in_fact": len(crm_keys - fact_keys) if crm_keys and fact_keys else None,
        "missing_in_crm": len(fact_keys - crm_keys) if crm_keys and fact_keys else None,
        "crm_min_date": crm_dates.min() if not crm_dates.empty else None,
        "crm_max_date": crm_dates.max() if not crm_dates.empty else None,
        "fact_min_date": fact_dates.min() if not fact_dates.empty else None,
        "fact_max_date": fact_dates.max() if not fact_dates.empty else None,
    }

    return {
        "summary": summary,
        "by_date": merged.sort_values("date"),
    }
