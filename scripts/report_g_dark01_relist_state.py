#!/usr/bin/env python3
"""Publish the G-DARK-01 dark-family relist live-state report."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "dark_family_relist_state.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_dark01_relist_state"

OFFER_STATE_COLUMNS = [
    "family_id",
    "sku_key",
    "size",
    "current_stock",
    "excluded_by_decision",
    "should_be_buyable",
    "active_available_offer_count",
    "store_ids",
    "merchant_skus",
    "links",
    "status",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(raw: str | None) -> datetime:
    text = str(raw or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _parse_dt(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table,),
    ).fetchone() is not None


def _as_int(raw: Any) -> int:
    try:
        return int(float(str(raw or "").strip() or "0"))
    except ValueError:
        return 0


def _upper(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _load_scoreboard(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            state = str(row.get("status") or row.get("state") or "").strip().upper()
            if gate_id and state:
                states[gate_id] = state
    return states


def _load_dashboard_gate_states(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    match = re.search(r"window\.GP\s*=\s*(\{.*\});\s*$", text, re.S)
    if not match:
        return {}
    payload = json.loads(match.group(1))
    states: dict[str, str] = {}
    for row in payload.get("gates", []):
        gate_id = str(row.get("id") or "").strip()
        state = str(row.get("status") or "").strip().upper()
        if gate_id and state:
            states[gate_id] = state
    return states


def _check(ok: bool, check_id: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": check_id, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{column: row.get(column, "") for column in columns} for row in rows])


def _extract_offer_size(merchant_sku: str, sku_key: str) -> str:
    text = str(merchant_sku or "").strip()
    prefix = f"{sku_key}_"
    if text.startswith(prefix):
        return text[len(prefix) :].split("_", 1)[0].strip().upper()
    match = re.search(r"_(S|M|L|XL|2XL|3XL|4XL)(?:_|$)", text.upper())
    return match.group(1) if match else ""


def _load_latest_stock(conn: sqlite3.Connection, sku_key: str) -> tuple[str | None, list[dict[str, Any]]]:
    latest = conn.execute("SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size").fetchone()[0]
    if not latest:
        return None, []
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ? AND sku_key = ?
            ORDER BY my_size, sku_id
            """,
            (latest, sku_key),
        ).fetchall()
    ]
    return str(latest), rows


