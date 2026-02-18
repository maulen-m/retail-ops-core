# Autonomous_business Repo Context Memo

Last updated: 2026-02-15 16:58:24 +05
Audience: external engineers onboarding to this repo
Scope: Kaspi-only operations (sales truth, inventory, PO, cashflow, reporting)

## 1) Purpose
This repository is an operations system for Kaspi commerce that keeps one decision-grade truth across:
- sales and delivered revenue,
- inventory and PO lifecycle,
- cashflow and paid-capital views,
- reporting exports used by Excel/UI and management reviews.

Primary business objective: maximize profit growth while protecting capital and data integrity.
Primary engineering objective: prevent "truth contamination" between legacy/parallel sources.

## 2) Top-level goals
1. Keep one canonical published sales interface (`view_sales_line_truth`, `view_sales_daily_truth`).
2. Keep PO math consistent with inventory master rules (`Master_Inventory_Rules_v8.md`).
3. Keep cashflow default lens aligned to paid truth (model lens is explicit optional mode).
4. Keep strict validation gates green before any automation/write rollout.
5. Keep all write paths dry-run by default and explicitly gated.

## 3) System architecture (compact)

```text
                       +----------------------------+
                       | Kaspi APIs / CRM Workbook |
                       | Inbound Calendar / Banks  |
                       +-------------+--------------+
                                     |
                                     v
+-------------------+     +-------------------------+     +------------------+
| Ingest scripts    +---->+ SQLite DB (`db/app.db`) +<----+ Config contracts |
| (orders/sales/PO) |     | facts/dims/ledger/views |     | (docs + yaml/csv)|
+---------+---------+     +-----------+-------------+     +---------+--------+
          |                             |                           |
          |                             v                           |
          |                 +-------------------------+             |
          +---------------> | Canonical truth layer   | <-----------+
                            | `view_sales_*_truth`    |
                            +-----------+-------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
      +---------------------------+                  +---------------------------+
      | PO / Inventory / Cashflow |                  | Reports / Exports / Excel |
      | engines + dashboard data  |                  | business-insides / CSVs   |
      +-------------+-------------+                  +-------------+-------------+
                    |                                              |
                    +-------------------+--------------------------+
                                        v
                           +----------------------------+
                           | Strict validators + tests  |
                           | (must pass before publish) |
                           +----------------------------+
```

## 4) Core components and responsibilities
- `db/app.db`: operational truth store (facts, dims, stock ledger, PO lifecycle, derived views).
- Published sales truth views: one consumer contract for line/day sales truth; used by business-insides and downstream exports.
- `core/po/recommender.py`: canonical PO calculation API used by scripts; implementation reference for order qty/ROP/SS flow.
- `docs/inventory/Master_Inventory_Rules_v8.md`: authoritative formulas/params (unit economics, SS/ROP/ROIC, fee rules).
- `docs/ARCHITECTURE.md`: high-level module boundaries and single-truth chain.
- `.claude/*`: durable execution memory (goals/tasks/decisions/issues) and current operational stage.

## 5) Current stage snapshot (timestamped)
As of 2026-02-15 16:58:24 +05:

### 5.1 Active goals
- Maintain strict-gate green status after the February single-truth remediation wave.
- Continue consolidation around sales truth integrity and workbook-anchored validation.
- Keep PO/cashflow/reporting consumers pinned to canonical views and contracts.

### 5.2 Active tasks (`.claude/TASKS.md`)
- IN_PROGRESS: TASK-386 (dim_sku weight recovery + drift guard).
- IN_PROGRESS: TASK-385 (COGS integrity + LINE61 canonical mapping).
- IN_PROGRESS: TASK-384 (workbook-anchored sales truth integrity).
- IN_PROGRESS: TASK-383 (single-truth canonical sequence: chronology fix -> canonical views -> ads sidecar).
- DONE recently: TASK-387 (stop-the-bleeding freeze + workbook anchor gate, completed 2026-02-11).

### 5.3 Active issues (`.claude/ISSUES.md`)
- OPEN: ISSUE-021 (data-grain DB checks failing in unrelated path).
- OPEN: ISSUE-020 (import-orders test mismatch in parallel-edited path).
- Resolved blockers: ISSUE-022 and ISSUE-023 (strict chain now green after settlement/workbook fixes).

### 5.4 Key decisions (`.claude/DECISIONS.md`)
- 2026-02-11: stabilization strategy favors minimal write surface and idempotent settlement path.
- 2026-02-09: strict execution order for sales truth: freeze overlap -> workbook gate -> business-insides binding.
- 2026-02-09: COGS publication contract requires full landed inputs; unresolved rows must be explicit.
- 2026-02-09: dim_sku weight restore source and guarded sync policy defined.

### 5.5 Execution plan shape
- Keep scope small and test-first.
- For any write action: backup first, dry-run default, explicit apply flag required.
- If strict gate fails: stop, log blocker in `.claude/ISSUES.md`, fix before expanding scope.

## 6) Single-truth operating contract (external engineer quick rules)
1. Read order: `AGENTS.md` -> `docs/00_START_HERE.md` -> owning spec.
2. Formula ownership: inventory master rules doc wins over code/comments if mismatch exists.
3. Schema/derived truth: DB + canonical views are source; exports and dashboards are derived.
4. No silent writes: all write scripts must be explicitly opt-in and evidenced.
5. Treat workbook/Excel artifacts as contracts/input surfaces, not independent truth engines.

## 7) Known sharp edges
- `core/po/recommender.py` docstring references older v6 wording; current contract authority is v8 rules doc.
- Parallel workstreams can produce unrelated red tests; scope discipline is required (fix only owning stream unless requested).
- Workbook-integrated flows are sensitive to schema drift and must stay guarded by validators.

## 8) Reference stack (max 10 files, includes this memo)
1. `docs/ideas/REPO_CONTEXT_MEMO_2026-02-15.md`
2. `AGENTS.md`
3. `docs/00_START_HERE.md`
4. `docs/ARCHITECTURE.md`
5. `docs/inventory/Master_Inventory_Rules_v8.md`
6. `core/po/recommender.py`
7. `.claude/GOALS.md`
8. `.claude/TASKS.md`
9. `.claude/DECISIONS.md`
10. `.claude/ISSUES.md`

## 9) Suggested first 90-minute onboarding sequence
- 0-20 min: read files 2-5 from the stack.
- 20-40 min: read files 7-10 to understand active execution state and risk.
- 40-70 min: inspect `core/po/recommender.py` + current validators used by active tasks.
- 70-90 min: run one non-writing validation loop and compare outputs to active issue/task notes.
