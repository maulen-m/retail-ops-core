# FINAL_10_OUT_OF_10_EXECUTION_PLAN

Status: ACTIVE_CANONICAL_EXECUTION_CONTRACT
Created: 2026-05-21
Timezone: Asia/Qyzylorda / local repo schedule +05
Repo: ~/Docs/Autonomous_business
Branch at review pack: codex/TASK-webui-archive-single-truth-v1
Known review HEAD at pack time: 118c5fae2f14fc4b7998af39a393d075792aa5b7
Owner goal: fastest reliable path to a fully functioning decision-grade autonomous business operating system.

This file is the active execution contract for the 10/10 push. It supersedes scattered local `PLAN*.md` files for current execution routing. Historical plans remain evidence/history only unless this file explicitly references them.

No production DB write, workbook write, scheduler/LaunchAgent/cron change, source pointer write, WebUI/API mutation, ad-platform write, bank/cash movement, supplier payment, PO commitment, stock change, price change, owner publication, external write, production preflight, or production apply is authorized by this file.

---

## 0. READCHECK

### Exact authority files to read first

1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `.claude/OPERATING.md`
4. `docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
5. `docs/PARALLEL_EXECUTION_PROTOCOL.md`
6. `docs/WRITE_SIDE_GATING_CONTRACT.md`
7. `docs/WRITE_APPLY_RUNBOOK.md`
8. `docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
9. `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
10. `docs/inventory/Master_Inventory_Rules_v9.md`
11. `docs/protocol/active/PO_making_logic_v3.md`
12. `docs/inventory/Sales_Data_Model_V16.md`
13. `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
14. `ARCHITECTURE.md`
15. `docs/DAILY_SOP.md`
16. `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`

### Current canonical authority files discovered

