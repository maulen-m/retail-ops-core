#!/usr/bin/env python3
"""Fail-closed validator for recent order identity coverage."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import (
    DEFAULT_ACTIVE_STORES,
    IdentityPlanError,
    StatusError,
    parse_iso_date,
    write_json,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"
PENDING_LATEST_STATUSES = {"READY", "ACCEPTED"}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _load_latest_status_context(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    stores: tuple[str, ...],
) -> tuple[dict[tuple[str, str], str], dict[str, datetime]]:
    if not _table_exists(conn, "fact_order_status_observations"):
        return {}, {}
    rows = conn.execute(
        """
        SELECT
            CAST(order_id AS TEXT) AS order_id,
            UPPER(COALESCE(store_code, '')) AS store_code,
            COALESCE(status_internal, '') AS status_internal,
            COALESCE(observed_at, '') AS observed_at
        FROM fact_order_status_observations
        WHERE date(observed_at) <= ?
          AND UPPER(COALESCE(store_code, '')) IN ({})
        ORDER BY
            CAST(order_id AS TEXT),
            UPPER(COALESCE(store_code, '')),
            datetime(observed_at) DESC,
            rowid DESC
        """.format(",".join(["?"] * len(stores))),
        (as_of.isoformat(), *stores),
    ).fetchall()
    latest: dict[tuple[str, str], str] = {}
    watermarks: dict[str, datetime] = {}
    for row in rows:
        store = str(row["store_code"] or "").strip().upper()
        order_id = str(row["order_id"] or "").strip()
        observed_at = _parse_dt(row["observed_at"])
        if observed_at is not None:
            prev = watermarks.get(store)
            if prev is None or observed_at > prev:
                watermarks[store] = observed_at
        key = (store, order_id)
        latest.setdefault(key, str(row["status_internal"] or "").strip().upper())
    return latest, watermarks


def _resolve_store_watermark(
    store: str,
    *,
    observation_watermarks: dict[str, datetime],
) -> datetime | None:
    return observation_watermarks.get(store)


def _missing_fields(row: sqlite3.Row) -> list[str]:
    missing: list[str] = []
    for col in ("sku_key", "sku_id", "my_size", "kaspi_offer_name"):
        if not str(row[col] or "").strip():
            missing.append(col)
    return missing


def _store_payload(name: str) -> dict[str, Any]:
    return {
        "store_code": name,
        "total_orders": 0,
        "missing_all_identity_core": 0,
        "missing_any_identity_core": 0,
        "missing_any_pct": 0.0,
        "missing_all_pct": 0.0,
        "avg_missing_any_per_day": 0.0,
    }


def _identity_required(
    row: sqlite3.Row,
    *,
    as_of: date,
    latest_status_internal: str = "",
    store_watermark: datetime | None = None,
) -> bool:
    status_detail = str(row["kaspi_status_detail"] or "").strip().upper()
    internal_status = str(row["internal_status"] or "").strip().upper()
    kaspi_status = str(row["kaspi_status"] or "").strip().upper()
    if latest_status_internal in PENDING_LATEST_STATUSES:
        return False
    if latest_status_internal in {"CANCELLED", "RETURNED"}:
        return False
    if store_watermark is not None:
        created_at = _parse_dt(row["created_at"])
        if created_at is not None and created_at > store_watermark:
            return False

    # Terminal states that do not require identity completion for recent governance.
    if status_detail in {"CANCELLED", "RETURNED"}:
        return False
    if internal_status in {"CANCELLED", "RETURNED"}:
        return False

    # Pending/pre-assembly orders can legitimately lack resolved identity.
    pending_like = {"ACCEPTED_BY_MERCHANT", "APPROVED_BY_BANK", "NEW", "ASSEMBLY"}
    if (
        status_detail in pending_like
        or internal_status in {"NEW", "ACCEPTED", "READY"}
        or kaspi_status in {"NEW", "ASSEMBLY"}
    ):
        created_text = str(row["created_at"] or "").strip()
        created_date = created_text[:10] if len(created_text) >= 10 else ""
        if created_date <= as_of.isoformat():
            return False
    return True


def validate_recent_identity_coverage(
    *,
    db_path: Path,
    as_of: date,
    lookback_days: int,
    stores: tuple[str, ...],
    output_root: Path,
    strict: bool,
    max_missing_all: int,
    max_missing_any_pct: float,
    max_missing_any_per_day: float,
) -> dict[str, Any]:
    if lookback_days <= 0:
        raise IdentityPlanError("lookback_days must be > 0")
    if max_missing_any_pct < 0:
        raise IdentityPlanError("max_missing_any_pct must be >= 0")

    start_day = as_of - timedelta(days=lookback_days - 1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                order_id,
                UPPER(COALESCE(store_code, '')) AS store_code,
                COALESCE(sku_key, '') AS sku_key,
                COALESCE(sku_id, '') AS sku_id,
                COALESCE(my_size, '') AS my_size,
                COALESCE(kaspi_offer_name, '') AS kaspi_offer_name,
                COALESCE(kaspi_status_detail, '') AS kaspi_status_detail,
                COALESCE(internal_status, '') AS internal_status,
                COALESCE(kaspi_status, '') AS kaspi_status,
                COALESCE(created_at, '') AS created_at
            FROM fact_orders_kaspi
            WHERE date(created_at) BETWEEN ? AND ?
              AND UPPER(COALESCE(store_code, '')) IN ({})
            """.format(",".join(["?"] * len(stores))),
            (start_day.isoformat(), as_of.isoformat(), *stores),
        ).fetchall()
        latest_status_by_order, observation_watermarks = _load_latest_status_context(
            conn,
            as_of=as_of,
            stores=stores,
        )
    finally:
        conn.close()

    per_store = {store: _store_payload(store) for store in stores}
    missing_rows: list[dict[str, str]] = []

    for row in rows:
        store = str(row["store_code"] or "").strip().upper()
        if not _identity_required(
            row,
            as_of=as_of,
            latest_status_internal=latest_status_by_order.get((store, str(row["order_id"] or "").strip()), ""),
            store_watermark=_resolve_store_watermark(
                store,
                observation_watermarks=observation_watermarks,
            ),
        ):
            continue
        payload = per_store.setdefault(store, _store_payload(store))
        payload["total_orders"] += 1

        missing = _missing_fields(row)
        if not missing:
            continue
        payload["missing_any_identity_core"] += 1
        if len(missing) == 4:
            payload["missing_all_identity_core"] += 1

        missing_rows.append(
            {
                "order_id": str(row["order_id"] or "").strip(),
                "store_code": store,
                "created_at": str(row["created_at"] or "").strip(),
                "missing_fields": ",".join(missing),
            }
        )

    for payload in per_store.values():
        total = int(payload["total_orders"])
        if total <= 0:
            continue
        payload["missing_any_pct"] = round(100.0 * float(payload["missing_any_identity_core"]) / float(total), 4)
        payload["missing_all_pct"] = round(100.0 * float(payload["missing_all_identity_core"]) / float(total), 4)
        payload["avg_missing_any_per_day"] = round(float(payload["missing_any_identity_core"]) / float(lookback_days), 4)

    failing_stores: list[dict[str, Any]] = []
    for store in stores:
        p = per_store[store]
        missing_all = int(p["missing_all_identity_core"])
        missing_any_pct = float(p["missing_any_pct"])
        missing_any_per_day = float(p["avg_missing_any_per_day"])

        fail_all = missing_all > max_missing_all
        fail_any = (missing_any_pct > max_missing_any_pct) and (missing_any_per_day > max_missing_any_per_day)
        if fail_all or fail_any:
            failing_stores.append(
                {
                    "store_code": store,
                    "fail_missing_all": fail_all,
                    "fail_missing_any": fail_any,
                    "missing_all_identity_core": missing_all,
                    "missing_any_pct": missing_any_pct,
                    "avg_missing_any_per_day": missing_any_per_day,
                }
            )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "validate_recent_identity_coverage.json"
    report_md = out_dir / "validate_recent_identity_coverage.md"
    missing_csv = out_dir / "validate_recent_identity_coverage_missing_orders.csv"

    with missing_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["order_id", "store_code", "created_at", "missing_fields"])
        writer.writeheader()
        writer.writerows(missing_rows)

    status = "PASS" if not failing_stores else "IDENTITY_COVERAGE_FAIL"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "lookback_days": int(lookback_days),
        "stores": list(stores),
        "thresholds": {
            "max_missing_all": int(max_missing_all),
            "max_missing_any_pct": float(max_missing_any_pct),
            "max_missing_any_per_day": float(max_missing_any_per_day),
        },
        "per_store": [per_store[store] for store in stores],
        "failing_stores": failing_stores,
        "missing_orders_csv": str(missing_csv.resolve()),
        "status": status,
        "error_code": "" if status == "PASS" else status,
    }
    write_json(report_json, payload)

    lines = [
        "# Recent Identity Coverage",
        "",
        f"- as_of: `{as_of.isoformat()}`",
        f"- status: `{status}`",
        f"- lookback_days: `{lookback_days}`",
        "",
        "| store | total_orders | missing_all | missing_any | missing_any_pct | avg_missing_any_per_day |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["per_store"]:
        lines.append(
            f"| `{row['store_code']}` | {row['total_orders']} | {row['missing_all_identity_core']} | "
            f"{row['missing_any_identity_core']} | {row['missing_any_pct']:.4f} | {row['avg_missing_any_per_day']:.4f} |"
        )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if strict and status != "PASS":
        raise StatusError(
            "IDENTITY_COVERAGE_FAIL",
            f"identity coverage thresholds exceeded for stores: {', '.join(x['store_code'] for x in failing_stores)}",
        )
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate recent identity coverage for fact_orders_kaspi")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--lookback-days", type=int, default=15)
    parser.add_argument("--stores", default=",".join(DEFAULT_ACTIVE_STORES))
    parser.add_argument("--max-missing-all", type=int, default=0)
    parser.add_argument("--max-missing-any-pct", type=float, default=0.5)
    parser.add_argument("--max-missing-any-per-day", type=float, default=1.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    stores = tuple(normal.strip().upper() for normal in str(args.stores).split(",") if normal.strip())
    try:
        report = validate_recent_identity_coverage(
            db_path=args.db,
            as_of=parse_iso_date(args.as_of, field="as_of"),
            lookback_days=int(args.lookback_days),
            stores=stores,
            output_root=args.output_root,
            strict=bool(args.strict),
            max_missing_all=int(args.max_missing_all),
            max_missing_any_pct=float(args.max_missing_any_pct),
            max_missing_any_per_day=float(args.max_missing_any_per_day),
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

    print(f"identity_coverage_json={(args.output_root.resolve() / report['as_of'] / 'validate_recent_identity_coverage.json')}")
    print(f"identity_coverage_md={(args.output_root.resolve() / report['as_of'] / 'validate_recent_identity_coverage.md')}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
