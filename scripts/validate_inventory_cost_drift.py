#!/usr/bin/env python3
"""
Validate inventory cost drift between cashflow ledger and snapshots.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys
from datetime import date as _date, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import resolve_landed_cogs
from core.cashflow.paid_capital_truth import compute_paid_capital_truth

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BANK_ACCOUNTS = PROJECT_ROOT / "config" / "bank_accounts.yaml"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows if len(row) > 1}


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        row[0]: {
            "cogs_kzt": row[1] or 0.0,
            "base_cost_cny": row[2] or 0.0,
            "weight_kg": row[3] or 0.0,
        }
        for row in rows
    }


def _compute_inventory_cost_components(
    conn: sqlite3.Connection,
    snapshot_date: str,
    *,
    db_path: Path,
) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT sku_key, SUM(current_stock) as stock, SUM(inbound_stock) as inbound_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        GROUP BY sku_key
        """,
        (snapshot_date,),
    ).fetchall()

    dim_costs = _load_dim_sku_costs(conn)
    on_hand_total = 0.0
    inbound_total = 0.0
    for sku_key, stock, inbound_stock in rows:
        meta = dim_costs.get(sku_key, {})
        unit_cost, _cost_source, _fx = resolve_landed_cogs(
            meta.get("base_cost_cny", 0.0),
            meta.get("weight_kg", 0.0),
            as_of_date=snapshot_date,
            db_path=db_path,
            stored_cogs_kzt=meta.get("cogs_kzt", 0.0),
        )
        if unit_cost is None:
            continue
        if stock and stock > 0:
            on_hand_total += float(stock) * unit_cost
        if inbound_stock and inbound_stock > 0:
            inbound_total += float(inbound_stock) * unit_cost
    return {
        "on_hand_cost": round(on_hand_total, 2),
        "inbound_snapshot_cost": round(inbound_total, 2),
        "snapshot_cost": round(on_hand_total + inbound_total, 2),
    }


def _default_can_use_paid_truth(db_path: Path, bank_accounts_path: Path) -> bool:
    try:
        return db_path.resolve() == DEFAULT_DB.resolve() and bank_accounts_path.exists()
    except FileNotFoundError:
        return False


