from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd
import yaml

COVERED_STATUSES = frozenset(
    {
        "COVERED",
        "NO_SPEND_VERIFIED",
        "COMPLETE",
        "COMPLETED",
        "OK",
        "MAPPED",
    }
)


class CanonicalAdsError(RuntimeError):
    """Raised when canonical ads truth cannot be projected safely."""


@dataclass(frozen=True)
class EffectiveCostPolicy:
    default_multiplier: float = 1.0
    date_overrides: tuple[dict[str, Any], ...] = ()

    def multiplier_for_day(self, day_iso: str) -> float:
        multiplier = self.default_multiplier
        for row in self.date_overrides:
            start = str(row.get("start_date") or "").strip()
            end = str(row.get("end_date") or "").strip()
            if start and day_iso < start:
                continue
            if end and day_iso > end:
                continue
            multiplier = float(row.get("multiplier", multiplier) or multiplier)
        return multiplier


DAILY_SKU_COLUMNS = [
    "ads_date",
    "sale_month",
    "store_code",
    "sku_key",
    "mapped",
    "ads_kzt",
    "mapped_cost_kzt",
    "unmapped_cost_kzt",
    "row_count",
    "mapped_rows",
    "unmapped_rows",
    "verified_no_spend_rows",
    "positive_spend_rows",
    "coverage_status",
    "source_run_id",
]

DAILY_STORE_COLUMNS = [
    "ads_date",
    "sale_month",
    "store_code",
    "total_cost_kzt",
    "mapped_cost_kzt",
    "unmapped_cost_kzt",
    "row_count",
    "mapped_rows",
    "unmapped_rows",
    "verified_no_spend_rows",
    "positive_spend_rows",
    "mapping_coverage_pct",
]

MONTHLY_STORE_COLUMNS = [
    "sale_month",
    "store_code",
    "total_cost_kzt",
    "ads_kzt",
    "mapped_cost_kzt",
    "unmapped_cost_kzt",
    "row_count",
    "mapped_rows",
    "unmapped_rows",
    "verified_no_spend_rows",
    "positive_spend_rows",
    "mapping_coverage_pct",
]

MONTHLY_SKU_COLUMNS = [
    "sale_month",
    "store_code",
    "sku_key",
    "ads_kzt",
    "mapped_cost_kzt",
    "unmapped_cost_kzt",
    "mapped",
    "row_count",
    "mapped_rows",
    "unmapped_rows",
    "verified_no_spend_rows",
    "positive_spend_rows",
]


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def canonical_tables_available(db_path: Path) -> bool:
    if not Path(db_path).exists():
        return False
    with sqlite3.connect(str(db_path)) as conn:
        return _table_exists(conn, "ads_campaign_product_daily") and _table_exists(
            conn, "ads_source_refresh_runs"
        )


def load_effective_cost_policy(policy_path: Path | None) -> EffectiveCostPolicy:
    if policy_path is None:
        return EffectiveCostPolicy()
    candidate = Path(policy_path).expanduser()
    if not candidate.exists():
        raise CanonicalAdsError(f"ads effective-cost policy missing: {candidate}")
    try:
        payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - exact yaml error varies
        raise CanonicalAdsError(f"ads effective-cost policy parse error: {candidate}") from exc
    return EffectiveCostPolicy(
        default_multiplier=float(payload.get("default_multiplier", 1.0) or 1.0),
        date_overrides=tuple(payload.get("date_overrides") or ()),
    )


