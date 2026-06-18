#!/usr/bin/env python3
"""Replay CRM-derived fact_sales and daily aggregates under a write gate.

This wrapper intentionally updates only the legacy derived sales chain:
`fact_sales`, `fact_sales_daily`, and `fact_sales_daily_size`. It does not
write sales_fact_v2, stock_ledger, workbooks, external systems, or messages.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ingest.sales_ingest import ingest_sales_to_fact_sales  # noqa: E402
from scripts.build_daily_aggregates import (  # noqa: E402
    build_fact_sales_daily,
    build_fact_sales_daily_size,
)
import scripts.validate_data_completeness as data_completeness  # noqa: E402
from core.calc.economics import calc_cogs  # noqa: E402


ENV_GATE = "ENABLE_FACT_SALES_DERIVED_REPLAY_WRITE"
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CRM = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET = "SALES_KSP_CRM_1"


class FactSalesReplayError(RuntimeError):
    """Raised when the derived fact_sales replay cannot proceed safely."""


@dataclass(frozen=True)
class ChainStats:
    fact_sales_count: int
    fact_sales_min_date: str | None
    fact_sales_max_date: str | None
    fact_sales_units: float | None
    fact_sales_daily_count: int
    fact_sales_daily_min_date: str | None
    fact_sales_daily_max_date: str | None
    fact_sales_daily_units: float | None
    fact_sales_daily_size_count: int
    fact_sales_daily_size_min_date: str | None
    fact_sales_daily_size_max_date: str | None
    fact_sales_daily_size_units: float | None
    sales_fact_v2_count: int
    sales_fact_v2_min_date: str | None
    sales_fact_v2_max_date: str | None
    sales_fact_v2_units: float | None
    fact_cashflow_daily_count: int
    fact_cashflow_daily_min_date: str | None
    fact_cashflow_daily_max_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _sqlite_integrity_check(path: Path) -> str:
    conn = _connect_readonly(path)
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "")


def _sqlite_backup(src_path: Path, dst_path: Path) -> Path:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src = _connect_readonly(src_path)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    integrity = _sqlite_integrity_check(dst_path)
    if integrity.lower() != "ok":
        raise FactSalesReplayError(f"backup integrity_check failed for {dst_path}: {integrity}")
    return dst_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _load_chain_stats(db_path: Path) -> ChainStats:
    conn = _connect_readonly(db_path)
    try:
        rows = {
            name: row
            for name, row in [
                (
                    "fact_sales",
                    conn.execute(
                        "SELECT COUNT(*), MIN(order_date), MAX(order_date), SUM(quantity) FROM fact_sales"
                    ).fetchone(),
                ),
                (
                    "fact_sales_daily",
                    conn.execute(
                        "SELECT COUNT(*), MIN(sale_date), MAX(sale_date), SUM(units) FROM fact_sales_daily"
                    ).fetchone(),
                ),
                (
                    "fact_sales_daily_size",
                    conn.execute(
                        "SELECT COUNT(*), MIN(sale_date), MAX(sale_date), SUM(units) FROM fact_sales_daily_size"
                    ).fetchone(),
                ),
                (
                    "sales_fact_v2",
                    conn.execute(
                        "SELECT COUNT(*), MIN(order_date), MAX(order_date), SUM(quantity) FROM sales_fact_v2"
                    ).fetchone(),
                ),
                (
                    "fact_cashflow_daily",
                    conn.execute(
                        "SELECT COUNT(*), MIN(date), MAX(date), NULL FROM fact_cashflow_daily"
                    ).fetchone(),
                ),
            ]
        }
    finally:
        conn.close()

    return ChainStats(
        fact_sales_count=int(rows["fact_sales"][0] or 0),
        fact_sales_min_date=rows["fact_sales"][1],
        fact_sales_max_date=rows["fact_sales"][2],
        fact_sales_units=rows["fact_sales"][3],
        fact_sales_daily_count=int(rows["fact_sales_daily"][0] or 0),
        fact_sales_daily_min_date=rows["fact_sales_daily"][1],
        fact_sales_daily_max_date=rows["fact_sales_daily"][2],
        fact_sales_daily_units=rows["fact_sales_daily"][3],
        fact_sales_daily_size_count=int(rows["fact_sales_daily_size"][0] or 0),
        fact_sales_daily_size_min_date=rows["fact_sales_daily_size"][1],
        fact_sales_daily_size_max_date=rows["fact_sales_daily_size"][2],
        fact_sales_daily_size_units=rows["fact_sales_daily_size"][3],
        sales_fact_v2_count=int(rows["sales_fact_v2"][0] or 0),
        sales_fact_v2_min_date=rows["sales_fact_v2"][1],
        sales_fact_v2_max_date=rows["sales_fact_v2"][2],
        sales_fact_v2_units=rows["sales_fact_v2"][3],
        fact_cashflow_daily_count=int(rows["fact_cashflow_daily"][0] or 0),
        fact_cashflow_daily_min_date=rows["fact_cashflow_daily"][1],
        fact_cashflow_daily_max_date=rows["fact_cashflow_daily"][2],
    )


def _next_day(day: str | None) -> str | None:
    if not day:
        return None
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def _sanitize_ingest_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "inserted": int(stats.get("inserted", 0) or 0),
        "updated": int(stats.get("updated", 0) or 0),
        "skipped": int(stats.get("skipped", 0) or 0),
        "errors": len(stats.get("errors") or []),
        "unmapped": len(stats.get("unmapped") or []),
        "min_date": stats.get("min_date"),
        "max_date": stats.get("max_date"),
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _resolve_v2_unit_cogs(
    *,
    line_cogs: Any,
    quantity: int,
    sku_meta: dict[str, Any],
) -> float | None:
    cogs_line = _float_or_none(line_cogs)
    if cogs_line is not None and cogs_line > 0 and quantity > 0:
        return cogs_line / quantity
    stored = _float_or_none(sku_meta.get("cogs_kzt"))
    if stored is not None and stored > 0:
        return stored
    base = _float_or_none(sku_meta.get("base_cost_cny"))
    weight = _float_or_none(sku_meta.get("weight_kg"))
    if base is not None and base > 0 and weight is not None and weight > 0:
        return calc_cogs(base, weight)
    return None


def _replay_missing_from_sales_fact_v2(
    *,
    conn: sqlite3.Connection,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    required_cols = {
        "order_id",
        "order_date",
        "sku_key",
        "sku_id",
        "my_size",
        "kaspi_offer_name",
        "store_code",
        "quantity",
        "sell_price_kzt",
        "delivery_fee",
        "net_rev",
        "status",
        "return_flag",
    }
    v2_cols = _table_columns(conn, "sales_fact_v2")
    missing_cols = sorted(required_cols - v2_cols)
    stats: dict[str, Any] = {
        "source": "sales_fact_v2",
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "min_date": None,
        "max_date": None,
    }
    if missing_cols:
        stats["skipped_reason"] = f"sales_fact_v2 missing columns: {missing_cols}"
        return stats

    sku_meta = {
        str(row["sku_key"]): {
            "base_cost_cny": row["base_cost_cny"],
            "weight_kg": row["weight_kg"],
            "product_type": row["product_type"],
            "cogs_kzt": row["cogs_kzt"],
        }
        for row in conn.execute(
            """
            SELECT sku_key, base_cost_cny, weight_kg, product_type, cogs_kzt
            FROM dim_sku
            """
        ).fetchall()
    }
    source_rows = conn.execute(
        """
        SELECT
            order_id,
            order_date,
            sku_key,
            sku_id,
            my_size,
            kaspi_offer_name,
            store_code,
            quantity,
            sell_price_kzt,
            delivery_fee,
            cogs,
            net_rev,
            profit
        FROM sales_fact_v2
        WHERE date(order_date) BETWEEN date(?) AND date(?)
          AND UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
          AND COALESCE(return_flag, 0) = 0
        ORDER BY order_date, store_code, order_id, sku_id, kaspi_offer_name
        """,
        (from_date, to_date),
    ).fetchall()

    existing_rows = conn.execute(
        """
        SELECT id, order_id, store_code, kaspi_offer_name, sku_id
        FROM fact_sales
        WHERE date(order_date) BETWEEN date(?) AND date(?)
        """,
        (from_date, to_date),
    ).fetchall()
    existing_by_unique = {
        (
            str(row["order_id"]),
            str(row["store_code"]),
            str(row["kaspi_offer_name"] or ""),
            str(row["sku_id"] or ""),
        ): int(row["id"])
        for row in existing_rows
    }

    inserts: list[tuple[Any, ...]] = []
    updates: list[tuple[Any, ...]] = []
    for row in source_rows:
        order_id = str(row["order_id"] or "").strip()
        order_date = str(row["order_date"] or "").strip()[:10]
        sku_key = str(row["sku_key"] or "").strip()
        sku_id = str(row["sku_id"] or "").strip()
        my_size = str(row["my_size"] or "").strip()
        kaspi_offer_name = str(row["kaspi_offer_name"] or "").strip()
        store_code = str(row["store_code"] or "UNIVERSAL").strip().upper()
        quantity_raw = _float_or_none(row["quantity"])
        quantity = int(round(quantity_raw or 0))
        sell_price = _float_or_none(row["sell_price_kzt"])
        line_delivery_fee = _float_or_none(row["delivery_fee"]) or 0.0
        line_net_rev = _float_or_none(row["net_rev"])

        if (
            not order_id
            or not order_date
            or not sku_key
            or not sku_id
            or not kaspi_offer_name
            or quantity <= 0
            or sell_price is None
        ):
            stats["skipped"] += 1
            stats["errors"].append(f"incomplete v2 row order_id={order_id or '<blank>'}")
            continue
        meta = sku_meta.get(sku_key)
        if meta is None:
            stats["skipped"] += 1
            stats["errors"].append(f"missing dim_sku for v2 row order_id={order_id} sku_key={sku_key}")
            continue
        cogs_unit = _resolve_v2_unit_cogs(
            line_cogs=row["cogs"],
            quantity=quantity,
            sku_meta=meta,
        )
        if cogs_unit is None:
            stats["skipped"] += 1
            stats["errors"].append(f"missing COGS for v2 row order_id={order_id} sku_key={sku_key}")
            continue

        if line_net_rev is None:
            line_net_rev = (sell_price * quantity) - line_delivery_fee
        delivery_fee_unit = line_delivery_fee / quantity
        net_rev_unit = line_net_rev / quantity
        cogs_line = cogs_unit * quantity
        profit_unit = net_rev_unit - cogs_unit
        profit_line = line_net_rev - cogs_line
        product_type = str(meta.get("product_type") or "CL")

        payload = (
            order_id,
            kaspi_offer_name,
            store_code,
            order_date,
            sku_key,
            sku_id,
            my_size,
            quantity,
            sell_price,
            product_type,
            "Kaspi",
            delivery_fee_unit,
            net_rev_unit,
            line_net_rev,
            cogs_unit,
            cogs_line,
            profit_unit,
            profit_line,
            "KSP",
        )
        existing_id = existing_by_unique.get((order_id, store_code, kaspi_offer_name, sku_id))
        if existing_id:
            updates.append(payload[1:] + (existing_id,))
            stats["updated"] += 1
        else:
            inserts.append(payload)
            stats["inserted"] += 1
        if stats["min_date"] is None or order_date < stats["min_date"]:
            stats["min_date"] = order_date
        if stats["max_date"] is None or order_date > stats["max_date"]:
            stats["max_date"] = order_date

    if updates:
        conn.executemany(
            """
            UPDATE fact_sales
            SET kaspi_offer_name = ?,
                store_code = ?,
                order_date = ?,
                sku_key = ?,
                sku_id = ?,
                my_size = ?,
                quantity = ?,
                sell_price_kzt = ?,
                product_type = ?,
                channel = ?,
                delivery_fee = ?,
                net_rev_unit = ?,
                line_net_rev = ?,
                cogs_unit = ?,
                cogs_line = ?,
                profit_unit = ?,
                profit_line = ?,
                channel_code = ?
            WHERE id = ?
            """,
            updates,
        )
    if inserts:
        conn.executemany(
            """
            INSERT INTO fact_sales (
                order_id, kaspi_offer_name, store_code, order_date,
                sku_key, sku_id, my_size, quantity, sell_price_kzt,
                product_type, channel, delivery_fee,
                net_rev_unit, line_net_rev, cogs_unit, cogs_line,
                profit_unit, profit_line, channel_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            inserts,
        )
    return stats


