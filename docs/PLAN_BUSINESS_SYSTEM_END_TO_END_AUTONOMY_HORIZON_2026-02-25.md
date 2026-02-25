# PLAN_BUSINESS_SYSTEM_END_TO_END_AUTONOMY_HORIZON_2026-02-25

## Purpose
Build a single, reliable operating system for PO + inventory + cashflow + API + shipment/waybill workflows so the business runs end-to-end with:
- higher profit consistency,
- lower operational failures,
- minimal human intervention except exception handling.

## North-Star End State
The repo is considered "final efficient state" when all conditions hold:
1. Daily import and shipment/waybill flows run on schedule with deterministic pass/fail gates.
2. Single-truth validations pass continuously across workbook, DB, and dashboard.
3. Profit/cashflow decisions are generated from trusted facts without manual reconciliation loops.
4. Manual work is limited to approved exception queues, not core daily processing.
5. Any regression is detected within one run cycle and blocked before downstream damage.

## Business Outcomes (measured weekly)
- `Ops reliability`: scheduled run success rate >= 99%.
- `Capital safety`: zero uncontrolled write paths; every apply path gated + backed up + reversible.
- `Profit protection`: no publish of PO/cashflow outputs when truth gates are red.
- `Human reduction`: >70% reduction in manual daily touchpoints vs baseline.
- `Speed`: median daily import + append + health checks complete within target window (tracked by stage timings).

## Current Risk Map (as of 2026-02-25)
1. **Runtime/storage fragility**:
   - Active DB path can drift to non-local/dataless storage and break scheduled runs.
2. **Single-truth drift**:
   - Workbook part IDs, DB part IDs, and dashboard lifecycle can diverge (example: split parts vs legacy part IDs).
3. **Execution chain fragility**:
   - Excel append/backfill and API timing mismatches can cause partial success with hidden downstream failures.
4. **Docs authority contamination**:
   - Old plans/evidence can conflict with active contracts and cause wrong operator decisions.
5. **Observability gaps**:
   - Some failures are visible only in logs, not surfaced as immediate operational stop-lines.

## Evaluation Strategy (from any entry point)
Use one fail-closed triage pipeline, regardless of where failure is observed.

### Layer 1: Runtime + Scheduler
Checks:
- launchd job presence, schedule contract, last exit code, stdout/stderr freshness.
- active DB preflight (local regular file, readable SQLite).
Stop-line:
- any scheduled command exits non-zero or cannot prove valid local DB.

### Layer 2: Data Truth Integrity
Checks:
- `validate_params --strict`
- `validate_single_truth_system`
- inbound/workbook anchor consistency and freshness
Stop-line:
- any workbook/DB/dashboard mismatch or missing guard schema.

### Layer 3: Domain Engines
Checks:
- PO dashboard invariants,
- cashflow integrity,
- inventory/stock snapshot freshness and reconciliation.
Stop-line:
- output generation allowed but publication blocked on red signals.

### Layer 4: Execution APIs (fetch/assemble/waybill)
Checks:
- API fetch completeness, status transition confirmation, waybill URL/PDF integrity, grouping parity.
Stop-line:
- no "HTTP success only" acceptance; must confirm state transition or explicit exception.

### Layer 5: Governance + Docs
Checks:
- active docs contract tests,
- deprecated docs explicitly archived,
- promotion evidence completeness.
Stop-line:
- contradictory active docs or missing promotion evidence.

## Horizon Plan

## Phase H0 - Control-Plane Stabilization (Immediate, 1-3 days)
Goal:
- eliminate known hard-failure classes that break daily operations.

Tasks:
1. Lock active DB locality contract and enforce preflight in all scheduled/manual entrypoints.
2. Ensure all daily jobs have deterministic non-zero fail behavior and visible failure logs.
3. Align single-truth PO part topology between workbook, DB, and dashboard.
4. Confirm scheduler authority times are consistent in plist, tests, docs, and runbooks.

Done when:
- daily import preflight + waybill preflight both PASS on-demand.
- no symlink/dataless active DB path remains.

## Phase H1 - Truth Closure Across PO/Inventory/Cashflow (3-7 days)
Goal:
- remove truth mismatches and prevent reintroduction.