def _load_repricer_family_rows(conn: sqlite3.Connection, sku_key: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                fetched_at,
                store_id,
                store_name,
                row_id,
                merchant_sku,
                kaspi_sku,
                merchant_title,
                link,
                price,
                min_price,
                max_price,
                active,
                is_available
            FROM repricer_items
            WHERE merchant_sku LIKE ? OR merchant_title LIKE ?
            ORDER BY store_id, merchant_sku
            """,
            (f"%{sku_key}%", f"%{sku_key}%"),
        ).fetchall()
    ]


def _is_active_available(row: dict[str, Any]) -> bool:
    return _as_int(row.get("active")) == 1 and _as_int(row.get("is_available")) == 1


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-DARK-01 Dark Family Relist State Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Passed checks: {report['passed_checks']}/{report['total_checks']}",
        "",
        "## Summary",
        "",
        f"- family_count: {report['family_count']}",
        f"- stock_snapshot_date: {report['stock_snapshot_date']}",
        f"- repricer_source_max_fetched_at: {report['repricer_source_max_fetched_at']}",
        f"- missing_buyable_count: {report['missing_buyable_count']}",
        f"- excluded_or_zero_stock_buyable_count: {report['excluded_or_zero_stock_buyable_count']}",
        "",
        "## Checks",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_dark_relist_state_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    db_path = _resolve_path(config["db_path"])
    repricer_path = _resolve_path(config["repricer_sqlite_path"])
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    generated_at = _now_almaty()
    as_of_dt = _parse_as_of(as_of)
    run_id = generated_at.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_states = _load_dashboard_gate_states(dashboard_path)
    gate_states.update(_load_scoreboard(scoreboard_path))
    dependency_gates = [str(value) for value in config.get("dependency_gates") or []]
    dependency_statuses = {gate_id: gate_states.get(gate_id, "MISSING") for gate_id in dependency_gates}
    families = list(config.get("families") or [])
    fatal_errors: list[str] = []
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    dependency_missing = {gate: state for gate, state in dependency_statuses.items() if state != "GREEN"}
    checks.append(
        _check(
            not dependency_missing,
            "dependency_stack_green",
            "missing=" + ",".join(f"{gate}={state}" for gate, state in dependency_missing.items())
            if dependency_missing
            else "all dependencies GREEN",
            dependency_statuses=dependency_statuses,
        )
    )
    for gate, state in dependency_missing.items():
        blockers.append(f"dependency_gate_not_green:{gate}={state}")

    if not families:
        fatal_errors.append("families_config_missing")
    if not db_path.exists():
        fatal_errors.append("missing_db")
    if not repricer_path.exists():
        fatal_errors.append("missing_repricer_sqlite")

    offer_state_rows: list[dict[str, Any]] = []
    repricer_fetched: list[datetime] = []
    stock_snapshot_dates: set[str] = set()
    if db_path.exists() and repricer_path.exists():
        with _connect_ro(db_path) as db_conn, _connect_ro(repricer_path) as repricer_conn:
            if not _table_exists(db_conn, "fact_inventory_snapshot_size"):
                fatal_errors.append("missing_table:fact_inventory_snapshot_size")
            if not _table_exists(repricer_conn, "repricer_items"):
                fatal_errors.append("missing_table:repricer_items")
            if not fatal_errors:
                for family in families:
                    sku_key = str(family["sku_key"])
                    family_id = str(family.get("family_id") or sku_key)
                    excluded_sizes = {_upper(value) for value in family.get("exclude_sizes") or []}
                    latest_snapshot, stock_rows = _load_latest_stock(db_conn, sku_key)
                    if latest_snapshot:
                        stock_snapshot_dates.add(latest_snapshot)
                    offers = _load_repricer_family_rows(repricer_conn, sku_key)
                    for offer in offers:
                        fetched = _parse_dt(offer.get("fetched_at"))
                        if fetched:
                            repricer_fetched.append(fetched)
                    active_by_size: dict[str, list[dict[str, Any]]] = {}
                    for offer in offers:
                        if not _is_active_available(offer):
                            continue
                        size = _extract_offer_size(str(offer.get("merchant_sku") or ""), sku_key)
                        if size:
                            active_by_size.setdefault(size, []).append(offer)
                    seen_sizes = {_upper(row.get("my_size")) for row in stock_rows}
                    seen_sizes.update(active_by_size.keys())
                    for size in sorted(seen_sizes):
                        stock_qty = sum(
                            _as_int(row.get("current_stock"))
                            for row in stock_rows
                            if _upper(row.get("my_size")) == size
                        )
                        active_rows = active_by_size.get(size, [])
                        excluded = size in excluded_sizes
                        should_buyable = stock_qty > 0 and not excluded
                        is_buyable = bool(active_rows)
                        if should_buyable and not is_buyable:
                            status = "MISSING_BUYABLE"
                        elif not should_buyable and is_buyable:
                            status = "EXCLUDED_OR_ZERO_STOCK_BUYABLE"
                        else:
                            status = "OK"
                        offer_state_rows.append(
                            {
                                "family_id": family_id,
                                "sku_key": sku_key,
                                "size": size,
                                "current_stock": stock_qty,
                                "excluded_by_decision": excluded,
                                "should_be_buyable": should_buyable,
                                "active_available_offer_count": len(active_rows),
                                "store_ids": ";".join(str(row.get("store_id") or "") for row in active_rows),
                                "merchant_skus": ";".join(str(row.get("merchant_sku") or "") for row in active_rows),
                                "links": ";".join(str(row.get("link") or "") for row in active_rows),
                                "status": status,
                            }
                        )

    source_max = max(repricer_fetched) if repricer_fetched else None
    max_age_days = float(config.get("max_repricer_age_days") or 1)
    source_age_days = (
        round((as_of_dt - source_max).total_seconds() / 86400, 4) if source_max is not None else None
    )
    source_fresh = source_age_days is not None and source_age_days <= max_age_days
    checks.append(
        _check(
            bool(stock_snapshot_dates),
            "current_stock_snapshot_present",
            ",".join(sorted(stock_snapshot_dates)) if stock_snapshot_dates else "missing",
        )
    )
    checks.append(
        _check(
            source_fresh,
            "repricer_offer_state_fresh",
            f"max_fetched_at={source_max.isoformat() if source_max else 'none'} age_days={source_age_days} max={max_age_days}",
        )
    )

    missing_buyable = [row for row in offer_state_rows if row["status"] == "MISSING_BUYABLE"]
    excluded_or_zero = [row for row in offer_state_rows if row["status"] == "EXCLUDED_OR_ZERO_STOCK_BUYABLE"]
    checks.append(
        _check(
            not missing_buyable,
            "positive_stock_sizes_buyable",
            f"missing_buyable_count={len(missing_buyable)}",
        )
    )
    checks.append(
        _check(
            not excluded_or_zero,
            "excluded_or_zero_stock_sizes_not_buyable",
            f"excluded_or_zero_stock_buyable_count={len(excluded_or_zero)}",
        )
    )

    if not source_fresh:
        fatal_errors.append("repricer_offer_state_stale_or_missing")
    for row in missing_buyable:
        blockers.append(f"missing_buyable:{row['sku_key']}:{row['size']}:stock={row['current_stock']}")
    for row in excluded_or_zero:
        blockers.append(
            f"excluded_or_zero_stock_buyable:{row['sku_key']}:{row['size']}:stock={row['current_stock']}:offers={row['active_available_offer_count']}"
        )

    if fatal_errors:
        gate = "RED"
    elif missing_buyable or excluded_or_zero:
        gate = "RED"
    elif dependency_missing:
        gate = "ARMED"
    else:
        gate = "GREEN"

    offer_state_csv = out_dir / "dark_relist_offer_state_rows.csv"
    _write_csv(offer_state_csv, offer_state_rows, OFFER_STATE_COLUMNS)
    json_path = out_dir / "dark_relist_state_report.json"
    md_path = out_dir / "dark_relist_state_report.md"
    report: dict[str, Any] = {
        "contract_id": config.get("contract_id", "DARK_FAMILY_RELIST_STATE_V1"),
        "gate_id": config.get("gate_id", "G-DARK-01"),
        "gate": gate,
        "generated_at": generated_at,
        "as_of": as_of_dt.isoformat(),
        "db_open_mode": "ro",
        "repricer_open_mode": "ro",
        "db_path": str(db_path),
        "repricer_sqlite_path": str(repricer_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "dependency_statuses": dependency_statuses,
        "family_count": len(families),
        "stock_snapshot_date": ",".join(sorted(stock_snapshot_dates)),
        "repricer_source_max_fetched_at": source_max.isoformat() if source_max else "",
        "repricer_source_age_days": source_age_days,
        "offer_state_row_count": len(offer_state_rows),
        "missing_buyable_count": len(missing_buyable),
        "excluded_or_zero_stock_buyable_count": len(excluded_or_zero),
        "fatal_errors": fatal_errors,
        "blockers": blockers,
        "checks": checks,
        "passed_checks": sum(1 for row in checks if row["ok"]),
        "total_checks": len(checks),
        "offer_state_csv": str(offer_state_csv),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "external_writes_performed": False,
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when gate is RED.")
    args = parser.parse_args(argv)
    report = build_dark_relist_state_report(
        config_path=args.config,
        output_root=args.output_root,
        as_of=args.as_of,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