def _combined_min_max(*stats_items: dict[str, Any]) -> tuple[str | None, str | None]:
    mins = [item.get("min_date") for item in stats_items if item.get("min_date")]
    maxes = [item.get("max_date") for item in stats_items if item.get("max_date")]
    return (min(mins) if mins else None, max(maxes) if maxes else None)


def _run_data_completeness(db_path: Path, output_path: Path, as_of: date) -> dict[str, Any]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = data_completeness.validate(db_path=db_path, as_of=as_of, fresh_within_days=1)
    text = buf.getvalue()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return {
        "ok": bool(ok),
        "output_path": str(output_path),
    }


def _assert_freshness(stats: ChainStats, *, target_date: str) -> list[str]:
    errors: list[str] = []
    checks = {
        "fact_sales_max_date": stats.fact_sales_max_date,
        "fact_sales_daily_max_date": stats.fact_sales_daily_max_date,
        "fact_sales_daily_size_max_date": stats.fact_sales_daily_size_max_date,
        "sales_fact_v2_max_date": stats.sales_fact_v2_max_date,
        "fact_cashflow_daily_max_date": stats.fact_cashflow_daily_max_date,
    }
    for label, observed in checks.items():
        if observed is None or str(observed) < target_date:
            errors.append(f"{label}={observed} < target_date={target_date}")
    return errors


