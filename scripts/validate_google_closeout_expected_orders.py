#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import dump_json  # noqa: E402
from core.integrations.kaspi_order_stage import (  # noqa: E402
    StageCode,
    classify_kaspi_stage_from_db_row,
)
from core.paths import data_path  # noqa: E402
from core.utils.kaspi_dates import parse_kaspi_date  # noqa: E402


READY_TO_CLOSEOUT_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
}
DEFAULT_EXPECTED_FILENAME = "expected_closeout_orders.json"
DEFAULT_GATE_FILENAME = "expected_order_manifest_gate.json"


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _has_text(value: Any) -> bool:
    text = _clean(value).lower()
    return text not in {"", "nan", "none", "nat", "null", "<na>"}


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "no", "n", "none", "nan", "nat", "null", "<na>"}


def _normalize_store_code(value: Any) -> str:
    raw = _clean(value)
    upper = raw.upper().replace(" ", "")
    aliases = {
        "STORE-B": "STOREB",
        "STORE_B": "STOREB",
        "30137883_PP1": "ACMEWEAR",
        "30000001_PP1": "UNIVERSAL",
        "30290083_PP1": "11KZ",
        "30000002_PP1": "STOREB",
        "30362323_PP1": "MELVIS",
        "PP1": "ACMEWEAR",
        "PP2": "ACMEWEAR",
    }
    return aliases.get(upper, upper)


def normalize_active_order_ids_by_store(
    active_order_ids_by_store: Mapping[str, Iterable[Any]] | None,
) -> dict[str, set[str]] | None:
    if active_order_ids_by_store is None:
        return None
    normalized: dict[str, set[str]] = {}
    for store_code, order_ids in active_order_ids_by_store.items():
        normalized_store = _normalize_store_code(store_code)
        normalized[normalized_store] = {
            order_id
            for order_id in (_clean(value) for value in order_ids)
            if order_id
        }
    return normalized


def fetch_api_active_order_ids_by_store(
    *,
    target_date: date,
    lookback_days: int,
    store_codes: Iterable[str] | None = None,
    api_since_days: int = 14,
    verbose: bool = False,
) -> dict[str, set[str]]:
    """
    Independently fetch live Kaspi delivery-stage targets for the closeout window.

    This deliberately uses the overdue-inclusive API selector rather than trusting the
    downstream download cache. If the download path regresses to exact-date filtering,
    this expected set still contains the live overdue orders that must be bundled.
    """
    from core.integrations.kaspi_api_client import STORE_TOKEN_MAP  # noqa: WPS433
    from scripts.download_waybills_api import get_target_orders_from_api  # noqa: WPS433

    selected_store_codes = [
        _normalize_store_code(store_code)
        for store_code in (store_codes if store_codes is not None else STORE_TOKEN_MAP.keys())
    ]
    selected_store_codes = [store for store in selected_store_codes if store in STORE_TOKEN_MAP]
    since_days = max(int(api_since_days), int(lookback_days or 0))
    active: dict[str, set[str]] = {}
    api_errors: list[str] = []
    for store_code in selected_store_codes:
        orders, had_error = get_target_orders_from_api(
            store_code,
            target_date,
            since_days=since_days,
            exact_date=False,
            include_overdue=True,
            all_dates=False,
            verbose=verbose,
        )
        if had_error:
            api_errors.append(store_code)
        order_ids = {
            _clean((order.get("attributes") or {}).get("code"))
            for order in orders
            if isinstance(order, Mapping)
        }
        active[store_code] = {order_id for order_id in order_ids if order_id}
    if api_errors:
        raise RuntimeError("API expected-order selection failed for stores: " + ", ".join(sorted(api_errors)))
    return active


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _select_expr(columns: set[str], column: str, alias: str | None = None, default: str = "NULL") -> str:
    output = alias or column
    if column in columns:
        return column if output == column else f"{column} AS {output}"
    return f"{default} AS {output}"


def _row_to_dict(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()} if isinstance(row, sqlite3.Row) else dict(row)


