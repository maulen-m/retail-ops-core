# PLAN_BOARD_V9_SYSTEM_DOCTOR_E2E_AUTONOMY_2026-02-25

## Purpose
Create the fastest, safest path to an end-to-end “final efficient business repo state” by:
1) making evaluation deterministic from any entry point (PO / cashflow / inventory / API / docs),
2) turning evaluation into a single fail-closed triage pipeline (“System Doctor”),
3) enforcing publication/decision gates (profit/cashflow/PO outputs) so capital cannot be exposed by false-green runs,
4) pushing human involvement to exception handling only (0–5% of critical time).

This board is intentionally broad scope, but sequential and fail-closed.

---

## Context / Baseline (what changed recently)
Assume the following were merged/promoted already (commit IDs provided by operator logs; treat as baseline truth unless repo disagrees):

### Promotions (recent)
- V5: “prod write scale”
  - PR #12 merge SHA: 6beab4ed614368de4bfc59808a78d53a9a726a10
  - PR #13 merge SHA: b727a0d8811c9c91fb35913bd242c75efbecfeab
  - Key: drift pack SLO policy, daily ops workflow contract, write-canary readiness contracts.

- Risk closure:
  - PR #15 merge SHA: f1ff76953e0856a589bdd7003ada1088fa4fd09f
  - Key: scheduler authority cleanup + docs/test hardening + explicit “assemble state transition” guarantee.

- V6: “autonomous scale”
  - PR #16 merge SHA: 081e107eebb1921c46cab83e6693c838ed3d04a8
  - PR #17 merge SHA: ea01dc90d11b7b8e24056b1e0c03d10a1bbd7c7e
  - Key: daily ops orchestrator runbook + scale primitives.

- V7: “daily ops speed parity”
  - PR #18 merge SHA: f4633ef84f214838e81fed93e23d968c0c6fcefe
  - PR #19 merge SHA: d7a2e81a8435a2d21a5132cf023a0261fa3de259
  - PR #20 merge SHA: b7ce6de8bfdac9594d51a55dbce14495b6d61f45
  - PR #21 merge SHA: 0df91affe0bf052dc379807eab30d2b47c394c6a
  - Key: parity + timing harnesses; reduced wasteful loops while preserving result quality.

- V8: “daily ops autopilot truth scale”
  - PR #22 merge SHA: d47c55f44664d3cd94eefc320b34cf3e954a0ad6
  - PR #23 merge SHA: a5202991f37bb32f36faaed6b89312713b97b670
  - Key: strict daily report artifact + strict validator gate; daily report outputs in exports/daily.

### Key files / systems to treat as current operational surface
- Ops workflow contracts:
  - docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md
  - docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md
  - docs/DAILY_SOP.md
- Daily report artifacts (expected):
  - exports/daily/<YYYY-MM-DD>/daily_ops_report.json
  - exports/daily/<YYYY-MM-DD>/daily_ops_report.md
- Canonical business math:
  - docs/inventory/Master_Inventory_Rules_v8.md
  - protocol/active/PO_making_logic_v2.md
- Truth/contract gates (baseline “green loop”):
  - python3 scripts/validate_params.py --strict
  - PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
  - python3 scripts/run_contract_suite.py --fixture small
  - python3 scripts/validate_single_truth_system.py
  - bash scripts/lint_docs.sh
  - bash scripts/check_no_db_tracked.sh
  - bash scripts/install_single_truth_ops_scheduler.sh --validate-only
  - python3 scripts/check_anchor_health.py --project-root <REPO_PATH>
  - python3 scripts/ops_status.py --project-root <REPO_PATH>
  - python3 scripts/validate_daily_ops_report.py --strict --path exports/daily/<date>/daily_ops_report.json

---

## North-star End State (definition of “final efficient state”)
The repo is considered “final efficient state” only when:
1) daily import + shipment/waybill flows run on schedule with deterministic pass/fail gates,
2) single-truth validations pass continuously across workbook, DB, and dashboard,
3) profit/cashflow decisions are generated from trusted facts without manual reconciliation loops,
4) manual work is limited to exception queues, not core processing,
5) regressions are detected within one run cycle and blocked before downstream damage.

