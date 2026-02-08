# Plan: Single-Truth System Reconciliation (2026-02-08)

## Objective
Make PO dashboard, inventory, cashflow, and order/sales outputs trace to one operational truth model with no silent fallbacks and no magic-number assumptions.

## Truth Sources (Locked)
- Cash anchor (today): `~/Docs/Autonomous_business/config/bank_accounts.yaml`
- Paid on-hand inventory: Astana warehouse stock (fully paid by instruction)
- Inbound part/payment truth: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/backup/7.2.26/Inbound_calendar_V10.002.xlsx`
- Payment flags source sheet: `PO_part_id_Totals`
- Inbound line truth sheet: `Inbounds_sheet`
- ARC pricing source sheet: `DIM_SKU_light_v5` (`AvgPrc`)

## Scope
- PO archive and lifecycle transparency at `po_part_id` grain
- Inbound reconciliation into `po_header`/`po_part`/`po_line`
- Paid-capital truth alignment in cashflow dashboard exports
- Cross-realm validator for workbook -> DB -> dashboard alignment

## Out of Scope
- Pricelist sync
- Unrelated worktree changes

## Phase 0: Governance and Safety
1. Add READCHECK + assumptions to `.claude/SESSION_LOG.md`.
2. Claim/update task in `.claude/TASKS.md`.
3. Update next gate in `.claude/PROGRESS.md`.
4. Create DB backup before any write step.

Verification:
- Backup file exists in `db/backups/`.

## Phase 1: Tests First (Fail-First)
1. `tests/test_sync_po_parts_from_inbound_calendar.py`
- paid flag normalization (`YES/NO/blank`)
- part totals and header aggregate backfill
- invalid summary row rejection
2. `tests/test_po_archive_part_transparency.py`
- archive ids from part rows
- lifecycle includes part rows with weight/bags
- old received part rows remain visible for transparency
3. `tests/test_validate_single_truth_alignment.py`
- part-grain REAL_ARCHIVE id is validated against `po_line` through `po_part`
4. `tests/test_real_archive_recompute.py`
- REAL_ARCHIVE includes ordered SKUs that are not in plan baseline template
5. `tests/test_cashflow_paid_capital_truth.py`
- paid inbound includes only paid components and excludes unpaid obligations

Verification:
- New tests fail before code changes and pass after changes.

## Phase 2: PO Part Sync and Payment Truth
1. Update `scripts/sync_po_parts_from_inbound_calendar.py`:
- robust `is_paid_BASE`/`is_paid_DLV` parsing
- upsert `po_part` payment/to-pay fields
- remove pseudo part ids (`TOTAL`, `PENDING`, etc.)
- remove legacy null-part `po_line` duplicates when part-tagged rows exist
- refresh `po_header` aggregate weight/bags/units from `po_part`

Verification:
- Dry-run produces deterministic counts.
- Apply updates `po_part` payment and aggregate columns without duplicate inserts.

## Phase 3: PO Dashboard Part Transparency
1. Update `scripts/generate_po_dashboard_data.py`:
- resolve archives dynamically from valid `po_part_id` values
- load lifecycle rows at part grain, including older received parts
- build REAL_ARCHIVE from part payload, preserving part weights/bags
- include ordered SKUs that are not present in PLAN baseline template
2. Regenerate:
- `exports/po_dashboard_data.json`
- `exports/po_dashboard.html`

Verification:
- `archived_pos` contains part ids (`PO-5.1`, `PO-5.2`, `PO-6.0`, `ARC-1.0`, etc.).
- `real_pos` contains part rows with weight and bags.
- REAL_ARCHIVE summaries reflect actual part units.

## Phase 4: Cashflow Paid-Capital Alignment
1. Add `core/cashflow/paid_capital_truth.py`:
- compute paid capital from bank cash + paid on-hand + paid inbound + paid on-delivery
- report unpaid inbound obligations separately
2. Update `scripts/update_cashflow_dashboard.py`:
- include `paid_capital_truth` in dashboard metadata/cards
- keep event/daily ledger logic deterministic

Verification:
- cashflow dashboard exports include paid-capital component breakdown.

## Phase 5: Cross-Realm Validator
1. Add `scripts/validate_single_truth_system.py`:
- workbook part ids/flags vs DB `po_part`
- dashboard archived/lifecycle part ids vs DB
- lifecycle weight/bags parity with `po_part`
2. Wire into strict path (`scripts/validate_params.py --strict`).

Verification:
- strict validation fails on workbook/DB/dashboard drift and passes after sync/regeneration.

## Phase 6: Documentation and Contracts
1. Update `docs/validation/DASHBOARD_CONTRACT.md`:
- archive/lifecycle part-grain rules
- required REAL_ARCHIVE fields/invariants
2. Update `docs/inventory/Sales_Data_Model_V16.md`:
- `po_part` payment columns and `po_line.po_part_id` role
3. Update `docs/inventory/INBOUND_CALENDAR_V10_002_PO_PART_TRANSITION_2026-02-07.md`:
- v2 payment-truth and workbook path updates
4. Update `docs/ARCHITECTURE.md` and `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`:
- paid-capital and single-truth cross-realm path.

Verification:
- `scripts/lint_docs.sh` passes.

## Phase 7: Operational Reconciliation Run
1. Migration check:
- `python3 scripts/migrate_023_po_parts_schema.py`
2. Workbook sync:
- dry-run then apply with `ENABLE_PO_PART_SYNC_WRITE=1`
3. Dashboard regeneration:
- `python3 scripts/generate_po_dashboard_data.py`
- `python3 scripts/generate_po_dashboard_html.py`
- `python3 scripts/update_cashflow_dashboard.py`

Verification:
- part payment and aggregate values match workbook updates.

## Phase 8: Full Gate Chain
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_po_dashboard_invariants.py`
5. `python3 scripts/validate_single_truth_alignment.py`
6. `python3 scripts/validate_single_truth_system.py`
7. `python3 scripts/validate_cashflow_invariants.py`
8. `python3 scripts/validate_inventory_cost_drift.py`
9. `scripts/lint_docs.sh`
10. `scripts/check_no_db_tracked.sh`
11. DB backup + `ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose`

Done Criteria:
- All gates above are green.
- `po_part_id`-grain archive/lifecycle truth is visible in dashboard data.
- paid-capital cashflow view is anchored to bank cash and paid inventory truth.
- evidence captured in `.claude/SESSION_LOG.md`.