def _replay_on_db(
    *,
    db_path: Path,
    crm_path: Path,
    sheet_name: str,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    ingest_stats = ingest_sales_to_fact_sales(
        xlsx_path=str(crm_path),
        sheet_name=sheet_name,
        dry_run=False,
        source_file=crm_path.name,
        db_path=db_path,
        from_date=from_date,
        to_date=to_date,
    )
    sanitized = _sanitize_ingest_stats(ingest_stats)
    sales_fact_v2_fallback = {
        "source": "sales_fact_v2",
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "min_date": None,
        "max_date": None,
        "skipped_reason": "not needed; CRM replay reached target window",
    }
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not sanitized["max_date"] or str(sanitized["max_date"]) < to_date:
            sales_fact_v2_fallback = _replay_missing_from_sales_fact_v2(
                conn=conn,
                from_date=from_date,
                to_date=to_date,
            )
            conn.commit()
    finally:
        conn.close()
    aggregate_stats = {
        "fact_sales_daily": {"deleted": 0, "inserted": 0},
        "fact_sales_daily_size": {"deleted": 0, "inserted": 0},
    }
    aggregate_min, aggregate_max = _combined_min_max(sanitized, sales_fact_v2_fallback)
    if aggregate_min and aggregate_max:
        conn = sqlite3.connect(str(db_path))
        try:
            aggregate_stats = {
                "fact_sales_daily": build_fact_sales_daily(
                    conn,
                    from_date=aggregate_min,
                    to_date=aggregate_max,
                    dry_run=False,
                ),
                "fact_sales_daily_size": build_fact_sales_daily_size(
                    conn,
                    from_date=aggregate_min,
                    to_date=aggregate_max,
                    dry_run=False,
                ),
            }
        finally:
            conn.close()
    return {
        "fact_sales": sanitized,
        "sales_fact_v2_fallback": sales_fact_v2_fallback,
        "aggregates": aggregate_stats,
    }


def run_replay(
    *,
    db_path: Path = DEFAULT_DB,
    crm_path: Path = DEFAULT_CRM,
    sheet_name: str = DEFAULT_SHEET,
    output_dir: Path,
    backup_dir: Path | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    as_of: date | None = None,
    expected_pre_sha256: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of = as_of or date.today()
    if not db_path.exists():
        raise FactSalesReplayError(f"database not found: {db_path}")
    if not crm_path.exists():
        raise FactSalesReplayError(f"CRM workbook not found: {crm_path}")

    source_pre_sha = _sha256_file(db_path)
    if expected_pre_sha256 and source_pre_sha != expected_pre_sha256:
        raise FactSalesReplayError(
            f"pre-SHA mismatch: observed={source_pre_sha} expected={expected_pre_sha256}"
        )

    before = _load_chain_stats(db_path)
    effective_from = from_date or _next_day(before.fact_sales_max_date)
    effective_to = to_date or (as_of - timedelta(days=1)).isoformat()
    if not effective_from:
        raise FactSalesReplayError("could not infer from_date because fact_sales has no max date")
    if effective_from > effective_to:
        raise FactSalesReplayError(f"empty replay window: from_date={effective_from} to_date={effective_to}")

    target_db = db_path
    backup_path: Path | None = None
    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise FactSalesReplayError(f"{ENV_GATE}=1 is required with --apply")
        if backup_dir is None:
            raise FactSalesReplayError("--backup-dir is required with --apply")
        backup_path = _sqlite_backup(
            db_path,
            backup_dir / f"app_before_fact_sales_derived_replay_{source_pre_sha[:12]}.db",
        )
    else:
        sim_dir = Path(tempfile.mkdtemp(prefix="fact_sales_derived_replay_", dir=output_dir))
        target_db = sim_dir / "app.simulation.db"
        _sqlite_backup(db_path, target_db)

    target_pre = _load_chain_stats(target_db)
    replay = _replay_on_db(
        db_path=target_db,
        crm_path=crm_path,
        sheet_name=sheet_name,
        from_date=effective_from,
        to_date=effective_to,
    )
    target_post = _load_chain_stats(target_db)
    validation = _run_data_completeness(
        target_db,
        output_dir / "validate_data_completeness.txt",
        as_of=as_of,
    )
    freshness_errors = _assert_freshness(target_post, target_date=effective_to)
    if freshness_errors:
        raise FactSalesReplayError(f"freshness validation failed: {freshness_errors}")
    if not validation["ok"]:
        raise FactSalesReplayError(
            f"validate_data_completeness failed; see {validation['output_path']}"
        )

    source_post_sha = _sha256_file(db_path)
    report = {
        "status": "APPLIED" if apply else "DRY_RUN",
        "env_gate": ENV_GATE,
        "db_path": str(db_path),
        "target_db_path": str(target_db),
        "crm_path": str(crm_path),
        "crm_sha256": _sha256_file(crm_path),
        "as_of": as_of.isoformat(),
        "window": {
            "from_date": effective_from,
            "to_date": effective_to,
        },
        "source_db_sha256_before": source_pre_sha,
        "source_db_sha256_after": source_post_sha,
        "source_db_sha256_changed": source_pre_sha != source_post_sha,
        "backup_path": str(backup_path) if backup_path else None,
        "source_before": before.as_dict(),
        "target_before": target_pre.as_dict(),
        "target_after": target_post.as_dict(),
        "replay": replay,
        "validation": validation,
        "freshness_errors": freshness_errors,
        "integrity_check": _sqlite_integrity_check(db_path if apply else target_db),
    }
    if not apply and report["source_db_sha256_changed"]:
        raise FactSalesReplayError("dry-run changed source database SHA")

    _write_json(output_dir / "fact_sales_derived_replay_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--crm-path", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        report = run_replay(
            db_path=args.db_path,
            crm_path=args.crm_path,
            sheet_name=args.sheet,
            output_dir=args.output_dir,
            backup_dir=args.backup_dir,
            from_date=args.from_date,
            to_date=args.to_date,
            as_of=args.as_of,
            expected_pre_sha256=args.expected_pre_sha256,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