Final completion rule (hard): 14 consecutive daily cycles with all hard gates green.

---

## Evaluation Approach (single triage pipeline — from any entry point)
We standardize evaluation into 5 layers, run in order, fail-closed:
Layer 1: Runtime + Scheduler
Layer 2: Data Truth Integrity
Layer 3: Domain Engines (PO / inventory / cashflow)
Layer 4: Execution APIs (fetch/assemble/waybill/shipping)
Layer 5: Governance + Docs (contracts, evidence completeness, deprecations)

This board’s primary deliverable is turning that model into a single deterministic command + artifacts.

---

# Phase List (sequential, single-agent execution)

## Phase V9-T0 — Baseline Reproduction + Evidence Scaffold
### Goal (measurable)
Reproduce baseline “green loop” twice consecutively with identical results and capture evidence.

### Inputs
- AGENTS.md / CLAUDE.md / docs/00_START_HERE.md / .claude/OPERATING.md
- Baseline gate commands listed above.

### Outputs (exact paths)
- exports/validation/board_v9_<YYYY-MM-DD>/V9-T0_baseline/
  - baseline_run_1.md
  - baseline_run_2.md
  - environment_snapshot.json (python version, venv path, cwd, key env vars)
- docs/OPS_ROLLOUT_EVIDENCE_BOARD_V9_SYSTEM_DOCTOR_2026-02-25.md (created, with empty placeholders for later phases)

### Definition of Done
Accepted as done only when:
- both baseline runs are green,
- evidence artifacts exist and are linked from the evidence doc,
- repo working tree is clean after each run.

### Validation/Gates
Run:
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
- python3 scripts/run_contract_suite.py --fixture small
- python3 scripts/validate_single_truth_system.py
- bash scripts/lint_docs.sh
- bash scripts/check_no_db_tracked.sh
- bash scripts/install_single_truth_ops_scheduler.sh --validate-only
- python3 scripts/check_anchor_health.py --project-root <REPO_PATH>
- python3 scripts/ops_status.py --project-root <REPO_PATH>

### Rollback / Backout
- git reset --hard <pre-board-sha> (only if nothing merged)
- If any DB writes occurred unexpectedly: restore db/app.db from latest backup and document incident.

### Stop-the-line Criteria
- Any gate fails or is skipped.
- Any write/apply executed without explicit env + --apply and a pre-backup recorded.
- Any nondeterminism detected (run_1 green, run_2 red).

---

## Phase V9-C1 — Build “System Doctor” (single evaluation entrypoint)
### Goal (measurable)
Add one deterministic command that:
- can start from any domain symptom,
- runs layered checks in correct fail-closed order,
- emits a decision-grade report (JSON + Markdown),
- exits non-zero when any CRITICAL check is red.

### Inputs
- docs/PLAN_BUSINESS_SYSTEM_END_TO_END_AUTONOMY_HORIZON_2026-02-25.md (evaluation layers + stop-lines)
- Existing scripts:
  - scripts/validate_params.py
  - scripts/validate_single_truth_system.py
  - scripts/check_anchor_health.py
  - scripts/ops_status.py
  - scripts/validate_daily_ops_report.py
  - (and other existing domain validators)

### Outputs (exact paths)
- scripts/system_doctor.py  (new)
- docs/ops/SYSTEM_DOCTOR_RUNBOOK.md (new)
- exports/diagnostics/<YYYY-MM-DD>/
  - system_health.json
  - system_health.md
  - system_health_checks.json (raw per-check results)
- tests/test_system_doctor_contract.py (new)

### Definition of Done
Accepted as done only when:
- `python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>` runs with no writes,
- report artifacts are created every run,
- doctor fails closed (non-zero exit) on injected critical failure in tests,
- doctor never runs Layer 2–5 if Layer 1 is red (fail-closed ordering contract),
- runbook exists and references only repo-relative paths.

### Validation/Gates
- Targeted:
  - PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_system_doctor_contract.py
- Full baseline gate stack (same as V9-T0)
- New command:
  - python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>

### Rollback / Backout
- git revert <merge_sha> (if promoted)
- No DB rollback needed (phase must be read-only)

