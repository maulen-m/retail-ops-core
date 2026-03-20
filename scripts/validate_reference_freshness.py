#!/usr/bin/env python3
"""Validate delivered-reference freshness to prevent ambiguous 'no rows' failures."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import re
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import StatusError, parse_iso_date, write_json

DEFAULT_REFERENCE_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"


def _parse_range_dir(path: Path) -> tuple[date, date] | None:
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})", path.name)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    except ValueError:
        return None


def _resolve_dataset_path(reference_root: Path, as_of: date) -> Path:
    exact = reference_root / f"2025-06-06_to_{as_of.isoformat()}" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    if exact.exists():
        return exact.resolve()

    candidates: list[tuple[date, Path]] = []
    for d in reference_root.glob("*_to_*"):
        if not d.is_dir():
            continue
        rng = _parse_range_dir(d)
        if rng is None:
            continue
        _start, end = rng
        csv = d / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
        if csv.exists() and end <= as_of:
            candidates.append((end, csv.resolve()))

    if not candidates:
        raise StatusError(
            "REFERENCE_STALE",
            f"no mapped reference dataset found under {reference_root}; run export_sales_archive_statusdate_mapped.py",
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def validate_reference_freshness(
    *,
    as_of: date,
    reference_root: Path,
    output_root: Path,
    max_delivery_lag_days: int,
    enforce_per_store: bool,
    strict: bool,
    statusdate_cutover: date | None = None,
) -> dict[str, Any]:
    if max_delivery_lag_days < 0:
        raise StatusError("REFERENCE_STALE", "max_delivery_lag_days must be >= 0")

    csv_path = _resolve_dataset_path(reference_root.resolve(), as_of)
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if df.empty:
        raise StatusError("REFERENCE_STALE", f"reference dataset empty: {csv_path}")

    required = {"transaction_date", "status_internal", "return_flag", "store_code"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise StatusError("REFERENCE_STALE", f"reference dataset missing columns: {', '.join(missing)}")

    delivered = df[
        (df["status_internal"].astype(str).str.upper() == "DELIVERED")
        & (df["return_flag"].astype(str).str.strip().isin({"0", "0.0", ""}))
    ].copy()
    if delivered.empty:
        raise StatusError(
            "REFERENCE_STALE",
            "reference has no delivered rows; refresh mapped dataset with recent statusChangeDate coverage",
        )

    delivered["_tx_date"] = pd.to_datetime(delivered["transaction_date"], errors="coerce")
    delivered = delivered[delivered["_tx_date"].notna()].copy()
    if delivered.empty:
        raise StatusError("REFERENCE_STALE", "delivered rows have invalid transaction_date values")

    max_date = delivered["_tx_date"].max().date()
    effective_as_of = min(as_of, statusdate_cutover) if statusdate_cutover is not None else as_of
    lag_days = (effective_as_of - max_date).days

    per_store = (
        delivered.groupby(delivered["store_code"].str.upper())["_tx_date"]
        .max()
        .reset_index()
        .rename(columns={"store_code": "store_code", "_tx_date": "max_delivered_date"})
    )
    per_store_rows: list[dict[str, Any]] = []
    stale_stores: list[str] = []
    for _, row in per_store.iterrows():
        store = str(row["store_code"])
        max_store = row["max_delivered_date"].date()
        store_lag = (effective_as_of - max_store).days
        per_store_rows.append(
            {
                "store_code": store,
                "max_delivered_date": max_store.isoformat(),
                "lag_days": int(store_lag),
            }
        )
        if store_lag > max_delivery_lag_days:
            stale_stores.append(store)

    if lag_days > max_delivery_lag_days:
        raise StatusError(
            "REFERENCE_STALE",
            (
                f"reference max delivered date {max_date.isoformat()} is stale by {lag_days} day(s); "
                "run export_sales_archive_statusdate_mapped.py for latest range and refresh external/UI pack"
            ),
        )
    if enforce_per_store and stale_stores:
        raise StatusError(
            "REFERENCE_STALE",
            f"reference stale per-store for: {', '.join(sorted(set(stale_stores)))}",
        )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "validate_reference_freshness.json"
    report_md = out_dir / "validate_reference_freshness.md"

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "reference_csv": str(csv_path),
        "status": "PASS",
        "error_code": "",
        "max_delivery_lag_days": int(max_delivery_lag_days),
        "enforce_per_store": bool(enforce_per_store),
        "statusdate_cutover": statusdate_cutover.isoformat() if statusdate_cutover is not None else None,
        "effective_as_of": effective_as_of.isoformat(),
        "max_delivered_date": max_date.isoformat(),
        "global_lag_days": int(lag_days),
        "per_store": per_store_rows,
        "stale_stores": sorted(set(stale_stores)),
    }
    write_json(report_json, payload)

    report_md.write_text(
        "\n".join(
            [
                "# Reference Freshness",
                "",
                f"- as_of: `{as_of.isoformat()}`",
                "- status: `PASS`",
                f"- reference_csv: `{csv_path}`",
                f"- effective_as_of: `{effective_as_of.isoformat()}`",
                f"- max_delivered_date: `{max_date.isoformat()}`",
                f"- global_lag_days: `{lag_days}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return payload


def _write_failure_artifacts(*, as_of: date, output_root: Path, code: str, message: str) -> None:
    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "validate_reference_freshness.json"
    report_md = out_dir / "validate_reference_freshness.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "status": code,
        "error_code": code,
        "message": message,
    }
    write_json(report_json, payload)
    report_md.write_text(
        "\n".join(
            [
                "# Reference Freshness",
                "",
                f"- as_of: `{as_of.isoformat()}`",
                f"- status: `{code}`",
                f"- message: `{message}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate reference freshness for statusdate mapped dataset")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-delivery-lag-days", type=int, default=7)
    parser.add_argument("--enforce-per-store", action="store_true")
    parser.add_argument("--statusdate-cutover")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    as_of = parse_iso_date(args.as_of, field="as_of")
    statusdate_cutover = (
        parse_iso_date(args.statusdate_cutover, field="statusdate_cutover")
        if args.statusdate_cutover
        else None
    )
    try:
        report = validate_reference_freshness(
            as_of=as_of,
            reference_root=args.reference_root,
            output_root=args.output_root,
            max_delivery_lag_days=int(args.max_delivery_lag_days),
            enforce_per_store=bool(args.enforce_per_store),
            strict=bool(args.strict),
            statusdate_cutover=statusdate_cutover,
        )
    except StatusError as exc:
        _write_failure_artifacts(
            as_of=as_of,
            output_root=args.output_root,
            code=exc.code,
            message=exc.message,
        )
        print(f"status={exc.code}")
        print(f"error_code={exc.code}")
        print(f"message={exc.message}")
        return 1
    except Exception as exc:  # pragma: no cover
        print("status=FAIL")
        print("error_code=FAIL")
        print(f"message={exc}")
        return 1

    print(f"reference_freshness_json={(args.output_root.resolve() / report['as_of'] / 'validate_reference_freshness.json')}")
    print(f"reference_freshness_md={(args.output_root.resolve() / report['as_of'] / 'validate_reference_freshness.md')}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
