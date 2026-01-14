# PO Engine & Dashboard Finalization Plan (Jan 2026)

Date: 2026-01-14  
Context:
- PO dashboard generates a base PO and projected future POs.
- Real operations require lifecycle-backed POs (po_header/po_line) and ledger-backed stock.
- Constraint: PO-5 is NOT made yet; dashboard must not imply it is “made”.

## Success criteria (Definition of Done)
1) Real PO arrivals update stock:
   - Confirming arrival creates INBOUND ledger events and updates snapshot.
2) Dashboard cannot mislead:
   - “Plan POs” are clearly labeled as projections and are separate from “Real POs”.
3) Zero drift:
   - UI tables, JSON, and XLSX exports match exactly (size-level + sku-level totals).
4) Zero critical completeness gaps:
   - no_stock_snapshot == 0
   - no_demand_estimate == 0
   - day_complete_ok == true before generating a “real PO export”
5) Size normalization enforced:
   - No duplicate sizes (e.g., 3XL vs 3xl) for the same sku_key.

---

## Phase 12 — Reality Bridge: Plan → Real PO + arrivals
### P12.1 Separate Plan POs vs Real POs (UI + data contract)
- Rename PO-4..PO-10 in dashboard to PLAN-0..PLAN-6 (or “Projection +0..+6”).
- Add a “Real POs” section sourced from po_header/po_line lifecycle statuses.
- Add explicit disclaimer banner: “Plan POs are recommendations; only Real POs affect ledger.”

Acceptance:
- No screen shows PO-5 as “made” unless a po_header record exists.

### P12.2 Materialize Plan into Real PO draft
- Implement CLI: scripts/po_cli.py materialize-plan --plan PLAN-0 --name PO-5
- Creates po_header + po_lines with status DRAFT and a hash linking back to plan snapshot.

Acceptance:
- After materialize, Real PO appears in lifecycle list and can be sent/arrived.

### P12.3 Arrival workflow (Astana/Almaty)
- Ensure arrive command sets ARRIVED_AST / ARRIVED_ALM and writes inbound ledger events.
- Add optional bulk arrive from CSV manifest.

Acceptance:
- Marking PO arrived moves quantities from inbound to stock in next snapshot.

---

## Phase 13 — Prove Correctness: invariants + completeness gates
### P13.1 Invariant test suite (fast)
- Add script: scripts/validate_po_dashboard_invariants.py
  - Sum(size_level.order_qty) == sku_level.po_qty_total for apparel SKUs
  - No negative order_qty
  - No duplicate size codes per sku_key
  - D_size sums match D_sku within tolerance
- Make this run in CI.

### P13.2 Completeness gating
- Create “portfolio_active” scope list/table.
- Require stock snapshot + demand estimate for all portfolio_active SKUs.
- Fail dashboard generation (or force PROVISIONAL banner) if gaps exist.

### P13.3 Ledger health gating
- Snapshot rebuild must not auto-switch to simulation unless explicitly requested.
- Add diagnostics report listing negative ledger balances and their root events.

---

## Phase 14 — Reduce Manual Ops: sizing + workflow speed
### P14.1 Size canonicalization and synonyms
- Enforce canonical MY_SIZE set (uppercase).
- Add dim_size_synonyms and normalize on ingest and on SKU_ID parsing.

Acceptance:
- No “3xl” survives; all become “3XL”.

### P14.2 DB-first sizing (reduce CRM dependency)
- Persist inferred size decisions in DB and stop recomputing from CRM files.
- Make day_complete achievable without manual Excel steps.

### P14.3 Parallel-agent workflow doc + tooling
- Add .claude/PARALLEL_AGENTS.md with required git worktree workflow.
- Optional helper script: scripts/new_worktree.sh
