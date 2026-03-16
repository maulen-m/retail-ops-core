#!/usr/bin/env python3
"""Capture WebUI and API order status observations into the audit table."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_027_order_status_observations import validate_order_status_observation_schema
from scripts.webui_archive_truth_utils import DEFAULT_LEDGER_ROOT, load_status_ledger, resolve_latest_dir

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth"


class OrderStatusObservationCaptureError(RuntimeError):
    """Raised when status observations cannot be captured safely."""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


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


def _load_api_observations(conn: sqlite3.Connection, as_of: str) -> pd.DataFrame:
    columns = _table_columns(conn, "fact_orders_kaspi")
    if not columns:
        raise OrderStatusObservationCaptureError("fact_orders_kaspi table missing")
    observed_candidates = [
        "synced_at",
        "status_updated_at",
        "updated_at",
        "imported_at",
        "created_at",
    ]
    observed_expr_parts = [
        f"NULLIF({column}, '')" for column in observed_candidates if column in columns
    ]
    observed_expr = ", ".join(observed_expr_parts + ["?"])
    query = """
        SELECT
            CAST(order_id AS TEXT) AS order_id,
            UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
            UPPER(TRIM(COALESCE(internal_status, 'UNKNOWN'))) AS status_internal,
            COALESCE(__OBSERVED_AT__) AS observed_at,
            'API' AS source,
            NULL AS ledger_run_id,
            'fact_orders_kaspi' AS source_detail
        FROM fact_orders_kaspi
    """
    return pd.read_sql_query(query.replace("__OBSERVED_AT__", observed_expr), conn, params=[as_of])


def _load_existing_keys(conn: sqlite3.Connection) -> set[tuple[str, str, str, str, str]]:
    rows = conn.execute(
        """
        SELECT order_id, store_code, status_internal, observed_at, source
        FROM fact_order_status_observations
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))
        for row in rows
    }


def capture_order_status_observations(
    *,
    db_path: Path,
    ledger_root: Path | None,
    as_of: str,
    output_root: Path,
    apply: bool,
    strict: bool,
    backup_path: Path | None,
) -> dict[str, Any]:
    schema_errors = validate_order_status_observation_schema(db_path)
    if schema_errors:
        raise OrderStatusObservationCaptureError("; ".join(schema_errors))
    if apply and os.environ.get("ENABLE_ORDER_STATUS_OBSERVATION_WRITE") != "1":
        raise OrderStatusObservationCaptureError(
            "ENABLE_ORDER_STATUS_OBSERVATION_WRITE=1 is required with --apply"
        )
    if apply and (backup_path is None or not backup_path.exists()):
        raise OrderStatusObservationCaptureError("--backup-path must point to an existing DB backup when using --apply")

    resolved_ledger_root = _resolve_ledger_root(ledger_root)
    ledger, manifest = load_status_ledger(resolved_ledger_root)
    output_dir = output_root.resolve() / as_of
    output_dir.mkdir(parents=True, exist_ok=True)

    webui_obs = ledger[["order_id", "store_code", "status_internal", "status_change_at"]].copy()
    webui_obs = webui_obs[webui_obs["status_change_at"].astype(str).str.strip() != ""].copy()
    webui_obs = webui_obs.rename(columns={"status_change_at": "observed_at"})
    webui_obs["source"] = "WEBUI"
    webui_obs["ledger_run_id"] = manifest.get("run_id")
    webui_obs["source_detail"] = "webui_status_ledger"

    conn = sqlite3.connect(str(db_path))
    try:
        api_obs = _load_api_observations(conn, as_of)
        existing_keys = _load_existing_keys(conn)
        combined = pd.concat([webui_obs, api_obs], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["order_id", "store_code", "status_internal", "observed_at", "source"],
            keep="first",
        )
        combined["observation_key"] = combined.apply(
            lambda row: (
                str(row["order_id"]),
                str(row["store_code"]),
                str(row["status_internal"]),
                str(row["observed_at"]),
                str(row["source"]),
            ),
            axis=1,
        )
        inserts = combined[~combined["observation_key"].isin(existing_keys)].copy()
        before_counts = (
            pd.read_sql_query(
                "SELECT source, COUNT(*) AS rows FROM fact_order_status_observations GROUP BY source",
                conn,
            )
            if existing_keys
            else pd.DataFrame(columns=["source", "rows"])
        )
        if apply and not inserts.empty:
            conn.executemany(
                """
                INSERT OR IGNORE INTO fact_order_status_observations
                (order_id, store_code, status_internal, observed_at, source, ledger_run_id, source_detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(row["order_id"]),
                        str(row["store_code"]),
                        str(row["status_internal"]),
                        str(row["observed_at"]),
                        str(row["source"]),
                        row.get("ledger_run_id"),
                        row.get("source_detail"),
                    )
                    for row in inserts.to_dict("records")
                ],
            )
            conn.commit()
        after_counts = pd.read_sql_query(
            "SELECT source, COUNT(*) AS rows FROM fact_order_status_observations GROUP BY source",
            conn,
        )
    finally:
        conn.close()

    inserts_csv = output_dir / "order_status_observation_inserts.csv"
    before_after_json = output_dir / "order_status_observations_before_after.json"
    report_json = output_dir / "order_status_observation_capture.json"
    inserts.drop(columns=["observation_key"], errors="ignore").to_csv(inserts_csv, index=False, encoding="utf-8")
    before_after = {
        "before_counts": before_counts.to_dict("records"),
        "after_counts": after_counts.to_dict("records"),
        "insert_count": int(len(inserts)),
    }
    before_after_json.write_text(json.dumps(before_after, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS",
        "ok": True,
        "strict": bool(strict),
        "apply": bool(apply),
        "backup_path": str(backup_path) if backup_path else None,
        "ledger_root": str(resolved_ledger_root),
        "ledger_run_id": manifest.get("run_id"),
        "webui_rows": int(len(webui_obs)),
        "api_rows": int(len(api_obs)),
        "insert_count": int(len(inserts)),
        "outputs": {
            "order_status_observation_capture_json": str(report_json),
            "order_status_observation_inserts_csv": str(inserts_csv),
            "order_status_observations_before_after_json": str(before_after_json),
        },
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if strict and int(len(webui_obs)) == 0:
        raise OrderStatusObservationCaptureError("ledger produced 0 WebUI observations")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture order status observations")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--backup-path", type=Path, default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = capture_order_status_observations(
            db_path=args.db,
            ledger_root=args.ledger_root,
            as_of=str(args.as_of),
            output_root=args.output_root,
            apply=bool(args.apply),
            strict=bool(args.strict),
            backup_path=args.backup_path,
        )
    except OrderStatusObservationCaptureError as exc:
        print("status=FAIL")
        print("error_code=ORDER_STATUS_OBSERVATION_CAPTURE_FAIL")
        print(f"message={exc}")
        return 1

    print(f"order_status_observation_capture_json={report['outputs']['order_status_observation_capture_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