def _normalize_status(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper() or "UNKNOWN"


def _join_unique(values: pd.Series) -> str:
    unique = sorted({str(v).strip() for v in values.tolist() if str(v or "").strip()})
    return ",".join(unique)


def load_daily_sku_ads(
    *,
    db_path: Path,
    start: str | date,
    end: str | date,
    effective_cost_mode: bool = False,
    effective_policy_path: Path | None = None,
) -> pd.DataFrame:
    """Project canonical ads rows to one daily SKU row per store/SKU/date."""

    db_path = Path(db_path)
    if not db_path.exists():
        return _empty_frame(DAILY_SKU_COLUMNS)

    with sqlite3.connect(str(db_path)) as conn:
        if not _table_exists(conn, "ads_campaign_product_daily"):
            return _empty_frame(DAILY_SKU_COLUMNS)
        raw = pd.read_sql_query(
            """
            SELECT
                date(date) AS ads_date,
                substr(date(date), 1, 7) AS sale_month,
                UPPER(TRIM(COALESCE(store_code, 'UNKNOWN'))) AS store_code,
                COALESCE(NULLIF(TRIM(CAST(sku_key AS TEXT)), ''), '__UNMAPPED__') AS sku_key,
                CAST(COALESCE(cost_kzt, 0) AS REAL) AS cost_kzt,
                COALESCE(source_run_id, '') AS source_run_id,
                UPPER(TRIM(COALESCE(coverage_status, 'UNKNOWN'))) AS coverage_status
            FROM ads_campaign_product_daily
            WHERE date(date) BETWEEN date(?) AND date(?)
            """,
            conn,
            params=[str(start), str(end)],
        )

    if raw.empty:
        return _empty_frame(DAILY_SKU_COLUMNS)

    policy = load_effective_cost_policy(effective_policy_path) if effective_cost_mode else EffectiveCostPolicy()
    raw["coverage_status"] = raw["coverage_status"].map(_normalize_status)
    raw["mapped"] = raw["coverage_status"].isin(COVERED_STATUSES).astype(int)
    raw["cost_kzt"] = pd.to_numeric(raw["cost_kzt"], errors="coerce").fillna(0.0)
    if effective_cost_mode:
        raw["cost_kzt"] = raw.apply(
            lambda row: float(row["cost_kzt"]) * policy.multiplier_for_day(str(row["ads_date"])),
            axis=1,
        )
    raw["mapped_cost_kzt"] = raw["cost_kzt"].where(raw["mapped"] == 1, 0.0)
    raw["unmapped_cost_kzt"] = raw["cost_kzt"].where(raw["mapped"] != 1, 0.0)
    raw["verified_no_spend_rows"] = (
        (raw["coverage_status"] == "NO_SPEND_VERIFIED") & (raw["cost_kzt"].abs() < 0.005)
    ).astype(int)
    raw["positive_spend_rows"] = (raw["cost_kzt"] > 0).astype(int)

    grouped = (
        raw.groupby(["ads_date", "sale_month", "store_code", "sku_key"], as_index=False)
        .agg(
            mapped=("mapped", "max"),
            ads_kzt=("cost_kzt", "sum"),
            mapped_cost_kzt=("mapped_cost_kzt", "sum"),
            unmapped_cost_kzt=("unmapped_cost_kzt", "sum"),
            row_count=("sku_key", "size"),
            mapped_rows=("mapped", "sum"),
            unmapped_rows=("mapped", lambda s: int((s != 1).sum())),
            verified_no_spend_rows=("verified_no_spend_rows", "sum"),
            positive_spend_rows=("positive_spend_rows", "sum"),
            coverage_status=("coverage_status", _join_unique),
            source_run_id=("source_run_id", _join_unique),
        )
        .sort_values(["ads_date", "store_code", "sku_key"])
        .reset_index(drop=True)
    )
    for column in ["ads_kzt", "mapped_cost_kzt", "unmapped_cost_kzt"]:
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0.0).round(2)
    return grouped[DAILY_SKU_COLUMNS].copy()