### Stop-the-line Criteria
- System Doctor outputs success while a known failing underlying gate is red (“false-green”).
- Doctor silently ignores missing inputs (anchors/DB) instead of failing.

---

## Phase V9-C2 — Domain Scorecards (PO / Inventory / Cashflow) + Drift Packs
### Goal (measurable)
Make PO/inventory/cashflow evaluation decision-grade and daily-repeatable by adding:
- strict scorecards,
- drift packs with before/after diffs,
- publication blocks when any CRITICAL economics/truth signal is red.

### Inputs
- docs/inventory/Master_Inventory_Rules_v8.md (formulas/caps)
- protocol/active/PO_making_logic_v2.md
- Existing validators/generators:
  - scripts/update_po_dashboard.py (if present)
  - scripts/validate_po_money_gate.py
  - cashflow rebuild scripts + contracts
  - stock snapshot governance scripts/contracts

### Outputs (exact paths)
- scripts/build_domain_scorecards.py (new) OR extend existing drift-pack builder to include scorecards
- exports/daily/<YYYY-MM-DD>/
  - po_scorecard.json|.md
  - inventory_scorecard.json|.md
  - cashflow_scorecard.json|.md
  - truth_drift_report.json|.md
- tests:
  - tests/test_po_scorecard_contract.py
  - tests/test_inventory_scorecard_contract.py
  - tests/test_cashflow_scorecard_contract.py
  - tests/test_truth_drift_report_contract.py
- System Doctor integration:
  - Layer 3 must run scorecards and reflect CRITICAL failures.

### Definition of Done
Accepted as done only when:
- scorecards run read-only and deterministically on fixture,
- drift report clearly shows “resolved vs unresolved” mismatches,
- any CRITICAL mismatch blocks “publication” (doctor status red),
- strict validators are green for 3 consecutive daily cycles (tracked by artifact history).

### Validation/Gates
- Targeted tests for each scorecard + drift report
- Full baseline gate stack
- python3 scripts/system_doctor.py --strict (Layer 3 green required)

### Rollback / Backout
- Code rollback via git revert
- If this phase introduces any apply path: must be behind env + backup, with rollback documented (DB restore path)

### Stop-the-line Criteria
- Any scorecard depends on UI recomputation (Excel/UI layer doing business math).
- Any drift pack omits a critical mismatch class (e.g., part topology mismatch, paid flag drift).

---

## Phase V9-H1 — Execution Chain Parity + Performance Budgets (API/Waybill/Excel)
### Goal (measurable)
Guarantee that any “speed” or “refactor” work cannot regress quality, by making:
- parity tests mandatory (order IDs, assemble success set, PDF set, bundle set),
- stage timing artifacts mandatory,
- performance budgets measured and tracked (not guessed).

### Inputs
- scripts/run_kaspi_daily_ops.py and/or existing daily ops orchestrator
- scripts/download_waybills_api.py
- scripts/report_waybill_status.py (strict-stopline mode)
- excel_ui/run_build_waybills.command and excel_ui/run_full_import.command
- Existing parity + timing tests (from V7/V8)

### Outputs (exact paths)
- exports/perf/<YYYY-MM-DD>/daily_ops_timings.json|.md
- tests/test_daily_ops_result_parity_contract.py (new or expand)
- tests/test_daily_ops_timing_budget_contract.py (new or expand)
- docs/ops/DAILY_OPS_PERFORMANCE_BUDGETS.md (new)

### Definition of Done
Accepted as done only when:
- parity tests compare baseline vs optimized runs on fixture and PASS,
- timing artifacts are produced and budgets enforced (non-regression),
- System Doctor Layer 4 uses these tests/signals and fails closed.

### Validation/Gates
- Targeted tests for parity + timing
- Full baseline gate stack
- python3 scripts/system_doctor.py --strict (Layer 4 green required)

### Rollback / Backout
- git revert
- If any change touches DB apply flows: backup/restore mandatory

### Stop-the-line Criteria
- “HTTP success only” acceptance anywhere in assemble/ship/waybill chain.
- Any timing “improvement” without parity proof.

---