def _load_candidate_rows(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            raise RuntimeError("DB missing fact_orders_kaspi table")

        columns = _table_columns(conn, "fact_orders_kaspi")
        required = {"order_id", "planned_shipment_date"}
        missing = sorted(required - columns)
        if missing:
            raise RuntimeError(f"fact_orders_kaspi missing required columns: {', '.join(missing)}")

        select_parts = [
            _select_expr(columns, "id", default="NULL"),
            _select_expr(columns, "order_id"),
            _select_expr(columns, "store_code"),
            _select_expr(columns, "assigned_size"),
            _select_expr(columns, "my_size"),
            _select_expr(columns, "planned_shipment_date"),
            _select_expr(columns, "kaspi_status"),
            _select_expr(columns, "kaspi_status_detail"),
            _select_expr(columns, "internal_status"),
            _select_expr(columns, "signature_required", default="0"),
            _select_expr(columns, "pre_order", default="0"),
            _select_expr(columns, "courier_transmission_date"),
            _select_expr(columns, "actual_shipment_date"),
            _select_expr(columns, "delivery_mode"),
            _select_expr(columns, "waybill_url"),
            _select_expr(columns, "returned_to_warehouse", default="0"),
        ]
        rows = conn.execute(
            f"""
            SELECT {", ".join(select_parts)}
            FROM fact_orders_kaspi
            WHERE planned_shipment_date IS NOT NULL
              AND planned_shipment_date != ''
            """
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def build_expected_orders_from_db(
    *,
    db_path: Path,
    target_date: date,
    lookback_days: int,
    active_order_ids_by_store: Mapping[str, Iterable[Any]] | None = None,
) -> dict[str, Any]:
    """
    Build the canonical order set that must be present in today's send manifest.

    This is intentionally DB-first and generated after final size writeback. It catches
    the high-cost class where the PDF/send manifest is self-consistent but silently
    omits an overdue or freshly-sized closeout order.
    """
    min_date = target_date - timedelta(days=max(int(lookback_days or 0), 0))
    active_lookup = normalize_active_order_ids_by_store(active_order_ids_by_store)
    expected_rows: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()

    for row in _load_candidate_rows(Path(db_path)):
        order_id = _clean(row.get("order_id"))
        if not order_id:
            excluded["missing_order_id"] += 1
            continue

        planned_date = parse_kaspi_date(row.get("planned_shipment_date"))
        if planned_date is None:
            excluded["invalid_planned_date"] += 1
            continue
        if planned_date > target_date:
            excluded["future_planned_date"] += 1
            continue
        if planned_date < min_date:
            excluded["outside_lookback"] += 1
            continue

        assigned_size = _clean(row.get("assigned_size"))
        my_size = _clean(row.get("my_size"))
        final_size = assigned_size or my_size
        if not _has_text(final_size):
            excluded["missing_size"] += 1
            continue

        if _is_truthy(row.get("signature_required")):
            excluded["signature_required"] += 1
            continue
        if _is_truthy(row.get("returned_to_warehouse")):
            excluded["returned_to_warehouse"] += 1
            continue
        if _has_text(row.get("courier_transmission_date")) or _has_text(row.get("actual_shipment_date")):
            excluded["already_handed_over"] += 1
            continue

        stage = classify_kaspi_stage_from_db_row(row)
        if stage not in READY_TO_CLOSEOUT_STAGES:
            excluded[f"stage_{stage.value}"] += 1
            continue

        store_code = _normalize_store_code(row.get("store_code"))
        if active_lookup is not None and order_id not in active_lookup.get(store_code, set()):
            excluded["not_api_active"] += 1
            continue

        expected_rows.append(
            {
                "order_id": order_id,
                "store_code": store_code,
                "planned_shipment_date": planned_date.isoformat(),
                "assigned_size": assigned_size,
                "my_size": my_size,
                "final_size": final_size,
                "stage": stage.value,
                "overdue": planned_date < target_date,
            }
        )

    expected_rows.sort(key=lambda item: (item["planned_shipment_date"], item["order_id"]))
    expected_order_ids = sorted({row["order_id"] for row in expected_rows})
    overdue_order_ids = sorted({row["order_id"] for row in expected_rows if row["overdue"]})
    counts_by_store: Counter[str] = Counter()
    seen_store_order_pairs: set[tuple[str, str]] = set()
    for row in expected_rows:
        store_code = row["store_code"] or "UNKNOWN"
        key = (store_code, row["order_id"])
        if key in seen_store_order_pairs:
            continue
        seen_store_order_pairs.add(key)
        counts_by_store[store_code] += 1
    counts_by_stage = Counter(row["stage"] for row in expected_rows)

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "target_date": target_date.isoformat(),
        "lookback_days": int(lookback_days),
        "min_planned_shipment_date": min_date.isoformat(),
        "source": "fact_orders_kaspi_after_final_size_writeback",
        "active_order_filter": active_lookup is not None,
        "active_order_filter_counts_by_store": (
            {store: len(order_ids) for store, order_ids in sorted(active_lookup.items())}
            if active_lookup is not None
            else {}
        ),
        "expected_order_ids": expected_order_ids,
        "overdue_order_ids": overdue_order_ids,
        "orders": expected_rows,
        "counts": {
            "orders": len(expected_order_ids),
            "order_lines": len(expected_rows),
            "overdue_orders": len(overdue_order_ids),
            "excluded_rows": int(sum(excluded.values())),
        },
        "counts_by_store": dict(sorted(counts_by_store.items())),
        "counts_by_stage": dict(sorted(counts_by_stage.items())),
        "excluded_counts": dict(sorted(excluded.items())),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return payload


def _manifest_order_ids(manifest: Mapping[str, Any]) -> list[str]:
    order_ids = [_clean(value) for value in manifest.get("send_order_ids") or []]
    if not order_ids:
        seen: set[str] = set()
        for entry in manifest.get("entries") or []:
            if not isinstance(entry, Mapping):
                continue
            for value in entry.get("order_ids") or []:
                order_id = _clean(value)
                if order_id and order_id not in seen:
                    seen.add(order_id)
                    order_ids.append(order_id)
    return sorted({order_id for order_id in order_ids if order_id})


def validate_manifest_against_expected(
    *,
    expected_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    expected = _load_json(Path(expected_path))
    manifest = _load_json(Path(manifest_path))

    expected_ids = sorted({_clean(value) for value in expected.get("expected_order_ids") or [] if _clean(value)})
    manifest_ids = _manifest_order_ids(manifest)
    expected_set = set(expected_ids)
    manifest_set = set(manifest_ids)
    overdue_set = {_clean(value) for value in expected.get("overdue_order_ids") or [] if _clean(value)}

    missing = sorted(expected_set - manifest_set)
    extra = sorted(manifest_set - expected_set)
    missing_overdue = sorted(overdue_set & set(missing))
    issue_codes: list[str] = []

    expected_target = _clean(expected.get("target_date"))
    manifest_target = _clean(manifest.get("target_date"))
    if expected_target and manifest_target and expected_target != manifest_target:
        issue_codes.append("manifest_target_date_mismatch")
    if missing:
        issue_codes.append("expected_orders_missing_from_manifest")
    if missing_overdue:
        issue_codes.append("expected_overdue_missing_from_manifest")
    if extra:
        issue_codes.append("manifest_has_unexpected_orders")
    if len(expected_ids) != len(manifest_ids):
        issue_codes.append("manifest_order_count_mismatch")

    manifest_counts = manifest.get("counts") if isinstance(manifest.get("counts"), Mapping) else {}
    manifest_order_count = manifest_counts.get("orders")
    try:
        if manifest_order_count is not None and int(manifest_order_count) != len(manifest_ids):
            issue_codes.append("manifest_declared_order_count_mismatch")
    except (TypeError, ValueError):
        issue_codes.append("manifest_declared_order_count_invalid")

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "ok": not issue_codes,
        "expected_path": str(Path(expected_path)),
        "manifest_path": str(Path(manifest_path)),
        "target_date": expected_target,
        "manifest_target_date": manifest_target,
        "expected_count": len(expected_ids),
        "manifest_count": len(manifest_ids),
        "missing_order_ids": missing,
        "extra_order_ids": extra,
        "missing_overdue_order_ids": missing_overdue,
        "issue_codes": issue_codes,
    }


def find_latest_send_manifest(today_folder: Path) -> Path | None:
    root = Path(today_folder).expanduser() / "MERGED" / "SEND"
    if not root.exists():
        return None
    candidates = sorted(
        root.glob("*/send_batch_manifest.json"),
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )
    return candidates[0] if candidates else None


def write_expected_orders_report(report: Mapping[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_path, dict(report))
    return output_path


def _resolve_date(value: str) -> date:
    text = str(value or "").strip()
    if text.lower() in {"", "today"}:
        return datetime.now().astimezone().date()
    return date.fromisoformat(text)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Google closeout expected orders against send manifest.")
    parser.add_argument("--db-path", type=Path, default=data_path("db", "app.db"))
    parser.add_argument("--target-date", default="today")
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--expected-path", type=Path, default=None)
    parser.add_argument("--manifest-path", type=Path, default=None)
    parser.add_argument("--today-folder", type=Path, default=data_path("excel_ui", "Kaspi_orders", "Today"))
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--build-expected-only", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    expected_path = args.expected_path
    if expected_path is None:
        expected_path = Path(DEFAULT_EXPECTED_FILENAME)

    if args.build_expected_only or not expected_path.exists():
        expected = build_expected_orders_from_db(
            db_path=args.db_path,
            target_date=_resolve_date(args.target_date),
            lookback_days=args.lookback_days,
        )
        write_expected_orders_report(expected, expected_path)
        if args.build_expected_only:
            print(f"Expected closeout orders: {expected_path}")
            return 0

    manifest_path = args.manifest_path or find_latest_send_manifest(args.today_folder)
    if manifest_path is None:
        raise SystemExit(f"No send_batch_manifest.json found under {Path(args.today_folder) / 'MERGED' / 'SEND'}")

    gate = validate_manifest_against_expected(expected_path=expected_path, manifest_path=manifest_path)
    if args.output_json:
        dump_json(args.output_json, gate)
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if gate.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
