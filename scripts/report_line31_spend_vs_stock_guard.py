#!/usr/bin/env python3
"""Report LINE31 Kaspi ad spend against latest LINE31 stock truth.

Read-only over the operational DB. The report is intended to back the
G-LINE31-01 standing guard: positive LINE31 spend must not run against a LINE31 card
whose current latest stock snapshot contains zero/negative buyable sizes.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALMATY = ZoneInfo("Asia/Almaty")
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "line31_spend_vs_stock_guard"


class LINE31SpendStockGuardError(RuntimeError):
    """Raised when the strict LINE31 spend-vs-stock guard fails."""


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _db_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _latest_ads_date(conn: sqlite3.Connection, as_of: date) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(date) AS latest_date
        FROM ads_campaign_product_daily
        WHERE date <= ?
        """,
        (as_of.isoformat(),),
    ).fetchone()
    return str(row["latest_date"]) if row and row["latest_date"] else None


def _latest_stock_snapshot(conn: sqlite3.Connection, as_of: date) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(snapshot_date) AS latest_snapshot
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date <= ?
        """,
        (as_of.isoformat(),),
    ).fetchone()
    return str(row["latest_snapshot"]) if row and row["latest_snapshot"] else None


def _load_line31_ads_rows(conn: sqlite3.Connection, *, start: str, end: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            date,
            store_code,
            campaign_id,
            campaign_name,
            sku_key,
            cost_kzt
        FROM ads_campaign_product_daily
        WHERE date BETWEEN ? AND ?
          AND (
            UPPER(COALESCE(sku_key, '')) LIKE '%LINE31%'
            OR UPPER(COALESCE(campaign_name, '')) LIKE '%LINE31%'
          )
        ORDER BY date, store_code, campaign_id, sku_key
        """,
        (start, end),
    ).fetchall()
    return _rows_to_dicts(rows)


