#!/usr/bin/env python3
"""Validate external snapshot bridge freshness/parity against baseline unresolved tolerances."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import (
    DEFAULT_ACTIVE_STORES,
    WEB_SNAPSHOT_ROOT,
    StatusError,
    parse_iso_date,
    parse_snapshot_date_from_name,
    read_snapshot_frame,
    resolve_latest_snapshot_files,
    write_json,
)

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"
DEFAULT_BASELINE_JSON = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "identity_option1_option3_plan_2026-03-03"
    / "baseline_identity_gap_summary.json"
)


def _load_reference_csv(reference_csv: Path) -> pd.DataFrame:
    if not reference_csv.exists():
        raise StatusError("EXTERNAL_MAPPING_STALE", f"reference csv missing: {reference_csv}")
    df = pd.read_csv(reference_csv, dtype=str, keep_default_na=False)
    if df.empty:
        raise StatusError("EXTERNAL_MAPPING_STALE", f"reference csv empty: {reference_csv}")
    required = {"store_code", "effective_sku_key", "mapping_status", "identity_status"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise StatusError(
            "EXTERNAL_MAPPING_STALE",
            f"reference csv missing required columns: {', '.join(missing)}",
        )
    return df


def _count_unresolved(df: pd.DataFrame, store: str) -> int:
    subset = df[df["store_code"].str.upper() == store]
    if subset.empty:
        return 0
    missing_key = subset["effective_sku_key"].astype(str).str.strip() == ""
    deprecated = subset["mapping_status"].astype(str).str.strip().str.lower() == "deprecated"
    identity_bad = ~subset["identity_status"].astype(str).str.strip().str.lower().isin({"", "matched"})
    return int((missing_key | deprecated | identity_bad).sum())


def _load_baseline_thresholds(path: Path) -> dict[str, int]:
    defaults = {"UNIVERSAL": 52, "STOREB": 11}
    if not path.exists():
        return defaults
    payload = json.loads(path.read_text(encoding="utf-8"))

    # use explicit web snapshot summary if present
    rows = payload.get("web_snapshot_summary")
    if isinstance(rows, list):
        for row in rows:
            store = str(row.get("store") or "").strip().upper()
            if store in defaults and row.get("missing_effective_sku_key") is not None:
                defaults[store] = int(row["missing_effective_sku_key"])
    return defaults


def validate_external_snapshot_parity(
    *,
    as_of: date,
    reference_csv: Path,
    baseline_json: Path,
    snapshot_root: Path,
    output_root: Path,
    strict: bool,
    max_age_days: int,
) -> dict[str, Any]:
    if max_age_days < 0:
        raise StatusError("EXTERNAL_MAPPING_STALE", "max_age_days must be >= 0")

    df = _load_reference_csv(reference_csv)
    latest_files = resolve_latest_snapshot_files(snapshot_root=snapshot_root, stores=DEFAULT_ACTIVE_STORES)
    missing_snapshots = sorted(set(DEFAULT_ACTIVE_STORES) - set(latest_files))
    if missing_snapshots:
        raise StatusError(
            "EXTERNAL_MAPPING_STALE",
            f"missing latest external snapshots for stores: {', '.join(missing_snapshots)}",
        )

    snapshot_dates = {
        store: parse_snapshot_date_from_name(path)
        for store, path in latest_files.items()
    }
    if any(value is None for value in snapshot_dates.values()):
        raise StatusError("EXTERNAL_MAPPING_STALE", "failed to parse snapshot date from one or more snapshot file names")

    ages = {
        store: (as_of - snapshot_dates[store]).days  # type: ignore[arg-type]
        for store in DEFAULT_ACTIVE_STORES
    }
    stale = sorted([store for store, days in ages.items() if days > max_age_days])
    if stale:
        raise StatusError(
            "EXTERNAL_MAPPING_STALE",
            f"external snapshots stale for stores: {', '.join(stale)}; max_age_days={max_age_days}",
        )

    baseline = _load_baseline_thresholds(baseline_json)
    unresolved_by_store = {
        store: _count_unresolved(df, store)
        for store in DEFAULT_ACTIVE_STORES
    }

    parity_failures: list[dict[str, Any]] = []
    for store in DEFAULT_ACTIVE_STORES:
        current = unresolved_by_store[store]
        limit = int(baseline.get(store, 0))
        if current > limit:
            parity_failures.append(
                {
                    "store_code": store,
                    "unresolved_current": current,
                    "unresolved_baseline_limit": limit,
                }
            )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "validate_external_snapshot_parity.json"
    report_md = out_dir / "validate_external_snapshot_parity.md"

    status = "PASS" if not parity_failures else "IDENTITY_COVERAGE_FAIL"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "reference_csv": str(reference_csv.resolve()),
        "latest_snapshot_files": {k: str(v) for k, v in latest_files.items()},
        "snapshot_dates": {k: snapshot_dates[k].isoformat() for k in DEFAULT_ACTIVE_STORES},  # type: ignore[union-attr]
        "snapshot_ages_days": ages,
        "baseline_limits": baseline,
        "unresolved_by_store": unresolved_by_store,
        "parity_failures": parity_failures,
        "status": status,
        "error_code": "" if status == "PASS" else status,
    }
    write_json(report_json, payload)

    md_lines = [
        "# External Snapshot Parity",
        "",
        f"- as_of: `{as_of.isoformat()}`",
        f"- status: `{status}`",
        "",
        "| store | snapshot_date | snapshot_age_days | unresolved_current | unresolved_baseline_limit |",
        "|---|---|---:|---:|---:|",
    ]
    for store in DEFAULT_ACTIVE_STORES:
        md_lines.append(
            f"| `{store}` | `{payload['snapshot_dates'][store]}` | {ages[store]} | "
            f"{unresolved_by_store[store]} | {baseline[store]} |"
        )
    report_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    if strict and status != "PASS":
        raise StatusError(
            "IDENTITY_COVERAGE_FAIL",
            f"external parity unresolved counts exceeded baseline for stores: {', '.join(x['store_code'] for x in parity_failures)}",
        )
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate external snapshot parity vs baseline unresolved limits")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--reference-csv", type=Path, required=True)
    parser.add_argument("--baseline-json", type=Path, default=DEFAULT_BASELINE_JSON)
    parser.add_argument("--snapshot-root", type=Path, default=WEB_SNAPSHOT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-age-days", type=int, default=3)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_external_snapshot_parity(
            as_of=parse_iso_date(args.as_of, field="as_of"),
            reference_csv=args.reference_csv,
            baseline_json=args.baseline_json,
            snapshot_root=args.snapshot_root,
            output_root=args.output_root,
            strict=bool(args.strict),
            max_age_days=int(args.max_age_days),
        )
    except StatusError as exc:
        print(f"status={exc.code}")
        print(f"error_code={exc.code}")
        print(f"message={exc.message}")
        return 1
    except Exception as exc:  # pragma: no cover
        print("status=FAIL")
        print("error_code=FAIL")
        print(f"message={exc}")
        return 1

    print(f"external_snapshot_parity_json={(args.output_root.resolve() / report['as_of'] / 'validate_external_snapshot_parity.json')}")
    print(f"external_snapshot_parity_md={(args.output_root.resolve() / report['as_of'] / 'validate_external_snapshot_parity.md')}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