## Phase V9-O1 — Observability + Weekly Health Scorecard
### Goal (measurable)
Make system status decision-grade at a glance:
- daily: system_health + daily_ops_report + scorecards,
- weekly: a single scorecard showing reliability, capital safety, manual workload, and profit-risk blockers.

### Inputs
- System Doctor outputs
- exports/daily/ history
- ops scheduler contracts

### Outputs (exact paths)
- scripts/build_weekly_health_scorecard.py (new)
- docs/ops/WEEKLY_HEALTH_SCORECARD_CONTRACT.md (new)
- exports/health/weekly/<YYYY-WW>/
  - weekly_health_scorecard.json
  - weekly_health_scorecard.md
- tests/test_weekly_health_scorecard_contract.py (new)

### Definition of Done
Accepted as done only when:
- weekly scorecard builds deterministically from repo artifacts,
- clearly indicates: success rate, red causes, manual exceptions count, time budgets, and “publish blocks”.

### Validation/Gates
- Targeted weekly scorecard tests
- Full baseline gate stack
- python3 scripts/system_doctor.py --strict

### Rollback / Backout
- git revert
- read-only only (no DB writes)

### Stop-the-line Criteria
- any “hidden failure only in logs” category remains un-surfaced in doctor/scorecards.

---

## Phase V9-S1 — Governance + Docs Contamination Closure (active authority indexes)
### Goal (measurable)
Prevent operators from using stale/contradictory docs by enforcing:
- one active authority doc per domain,
- archived docs clearly labeled and excluded from “active contract” lint scope,
- CI tests that fail on schedule/contract contradictions in active docs,
- promotion evidence completeness (PR, SHAs, gate transcript, rollback steps).

### Inputs
- docs/00_START_HERE.md, docs/DAILY_SOP.md
- existing lint + docs contract tests
- existing evidence docs patterns

### Outputs (exact paths)
- docs/authority/INDEX.md (new) (links to active authority docs per domain)
- docs/archive/ (new or expanded)
- scripts/lint_docs_active_scope.py (new) OR expand scripts/lint_docs.sh with active-scope rules
- tests/test_docs_authority_index_contract.py (new)
- tests/test_active_docs_no_schedule_contradictions.py (new)

### Definition of Done
Accepted as done only when:
- active docs scope is contradiction-free under tests,
- archived docs do not affect ops decisions (must contain top banner + link to active authority),
- evidence docs are machine-checkable (no TODO/TBD placeholders allowed).

### Validation/Gates
- docs lint + docs contract tests PASS
- Full baseline gate stack
- System Doctor Layer 5 green

### Rollback / Backout
- git revert
- no DB changes

### Stop-the-line Criteria
- any active docs still reference deprecated schedules/contracts without explicit “ARCHIVED” labeling.

---

## Final Acceptance Criteria (Board V9 complete)
Board V9 is accepted only when:
1) System Doctor exists, is deterministic, fails closed, and produces artifacts every run.
2) System Doctor can evaluate from any entry point (PO/cashflow/inventory/API/docs) using layered checks.
3) Cross-domain scorecards + drift report are produced daily and block publication on red.
4) Parity + performance budgets exist for daily ops execution chain.
5) Weekly health scorecard exists and is deterministic.
6) Full promotion gate stack is green and captured in:
   - exports/validation/board_v9_<YYYY-MM-DD>/full_gates_green_final.md
7) Scope guard: no uncontrolled writes; any apply requires explicit env + --apply + pre-backup + rollback proof.

---

## If attachments are missing — assumptions policy
1) Prefer in-repo canonical docs over pasted summaries.
2) If a referenced file/path is missing:
   - mark it explicitly as MISSING in the evidence doc,
   - fail closed if it is required for correctness/capital safety,
   - otherwise proceed with a clearly stated assumption and add a test/contract that will fail when the file reappears with incompatible content.
3) If sources conflict:
   - resolve using the single-truth ladder:
     docs/inventory/Master_Inventory_Rules_v8.md → docs/00_START_HERE.md → protocol/active/PO_making_logic_v2.md → docs/inventory/Sales_Data_Model_V16.md → docs/ARCHITECTURE.md
   - record the resolution in .claude/DECISIONS.md with date + evidence.