def _load_line31_stock_rows(conn: sqlite3.Connection, snapshot_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            snapshot_date,
            sku_key,
            sku_id,
            my_size,
            current_stock,
            inbound_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
          AND UPPER(COALESCE(sku_key, '')) LIKE '%LINE31%'
        ORDER BY sku_key, my_size, sku_id
        """,
        (snapshot_date,),
    ).fetchall()
    return _rows_to_dicts(rows)


def _positive_cost(row: dict[str, Any]) -> float:
    try:
        return float(row.get("cost_kzt") or 0)
    except (TypeError, ValueError):
        return 0.0


def _build_violations(
    *,
    ads_rows: list[dict[str, Any]],
    stock_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stock_by_sku: dict[str, list[dict[str, Any]]] = {}
    for row in stock_rows:
        stock_by_sku.setdefault(str(row.get("sku_key") or ""), []).append(row)

    violations: list[dict[str, Any]] = []
    for ad in ads_rows:
        if _positive_cost(ad) <= 0:
            continue
        sku_key = str(ad.get("sku_key") or "")
        matching_stock = stock_by_sku.get(sku_key, [])
        if not matching_stock:
            violations.append(
                {
                    **ad,
                    "violation_reason": "positive_line31_spend_without_latest_stock_evidence",
                    "zero_or_negative_sizes": "",
                }
            )
            continue
        zero_sizes = [
            str(stock.get("my_size") or "")
            for stock in matching_stock
            if int(stock.get("current_stock") or 0) <= 0
        ]
        if zero_sizes:
            violations.append(
                {
                    **ad,
                    "violation_reason": "positive_line31_spend_with_zero_or_negative_size",
                    "zero_or_negative_sizes": ",".join(sorted(zero_sizes)),
                }
            )
    return violations


def _markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# LINE31 Spend Vs Stock Guard",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        f"Gate: `{payload['gate']}`",
        "",
        "## Summary",
        "",
        f"- Period: `{summary['start']}`..`{summary['end']}`",
        f"- Latest ads date: `{summary['latest_ads_date']}`",
        f"- Latest LINE31 ads row date: `{summary['latest_line31_ads_row_date']}`",
        f"- Latest positive LINE31 spend date: `{summary['latest_positive_line31_spend_date']}`",
        f"- Latest stock snapshot: `{summary['latest_stock_snapshot_date']}`",
        f"- LINE31 ad rows: `{summary['line31_ad_rows']}`",
        f"- Positive LINE31 ad rows: `{summary['positive_line31_ad_rows']}`",
        f"- Positive LINE31 spend KZT: `{summary['positive_line31_spend_kzt']}`",
        f"- LINE31 stock rows: `{summary['line31_stock_rows']}`",
        f"- Zero or negative LINE31 stock rows: `{summary['zero_or_negative_stock_rows']}`",
        f"- Violations: `{summary['violation_rows']}`",
        "",
        "## Safety",
        "",
        "This report is read-only over the DB. It does not mutate DB, workbook, Google Sheet, Telegram, Kaspi, Web_automation, Meta, price, stock, cash, PO, supplier, scheduler, or customer/operator-message surfaces.",
    ]
    if payload.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in payload["notes"])
    return "\n".join(lines) + "\n"


def report_line31_spend_vs_stock_guard(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    as_of: date,
    start: date | None = None,
    end: date | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_id: str | None = None,
) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    before_sha = _db_sha256(db_path)
    generated_at = datetime.now(ALMATY).isoformat(timespec="seconds")
    run_id = run_id or datetime.now(ALMATY).strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    with _connect_readonly(db_path) as conn:
        latest_ads_date = _latest_ads_date(conn, as_of)
        if end is None:
            if latest_ads_date is None:
                raise LINE31SpendStockGuardError("ads_campaign_product_daily has no rows on or before as_of")
            end = date.fromisoformat(latest_ads_date)
        if start is None:
            start = date(end.year, end.month, 1)
        latest_stock_snapshot = _latest_stock_snapshot(conn, as_of)
        if latest_stock_snapshot is None:
            raise LINE31SpendStockGuardError("fact_inventory_snapshot_size has no rows on or before as_of")

        ads_rows = _load_line31_ads_rows(conn, start=start.isoformat(), end=end.isoformat())
        stock_rows = _load_line31_stock_rows(conn, latest_stock_snapshot)

    violations = _build_violations(ads_rows=ads_rows, stock_rows=stock_rows)
    positive_ads = [row for row in ads_rows if _positive_cost(row) > 0]
    zero_or_negative_stock_rows = [
        row for row in stock_rows if int(row.get("current_stock") or 0) <= 0
    ]
    latest_line31_row_date = max((str(row["date"]) for row in ads_rows), default=None)
    latest_positive_date = max((str(row["date"]) for row in positive_ads), default=None)
    positive_spend = round(sum(_positive_cost(row) for row in positive_ads), 2)

    notes: list[str] = [
        "Missing LINE31 ad rows are not interpreted as synthetic zero-spend.",
        "Kaspi ads are product/card-level in this evidence; a positive spend row is treated as risky when any latest size under the advertised LINE31 sku_key is zero or negative.",
    ]
    gate_ok = bool(stock_rows) and len(violations) == 0
    if not ads_rows:
        notes.append("No LINE31 ad rows were present in the selected period.")
    if latest_ads_date and end.isoformat() > latest_ads_date:
        gate_ok = False
        notes.append("Selected end date is newer than latest canonical ads date.")

    after_sha = _db_sha256(db_path)
    db_hash_unchanged = before_sha == after_sha
    if not db_hash_unchanged:
        gate_ok = False
        notes.append("DB hash changed during read-only guard execution.")

    payload: dict[str, Any] = {
        "gate": "GREEN" if gate_ok else "YELLOW",
        "generated_at": generated_at,
        "db_path": str(db_path),
        "db_sha256_before": before_sha,
        "db_sha256_after": after_sha,
        "db_hash_unchanged": db_hash_unchanged,
        "summary": {
            "as_of": as_of.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "latest_ads_date": latest_ads_date,
            "latest_line31_ads_row_date": latest_line31_row_date,
            "latest_positive_line31_spend_date": latest_positive_date,
            "latest_stock_snapshot_date": latest_stock_snapshot,
            "line31_ad_rows": len(ads_rows),
            "positive_line31_ad_rows": len(positive_ads),
            "positive_line31_spend_kzt": positive_spend,
            "line31_stock_rows": len(stock_rows),
            "zero_or_negative_stock_rows": len(zero_or_negative_stock_rows),
            "violation_rows": len(violations),
        },
        "output_files": {
            "report_json": str(output_dir / "line31_spend_vs_stock_guard.json"),
            "report_md": str(output_dir / "line31_spend_vs_stock_guard.md"),
            "ads_rows_csv": str(output_dir / "line31_ads_rows.csv"),
            "stock_rows_csv": str(output_dir / "line31_stock_rows.csv"),
            "violations_csv": str(output_dir / "line31_violations.csv"),
        },
        "notes": notes,
        "no_external_writes_performed": True,
    }
    _write_csv(output_dir / "line31_ads_rows.csv", ads_rows)
    _write_csv(output_dir / "line31_stock_rows.csv", stock_rows)
    _write_csv(output_dir / "line31_violations.csv", violations)
    _write_json(output_dir / "line31_spend_vs_stock_guard.json", payload)
    (output_dir / "line31_spend_vs_stock_guard.md").write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", default=datetime.now(ALMATY).date().isoformat())
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = report_line31_spend_vs_stock_guard(
            db_path=args.db_path,
            as_of=date.fromisoformat(str(args.as_of)),
            start=date.fromisoformat(str(args.start)) if args.start else None,
            end=date.fromisoformat(str(args.end)) if args.end else None,
            output_root=args.output_root,
            run_id=args.run_id,
        )
    except LINE31SpendStockGuardError as exc:
        print(f"line31_spend_vs_stock_guard: YELLOW")
        print(f"ERROR: {exc}")
        return 1 if args.strict else 0

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"line31_spend_vs_stock_guard: {payload['gate']}")
        print(payload["output_files"]["report_json"])
    return 0 if (payload["gate"] == "GREEN" or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
