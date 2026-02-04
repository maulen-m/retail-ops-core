#!/usr/bin/env python3
"""
TASK-182: PO CLI (Phase 10)
TASK-185: Stock Adjustment CLI (Phase 10)

Command-line interface for Purchase Order and Stock management.

PO Commands:
  create    - Create new PO
  add-line  - Add line item to PO
  update    - Update PO fields (dates, FX rates, etc.)
  arrive    - Confirm PO arrival (ALM or AST)
  arrive-csv - Bulk confirm arrivals from CSV manifest
  receive   - Receive inventory (creates INBOUND events)
  cargo     - Enter cargo costs (weight + USD rate)
  show      - View PO details
  list      - List all POs
  materialize-plan - Create a real PO draft from a dashboard plan

Stock Commands:
  adjust    - Create stock adjustment (ADJUSTMENT event)
  stock     - View current stock balance
  ledger    - View ledger events for a SKU

Usage:
  python scripts/po_cli.py create --supplier SUPP_A
  python scripts/po_cli.py add-line PO-2025-001 --sku LINE52 --size XL --qty 50 --cost 47
  python scripts/po_cli.py update PO-2025-001 --ship-cargo 2025-12-17
  python scripts/po_cli.py arrive PO-2025-001 --type AST --date 2025-12-30
  python scripts/po_cli.py arrive-csv --csv arrivals.csv --type AST --date 2026-01-14
  python scripts/po_cli.py receive PO-2025-001
  python scripts/po_cli.py show PO-2025-001
  python scripts/po_cli.py list --status IN_TRANSIT
  PO_WRITE_ENABLED=true python scripts/po_cli.py materialize-plan --plan PLAN-0 --name PO-5 --supplier SUPP_A --apply
  python scripts/po_cli.py adjust LINE52_XL --qty 5 --reason "Found in warehouse"
  python scripts/po_cli.py adjust LINE52_XL --qty -3 --reason "Damaged items write-off"
  python scripts/po_cli.py stock LINE52_XL
  python scripts/po_cli.py stock --sku-key LINE52
  python scripts/po_cli.py ledger LINE52_XL --limit 20
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, DEFAULT_DB_PATH
from core.po.lifecycle import (
    create_po,
    add_po_line,
    get_po,
    get_po_lines,
    update_po_field,
    update_po_status,
    confirm_po_arrival,
    close_po,
    receive_po_line,
    PO_STATUS_FLOW,
)
from core.po.eta import update_po_eta, calc_eta
from core.calc.landed_cost import calc_supplier_costs, calc_cargo_costs, calc_landed_costs
from core.po.materialize import materialize_plan_po
from core.db.ledger import (
    add_ledger_event,
    get_stock_balance,
    get_stock_balances_all,
    get_ledger_events,
    count_ledger_events,
    get_event_summary,
    log_audit,
    VALID_EVENT_TYPES,
)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


def cmd_create(args):
    """Create a new PO."""
    message_date = None
    if args.message_date:
        message_date = datetime.strptime(args.message_date, "%Y-%m-%d").date()

    po_id = create_po(
        supplier_code=args.supplier,
        po_id=args.po_id,
        order_date=message_date,
        notes=args.notes,
        created_by=args.user or "cli",
        db_path=DEFAULT_DB_PATH,
    )

    print(f"Created PO: {po_id}")

    # Update ETA if message_date was provided
    if message_date and args.weight:
        # Store weight first
        update_po_field(po_id, "weight_nom_kg", args.weight, db_path=DEFAULT_DB_PATH)
        alm, ast = update_po_eta(po_id, db_path=DEFAULT_DB_PATH)
        if ast:
            print(f"  ETA: ALM {alm}, AST {ast}")


def cmd_materialize_plan(args):
    """Materialize a plan from dashboard JSON into a real PO draft."""
    dashboard_path = Path(args.dashboard) if args.dashboard else DEFAULT_DASHBOARD_PATH
    try:
        result = materialize_plan_po(
            dashboard_path=dashboard_path,
            plan_name=args.plan,
            po_id=args.name,
            supplier=args.supplier,
            notes=args.notes,
            user=args.user or "cli",
            db_path=DEFAULT_DB_PATH,
            apply=args.apply,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(2)

    status = result.get("status")
    if status == "DRY_RUN":
        print(f"DRY RUN: would materialize {args.plan} → {args.name}")
        print(f"  PLAN_HASH: {result.get('plan_hash')}")
        return
    if status == "IDEMPOTENT":
        print(f"OK: {args.name} already materialized (PLAN_HASH match).")
        return

    print(f"Materialized plan {args.plan} → {args.name}")
    print(
        f"  Units: {result.get('units_total', 0)}, "
        f"Weight: {result.get('weight_nom_kg', 0.0):.2f} kg, "
        f"Cost: ¥{result.get('total_cost_cny', 0.0):.0f}"
    )


def cmd_arrive_csv(args):
    """Bulk confirm PO arrivals from CSV manifest."""
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(2)

    processed = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            po_id = (row.get("po_id") or row.get("po") or "").strip()
            if not po_id:
                continue
            arrival_type = (row.get("arrival_type") or row.get("type") or args.type or "").strip().upper()
            if arrival_type not in {"ALM", "AST"}:
                print(f"Invalid arrival type for {po_id}: {arrival_type}")
                sys.exit(2)

            arrival_date_str = (row.get("arrival_date") or row.get("date") or args.date or "").strip()
            arrival_date = date.today()
            if arrival_date_str:
                arrival_date = datetime.strptime(arrival_date_str, "%Y-%m-%d").date()

            partial_str = (row.get("partial") or row.get("partial_qty") or "").strip()
            received_qty = None
            if partial_str:
                received_qty = {}
                for item in partial_str.split(","):
                    sku, qty = item.split(":")
                    received_qty[sku] = int(qty)

            confirm_po_arrival(
                po_id=po_id,
                arrival_type=arrival_type,
                arrival_date=arrival_date,
                received_qty_by_sku=received_qty,
                create_ledger_events=not args.no_ledger,
                db_path=DEFAULT_DB_PATH,
            )
            processed += 1
            print(f"Arrived {po_id} ({arrival_type}) on {arrival_date.isoformat()}")

    print(f"Processed {processed} arrivals")


def cmd_add_line(args):
    """Add a line item to a PO."""
    # Build sku_id from sku and size
    if args.size:
        sku_id = f"{args.sku}_{args.size}"
    else:
        sku_id = args.sku

    line_id = add_po_line(
        po_id=args.po_id,
        sku_id=sku_id,
        order_qty=args.qty,
        unit_cost_cny=args.cost,
        db_path=DEFAULT_DB_PATH,
    )

    print(f"Added line {line_id} to {args.po_id}: {sku_id} x{args.qty} @ {args.cost} CNY")


def cmd_update(args):
    """Update PO fields."""
    updated = []

    # Date fields
    date_mappings = [
        ("message_date", args.message_date),
        ("ship_date_seller", args.ship_seller),
        ("ship_date_cargo", args.ship_cargo),
        ("alm_arrival_real", args.alm_date),
        ("ast_arrival_real", args.ast_date),
    ]

    for field, value in date_mappings:
        if value:
            parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
            update_po_field(args.po_id, field, parsed_date, db_path=DEFAULT_DB_PATH)
            updated.append(f"{field}={value}")

    # Numeric fields
    if args.fx_cny is not None:
        update_po_field(args.po_id, "fx_rate_cny_actual", args.fx_cny, db_path=DEFAULT_DB_PATH)
        updated.append(f"fx_rate_cny_actual={args.fx_cny}")

    if args.fx_usd is not None:
        update_po_field(args.po_id, "fx_rate_usd_kzt", args.fx_usd, db_path=DEFAULT_DB_PATH)
        updated.append(f"fx_rate_usd_kzt={args.fx_usd}")

    if args.weight is not None:
        update_po_field(args.po_id, "weight_nom_kg", args.weight, db_path=DEFAULT_DB_PATH)
        updated.append(f"weight_nom_kg={args.weight}")

    if args.weight_real is not None:
        update_po_field(args.po_id, "weight_real_kg", args.weight_real, db_path=DEFAULT_DB_PATH)
        updated.append(f"weight_real_kg={args.weight_real}")

    # Status update
    if args.status:
        update_po_status(args.po_id, args.status, db_path=DEFAULT_DB_PATH)
        updated.append(f"status={args.status}")

    # Notes
    if args.notes:
        update_po_field(args.po_id, "notes", args.notes, db_path=DEFAULT_DB_PATH)
        updated.append(f"notes={args.notes[:20]}...")

    # Recalc ETA if any date was updated
    if any([args.message_date, args.ship_seller, args.ship_cargo]):
        delay = args.delay_days or 0
        alm, ast = update_po_eta(args.po_id, delay_days=delay, db_path=DEFAULT_DB_PATH)
        if ast:
            updated.append(f"ETA AST={ast}")

    if updated:
        print(f"Updated {args.po_id}: {', '.join(updated)}")
    else:
        print("No fields updated. Use --help to see available options.")


def cmd_arrive(args):
    """Confirm PO arrival."""
    arrival_date = None
    if args.date:
        arrival_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        arrival_date = date.today()

    # Parse partial quantities if provided
    received_qty = None
    if args.partial:
        received_qty = {}
        for item in args.partial.split(","):
            sku, qty = item.split(":")
            received_qty[sku] = int(qty)

    result = confirm_po_arrival(
        po_id=args.po_id,
        arrival_type=args.type.upper(),
        arrival_date=arrival_date,
        received_qty_by_sku=received_qty,
        create_ledger_events=not args.no_ledger,
        db_path=DEFAULT_DB_PATH,
    )

    print(f"Arrival confirmed for {args.po_id} at {args.type.upper()}")
    print(f"  Lines updated: {result['lines_updated']}")
    print(f"  Units received: {result['units_received']}")
    print(f"  Ledger events: {result['ledger_events']}")


def cmd_receive(args):
    """Receive PO (shortcut for AST arrival + ledger events)."""
    arrival_date = None
    if args.date:
        arrival_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        arrival_date = date.today()

    # Parse partial quantities if provided
    received_qty = None
    if args.partial:
        received_qty = {}
        for item in args.partial.split(","):
            sku, qty = item.split(":")
            received_qty[sku] = int(qty)

    # Confirm AST arrival
    result = confirm_po_arrival(
        po_id=args.po_id,
        arrival_type="AST",
        arrival_date=arrival_date,
        received_qty_by_sku=received_qty,
        create_ledger_events=True,
        db_path=DEFAULT_DB_PATH,
    )

    # Update status to RECEIVED
    update_po_status(args.po_id, "RECEIVED", db_path=DEFAULT_DB_PATH)

    print(f"Received {args.po_id}")
    print(f"  Lines: {result['lines_updated']}")
    print(f"  Units: {result['units_received']}")
    print(f"  Ledger events created: {result['ledger_events']}")


def cmd_cargo(args):
    """Enter cargo costs."""
    # Update weight and FX rate
    if args.weight:
        update_po_field(args.po_id, "weight_real_kg", args.weight, db_path=DEFAULT_DB_PATH)
        print(f"  weight_real_kg = {args.weight}")

    if args.usd_rate:
        update_po_field(args.po_id, "fx_rate_usd_kzt", args.usd_rate, db_path=DEFAULT_DB_PATH)
        print(f"  fx_rate_usd_kzt = {args.usd_rate}")

    # Calculate cargo costs
    try:
        result = calc_cargo_costs(args.po_id, db_path=DEFAULT_DB_PATH)
        print(f"Cargo costs for {args.po_id}:")
        print(f"  Weight: {result['weight_kg']} kg")
        print(f"  USD: {result['cargo_cost_usd']:.2f}")
        print(f"  KZT: {result['cargo_cost_kzt']:,.0f}")

        # Try to calculate landed costs if supplier costs exist
        try:
            landed = calc_landed_costs(args.po_id, db_path=DEFAULT_DB_PATH)
            print(f"  Total landed: {landed['total_landed_kzt']:,.0f} KZT")
        except ValueError:
            print("  (Run 'update --fx-cny' to set supplier FX rate first)")

    except ValueError as e:
        print(f"Error: {e}")


def cmd_show(args):
    """Show PO details."""
    po = get_po(args.po_id, db_path=DEFAULT_DB_PATH)
    if not po:
        print(f"PO not found: {args.po_id}")
        return

    lines = get_po_lines(args.po_id, db_path=DEFAULT_DB_PATH)

    print(f"\n=== {args.po_id} ===")
    print(f"Supplier: {po['supplier_code']}")
    print(f"Status: {po['status']}")

    if po.get("message_date"):
        print(f"Message date: {po['message_date']}")
    if po.get("ship_date_seller"):
        print(f"Ship (seller): {po['ship_date_seller']}")
    if po.get("ship_date_cargo"):
        print(f"Ship (cargo): {po['ship_date_cargo']}")
    if po.get("alm_arrival_nom"):
        print(f"ETA ALM: {po['alm_arrival_nom']}")
    if po.get("ast_arrival_nom"):
        print(f"ETA AST: {po['ast_arrival_nom']}")
    if po.get("alm_arrival_real"):
        print(f"Arrived ALM: {po['alm_arrival_real']}")
    if po.get("ast_arrival_real"):
        print(f"Arrived AST: {po['ast_arrival_real']}")

    # FX rates
    if po.get("fx_rate_cny_actual"):
        print(f"FX CNY: {po['fx_rate_cny_actual']}")
    if po.get("fx_rate_usd_kzt"):
        print(f"FX USD: {po['fx_rate_usd_kzt']}")

    # Weights
    if po.get("weight_nom_kg"):
        print(f"Weight (nominal): {po['weight_nom_kg']} kg")
    if po.get("weight_real_kg"):
        print(f"Weight (real): {po['weight_real_kg']} kg")

    # Costs
    if po.get("total_cost_kzt_supplier"):
        print(f"Supplier cost: {po['total_cost_kzt_supplier']:,.0f} KZT")
    if po.get("cargo_cost_kzt"):
        print(f"Cargo cost: {po['cargo_cost_kzt']:,.0f} KZT")
    if po.get("total_landed_cost_kzt"):
        print(f"Total landed: {po['total_landed_cost_kzt']:,.0f} KZT")

    if po.get("notes"):
        print(f"Notes: {po['notes']}")

    # Lines
    if lines:
        print(f"\nLines ({len(lines)}):")
        total_qty = 0
        total_received = 0
        for line in lines:
            qty = line['order_qty']
            rcvd = line['received_qty']
            total_qty += qty
            total_received += rcvd
            status = "OK" if rcvd >= qty else f"{rcvd}/{qty}"
            cost_info = ""
            if line.get('landed_cost_unit_kzt'):
                cost_info = f" @ {line['landed_cost_unit_kzt']:,.0f} KZT"
            print(f"  {line['sku_id']}: x{qty} [{status}]{cost_info}")

        print(f"\nTotal: {total_qty} ordered, {total_received} received")


def cmd_list(args):
    """List POs."""
    with get_db(DEFAULT_DB_PATH) as conn:
        query = """
            SELECT po_id, supplier_code, status, message_date, ast_arrival_nom,
                   (SELECT SUM(order_qty) FROM po_line WHERE po_line.po_id = po_header.po_id) as total_qty
            FROM po_header
        """
        params = []

        if args.status:
            query += " WHERE status = ?"
            params.append(args.status)

        query += " ORDER BY created_at DESC"

        if args.limit:
            query += f" LIMIT {args.limit}"

        rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No POs found.")
        return

    print(f"\n{'PO ID':<15} {'Supplier':<10} {'Status':<15} {'Msg Date':<12} {'ETA AST':<12} {'Qty':>6}")
    print("-" * 75)

    for row in rows:
        po_id = row['po_id'] or '-'
        supplier = row['supplier_code'] or '-'
        status = row['status'] or '-'
        msg_dt = row['message_date'][:10] if row['message_date'] else '-'
        eta = row['ast_arrival_nom'][:10] if row['ast_arrival_nom'] else '-'
        qty = row['total_qty'] or 0

        print(f"{po_id:<15} {supplier:<10} {status:<15} {msg_dt:<12} {eta:<12} {qty:>6}")

    print(f"\nTotal: {len(rows)} POs")


def cmd_close(args):
    """Close a PO."""
    try:
        close_po(args.po_id, db_path=DEFAULT_DB_PATH)
        print(f"PO {args.po_id} closed.")
    except ValueError as e:
        print(f"Error: {e}")


# ==============================================================================
# TASK-185: Stock Adjustment Commands
# ==============================================================================

def cmd_adjust(args):
    """Create a stock adjustment."""
    sku_id = args.sku_id
    qty = args.qty
    reason = args.reason or ""
    event_date = date.today()
    if args.date:
        event_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    # Determine event type based on quantity
    if qty < 0:
        event_type = "WRITE_OFF" if args.write_off else "ADJUSTMENT"
    else:
        event_type = "ADJUSTMENT"

    # Get current balance first
    old_balance = get_stock_balance(sku_id, db_path=DEFAULT_DB_PATH)

    # Create ledger event
    ledger_id = add_ledger_event(
        event_type=event_type,
        sku_id=sku_id,
        qty_change=qty,
        event_date=event_date,
        store_code=args.store or "UNIVERSAL",
        notes=reason,
        input_source="MANUAL",
        created_by=args.user or "cli",
        db_path=DEFAULT_DB_PATH,
    )

    # Get new balance
    new_balance = get_stock_balance(sku_id, db_path=DEFAULT_DB_PATH)

    # Log to audit
    log_audit(
        table_name="stock_ledger",
        record_id=str(ledger_id),
        field_name="qty_change",
        old_value=str(old_balance),
        new_value=str(new_balance),
        change_type="INSERT",
        reason=reason,
        source=args.user or "cli",
        db_path=DEFAULT_DB_PATH,
    )

    sign = "+" if qty > 0 else ""
    print(f"Stock adjustment for {sku_id}:")
    print(f"  Event type: {event_type}")
    print(f"  Change: {sign}{qty}")
    print(f"  Balance: {old_balance} → {new_balance}")
    print(f"  Ledger ID: {ledger_id}")
    if reason:
        print(f"  Reason: {reason}")


def cmd_stock(args):
    """View stock balance."""
    if args.sku_id:
        # Single SKU
        balance = get_stock_balance(
            args.sku_id,
            store_code=args.store or "UNIVERSAL",
            db_path=DEFAULT_DB_PATH,
        )
        print(f"\n{args.sku_id}: {balance} units")

        # Show recent events if verbose
        if args.verbose:
            events = get_ledger_events(
                sku_id=args.sku_id,
                store_code=args.store,
                limit=5,
                db_path=DEFAULT_DB_PATH,
            )
            if events:
                print("\nRecent events:")
                for e in events:
                    sign = "+" if e['qty_change'] > 0 else ""
                    print(f"  {e['event_date']} {e['event_type']}: {sign}{e['qty_change']}")

    elif args.sku_key:
        # All sizes for a SKU key
        with get_db(DEFAULT_DB_PATH) as conn:
            rows = conn.execute("""
                SELECT sku_id, SUM(qty_change) as balance
                FROM stock_ledger
                WHERE sku_key = ? AND store_code = ?
                GROUP BY sku_id
                ORDER BY sku_id
            """, (args.sku_key, args.store or "UNIVERSAL")).fetchall()

        if not rows:
            print(f"No stock found for {args.sku_key}")
            return

        print(f"\nStock for {args.sku_key}:")
        total = 0
        for row in rows:
            print(f"  {row['sku_id']}: {row['balance']}")
            total += row['balance']
        print(f"\nTotal: {total} units")

    else:
        # Summary
        summary = get_event_summary(
            store_code=args.store or "UNIVERSAL",
            db_path=DEFAULT_DB_PATH,
        )

        print("\nStock Summary by Event Type:")
        print("-" * 40)
        total_events = 0
        for event_type in ["INITIAL", "INBOUND", "SALE", "RETURN", "ADJUSTMENT", "WRITE_OFF"]:
            if event_type in summary:
                data = summary[event_type]
                sign = "+" if data['qty_total'] >= 0 else ""
                print(f"  {event_type:<12}: {data['count']:>5} events, {sign}{data['qty_total']:>8} units")
                total_events += data['count']

        print("-" * 40)
        print(f"  {'Total events:':<12} {total_events:>5}")

        # Show total balance
        balances = get_stock_balances_all(
            store_code=args.store or "UNIVERSAL",
            db_path=DEFAULT_DB_PATH,
        )
        total_balance = sum(balances.values())
        print(f"  {'Total stock:':<12} {'':<5} {'+' if total_balance >= 0 else ''}{total_balance:>8} units")


def cmd_ledger(args):
    """View ledger events for a SKU."""
    events = get_ledger_events(
        sku_id=args.sku_id if args.sku_id else None,
        sku_key=args.sku_key if args.sku_key else None,
        event_type=args.type,
        store_code=args.store,
        limit=args.limit,
        db_path=DEFAULT_DB_PATH,
    )

    if not events:
        print("No events found.")
        return

    print(f"\n{'Date':<12} {'Type':<12} {'SKU':<25} {'Change':>8} {'Balance':>8} {'Ref':<15}")
    print("-" * 90)

    for e in events:
        evt_date = e['event_date'][:10] if e['event_date'] else '-'
        evt_type = e['event_type']
        sku = e['sku_id'][:25] if e['sku_id'] else '-'
        change = e['qty_change']
        sign = "+" if change > 0 else ""
        balance = e['running_balance'] or '-'
        ref = (e['reference_id'] or '-')[:15]

        print(f"{evt_date:<12} {evt_type:<12} {sku:<25} {sign}{change:>7} {balance:>8} {ref:<15}")

    print(f"\nTotal: {len(events)} events")


def main():
    parser = argparse.ArgumentParser(
        description="PO CLI - Purchase Order Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create
    p_create = subparsers.add_parser("create", help="Create new PO")
    p_create.add_argument("--supplier", required=True, help="Supplier code")
    p_create.add_argument("--po-id", help="Custom PO ID (auto-generated if not provided)")
    p_create.add_argument("--message-date", help="Message date (YYYY-MM-DD)")
    p_create.add_argument("--weight", type=float, help="Estimated weight in kg")
    p_create.add_argument("--notes", help="Notes")
    p_create.add_argument("--user", help="User creating the PO")

    # add-line
    p_add = subparsers.add_parser("add-line", help="Add line to PO")
    p_add.add_argument("po_id", help="PO ID")
    p_add.add_argument("--sku", required=True, help="SKU key")
    p_add.add_argument("--size", help="Size (S, M, L, XL, etc.)")
    p_add.add_argument("--qty", type=int, required=True, help="Quantity")
    p_add.add_argument("--cost", type=float, required=True, help="Unit cost in CNY")

    # update
    p_update = subparsers.add_parser("update", help="Update PO fields")
    p_update.add_argument("po_id", help="PO ID")
    p_update.add_argument("--message-date", help="Message date (YYYY-MM-DD)")
    p_update.add_argument("--ship-seller", help="Ship date from seller (YYYY-MM-DD)")
    p_update.add_argument("--ship-cargo", help="Ship date from cargo (YYYY-MM-DD)")
    p_update.add_argument("--alm-date", help="Almaty arrival date (YYYY-MM-DD)")
    p_update.add_argument("--ast-date", help="Astana arrival date (YYYY-MM-DD)")
    p_update.add_argument("--fx-cny", type=float, help="FX rate CNY/KZT")
    p_update.add_argument("--fx-usd", type=float, help="FX rate USD/KZT")
    p_update.add_argument("--weight", type=float, help="Estimated weight in kg")
    p_update.add_argument("--weight-real", type=float, help="Actual weight in kg")
    p_update.add_argument("--delay-days", type=int, help="Additional delay days for ETA")
    p_update.add_argument("--status", choices=PO_STATUS_FLOW, help="Update status")
    p_update.add_argument("--notes", help="Notes")

    # arrive
    p_arrive = subparsers.add_parser("arrive", help="Confirm PO arrival")
    p_arrive.add_argument("po_id", help="PO ID")
    p_arrive.add_argument("--type", required=True, choices=["ALM", "AST", "alm", "ast"],
                          help="Arrival type")
    p_arrive.add_argument("--date", help="Arrival date (YYYY-MM-DD, default: today)")
    p_arrive.add_argument("--partial", help="Partial quantities (SKU:QTY,SKU:QTY)")
    p_arrive.add_argument("--no-ledger", action="store_true",
                          help="Don't create ledger events")

    # receive
    p_receive = subparsers.add_parser("receive", help="Receive inventory")
    p_receive.add_argument("po_id", help="PO ID")
    p_receive.add_argument("--date", help="Receive date (YYYY-MM-DD, default: today)")
    p_receive.add_argument("--partial", help="Partial quantities (SKU:QTY,SKU:QTY)")

    # cargo
    p_cargo = subparsers.add_parser("cargo", help="Enter cargo costs")
    p_cargo.add_argument("po_id", help="PO ID")
    p_cargo.add_argument("--weight", type=float, help="Actual weight in kg")
    p_cargo.add_argument("--usd-rate", type=float, help="USD/KZT exchange rate")

    # show
    p_show = subparsers.add_parser("show", help="Show PO details")
    p_show.add_argument("po_id", help="PO ID")

    # list
    p_list = subparsers.add_parser("list", help="List POs")
    p_list.add_argument("--status", choices=PO_STATUS_FLOW, help="Filter by status")
    p_list.add_argument("--limit", type=int, default=20, help="Max results")

    # close
    p_close = subparsers.add_parser("close", help="Close a PO")
    p_close.add_argument("po_id", help="PO ID")

    # materialize-plan
    p_materialize = subparsers.add_parser("materialize-plan", help="Create a real PO draft from a plan")
    p_materialize.add_argument("--plan", required=True, help="Plan name (e.g., PLAN-0)")
    p_materialize.add_argument("--name", required=True, help="New PO ID (e.g., PO-5)")
    p_materialize.add_argument("--supplier", default="SUPP_A", help="Supplier code")
    p_materialize.add_argument("--dashboard", help="Path to po_dashboard_data.json")
    p_materialize.add_argument("--notes", help="Extra notes to append")
    p_materialize.add_argument("--user", help="User creating the PO")
    p_materialize.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes (requires PO_WRITE_ENABLED=true)",
    )

    # arrive-csv
    p_arrive_csv = subparsers.add_parser("arrive-csv", help="Bulk confirm PO arrivals from CSV")
    p_arrive_csv.add_argument("--csv", required=True, help="CSV manifest path")
    p_arrive_csv.add_argument("--type", choices=["ALM", "AST", "alm", "ast"], help="Default arrival type")
    p_arrive_csv.add_argument("--date", help="Default arrival date (YYYY-MM-DD)")
    p_arrive_csv.add_argument("--no-ledger", action="store_true", help="Don't create ledger events")

    # ==============================================================================
    # Stock Commands (TASK-185)
    # ==============================================================================

    # adjust
    p_adjust = subparsers.add_parser("adjust", help="Create stock adjustment")
    p_adjust.add_argument("sku_id", help="SKU ID (e.g., LINE52_XL)")
    p_adjust.add_argument("--qty", type=int, required=True, help="Quantity change (+/-)")
    p_adjust.add_argument("--reason", help="Reason for adjustment")
    p_adjust.add_argument("--date", help="Adjustment date (YYYY-MM-DD, default: today)")
    p_adjust.add_argument("--store", help="Store code (default: UNIVERSAL)")
    p_adjust.add_argument("--write-off", action="store_true",
                          help="Mark as WRITE_OFF instead of ADJUSTMENT")
    p_adjust.add_argument("--user", help="User making adjustment")

    # stock
    p_stock = subparsers.add_parser("stock", help="View stock balance")
    p_stock.add_argument("sku_id", nargs="?", help="SKU ID (e.g., LINE52_XL)")
    p_stock.add_argument("--sku-key", help="View all sizes for a SKU key")
    p_stock.add_argument("--store", help="Store code (default: UNIVERSAL)")
    p_stock.add_argument("-v", "--verbose", action="store_true",
                         help="Show recent events")

    # ledger
    p_ledger = subparsers.add_parser("ledger", help="View ledger events")
    p_ledger.add_argument("sku_id", nargs="?", help="SKU ID")
    p_ledger.add_argument("--sku-key", help="Filter by SKU key")
    p_ledger.add_argument("--type", choices=list(VALID_EVENT_TYPES), help="Filter by event type")
    p_ledger.add_argument("--store", help="Store code")
    p_ledger.add_argument("--limit", type=int, default=20, help="Max results")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Route to command handler
    if args.command == "create":
        cmd_create(args)
    elif args.command == "add-line":
        cmd_add_line(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "arrive":
        cmd_arrive(args)
    elif args.command == "receive":
        cmd_receive(args)
    elif args.command == "cargo":
        cmd_cargo(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "close":
        cmd_close(args)
    elif args.command == "materialize-plan":
        cmd_materialize_plan(args)
    elif args.command == "arrive-csv":
        cmd_arrive_csv(args)
    # Stock commands (TASK-185)
    elif args.command == "adjust":
        cmd_adjust(args)
    elif args.command == "stock":
        cmd_stock(args)
    elif args.command == "ledger":
        cmd_ledger(args)


if __name__ == "__main__":
    main()