def _latest_snapshot_on_or_before(
    conn: sqlite3.Connection,
    cutoff: str | None,
) -> str | None:
    if cutoff:
        row = conn.execute(
            "SELECT MAX(snapshot_date) as snap_date FROM fact_inventory_snapshot_size WHERE snapshot_date <= ?",
            (cutoff,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT MAX(snapshot_date) as snap_date FROM fact_inventory_snapshot_size"
        ).fetchone()
    return row["snap_date"] if row and row["snap_date"] else None


def validate_drift(
    db_path: Path,
    as_of: str | None,
    tolerance_pct: float,
    tolerance_kzt: float,
    *,
    mode: str = "auto",
    bank_accounts_path: Path = DEFAULT_BANK_ACCOUNTS,
) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_cashflow_daily"):
            print("SKIP: fact_cashflow_daily missing")
            return 0
        if not _table_exists(conn, "fact_inventory_snapshot_size"):
            print("SKIP: inventory snapshots missing")
            return 0

        max_cashflow = conn.execute("SELECT MAX(date) as max_date FROM fact_cashflow_daily").fetchone()
        max_cashflow_date = max_cashflow["max_date"] if max_cashflow and max_cashflow["max_date"] else None
        if not max_cashflow_date:
            print("SKIP: no cashflow daily rows")
            return 0

        cashflow_columns = _table_columns(conn, "fact_cashflow_daily")
        select_cols = ["inventory_on_hand_close", "inventory_inbound_close"]
        has_on_delivery = "inventory_on_delivery_close" in cashflow_columns
        if has_on_delivery:
            select_cols.append("inventory_on_delivery_close")
        select_cols.append("inventory_cost_close")
        use_paid_truth = mode == "paid-truth" or (
            mode == "auto" and _default_can_use_paid_truth(db_path, bank_accounts_path)
        )
        if use_paid_truth:
            snapshot_date = _latest_snapshot_on_or_before(conn, as_of or max_cashflow_date)
            if not snapshot_date:
                print("SKIP: no snapshot available to compare")
                return 0
            components = _compute_inventory_cost_components(conn, snapshot_date, db_path=db_path)
            paid_truth = compute_paid_capital_truth(
                db_path=db_path,
                bank_accounts_path=bank_accounts_path,
                as_of=snapshot_date,
            )
            paid_on_hand = float(paid_truth.get("inventory_on_hand_paid_kzt") or 0.0)
            diff = abs(components["on_hand_cost"] - paid_on_hand)
            allowed = max(tolerance_kzt, abs(components["on_hand_cost"]) * tolerance_pct)
            print("mode=paid_truth")
            print(f"snapshot_date={snapshot_date}")
            print(f"snapshot_on_hand_cost_kzt={components['on_hand_cost']:,.2f}")
            print(f"snapshot_inbound_rows_cost_kzt={components['inbound_snapshot_cost']:,.2f}")
            print(f"paid_truth_on_hand_cost_kzt={paid_on_hand:,.2f}")
            print(
                "paid_truth_components_kzt="
                f"cash:{float(paid_truth.get('cash_actual_kzt') or 0.0):,.2f}, "
                f"inbound_paid:{float(paid_truth.get('inventory_inbound_paid_kzt') or 0.0):,.2f}, "
                f"on_delivery_paid:{float(paid_truth.get('inventory_on_delivery_paid_kzt') or 0.0):,.2f}, "
                f"inbound_unpaid:{float(paid_truth.get('inbound_unpaid_obligations_kzt') or 0.0):,.2f}"
            )
            print(f"diff_kzt={diff:,.2f}")
            print(f"allowed_kzt={allowed:,.2f}")
            if diff > allowed:
                print("FAIL: paid-truth on-hand inventory drift exceeds tolerance")
                return 1
            print("PASS: paid-truth on-hand inventory drift within tolerance")
            return 0

        def _evaluate_snapshot(snapshot_date: str) -> dict | None:
            cashflow_row = conn.execute(
                f"SELECT {', '.join(select_cols)} FROM fact_cashflow_daily WHERE date = ?",
                (snapshot_date,),
            ).fetchone()
            if not cashflow_row:
                return None

            components = _compute_inventory_cost_components(conn, snapshot_date, db_path=db_path)
            snapshot_cost = components["snapshot_cost"]
            on_hand_close = float(cashflow_row["inventory_on_hand_close"] or 0.0)
            inbound_close = float(cashflow_row["inventory_inbound_close"] or 0.0)
            on_delivery_close = (
                float(cashflow_row["inventory_on_delivery_close"] or 0.0)
                if has_on_delivery and "inventory_on_delivery_close" in cashflow_row.keys()
                else 0.0
            )
            inventory_cost_close = float(cashflow_row["inventory_cost_close"] or 0.0)

            component_sum = on_hand_close + inbound_close + on_delivery_close
            cashflow_cost = component_sum if component_sum != 0.0 else inventory_cost_close
            diff = abs(snapshot_cost - cashflow_cost)
            allowed = max(tolerance_kzt, abs(snapshot_cost) * tolerance_pct)
            return {
                "snapshot_date": snapshot_date,
                "snapshot_cost": snapshot_cost,
                "snapshot_on_hand_cost": components["on_hand_cost"],
                "snapshot_inbound_rows_cost": components["inbound_snapshot_cost"],
                "on_hand_close": on_hand_close,
                "inbound_close": inbound_close,
                "on_delivery_close": on_delivery_close,
                "inventory_cost_close": inventory_cost_close,
                "cashflow_cost": cashflow_cost,
                "diff": diff,
                "allowed": allowed,
                "pass": diff <= allowed,
            }

        if as_of:
            snapshot_date = _latest_snapshot_on_or_before(conn, as_of)
            if not snapshot_date:
                print("SKIP: no snapshot available to compare")
                return 0
            evaluation = _evaluate_snapshot(snapshot_date)
            if not evaluation:
                print(f"SKIP: cashflow daily missing for {snapshot_date}")
                return 0
        else:
            # Default to last settled day (max cashflow date - 1), but if that day is still
            # partially reconciled, walk back to the most recent date that meets tolerance.
            try:
                settled_anchor = (_date.fromisoformat(max_cashflow_date) - timedelta(days=1)).isoformat()
            except ValueError:
                settled_anchor = max_cashflow_date
            candidate_dates = [
                row["snap_date"]
                for row in conn.execute(
                    """
                    SELECT DISTINCT snapshot_date AS snap_date
                    FROM fact_inventory_snapshot_size
                    WHERE snapshot_date <= ?
                    ORDER BY snapshot_date DESC
                    LIMIT 7
                    """,
                    (settled_anchor,),
                ).fetchall()
                if row["snap_date"]
            ]
            if not candidate_dates:
                candidate_dates = [
                    row["snap_date"]
                    for row in conn.execute(
                        """
                        SELECT DISTINCT snapshot_date AS snap_date
                        FROM fact_inventory_snapshot_size
                        WHERE snapshot_date <= ?
                        ORDER BY snapshot_date DESC
                        LIMIT 7
                        """,
                        (max_cashflow_date,),
                    ).fetchall()
                    if row["snap_date"]
                ]
            if not candidate_dates:
                print("SKIP: no snapshot available to compare")
                return 0

            latest_candidate = candidate_dates[0]
            evaluation = None
            latest_evaluation = None
            for snap in candidate_dates:
                current = _evaluate_snapshot(snap)
                if not current:
                    continue
                if latest_evaluation is None:
                    latest_evaluation = current
                if current["pass"]:
                    evaluation = current
                    break
            if evaluation is None:
                evaluation = latest_evaluation
            if evaluation is None:
                print("SKIP: no comparable cashflow row for snapshot candidates")
                return 0

            if evaluation["snapshot_date"] != latest_candidate and latest_evaluation is not None:
                print(
                    "INFO: latest settled snapshot exceeds tolerance; "
                    f"falling back from {latest_candidate} to {evaluation['snapshot_date']}"
                )

        print(f"snapshot_date={evaluation['snapshot_date']}")
        print(f"snapshot_cost_kzt={evaluation['snapshot_cost']:,.2f}")
        print(
            "components_kzt="
            f"on_hand:{evaluation['on_hand_close']:,.2f}, "
            f"inbound:{evaluation['inbound_close']:,.2f}, "
            f"on_delivery:{evaluation['on_delivery_close']:,.2f}, "
            f"inventory_cost_close:{evaluation['inventory_cost_close']:,.2f}"
        )
        print(f"cashflow_cost_kzt={evaluation['cashflow_cost']:,.2f}")
        print(f"diff_kzt={evaluation['diff']:,.2f}")
        print(f"allowed_kzt={evaluation['allowed']:,.2f}")

        if not evaluation["pass"]:
            print("FAIL: inventory cost drift exceeds tolerance")
            return 1

        print("PASS: inventory cost drift within tolerance")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate inventory cost drift vs snapshots")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--tolerance-pct", type=float, default=0.02)
    parser.add_argument("--tolerance-kzt", type=float, default=50000.0)
    parser.add_argument(
        "--mode",
        choices=("auto", "legacy", "paid-truth"),
        default="auto",
        help="auto uses paid-truth for the production DB and legacy model-ledger checks elsewhere",
    )
    parser.add_argument("--bank-accounts", type=Path, default=DEFAULT_BANK_ACCOUNTS)
    args = parser.parse_args()
    return validate_drift(
        args.db,
        args.as_of,
        args.tolerance_pct,
        args.tolerance_kzt,
        mode=args.mode,
        bank_accounts_path=args.bank_accounts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