def _with_mapping_pct(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    total_rows = pd.to_numeric(frame["mapped_rows"], errors="coerce").fillna(0) + pd.to_numeric(
        frame["unmapped_rows"], errors="coerce"
    ).fillna(0)
    frame["mapping_coverage_pct"] = (
        (pd.to_numeric(frame["mapped_rows"], errors="coerce").fillna(0) / total_rows.replace({0: pd.NA}))
        * 100.0
    ).fillna(0.0).round(2)
    return frame


def load_daily_store_ads(
    *,
    db_path: Path,
    start: str | date,
    end: str | date,
    effective_cost_mode: bool = False,
    effective_policy_path: Path | None = None,
) -> pd.DataFrame:
    daily_sku = load_daily_sku_ads(
        db_path=db_path,
        start=start,
        end=end,
        effective_cost_mode=effective_cost_mode,
        effective_policy_path=effective_policy_path,
    )
    if daily_sku.empty:
        return _empty_frame(DAILY_STORE_COLUMNS)
    daily = (
        daily_sku.groupby(["ads_date", "sale_month", "store_code"], as_index=False)
        .agg(
            total_cost_kzt=("ads_kzt", "sum"),
            mapped_cost_kzt=("mapped_cost_kzt", "sum"),
            unmapped_cost_kzt=("unmapped_cost_kzt", "sum"),
            row_count=("row_count", "sum"),
            mapped_rows=("mapped_rows", "sum"),
            unmapped_rows=("unmapped_rows", "sum"),
            verified_no_spend_rows=("verified_no_spend_rows", "sum"),
            positive_spend_rows=("positive_spend_rows", "sum"),
        )
        .sort_values(["ads_date", "store_code"])
        .reset_index(drop=True)
    )
    for column in ["total_cost_kzt", "mapped_cost_kzt", "unmapped_cost_kzt"]:
        daily[column] = pd.to_numeric(daily[column], errors="coerce").fillna(0.0).round(2)
    daily = _with_mapping_pct(daily)
    return daily[DAILY_STORE_COLUMNS].copy()


def load_monthly_store_ads(
    *,
    db_path: Path,
    start: str | date,
    end: str | date,
    effective_cost_mode: bool = False,
    effective_policy_path: Path | None = None,
) -> pd.DataFrame:
    daily = load_daily_store_ads(
        db_path=db_path,
        start=start,
        end=end,
        effective_cost_mode=effective_cost_mode,
        effective_policy_path=effective_policy_path,
    )
    if daily.empty:
        return _empty_frame(MONTHLY_STORE_COLUMNS)
    monthly = (
        daily.groupby(["sale_month", "store_code"], as_index=False)
        .agg(
            total_cost_kzt=("total_cost_kzt", "sum"),
            mapped_cost_kzt=("mapped_cost_kzt", "sum"),
            unmapped_cost_kzt=("unmapped_cost_kzt", "sum"),
            row_count=("row_count", "sum"),
            mapped_rows=("mapped_rows", "sum"),
            unmapped_rows=("unmapped_rows", "sum"),
            verified_no_spend_rows=("verified_no_spend_rows", "sum"),
            positive_spend_rows=("positive_spend_rows", "sum"),
        )
        .sort_values(["sale_month", "store_code"])
        .reset_index(drop=True)
    )
    for column in ["total_cost_kzt", "mapped_cost_kzt", "unmapped_cost_kzt"]:
        monthly[column] = pd.to_numeric(monthly[column], errors="coerce").fillna(0.0).round(2)
    monthly["ads_kzt"] = monthly["total_cost_kzt"]
    monthly = _with_mapping_pct(monthly)
    return monthly[MONTHLY_STORE_COLUMNS].copy()


def load_monthly_sku_ads(
    *,
    db_path: Path,
    start: str | date,
    end: str | date,
    effective_cost_mode: bool = False,
    effective_policy_path: Path | None = None,
) -> pd.DataFrame:
    daily_sku = load_daily_sku_ads(
        db_path=db_path,
        start=start,
        end=end,
        effective_cost_mode=effective_cost_mode,
        effective_policy_path=effective_policy_path,
    )
    if daily_sku.empty:
        return _empty_frame(MONTHLY_SKU_COLUMNS)
    monthly = (
        daily_sku.groupby(["sale_month", "store_code", "sku_key"], as_index=False)
        .agg(
            ads_kzt=("ads_kzt", "sum"),
            mapped_cost_kzt=("mapped_cost_kzt", "sum"),
            unmapped_cost_kzt=("unmapped_cost_kzt", "sum"),
            mapped=("mapped", "max"),
            row_count=("row_count", "sum"),
            mapped_rows=("mapped_rows", "sum"),
            unmapped_rows=("unmapped_rows", "sum"),
            verified_no_spend_rows=("verified_no_spend_rows", "sum"),
            positive_spend_rows=("positive_spend_rows", "sum"),
        )
        .sort_values(["sale_month", "store_code", "sku_key"])
        .reset_index(drop=True)
    )
    for column in ["ads_kzt", "mapped_cost_kzt", "unmapped_cost_kzt"]:
        monthly[column] = pd.to_numeric(monthly[column], errors="coerce").fillna(0.0).round(2)
    return monthly[MONTHLY_SKU_COLUMNS].copy()


def load_daily_total_ads(
    *,
    db_path: Path,
    start: str | date,
    end: str | date,
    effective_cost_mode: bool = False,
    effective_policy_path: Path | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    daily = load_daily_store_ads(
        db_path=db_path,
        start=start,
        end=end,
        effective_cost_mode=effective_cost_mode,
        effective_policy_path=effective_policy_path,
    )
    if daily.empty:
        return {}, {
            "status": "unavailable",
            "reason": "canonical_ads_empty",
            "source_path": str(Path(db_path).resolve()),
            "mapped_rows": None,
            "unmapped_rows": None,
            "mapped_cost_kzt": None,
            "unmapped_cost_kzt": None,
            "total_cost_kzt": None,
            "mapping_coverage_pct": None,
        }
    by_date = (
        daily.groupby("ads_date", as_index=False)["total_cost_kzt"]
        .sum()
        .sort_values("ads_date")
    )
    mapped_rows = float(daily["mapped_rows"].sum())
    unmapped_rows = float(daily["unmapped_rows"].sum())
    total_rows = mapped_rows + unmapped_rows
    totals = {
        "status": "available",
        "reason": "canonical_ads_truth",
        "source_path": str(Path(db_path).resolve()),
        "mapped_rows": mapped_rows,
        "unmapped_rows": unmapped_rows,
        "mapped_cost_kzt": round(float(daily["mapped_cost_kzt"].sum()), 2),
        "unmapped_cost_kzt": round(float(daily["unmapped_cost_kzt"].sum()), 2),
        "total_cost_kzt": round(float(daily["total_cost_kzt"].sum()), 2),
        "mapping_coverage_pct": round((mapped_rows / total_rows) * 100.0, 2) if total_rows else 0.0,
        "canonical_table": "ads_campaign_product_daily",
    }
    return {
        str(row["ads_date"]): round(float(row["total_cost_kzt"] or 0.0), 2)
        for row in by_date.to_dict("records")
    }, totals


def load_readiness_metadata(
    *,
    db_path: Path,
    start: str | date,
    end: str | date,
) -> dict[str, Any]:
    db_path = Path(db_path)
    start_iso = str(start)
    end_iso = str(end)
    if not db_path.exists():
        return {
            "canonical_available": False,
            "missing_tables": ["ads_campaign_product_daily", "ads_source_refresh_runs"],
            "campaign_rows": 0,
            "refresh_rows": 0,
        }
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        has_campaign = _table_exists(conn, "ads_campaign_product_daily")
        has_refresh = _table_exists(conn, "ads_source_refresh_runs")
        missing = [
            name
            for name, ok in {
                "ads_campaign_product_daily": has_campaign,
                "ads_source_refresh_runs": has_refresh,
            }.items()
            if not ok
        ]
        campaign = None
        if has_campaign:
            campaign = conn.execute(
                """
                SELECT
                    COUNT(*) AS rows,
                    MIN(date(date)) AS min_date,
                    MAX(date(date)) AS max_date,
                    SUM(COALESCE(cost_kzt, 0)) AS total_cost_kzt,
                    SUM(CASE WHEN UPPER(TRIM(COALESCE(coverage_status, 'UNKNOWN'))) IN
                        ('COVERED','NO_SPEND_VERIFIED','COMPLETE','COMPLETED','OK','MAPPED')
                        THEN 1 ELSE 0 END) AS mapped_rows,
                    SUM(CASE WHEN UPPER(TRIM(COALESCE(coverage_status, 'UNKNOWN'))) IN
                        ('COVERED','NO_SPEND_VERIFIED','COMPLETE','COMPLETED','OK','MAPPED')
                        THEN 0 ELSE 1 END) AS unmapped_rows
                FROM ads_campaign_product_daily
                WHERE date(date) BETWEEN date(?) AND date(?)
                """,
                (start_iso, end_iso),
            ).fetchone()
        refresh = None
        if has_refresh:
            refresh = conn.execute(
                """
                SELECT
                    COUNT(*) AS rows,
                    MIN(date(date_start)) AS min_date_start,
                    MAX(date(date_end)) AS max_date_end,
                    SUM(COALESCE(product_rows_total, 0)) AS product_rows_total
                FROM ads_source_refresh_runs
                WHERE UPPER(COALESCE(status, '')) = 'SUCCESS'
                  AND date(date_start) <= date(?)
                  AND date(date_end) >= date(?)
                """,
                (end_iso, start_iso),
            ).fetchone()

    campaign_rows = int((campaign["rows"] if campaign is not None else 0) or 0)
    refresh_rows = int((refresh["rows"] if refresh is not None else 0) or 0)
    mapped_rows = float((campaign["mapped_rows"] if campaign is not None else 0.0) or 0.0)
    unmapped_rows = float((campaign["unmapped_rows"] if campaign is not None else 0.0) or 0.0)
    total_rows = mapped_rows + unmapped_rows
    return {
        "canonical_available": has_campaign and has_refresh,
        "missing_tables": missing,
        "campaign_rows": campaign_rows,
        "campaign_min_date": str(campaign["min_date"]) if campaign is not None and campaign["min_date"] else None,
        "campaign_max_date": str(campaign["max_date"]) if campaign is not None and campaign["max_date"] else None,
        "campaign_total_cost_kzt": round(float((campaign["total_cost_kzt"] if campaign is not None else 0.0) or 0.0), 2),
        "mapped_rows": mapped_rows,
        "unmapped_rows": unmapped_rows,
        "mapping_coverage_pct": round((mapped_rows / total_rows) * 100.0, 2) if total_rows else 0.0,
        "refresh_rows": refresh_rows,
        "refresh_min_date_start": (
            str(refresh["min_date_start"]) if refresh is not None and refresh["min_date_start"] else None
        ),
        "refresh_max_date_end": (
            str(refresh["max_date_end"]) if refresh is not None and refresh["max_date_end"] else None
        ),
        "refresh_product_rows_total": int((refresh["product_rows_total"] if refresh is not None else 0) or 0),
        "refresh_covers_start": bool(
            refresh is not None and refresh["min_date_start"] and str(refresh["min_date_start"]) <= start_iso
        ),
        "refresh_covers_end": bool(
            refresh is not None and refresh["max_date_end"] and str(refresh["max_date_end"]) >= end_iso
        ),
        "campaign_covers_end": bool(
            campaign is not None and campaign["max_date"] and str(campaign["max_date"]) >= end_iso
        ),
    }