Rule/formula authority:
- `docs/inventory/Master_Inventory_Rules_v9.md`
- `docs/protocol/active/PO_making_logic_v3.md`
- `docs/inventory/Sales_Data_Model_V16.md`
- `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
- `ARCHITECTURE.md`

Operational truth:
- `db/app.db`
- source packet roots and accepted source-contract registry rows
- event tables and operational fact tables in DB

Validation truth:
- validators under `scripts/validate_*.py`
- contracts under `docs/validation/`
- golden fixtures under `tests/fixtures/`
- captured command outputs under `exports/validation/` and out-of-repo agent handoff folders

Derived truth:
- dashboards
- owner reports
- exports
- generated docs/reports
- Excel/UI views
- Google Ops Board views

Write authority:
- `docs/WRITE_SIDE_GATING_CONTRACT.md`
- `docs/WRITE_APPLY_RUNBOOK.md`
- `config/write_side_gating_manifest.yaml`

Parallel execution authority:
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Automation pause/resume authority:
- `docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md`
- `config/business_automation_manifest.json`
- `scripts/manage_business_automation.py`

### Stale/deprecated/conflicting docs found

- Many old `PLAN*.md` files exist and are not current execution authority.
- Historical scorecards may describe earlier states but are not current truth.
- Mutable `.claude/*` files are work-state logs only and do not own formulas, schemas, or business truth.
- Current local repo state is dirty and must be grouped before production work.
- Current Agent9178 result remains YELLOW retained-blocker evidence, not full GREEN proof.

### Assumptions

- The May 21 review direction is accepted by the Human Owner.
- The 10/10 acceptance contract is the working target unless the Human Owner amends it.
- Dates in this plan are latest checkpoints, not waiting rules.
- If a gate passes earlier, move earlier.
- If a required gate fails, stop at the gate and repair that blocker.

### Missing inputs

- Fresh physical stock source after the stale stock snapshot boundary remains missing, but Phase20 owner fact says no fresher physical stock source currently exists. Do not re-ask unless the owner creates/provides a new source/export or requests substitute stock/capital-risk review.
- Current local full `git diff`.
- Current full repo tree.
- Owner approval of final 10/10 target wording.
- Owner decision on which paused automations may resume.
- Owner/source answer for any future unresolved identity rows only if repo evidence cannot decide and no current owner fact already covers the row.

### Confidence

High on execution structure. Medium on exact schedule because source acquisition and production-readiness gates can reveal new blockers.

---

## 1. Executive diagnosis

Current business-readiness level: 5.5 / 10.

The repo has strong components but is not execution-ready as a whole. It is a YELLOW, dirty, partially integrated proof stack with useful validators, contracts, and copied-temp machinery, but it is not production/publication-ready.

The main reasons progress is too slow are:
- too many scattered plans;
- too many proof waves without decisive blocker closure;
- dirty repo state from multiple implementation waves;
- unclear active authority at the moment of execution;
- retained blockers being repackaged instead of routed to source/action/owner;
- too much dependence on mutable `.claude/*` logs;
- no single active blocker board tied to business owner surfaces.

Highest-risk failure points:
- false-green owner publication;
- treating copied-temp proof as production truth;
- treating scoped proof as full-scope proof;
- treating missing source data as zero;
- treating offer availability as physical stock;
- using stale stock/sales/workbook/cash/ads sources for PO, profit, cash, ad, or stock decisions;
- production write without dry-run, backup, explicit apply gate, owner approval, and rollback.

Current execution readiness:
- Read-only analysis: allowed.
- Phase 0 docs/current canonicalization: closed; further current-state documentation alignment is allowed.
- Copied-temp validator proof: allowed when explicitly scoped.
- Production preflight: blocked until the current Phase 18/19 review boundary, retained blockers, and exact owner authority clear.
- Production apply: blocked until exact owner approval phrase after reviewed preflight.
- Owner publication: blocked until relevant source/gate truth is green or retained blockers are explicitly visible and non-decision-grade.
- Scheduler resume: blocked until owner approves exact labels and verification passes.

---

## 2. Efficiency philosophy

Efficient means fastest movement toward trustworthy daily owner decisions without capital-dangerous shortcuts.

Efficient work improves at least one of:
1. Owner Profit Daily
2. Cash Risk Daily
3. PO/SKU Daily
4. Source freshness
5. Single-truth integrity
6. Write safety
7. Repeated-run reliability
8. Owner/operator time saved

Inefficient work includes:
- broad “make it green” waves;
- creating new plans without retiring old ones;
- validators that are not tied to owner decisions;
- proof packets that do not change a blocker status;
- asking the Human Owner questions that repo evidence can answer;
- asking CodeCaptain for small local execution decisions;
- turning missing source data into assumptions;
- making dashboard/export layers recompute business math;
- allowing multiple agents to write shared state.

Rule: every task must name the owner output, source gate, or capital-risk blocker it improves. If it cannot, it should not run.

---

## 3. Source-of-truth hierarchy

Use this hierarchy by role, not by filename age.

### 3.1 Rule truth

Active rule docs and configs define formulas, parameters, gates, caps, and authority.

Formula or business-rule changes must flow:

Authority doc/config -> tests/golden fixtures -> implementation -> derived outputs

### 3.2 Operational truth

DB tables and event logs store:
- orders;
- order entries;
- stock movements;
- sales facts;
- returns/cancellations;
- inbound;
- cashflow;
- ads;
- run status;
- source freshness;
- policy gates.

### 3.3 Validation truth

Tests, contracts, fixtures, validators, and reconciliation reports prove implementation matches rule truth.

### 3.4 Derived truth

Workbooks, dashboards, exports, owner reports, and generated markdown are outputs. They must not silently recompute business logic.

---

## 4. Non-negotiables

1. Do not call copied-temp proof production truth.
2. Do not call scoped proof full-scope proof.
3. Do not hide retained blockers.
4. Do not turn missing source data into zero.
5. Do not treat API/WebUI/Excel/manual owner truth as interchangeable unless an accepted contract says so.
6. Do not use offer availability as physical stock truth.
7. Do not use workbook/dashboard/export logic as business-rule authority.
8. Do not run production preflight until copied-temp proof and blocker board justify it.
9. Do not apply production writes without:
   - current preflight;
   - exact owner approval phrase;
   - env gate;
   - `--apply`;
   - DB backup;
   - expected diff;
   - rollback command;
   - post-apply validation.
10. Do not resume scheduler/automation without exact owner authorization for labels or groups.

---

## 5. 10/10 target definition

A 10/10 system is not “all code exists.” It is a daily decision-grade business operating system that can run from source truth to owner action without rediscovery, hidden stale data, mixed authority, silent mutation, or false-green publication.

### 5.1 Business capabilities required

The system must produce decision-grade or explicitly blocked versions of:

1. Owner Profit Daily
   - revenue;
   - COGS;
   - ads;
   - OPEX impact where relevant;
   - profit;
   - trust banner;
   - blocked-decision banner.

2. Cash Risk Daily
   - usable cash;
   - expected receipts;
   - commitments;
   - conservative cash floor;
   - low-cash dates;
   - statement/API/source trust labels.

3. PO/SKU Daily
   - reorder/freeze/kill list;
   - ROIC;
   - demand evidence;
   - COGS exposure;
   - stock/inbound/on-delivery capital;
   - new/unproven SKU capital caps;
   - liquidation/exit path for weak inventory.

4. Daily Survival / Owner Brief
   - one operator-readable cockpit;
   - what is green;
   - what is blocked;
   - what requires owner action;
   - what not to do.

### 5.2 Technical capabilities required

- `db/app.db` remains operational truth.
- Source-contract registry validates.
- Required child source freshness gates pass or explicitly block related outputs.
- Policy gates expose business-surface blocking.
- Stock, sales, order-entry, ads, cashflow, PO, COGS, status-ledger, workbook-anchor, single-truth, and day-complete validators are deterministic.
- Owner surfaces are derived outputs only.
- Write paths are guarded by manifest, env gate, `--apply`, backup, and rollback.
- Scheduler state is observable and controllable.

### 5.3 Reliability requirements

- Three consecutive validate-only daily runs for the declared scope.
- No hidden manual intervention.
- No silent source fallback.
- No mutable `.claude/*` dependency for business truth.
- Source freshness visible.
- Retained blockers visible.
- System Doctor strict path green or explicitly blocked.
- Protected surfaces hash before/after any apply.

### 5.4 Test requirements

At minimum:
- source-contract registry validator;
- policy source freshness validator;
- policy gate validator;
- PO dashboard invariants;
- single-truth system and alignment;
- PO money gate;
- sales/order-entry freshness and identity;
- workbook anchor validation;
- cashflow invariants;
- ads coverage/spend reality where in scope;
- write-side gating;
- no-help-command writes;
- repeated-run validator;
- scheduler heartbeat/status validators before resume.

### 5.5 Documentation requirements

Exactly one active current layer:
- `docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
- `docs/current/CURRENT_AUTHORITY_INDEX.md`
- `docs/current/CURRENT_ARCHITECTURE_MAP.md`
- `docs/current/CURRENT_SOURCE_TRUTH_MAP.md`
- `docs/current/CURRENT_BLOCKER_BOARD.tsv`
- `docs/current/CURRENT_GATE_MATRIX.tsv`
- `docs/current/CURRENT_AGENT_OPERATING_CONTRACT.md`
- `docs/current/CURRENT_PRODUCTION_WRITE_BOUNDARY.md`
- `docs/current/SUPERSEDED_PLAN_INDEX.tsv`

---

## 6. Current retained blocker seed board

This is the historical seed board for Phase 0. It is not the current blocker
authority. Use `docs/current/CURRENT_BLOCKER_BOARD.tsv` for current blocker
state, exit gates, and owner/CodeCaptain routing.

| Blocker ID | Current status | Evidence signal | Business surface blocked | Severity | Default route |
|---|---|---|---|---|---|
| B001_source_freshness_child_sources | STALE/BLOCKING | Six internal AB child sources stale: ads, cashflow, order entry, order status, sales, stock | owner publication, profit, cash, PO | STOP | Route each child source to source acquisition or accepted retained-blocker contract |
| B002_policy_gates | BLOCKED | ads_source_truth, cashflow_source_truth, source_freshness, stock_source_truth blocked | owner publication | STOP | Repair source/gate inputs; no publication |
| B003_physical_stock_stale | STALE | stock snapshot stale vs cutoff; Phase20 owner fact says no fresher physical stock source currently exists; offer availability is not stock | PO/SKU Daily, stock actions | STOP | Keep retained unless new physical stock source/export appears or CodeCaptain reviews a substitute stock/capital-risk contract |
| B004_sales_identity_order_entry | COPIED-TEMP CLOSED / STOP FOR PRODUCTION | Universal offer identity is owner-confirmed for copied-temp proof planning only; no-real-entry quarantine remains review evidence only | sales truth, profit, stock depletion | STOP | Package for CodeCaptain; no production apply before retained blockers and review clear |
| B005_workbook_anchor_lag | STALE | workbook max date lag exceeds threshold | sales/workbook anchor trust | STOP/WARN depending claimed surface | Repair anchor or keep related outputs blocked |
| B006_single_truth_system | FAIL | DB part IDs missing in dashboard archived_pos/pos/real_pos lifecycle | PO money, dashboard trust | STOP | Copied-temp repair route before PO gate |
| B007_po_money_gate | FAIL | required failures: single_truth_system, single_truth_alignment | PO commitment | STOP | Repair single-truth alignment first |
| B008_retained_stock_exceptions | OPEN | nine high stock exceptions visible | stock/PO trust | QUARANTINE/STOP depending SKU | Keep visible; do not auto-clear |
| B009_dirty_repo_state | DIRTY | modified and untracked implementation/handoff areas | execution readiness | STOP for production | Group into logical batches; commit or park |
| B010_plan_sprawl | ACTIVE RISK | many scattered plans and parallel-run PLAN files | orchestration speed | WARN/HIGH | Supersede with docs/current plan and archive index |
| B011_automation_paused | PAUSED | all-business automations paused, loaded 0/27 | live automation | STOP until owner resumes | Keep paused unless owner approves exact labels |

---

## 7. Canonical `docs/current/` structure

Create and maintain:

```text
docs/current/
  FINAL_10_OUT_OF_10_EXECUTION_PLAN.md
  CURRENT_AUTHORITY_INDEX.md
  CURRENT_ARCHITECTURE_MAP.md
  CURRENT_SOURCE_TRUTH_MAP.md
  CURRENT_BLOCKER_BOARD.tsv
  CURRENT_GATE_MATRIX.tsv
  CURRENT_AGENT_OPERATING_CONTRACT.md
  CURRENT_PRODUCTION_WRITE_BOUNDARY.md
  SUPERSEDED_PLAN_INDEX.tsv
```

### 7.1 Purpose of each file

`FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
- single active execution plan;
- phases, gates, roles, schedule, stoplines.

`CURRENT_AUTHORITY_INDEX.md`
- one-page router to active authority docs;
- no formulas;
- no new business rules.

`CURRENT_ARCHITECTURE_MAP.md`
- source -> DB -> validators -> owner surfaces -> write boundaries.

`CURRENT_SOURCE_TRUTH_MAP.md`
- source IDs;
- authority;
- freshness rule;
- accepted packet path;
- blocks publication yes/no;
- owner/source dependency.

`CURRENT_BLOCKER_BOARD.tsv`
- active blockers only;
- validator;
- surface blocked;
- owner needed yes/no;
- next action;
- current owner;
- exit gate.

`CURRENT_GATE_MATRIX.tsv`
- exact commands;
- scope;
- expected output;
- pass/fail semantics;
- allowed green label.

`CURRENT_AGENT_OPERATING_CONTRACT.md`
- when to spawn agents;
- how to hand off;
- closeout requirements;
- unsafe surfaces.

`CURRENT_PRODUCTION_WRITE_BOUNDARY.md`
- forbidden surfaces;
- allowed read-only surfaces;
- production preflight prerequisites;
- apply prerequisites;
- rollback.

`SUPERSEDED_PLAN_INDEX.tsv`
- old plans;
- status;
- superseded_by;
- archive location;
- keep/delete/park recommendation.

### 7.2 Source-of-truth rules for docs

- Active current docs route work.
- Historical plan docs explain history only.
- No formula changes in current planning docs.
- No mutable `.claude/*` file is business-rule authority.
- No generated report is hand-edited unless its governance doc allows it.

---

## 8. Phase plan

### Phase 0 — Freeze, canonicalize, route

Objective:
Stop waste before more implementation.

Owner:
Main Orchestrator.

Allowed agents:
- two read-only analysts;
- orchestrator/execution owner may write only docs/current and run docs-only gates.

Inputs:
- this plan;
- `AGENTS.md`;
- `docs/00_START_HERE.md`;
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`;
- latest Agent9178 evidence;
- current local `git status`, `git diff`, and plan inventory.

Deliverables:
- `CURRENT_AUTHORITY_INDEX.md`
- `CURRENT_ARCHITECTURE_MAP.md`
- `CURRENT_SOURCE_TRUTH_MAP.md`
- `CURRENT_BLOCKER_BOARD.tsv`
- `CURRENT_GATE_MATRIX.tsv`
- `CURRENT_AGENT_OPERATING_CONTRACT.md`
- `CURRENT_PRODUCTION_WRITE_BOUNDARY.md`
- `SUPERSEDED_PLAN_INDEX.tsv`
- Phase 0 closeout

Guardrails:
- no DB writes;
- no workbook writes;
- no scheduler changes;
- no external writes;
- no source pointer writes;
- no implementation repairs except docs/current routing.

Tests/gates:
```bash
git diff --check
./scripts/check_no_db_tracked.sh
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
bash scripts/lint_docs.sh
```

Success criteria:
- active authority discoverable in less than 60 seconds;
- each retained blocker has owner, next route, and exit gate;
- every old plan has active/superseded/archive status;
- no production state changed.

Exit gate:
`PHASE0_CANONICAL_ROUTE_GREEN` if all docs/gates pass and blocker board is complete. Otherwise `PHASE0_YELLOW_ROUTE_INCOMPLETE`.

Relative effort:
Medium.

Human Owner required:
No, unless physical source or target approval is immediately needed.

CodeCaptain required:
No, unless authority conflict is discovered.

---

### Phase 1 — Source truth closure

Objective:
Kill actual source blockers or classify them as explicit retained blockers.

Owner:
Main Orchestrator.

Allowed agents:
- independent read-only/source agents by blocker class;
- one serialized execution agent only after source routes are clear.

Workstreams:
1. Physical stock truth
2. Sales identity and order-entry freshness
3. Ads source truth and no-zero-spend scope
4. Cashflow source truth
5. PO/single-truth alignment
6. Workbook/anchor lag
7. Retained exception queue visibility

Deliverables:
- accepted source packets or retained-blocker rows;
- updated `CURRENT_SOURCE_TRUTH_MAP.md`;
- updated `CURRENT_BLOCKER_BOARD.tsv`;
- focused copied-temp repair patches only if source-backed.

Guardrails:
- offer availability cannot clear physical stock truth;
- missing ads spend cannot become zero;
- copied-temp bridge cannot claim production freshness;
- owner publication remains blocked;
- PO commitment remains blocked.

Tests/gates:
```bash
python3 scripts/validate_mvos_source_contract_registry.py --json
python3 scripts/validate_policy_source_freshness.py --db <copied_db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied_db> --strict --json
python3 scripts/validate_order_entries_freshness.py --db <copied_db> --as-of <YYYY-MM-DD> --strict
python3 scripts/validate_sales_vs_workbook_anchor.py --db <copied_db> --as-of <YYYY-MM-DD>
python3 scripts/validate_single_truth_system.py --db <copied_db>
python3 scripts/validate_single_truth_alignment.py --db <copied_db>
python3 scripts/validate_po_money_gate.py --db <copied_db> --json
python3 scripts/validate_po_dashboard_invariants.py --db <copied_db> --strict
python3 scripts/validate_cashflow_invariants.py --db <copied_db>
```

Success criteria:
- each source blocker is resolved, routed to owner/source, or retained with explicit blocked surface;
- no hidden stale source drives decisions;
- PO/stock/profit/cash/ad claims are scope-labeled.

Exit gate:
`PHASE1_SOURCE_TRUTH_GREEN` if no unresolved source blockers affect claimed outputs. Otherwise `PHASE1_YELLOW_RETAINED_SOURCE_BOARD`.

Relative effort:
High.

Human Owner required:
Only for a new physical stock source/export if one is created, a desired substitute stock/capital-risk contract, automation resume decision, final target approval, or future unresolved identity if repo evidence and existing owner facts cannot decide.

CodeCaptain required:
No, unless a source contract conflict or capital-risk override is proposed.

---

### Phase 2 — Full copied-temp MVOS proof

Objective:
Prove the complete declared scope safely before any production preflight.

Owner:
Main Orchestrator plus one serialized integrator.

Inputs:
- Phase 0 docs/current;
- Phase 1 source routes;
- copied DB manifest;
- source packets;
- current blocker board.

Deliverables:
- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json`
- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- `RETAINED_BLOCKER_BOARD.md`
- `COPIED_DB_BOUNDARY_SHA256.tsv`

Guardrails:
- copied-temp proof is not production truth;
- scoped proof is not full proof;
- no source pointer writes;
- no owner publication;
- no production preflight until CodeCaptain review packet is ready.

Tests/gates:
```bash
python3 scripts/validate_mvos_source_contract_registry.py --json
python3 scripts/validate_policy_source_freshness.py --db <copied_db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied_db> --strict --json
python3 scripts/validate_day_complete.py --db <copied_db> --cutoff-date <YYYY-MM-DD>
python3 scripts/validate_status_ledger_continuity.py --db <copied_db> --start <YYYY-MM-DD> --end <YYYY-MM-DD> --strict
python3 scripts/validate_order_entries_freshness.py --db <copied_db> --as-of <YYYY-MM-DD> --strict
python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db <copied_db> --strict
python3 scripts/validate_sales_vs_workbook_anchor.py --db <copied_db> --as-of <YYYY-MM-DD>
python3 scripts/validate_po_dashboard_invariants.py --db <copied_db> --strict
python3 scripts/validate_single_truth_system.py --db <copied_db>
python3 scripts/validate_single_truth_alignment.py --db <copied_db>
python3 scripts/validate_po_money_gate.py --db <copied_db> --json
python3 scripts/validate_cashflow_invariants.py --db <copied_db>
python3 scripts/validate_order_cashflow_coverage.py --db <copied_db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
python3 scripts/validate_no_help_command_writes.py
pytest -q
```

Success criteria:
- all required validators pass for declared scope;
- retained blockers are zero or explicitly visible and non-decision-grade;
- no missing source data inferred;
- no production authority claimed.

Exit gate:
`COPIED_TEMP_GREEN_PROOF` or honest `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

Relative effort:
Medium to High.

Human Owner required:
Only if source blocker or target approval remains open.

CodeCaptain required:
Yes after proof if production preflight is requested.

---

### Phase 3 — Production preflight, owner approval, serialized apply

Objective:
Move exact approved changes to production only after reviewed preflight.

Owner:
Main Orchestrator.

Allowed agent:
One serialized execution agent only.

Inputs:
- copied-temp proof;
- CodeCaptain review;
- owner exact approval phrase;
- production preflight packet.

Deliverables:
- `PRODUCTION_PREFLIGHT_PACKET.md`
- `OWNER_APPROVAL_PHRASE_REQUEST.md`
- `PRODUCTION_BACKUP_AND_ROLLBACK.md`
- `DRY_RUN_EXPECTED_DIFF.json`
- `WRITE_COMMAND_MANIFEST.tsv`
- backup path and hashes

Guardrails:
- no parallel writers;
- no production apply without exact owner phrase;
- no apply without backup;
- no apply without rollback command;
- no apply if protected-surface hash drift is unexplained.

Preflight tests:
```bash
./scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml --strict
python3 scripts/validate_params.py --strict
<apply-script> --dry-run --json
```

Apply pattern:
```bash
mkdir -p db/backups
cp db/app.db "db/backups/app.db.pre_apply_$(date +%Y%m%d_%H%M%S).sqlite"

ENABLE_<GATE>=1 python3 scripts/<write_script>.py --apply
```

Rollback:
```bash
git revert <newest_commit> ... <oldest_commit>
cp db/backups/app.db.pre_apply_<timestamp>.sqlite db/app.db
python3 scripts/validate_params.py --strict
./scripts/check_no_db_tracked.sh
```

Success criteria:
- exact production apply completes;
- post-apply validators pass;
- rollback is documented and tested where practical;
- release anchor created.

Exit gate:
`PRODUCTION_APPLY_GREEN` or `NO_APPLY_AUTHORIZED`.

Relative effort:
High.

Human Owner required:
Yes.

CodeCaptain required:
Yes.

---

### Phase 4 — Post-apply anchor and repeated-run autonomy

Objective:
Prove the system stays green and is not a one-time local proof.

Owner:
Main Orchestrator.

Deliverables:
- `RELEASE_ANCHOR.md`
- `RELEASE_ANCHOR.json`
- `POST_APPLY_VALIDATION_MATRIX.tsv`
- `MVOS_REPEATED_RUN_MATRIX.tsv`
- daily owner brief outputs

Tests/gates:
```bash
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_mvos_repeated_run.py --days 3 --strict
python3 scripts/system_doctor.py --strict --project-root .
python3 scripts/validate_scheduler_heartbeat.py --strict
python3 scripts/manage_business_automation.py status
pytest -q
```

Success criteria:
- three consecutive validate-only daily runs pass for declared scope;
- owner surfaces are generated with correct trust banners;
- no source freshness drift;
- no protected-surface drift;
- no hidden manual steps.

Exit gate:
`REPEATED_RUN_GREEN`.

Relative effort:
Medium.

Human Owner required:
Only for reviewing owner surfaces and approving scheduler/publication next step.

CodeCaptain required:
Optional unless final publication/scheduler gate is requested.

---

### Phase 5 — Owner publication and safe scheduler reactivation

Objective:
Make the system business-ready in live operations.

Owner:
Main Orchestrator with Human Owner approval.

Deliverables:
- owner cockpit;
- allowed/blocked decision matrix;
- scheduler resume packet;
- pause/resume evidence;
- final owner workflow guide.

Guardrails:
- no publication if required source gates are red;
- no scheduler resume without exact owner-approved labels/groups;
- no cash/PO/ad/stock/price action without the relevant gate.

Tests/gates:
```bash
python3 scripts/manage_business_automation.py status
python3 scripts/manage_business_automation.py verify --expect paused --scope all-business
python3 scripts/validate_scheduler_heartbeat.py --strict
python3 scripts/system_doctor.py --strict --project-root .
python3 scripts/validate_mvos_repeated_run.py --days 3 --strict
```

Success criteria:
- owner can see daily:
  - what is safe to act on;
  - what is blocked;
  - what source is stale;
  - what cash/PO/ad/stock/price actions are forbidden;
- automation can be paused/resumed with evidence;
- owner no longer depends on agent memory to operate.

Exit gate:
`BUSINESS_READY_10_OUT_OF_10` only if all required gates pass and owner accepts the final operating state.

Relative effort:
Medium.

Human Owner required:
Yes.

CodeCaptain required:
Recommended for final 10/10 publication claim.

---

## 9. Parallelization rules

Allowed in parallel:
- doc inventory;
- dirty diff grouping;
- source provenance audit;
- validator output audit;
- owner request queue draft;
- gate matrix drafting.

Not allowed in parallel:
- production DB writes;
- workbook writes;
- scheduler changes;
- config writes used by validators;
- `.claude/*` updates by multiple agents;
- source pointer writes;
- external/API/WebUI/ad/cash/PO/stock/price changes;
- production apply.

Default topology:
- Main Orchestrator owns execution.
- Two read-only analysts publish first-pass reports.
- One execution/integration agent writes shared repo state only after analyst reports are in.
- No analyst reads the other analyst’s report before publishing first pass.
- Completion pings are not authority; closeout files are authority.

---

## 10. Agent execution model

### 10.1 When to spawn agents

Spawn agents only when:
- task has one blocker-board row or one bounded artifact;
- files/surfaces are non-overlapping;
- exit gate is explicit;
- closeout format is defined.

Do not spawn agents for:
- “make it green”;
- “review everything”;
- “continue previous wave”;
- “fix whatever you find.”

### 10.2 Handoff pack requirements

Every handoff pack must include:
- objective;
- blocker-board row IDs;
- allowed files;
- forbidden files/surfaces;
- read-only or write permission;
- exact commands allowed;
- output files required;
- stop conditions;
- closeout format;
- rollback expectation.

### 10.3 Verification

The orchestrator must:
- inspect closeout files;
- rerun required gates or inspect captured stdout;
- update blocker board;
- classify result as GREEN/YELLOW/RED;
- never infer success from agent wording alone.

### 10.4 Recovery from failed agents

If an agent fails:
- preserve its worktree and handoff folder;
- mark rows BLOCKED or RED;
- do not merge partial changes unless validator-visible and scoped;
- restore protected surfaces if touched;
- rerun `git diff --check`, `check_no_db_tracked`, and relevant validators.

---

## 11. Human Owner request queue

Only ask the Human Owner for decisions that cannot be resolved from repo evidence.

| Request ID | Owner | Exact request | Why necessary | Work blocked | Priority | Default if no answer |
|---|---|---|---|---|---|---|
| H001 | Human Owner | Approve or amend the 10/10 acceptance target. | Final target must be owner-accepted. | Final publication semantics. | High | Use candidate target for implementation only; no publication authority. |
| H002 | Human Owner / warehouse source | Provide or authorize fresh independent physical stock source after stale stock cutoff, or request a CodeCaptain-reviewed substitute stock/capital-risk contract. Owner confirmed no fresher physical stock source currently exists. | PO/SKU cannot be decision-grade from stale stock. | PO/SKU Daily, stock action, PO commitment. | Critical | Keep PO/SKU execution blocked. |
| H003 | Human Owner | Decide whether any paused automations may resume, with exact labels/groups. | All-business automations are paused. | Live automation. | Critical if ops need automation | Keep paused. |
| H004 | Human Owner / source evidence | Universal offer `132822924_328581041` identity is owner-confirmed for copied-temp proof planning only. | The mapping supports review evidence but not production/source application authority. | Sales truth, order-entry freshness. | High | Treat `CL_NEW-CLO_MEN_LEG_WHITE_XL` as copied-temp evidence only; production remains blocked. |
| H005 | Human Owner | Approve exact production apply phrase only after CodeCaptain-reviewed preflight. | Production writes require explicit approval. | Production apply. | Critical at production gate | No apply. |
| H006 | Human Owner / CodeCaptain | Provide explicit copied-temp-only `LINE-31-LS` COGS authority, accept a component-level ChildSum route, or leave `ACMEWEAR 929183530 / LINE-31-LS_2XL` quarantined for CodeCaptain review. | B012 default/repeated-run daily autonomy is narrowed but not green. | Repeated-run autonomy, owner decision loop. | High | Keep B012 `YELLOW`; do not infer LINE-31-LS COGS from adjacent families. |

---

## 12. CodeCaptain request queue

Use CodeCaptain only for big gates:
1. authority conflict;
2. final target acceptance conflict;
3. production preflight review;
4. production apply packet review;
5. final 10/10 publication/scheduler gate;
6. capital-risk override.

Do not use CodeCaptain for:
- local docs/current routing;
- dirty-diff grouping;
- read-only source inventory;
- obvious validator reruns;
- small non-production copied-temp repair unless it changes authority.

---

## 13. Calendared rough schedule

Dates are latest checkpoints, not waiting periods. Move earlier if gates pass. Stop if gates fail.

| Date | Deadline | Target state | Gate |
|---|---|---|---|
| Thu 2026-05-21 | D0 | Save this plan; launch Phase 0 with two read-only analysts | analyst prompts launched |
| Fri 2026-05-22 | D1 | Phase 0 closeout complete; docs/current created; blocker board and gate matrix drafted | `PHASE0_CANONICAL_ROUTE_GREEN` or yellow with explicit missing rows |
| Sat 2026-05-23 | D2 | Dirty diff grouped; old plans classified; source blockers routed | blocker board complete |
| Sun 2026-05-24 | D3 | Owner-source requests minimized; physical stock/identity/default routes known | all blockers have route/owner/default |
| Mon 2026-05-25 | D4 | Targeted copied-temp source repairs underway or blockers retained honestly | source truth validators improving |
| Tue 2026-05-26 | D5 | Full copied-temp proof attempt | `COPIED_TEMP_GREEN_PROOF` or honest YELLOW board |
| Wed 2026-05-27 | D6 | CodeCaptain packet only if copied-temp proof changed blocker status materially | CodeCaptain review packet |
| Thu 2026-05-28 | D7 | Production preflight candidate only if CodeCaptain allows | preflight dry-run packet |
| Fri 2026-05-29 | D8 | Owner exact approval request only if preflight is clean | owner phrase request or no-apply decision |
| Sat 2026-05-30 | D9 | Serialized apply only if exact owner phrase and all preflight gates pass | production apply or no-apply |
| Sun 2026-05-31 | D10 | Post-apply anchor or continued retained-blocker repair | release anchor or blocker repair |
| Mon 2026-06-01 | D11 | Repeated-run day 1 | validate-only run 1 |
| Tue 2026-06-02 | D12 | Repeated-run day 2 | validate-only run 2 |
| Wed 2026-06-03 | D13 | Repeated-run day 3 | validate-only run 3 |
| Thu 2026-06-04 | D14 | Scheduler/publication readiness review | final owner + optional CodeCaptain gate |

Schedule rule:
- No date overrides a failed gate.
- No gate should wait for date if it passes early.
- Source acquisition can move the whole schedule.
- Production apply can be skipped; a strong no-apply decision is better than unsafe apply.

---

## 14. Phase 0 immediate actions

1. Create `docs/current/` if missing.
2. Save this file as `docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`.
3. Scaffold a parallel run for Phase 0.
4. Launch read-only Agent B: dirty diff and plan/document canonicalization audit.
5. Launch read-only Agent C: source blocker and gate matrix audit.
6. Wait for both closeouts.
7. Integrate into docs/current.
8. Run docs-only gates.
9. Produce Phase 0 closeout.
10. Prepare Phase 1 launch pack only after Phase 0 is closed.

---

## 15. Minimum Phase 0 closeout format

Create:

`docs/parallel_runs/<date>_mvos_phase0_canonical_route/PHASE0_CLOSEOUT.md`

Required sections:
- READCHECK
- exact files read
- exact files written
- commands run
- results
- blocker board summary
- gate matrix summary
- owner requests opened
- CodeCaptain requests opened
- production/write/scheduler/publication authority status
- rollback
- next actions

Final label must be one of:
- `PHASE0_CANONICAL_ROUTE_GREEN`
- `PHASE0_YELLOW_ROUTE_INCOMPLETE`
- `PHASE0_RED_AUTHORITY_CONFLICT`

---

## 16. Rollback and recovery

For Phase 0:
- Docs-only changes should be reversible by git.
- Do not delete historical plans on first pass.
- Mark superseded and archive/index first.
- Rollback by `git restore docs/current docs/archive ...` or `git revert <commit>`.

For code/config:
- One logical commit per blocker class.
- Do not mix docs cleanup with validator implementation.
- If a focused test fails, do not merge.

For production write:
- Use write runbook only.
- Backup before apply.
- Owner exact phrase required.
- Restore DB backup and git revert on failure.
- Rerun minimum gates after rollback.

For automation:
- Keep all-business paused unless owner approves exact labels/groups.
- Resume one group at a time.
- Verify after resume.
- If drift appears, pause all-business and capture evidence.

---

## 17. Current final stance

Current status is not production-ready and not owner-publication-ready.

The fastest reliable route is:
1. one canonical current plan;
2. two read-only Phase 0 reports;
3. one integrated blocker board/gate matrix;
4. targeted source-truth closure;
5. one full copied-temp proof;
6. CodeCaptain only at production/final gates;
7. owner approval only where the owner is truly needed.

Do not run another broad retained-blocker wave until Phase 0 closes.