Tasks:
1. Close all strict validator failures for part IDs, paid flags, and lifecycle coverage.
2. Enforce stock snapshot governance (single active snapshot, explicit deprecation of contaminated snapshots).
3. Add strict contracts for cashflow inputs and publication integrity.
4. Add drift reports (before/after artifacts) per run day.

Done when:
- strict validators are green for 3 consecutive daily cycles.
- truth drift report shows zero unresolved critical mismatches.

## Phase H2 - Daily Ops Reliability + Speed Parity (1-2 weeks)
Goal:
- make fetch/import/append/assemble/waybill pipeline both reliable and measurable.

Tasks:
1. Benchmark every stage and persist timing artifacts.
2. Remove wasteful API/Excel patterns with deterministic parity tests.
3. Add resume/checkpoint cache only where parity is proven.
4. Standardize "green/red" daily report artifacts and strict report validator.

Done when:
- correctness parity holds, and median runtime improves without quality regression.

## Phase H3 - Decision Engine Hardening (PO/Cashflow/Inventory) (1-2 weeks)
Goal:
- protect profit decisions from noisy or stale data.

Tasks:
1. Enforce strict mapping completeness for fact_sales and downstream joins.
2. Strengthen economic guardrails: margin floors, delivery cost sanity, unresolved COGS stop-lines.
3. Add machine-readable exception categories for operator handling.

Done when:
- no production recommendation is published with unresolved critical economics gaps.

## Phase H4 - Docs Authority + Change Governance (parallel, 1 week)
Goal:
- prevent docs contamination and false operating assumptions.

Tasks:
1. Create active authority index per domain (ops, PO, inventory, cashflow, API).
2. Mark historical plans as archived with forward link to active authority docs.
3. Add docs tests that fail on schedule/contract contradictions in active docs.
4. Require promotion evidence templates with PR, SHAs, gates, logs, rollback steps.

Done when:
- active docs are contradiction-free under lint/tests.

## Phase H5 - Autonomous Operations Rollout (2-4 weeks)
Goal:
- minimize human-in-the-loop by default.

Tasks:
1. Build orchestrator-driven daily run with strict stop-lines and exception queue output.
2. Route red exceptions into structured operator actions with clear severity and owner.
3. Keep all write/apply actions optional, gated, and reversible.
4. Add weekly health scorecard summarizing reliability, profitability risk, and manual workload.

Done when:
- humans intervene only on exceptions; routine flow runs unattended.

## Core Backlog by Domain

### PO
1. Complete part-level lifecycle consistency and dashboard alignment.
2. Ensure split-part handling is canonical (no legacy aggregate duplicates).
3. Validate paid/unpaid semantics between workbook and DB.

### Inventory
1. Enforce single active stock snapshot contract.
2. Validate stock rebuild parity daily.
3. Block stale snapshot-driven planning outputs.

### Cashflow
1. Lock calendar and payout inputs to validated fact sources.
2. Block publication if unresolved receivables inconsistencies appear.
3. Add reconciliation diagnostics as required artifacts.

### API + Shipment/Waybill
1. Confirm state transition after assemble calls.
2. Enforce waybill completeness thresholds and explicit missing-PDF exception list.
3. Keep preflight strict and deterministic.

### Single-Truth Docs + Governance
1. Maintain one active authority doc per operational contract.
2. Auto-test schedule/contract consistency.
3. Enforce evidence completeness before promotions.

## Gate Stack (minimum before promotion)
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `bash scripts/lint_docs.sh`
6. `bash scripts/check_no_db_tracked.sh`
7. Scheduler validate-only + anchor health + ops status
8. Daily report strict validator for current date artifact

## Operational Rule
No "yellow" releases:
- if critical truth or execution gates are red, output may be generated for diagnostics but cannot be treated as operationally valid.

## Final Completion Criteria
The repo reaches the target state when:
1. 14 consecutive daily cycles complete with all hard gates green.
2. No unresolved critical truth mismatches remain.
3. Daily workflow executes unattended except structured exception handling.
4. Profit-impacting decisions (PO/cashflow/inventory) are fully evidence-backed and reproducible from repo artifacts.
