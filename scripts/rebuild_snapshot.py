#!/usr/bin/env python3
"""
TASK-175: Rebuild Inventory Snapshot from Stock Ledger

Rebuilds fact_inventory_snapshot_size from stock_ledger events.
Also calculates inbound_stock from pending po_line entries.

Usage:
    python scripts/rebuild_snapshot.py              # Rebuild for today
    python scripts/rebuild_snapshot.py --date 2025-12-09
    python scripts/rebuild_snapshot.py --verbose
    python scripts/rebuild_snapshot.py --compare    # Compare with existing snapshot

This script is designed to be run daily to sync the snapshot table
with the authoritative stock_ledger events.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, DEFAULT_DB_PATH
from core.calc.stock_timeline import StockTimelineBuilder
from core.db.ledger import (
    rebuild_snapshot_from_ledger,
    get_accepted_negative_active_zero_sku_ids,
    get_stock_balances_all,
    get_event_summary,
)

DIAGNOSTICS_DIR = Path(__file__).parent.parent / "exports"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _table_has_column(conn, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def write_negative_balance_report(
    snapshot_date: date,
    balances: dict,
    db_path: Path,
) -> Path | None:
    negative = {sku_id: bal for sku_id, bal in balances.items() if bal < 0}
    if not negative:
        return None

    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DIAGNOSTICS_DIR / f"ledger_negative_balances_{snapshot_date.isoformat()}.md"

    with get_db(db_path) as conn, output_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# Negative Ledger Balances — {snapshot_date.isoformat()}\n\n")
        fh.write(f"Total negative SKUs: {len(negative)}\n\n")

        for sku_id, balance in sorted(negative.items(), key=lambda x: x[1]):
            fh.write(f"## {sku_id} (balance {balance})\n\n")
            rows = conn.execute(
                """
                SELECT event_date, event_type, qty_change, reference_id, notes
                FROM stock_ledger
                WHERE sku_id = ?
                  AND event_date <= ?
                ORDER BY event_date DESC, event_time DESC
                LIMIT 8
                """,
                (sku_id, snapshot_date.isoformat()),
            ).fetchall()

            fh.write("| Date | Type | Qty | Ref | Notes |\n")
            fh.write("| --- | --- | --- | --- | --- |\n")
            for row in rows:
                fh.write(
                    f"| {row['event_date']} | {row['event_type']} | {row['qty_change']} | "
                    f"{row['reference_id'] or ''} | {row['notes'] or ''} |\n"
                )
            fh.write("\n")

    return output_path


def get_stock_balances_exclusive(
    snapshot_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Path = None,
) -> dict:
    """Return ledger balances with event_date < snapshot_date (morning semantics)."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    params = [snapshot_date.isoformat()]
    store_filter = ""
    if store_code and store_code != "ALL":
        store_filter = "AND store_code = ?"
        params.append(store_code)
    with get_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT sku_id, SUM(qty_change) as balance
            FROM stock_ledger
            WHERE event_date < ?
              {store_filter}
            GROUP BY sku_id
            """,
            params,
        ).fetchall()
    return {row["sku_id"]: row["balance"] for row in rows}

def get_existing_snapshot(
    snapshot_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Path = None,
) -> dict:
    """
    Get existing snapshot data for comparison.

    Returns:
        Dict with {sku_id: (current_stock, inbound_stock)}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        # Note: fact_inventory_snapshot_size doesn't have store_code column
        rows = conn.execute("""
            SELECT sku_id, current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(),)).fetchall()

        return {row["sku_id"]: (row["current_stock"], row["inbound_stock"]) for row in rows}


def compare_snapshots(
    old_snapshot: dict,
    new_snapshot: dict,
) -> dict:
    """
    Compare old and new snapshots.

    Returns:
        Dict with {added: [...], removed: [...], changed: [...]}
    """
    old_skus = set(old_snapshot.keys())
    new_skus = set(new_snapshot.keys())

    added = new_skus - old_skus
    removed = old_skus - new_skus
    common = old_skus & new_skus

    changed = []
    for sku_id in common:
        old_stock, old_inbound = old_snapshot[sku_id]
        new_stock, new_inbound = new_snapshot[sku_id]
        if old_stock != new_stock or old_inbound != new_inbound:
            changed.append({
                "sku_id": sku_id,
                "old_stock": old_stock,
                "new_stock": new_stock,
                "old_inbound": old_inbound,
                "new_inbound": new_inbound,
            })

    return {
        "added": list(added),
        "removed": list(removed),
        "changed": changed,
    }


def plan_snapshot_from_ledger(
    snapshot_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Path = None,
) -> dict[str, dict]:
    """Return the snapshot rows that ledger mode would write, without DB writes."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        accepted_negative_active_zero_skus = get_accepted_negative_active_zero_sku_ids(conn)
        params = [snapshot_date.isoformat()]
        store_filter = ""
        if store_code and store_code != "ALL":
            store_filter = "AND store_code = ?"
            params.append(store_code)

        ledger_rows = conn.execute(
            f"""
            SELECT sku_id, sku_key, my_size, SUM(qty_change) AS current_stock
            FROM stock_ledger
            WHERE event_date < ?
              {store_filter}
            GROUP BY sku_id, sku_key, my_size
            """,
            params,
        ).fetchall()

        if _table_exists(conn, "dim_sku_size"):
            if (
                _table_exists(conn, "dim_sku")
                and _table_has_column(conn, "dim_sku_size", "active_flag")
                and _table_has_column(conn, "dim_sku", "active_flag")
            ):
                active_rows = conn.execute(
                    """
                    SELECT ds.sku_id, ds.sku_key, ds.my_size
                    FROM dim_sku_size ds
                    JOIN dim_sku d ON ds.sku_key = d.sku_key
                    WHERE ds.active_flag = 1
                      AND d.active_flag = 1
                      AND ds.my_size IS NOT NULL
                      AND ds.my_size != ''
                    """
                ).fetchall()
            else:
                active_rows = conn.execute(
                    """
                    SELECT sku_id, sku_key, my_size
                    FROM dim_sku_size
                    WHERE my_size IS NOT NULL
                      AND my_size != ''
                    """
                ).fetchall()
        else:
            active_rows = []

    inbound_by_sku = get_pending_inbound_by_sku(snapshot_date, db_path=db_path)

    planned: dict[str, dict] = {}
    for row in active_rows:
        planned[str(row["sku_id"])] = {
            "sku_id": str(row["sku_id"]),
            "sku_key": str(row["sku_key"]),
            "my_size": str(row["my_size"]),
            "current_stock": 0,
            "inbound_stock": int(inbound_by_sku.get(row["sku_id"], 0) or 0),
        }

    for row in ledger_rows:
        sku_id = str(row["sku_id"])
        planned.setdefault(
            sku_id,
            {
                "sku_id": sku_id,
                "sku_key": str(row["sku_key"]),
                "my_size": str(row["my_size"]),
                "current_stock": 0,
                "inbound_stock": int(inbound_by_sku.get(sku_id, 0) or 0),
            },
        )
        current_stock = int(row["current_stock"] or 0)
        if current_stock < 0 and sku_id in accepted_negative_active_zero_skus:
            current_stock = 0
        planned[sku_id]["current_stock"] += current_stock

    return planned


def get_latest_snapshot_before(
    snapshot_date: date,
    db_path: Path = None,
) -> str | None:
    """Return latest snapshot_date strictly before the target date."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    with get_db(db_path) as conn:
        row = conn.execute("""
            SELECT MAX(snapshot_date) as max_date
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date < ?
        """, (snapshot_date.isoformat(),)).fetchone()
        return row["max_date"] if row and row["max_date"] else None


def get_active_sizes(
    db_path: Path = None,
) -> list[dict]:
    """Return active size rows from dim_sku_size + dim_sku."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT ds.sku_id, ds.sku_key, ds.my_size
            FROM dim_sku_size ds
            JOIN dim_sku d ON ds.sku_key = d.sku_key
            WHERE ds.active_flag = 1
              AND d.active_flag = 1
              AND ds.my_size IS NOT NULL
              AND ds.my_size != ''
        """).fetchall()
    return [dict(r) for r in rows]


def get_pending_inbound_by_sku(
    snapshot_date: date,
    db_path: Path = None,
) -> dict[str, int]:
    """
    Get pending inbound units per sku_id for snapshot_date.

    Uses Fact_PO_Lines (IN_TRANSIT, ETA after snapshot) plus po_line (PENDING/PARTIAL/IN_TRANSIT).
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    inbound_by_sku: dict[str, int] = {}
    with get_db(db_path) as conn:
        # Fact_PO_Lines: IN_TRANSIT/ARRIVED with ETA on/after snapshot (day-start snapshots)
        if _table_exists(conn, "fact_po_lines"):
            po_line_filter = ""
            if _table_exists(conn, "po_line"):
                po_line_filter = "AND po_id NOT IN (SELECT DISTINCT po_id FROM po_line)"
            rows = conn.execute(f"""
                SELECT sku_id, SUM(order_quantity - COALESCE(received_qty, 0)) as inbound_stock
                FROM fact_po_lines
                WHERE status IN ('IN_TRANSIT', 'ARRIVED')
                  AND (est_arrival_date IS NULL OR est_arrival_date >= ?)
                  {po_line_filter}
                GROUP BY sku_id
            """, (snapshot_date.isoformat(),)).fetchall()
            for row in rows:
                inbound_by_sku[row["sku_id"]] = row["inbound_stock"] or 0

        # po_line: include pending units (no ETA in schema)
        if _table_exists(conn, "po_line"):
            rows = conn.execute("""
                SELECT sku_id, SUM(order_qty - COALESCE(received_qty, 0)) as inbound_stock
                FROM po_line
                WHERE status IN ('PENDING', 'PARTIAL', 'IN_TRANSIT')
                GROUP BY sku_id
            """).fetchall()
            for row in rows:
                inbound_by_sku[row["sku_id"]] = inbound_by_sku.get(row["sku_id"], 0) + (row["inbound_stock"] or 0)

    return inbound_by_sku


def rebuild_snapshot_from_simulation(
    snapshot_date: date,
    store_code: str = "UNIVERSAL",
    include_estimated_arrivals: bool = True,
    verbose: bool = False,
    db_path: Path = None,
) -> dict:
    """
    Rebuild snapshot by forward-simulating from the latest prior snapshot.

    Uses sales_fact_v2 and PO arrivals (actual + ETA for IN_TRANSIT if enabled).
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    builder = StockTimelineBuilder(db_path)
    base_date = get_latest_snapshot_before(snapshot_date, db_path=db_path)
    if base_date is None:
        base_date = builder.get_latest_snapshot_date(snapshot_date.isoformat(), include_end_date=True)

    if base_date is None:
        raise RuntimeError("No snapshot found to use as base for simulation.")

    base_stock = builder.get_current_stock_by_size(base_date)

    # Ensure all active sizes exist in base_stock
    for row in get_active_sizes(db_path=db_path):
        base_stock.setdefault(
            row["sku_id"],
            {
                "current_stock": 0,
                "inbound_stock": 0,
                "sku_key": row["sku_key"],
                "my_size": row["my_size"],
            },
        )

    inbound_by_sku = get_pending_inbound_by_sku(snapshot_date, db_path=db_path)

    missing_in_base = [sku_id for sku_id in inbound_by_sku if sku_id not in base_stock]
    if missing_in_base:
        with get_db(db_path) as conn:
            placeholders = ",".join("?" for _ in missing_in_base)
            rows = conn.execute(f"""
                SELECT sku_id, sku_key, my_size
                FROM dim_sku_size
                WHERE sku_id IN ({placeholders})
            """, missing_in_base).fetchall()
            for row in rows:
                base_stock.setdefault(
                    row["sku_id"],
                    {
                        "current_stock": 0,
                        "inbound_stock": 0,
                        "sku_key": row["sku_key"],
                        "my_size": row["my_size"],
                    },
                )

    simulated = builder.forward_simulate_stock(
        base_stock,
        base_date,
        snapshot_date.isoformat(),
        include_estimated_arrivals=include_estimated_arrivals,
    )

    negative_clamps = 0
    for info in simulated.values():
        raw = info.get("_base_stock", 0) - info.get("_sales_simulated", 0) + info.get("_arrivals_simulated", 0)
        if raw < 0:
            negative_clamps += 1

    if verbose:
        print(f"  Base snapshot date: {base_date}")
        if negative_clamps:
            print(f"  WARNING: {negative_clamps} SKUs clamped to 0 during simulation")

    with get_db(db_path) as conn:
        conn.execute("""
            DELETE FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(),))

        inserted = 0
        for sku_id, info in simulated.items():
            conn.execute("""
                INSERT INTO fact_inventory_snapshot_size
                (sku_id, sku_key, my_size, current_stock, inbound_stock, snapshot_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sku_id,
                info.get("sku_key"),
                info.get("my_size"),
                info.get("current_stock", 0),
                inbound_by_sku.get(sku_id, 0),
                snapshot_date.isoformat(),
            ))
            inserted += 1

    return {
        "rows_created": inserted,
        "base_snapshot_date": base_date,
        "negative_clamps": negative_clamps,
    }


def rebuild_snapshot(
    snapshot_date: date = None,
    store_code: str = "UNIVERSAL",
    verbose: bool = False,
    compare: bool = False,
    mode: str = "auto",
    include_estimated_arrivals: bool = True,
    db_path: Path = None,
    apply: bool = True,
) -> dict:
    """
    Rebuild snapshot from ledger.

    Args:
        snapshot_date: Date for snapshot (default: today)
        store_code: Store code (default: UNIVERSAL)
        verbose: Print detailed output
        compare: Compare with existing snapshot before overwriting
        db_path: Database path

    Returns:
        Dict with results
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    print(f"\n{'=' * 60}")
    print(f"Rebuild Inventory Snapshot")
    print(f"{'=' * 60}")
    print(f"Date:    {snapshot_date}")
    print(f"Store:   {store_code}")
    print(f"Apply:   {apply}")

    # Get event summary for auto/ledger mode
    event_summary = get_event_summary(as_of_date=snapshot_date, store_code=store_code, db_path=db_path)
    inbound_events = event_summary.get("INBOUND", {}).get("count", 0) if event_summary else 0

    print(f"\nLedger Events (as of {snapshot_date}):")
    total_events = 0
    for event_type, stats in sorted(event_summary.items()):
        print(f"  {event_type:12}: {stats['count']:4} events, {stats['qty_total']:+6} units")
        total_events += stats["count"]

    if mode not in {"ledger", "simulate", "auto"}:
        raise ValueError(f"Invalid mode: {mode}. Use ledger, simulate, or auto.")

    if total_events == 0 and mode in {"auto", "ledger"}:
        raise RuntimeError(
            "No ledger events found. Refusing to auto-simulate. "
            "Re-run with --mode simulate if intended."
        )
    if mode in {"auto", "ledger"}:
        balances = get_stock_balances_exclusive(
            snapshot_date=snapshot_date,
            store_code=store_code,
            db_path=db_path,
        )
        with get_db(db_path) as conn:
            accepted_negative_active_zero_skus = get_accepted_negative_active_zero_sku_ids(conn)
        blocking_negative_balances = {
            sku_id: balance
            for sku_id, balance in balances.items()
            if balance < 0 and sku_id not in accepted_negative_active_zero_skus
        }
        if blocking_negative_balances:
            report_path = write_negative_balance_report(
                snapshot_date,
                blocking_negative_balances,
                db_path,
            )
            msg = f"{len(blocking_negative_balances)} negative ledger balances detected."
            if report_path:
                msg += f" Report: {report_path}"
            raise RuntimeError(
                f"{msg} Refusing to auto-simulate. Re-run with --mode simulate if intended."
            )

    # Get existing snapshot for comparison
    old_snapshot = {}
    if compare:
        old_snapshot = get_existing_snapshot(snapshot_date, store_code, db_path)
        print(f"\nExisting snapshot: {len(old_snapshot)} SKUs")

    # Rebuild or plan snapshot
    print(f"\nRebuilding snapshot (mode={mode})...")
    planned_snapshot: dict[str, dict] = {}
    if not apply and mode != "ledger":
        raise RuntimeError("Dry-run snapshot planning currently supports --mode ledger only.")

    if mode == "simulate":
        sim_result = rebuild_snapshot_from_simulation(
            snapshot_date=snapshot_date,
            store_code=store_code,
            include_estimated_arrivals=include_estimated_arrivals,
            verbose=verbose,
            db_path=db_path,
        )
        rows_created = sim_result["rows_created"]
    elif apply:
        rows_created = rebuild_snapshot_from_ledger(
            snapshot_date=snapshot_date,
            store_code=store_code,
            db_path=db_path,
        )

        with get_db(db_path) as conn:
            negatives = conn.execute("""
                SELECT COUNT(*) as cnt
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date = ? AND current_stock < 0
            """, (snapshot_date.isoformat(),)).fetchone()["cnt"]
        if negatives:
            balances = get_stock_balances_exclusive(
                snapshot_date=snapshot_date,
                store_code=store_code,
                db_path=db_path,
            )
            report_path = write_negative_balance_report(snapshot_date, balances, db_path)
            msg = f"{negatives} negative balances after ledger rebuild."
            if report_path:
                msg += f" Report: {report_path}"
            raise RuntimeError(
                f"{msg} Refusing to auto-simulate. Re-run with --mode simulate if intended."
            )
    else:
        planned_snapshot = plan_snapshot_from_ledger(
            snapshot_date=snapshot_date,
            store_code=store_code,
            db_path=db_path,
        )
        rows_created = len(planned_snapshot)

    # Get new snapshot for summary
    if apply:
        with get_db(db_path) as conn:
            # Total current stock
            current_total = conn.execute("""
                SELECT COALESCE(SUM(current_stock), 0) as total
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date = ?
            """, (snapshot_date.isoformat(),)).fetchone()["total"]

            # Total inbound stock
            inbound_total = conn.execute("""
                SELECT COALESCE(SUM(inbound_stock), 0) as total
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date = ?
            """, (snapshot_date.isoformat(),)).fetchone()["total"]
    else:
        current_total = sum(row["current_stock"] for row in planned_snapshot.values())
        inbound_total = sum(row["inbound_stock"] for row in planned_snapshot.values())

    # Compare if requested
    if compare and old_snapshot:
        if apply:
            new_snapshot = get_existing_snapshot(snapshot_date, store_code, db_path)
        else:
            new_snapshot = {
                sku_id: (row["current_stock"], row["inbound_stock"])
                for sku_id, row in planned_snapshot.items()
            }
        diff = compare_snapshots(old_snapshot, new_snapshot)

        if diff["added"] or diff["removed"] or diff["changed"]:
            print(f"\nChanges detected:")
            if diff["added"]:
                print(f"  Added:   {len(diff['added'])} SKUs")
                if verbose:
                    for sku_id in diff["added"][:5]:
                        print(f"    - {sku_id}")
                    if len(diff["added"]) > 5:
                        print(f"    ... and {len(diff['added']) - 5} more")

            if diff["removed"]:
                print(f"  Removed: {len(diff['removed'])} SKUs")
                if verbose:
                    for sku_id in diff["removed"][:5]:
                        print(f"    - {sku_id}")

            if diff["changed"]:
                print(f"  Changed: {len(diff['changed'])} SKUs")
                if verbose:
                    for change in diff["changed"][:5]:
                        print(f"    - {change['sku_id']}: "
                              f"stock {change['old_stock']} → {change['new_stock']}, "
                              f"inbound {change['old_inbound']} → {change['new_inbound']}")
        else:
            print(f"\nNo changes detected (snapshot unchanged)")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"Snapshot rows created: {rows_created}")
    print(f"Total current stock:   {current_total}")
    print(f"Total inbound stock:   {inbound_total}")
    print(f"Total stock (current + inbound): {current_total + inbound_total}")

    return {
        "rows_created": rows_created,
        "current_stock_total": current_total,
        "inbound_stock_total": inbound_total,
        "apply_status": "APPLIED" if apply else "DRY_RUN",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild fact_inventory_snapshot_size from stock_ledger"
    )
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
        help="Snapshot date (default: today)",
    )
    parser.add_argument(
        "--store",
        default="UNIVERSAL",
        help="Store code (default: UNIVERSAL)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output",
    )
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Compare with existing snapshot before rebuilding",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "ledger", "simulate"],
        default="auto",
        help="Snapshot rebuild mode (default: auto)",
    )
    parser.add_argument(
        "--no-estimated-arrivals",
        action="store_true",
        help="When simulating, use only actual arrivals (ignore ETA)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to SQLite DB (default: db/app.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist snapshot rows. Omit for dry-run/compare-only.",
    )

    args = parser.parse_args()

    result = rebuild_snapshot(
        snapshot_date=args.date,
        store_code=args.store,
        verbose=args.verbose,
        compare=args.compare,
        mode=args.mode,
        include_estimated_arrivals=not args.no_estimated_arrivals,
        db_path=args.db,
        apply=bool(args.apply),
    )

    print("\nRebuild complete!" if args.apply else "\nDry run complete!")


if __name__ == "__main__":
    main()
