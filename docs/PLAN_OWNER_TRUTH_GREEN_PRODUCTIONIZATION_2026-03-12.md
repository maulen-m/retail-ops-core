# PLAN_OWNER_TRUTH_GREEN_PRODUCTIONIZATION_2026-03-12

## Purpose
Take the current green owner-truth closeout and convert it from “green technical evidence” into “clean, committed, owner-usable production state” without reopening source-truth debates or broad subsystem work.

Execution model:
- single-agent
- sequential
- fail-closed
- one worktree / branch only
- human only for prompt copy/paste unless a proven external auth issue appears

Baseline assumptions:
- active repo/worktree: `~/Docs/wt_webui_owner_truth_operationalization_v1`
- active branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- canonical target head: `761c66775042adeed34fa66b3b102f8acf7d691f` (per supplied latest handoff)
- earlier green evidence references may still mention `bc63db87...` / `b6d6bbe...`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- current live owner-truth chain is already green
- no new WebUI scrape
- no replay fallback in live mode
- no new DB write unless a new defect is separately proven

Evidence root:
- `exports/validation/owner_truth_green_productionization/2026-03-12/`

Global non-negotiables:
1. Do not break any current green gate.
2. Do not fabricate runtime logs or derived artifacts.
3. Do not reopen historical lineage cleanup or scheduler/import parity proving unless explicitly starting a deferred phase.
4. Do not expand broad business modules before the current owner surfaces are productionized.
5. Do not claim “done” until the green state is reference-consistent and owner-visible.

---

## Phase P0 — Canonical Green Baseline Reconciliation

### Goal (measurable)
Make all release/oracle references point to one canonical committed green head.

### Inputs
- current worktree at `codex/TASK-webui-owner-truth-operationalization-v1`
- `merge_manifest.json`
- `merge_manifest.md`
- `full_gates_green_live_ops.md`
- latest oracle pack docs
- supplied current head from latest handoff

### Outputs
- `exports/validation/owner_truth_green_productionization/2026-03-12/readcheck.md`
- `exports/validation/owner_truth_green_productionization/2026-03-12/worktree_status.txt`
- `exports/validation/owner_truth_green_productionization/2026-03-12/release_reference_reconciliation.md`
- `exports/validation/owner_truth_green_productionization/2026-03-12/checkpoint_decision.md`
- one of:
  - checkpoint commit SHA(s) in `checkpoint_decision.md`
  - or `exports/validation/owner_truth_green_productionization/2026-03-12/worktree_checkpoint.patch`

### Definition of Done
Accepted as done only when:
- exact branch/head are recorded
- dirty/clean state is recorded
- rollback anchor is recorded
- all active release references clearly map to one canonical committed green head

### Validation/Gates
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert/drop P0 artifacts or reset to checkpoint commit
- no DB writes and no code changes in P0

### Stop-the-line criteria
- unexplained head mismatch
- active release refs still point to conflicting heads
- tracked/staged `.db` file appears

---

## Phase P1 — Owner Profit Semantics Closeout

### Goal (measurable)
Turn the current provisional `Owner Profit Daily` trust state into an explicitly acceptable production decision.

### Inputs
- `build_owner_profit_daily.py`
- `owner_profit_daily.json`
- `owner_profit_daily.md`
- `trust_report.json`
- `docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md`
- current upstream monthly-review lock semantics

### Outputs
- updated `docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md`
- updated `build_owner_profit_daily.py` if needed
- updated/new targeted tests if needed
- refreshed:
  - `exports/owner/2026-03-09/owner_profit_daily.json`
  - `exports/owner/2026-03-09/owner_profit_daily.md`
  - `exports/validation/owner_profit_daily/2026-03-09/trust_report.json`
- `exports/validation/owner_truth_green_productionization/2026-03-12/profit_semantics_decision.md`

### Definition of Done
Accepted as done only when:
- the trust banner is either upgraded to a non-provisional production state, or
- the provisional state is explicitly accepted by contract as production-usable with exact limitations
- no current green gate regresses

### Validation/Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_surfaces.py`
- `python3 -m py_compile scripts/build_owner_profit_daily.py`
- `python3 scripts/build_owner_profit_daily.py --as-of 2026-03-09 ...`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`

### Rollback / backout strategy
- revert P1 code/docs/tests only
- preserve pre-change trust artifacts for comparison

### Stop-the-line criteria
- provisional banner removed without explicit contract evidence
- any green gate turns red

---

## Phase P2 — Owner Daily Brief

### Goal (measurable)
Create one combined daily owner-facing brief from the three already-green surfaces.

### Inputs
- `owner_profit_daily.json`
- `cash_risk_daily.json`
- `po_sku_daily.json`
- their trust reports

### Outputs
- `scripts/build_owner_daily_brief.py`
- `tests/test_owner_daily_brief.py`
- `exports/owner/2026-03-09/owner_daily_brief.json`
- `exports/owner/2026-03-09/owner_daily_brief.md`
- `exports/validation/owner_daily_brief/2026-03-09/trust_report.json`

### Definition of Done
Accepted as done only when one file truthfully shows:
- revenue / COGS / ads / OPEX / profit
- near-term cash-risk summary
- reorder / freeze / kill summary
- trust banner per section plus overall status

### Validation/Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_brief.py tests/test_owner_daily_surfaces.py`
- `python3 -m py_compile scripts/build_owner_daily_brief.py`
- `python3 scripts/build_owner_daily_brief.py --as-of 2026-03-09 ...`
- if cashflow touched: `python3 scripts/validate_cashflow_invariants.py`
- if PO touched: `python3 scripts/validate_po_dashboard_invariants.py`

### Rollback / backout strategy
- revert P2 code/docs only
- restore prior output files from artifacts if needed

### Stop-the-line criteria
- brief omits trust semantics
- brief contradicts any underlying owner surface

---

## Phase P3 — 3-Day Review Automation

### Goal (measurable)
Reduce owner/manual work by making one command refresh the three owner surfaces, the brief, and the scorecard.

### Inputs
- P1/P2 outputs
- current `OWNER_PROGRESS_SCORECARD_2026-03-11.md`
- existing owner-surface builders

### Outputs
- `scripts/run_owner_review_cycle.py`
- `tests/test_run_owner_review_cycle.py`
- refreshed scorecard file or dated successor
- `exports/validation/owner_truth_green_productionization/2026-03-12/scorecard_refresh_report.md`

### Definition of Done
Accepted as done only when one command regenerates:
- `owner_profit_daily`
- `cash_risk_daily`
- `po_sku_daily`
- `owner_daily_brief`
- scorecard refresh report

### Validation/Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_run_owner_review_cycle.py tests/test_owner_daily_surfaces.py`
- `python3 -m py_compile scripts/run_owner_review_cycle.py`
- `python3 scripts/run_owner_review_cycle.py --as-of 2026-03-09 ...`

### Rollback / backout strategy
- revert P3 code/docs/tests only

### Stop-the-line criteria
- automation hides a red trust banner
- automation mixes stale and fresh artifacts

---

## Phase P4 — Release / Oracle Refresh from Canonical Tip

### Goal (measurable)
Refresh merge/release/oracle evidence from the canonical committed head after P0–P3.

### Inputs
- P0–P3 outputs
- current merge/release/oracle artifacts

### Outputs
- refreshed:
  - `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json`
  - `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md`
  - `exports/validation/owner_truth_release/2026-03-09/full_gates_green_live_ops.md`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/PACK_SUMMARY.md`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/bundle.md`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/oracle_files_manifest.txt`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`
- `exports/validation/owner_truth_green_productionization/2026-03-12/release_refresh_report.md`

### Definition of Done
Accepted as done only when:
- merge manifest remains GREEN
- all release/oracle docs point to the canonical head
- rollback mapping is explicit
- canonical merged-orders CSV is included

### Validation/Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`

### Rollback / backout strategy
- revert P4 docs/pack refresh only
- preserve previous green evidence

### Stop-the-line criteria
- pack still points at stale or dirty-only local state
- wrong canonical CSV is packed
- rollback mapping missing

---

## Phase P5 — Optional Scheduler/Import Proving

### Goal (measurable)
If desired, run separate scheduler/import parity proving without making it part of the owner-truth green closeout.

### Inputs
- current green owner-truth release
- deferred scheduler/import proving scope

### Outputs
- separate proving plan/evidence under a separate validation root

### Definition of Done
Accepted as done only when this proving is explicitly separate and does not regress owner-truth green.

### Validation/Gates
- as defined in the separate proving plan

### Rollback / backout strategy
- separate from this closeout

### Stop-the-line criteria
- any regression in current owner-truth green chain

---

## Phase P6 — Deferred Scale Queue Lock

### Goal (measurable)
Keep broader expansion visible but out of the current productionization merge.

### Inputs
- current merge manifest
- current scorecard
- deferred items list

### Outputs
- `exports/validation/owner_truth_green_productionization/2026-03-12/deferred_scale_backlog.md`

### Definition of Done
Accepted as done only when:
- broader items remain explicit and out of scope
- no unrelated cleanup or architecture detour enters the closeout

### Validation/Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert P6 backlog doc only

### Stop-the-line criteria
- deferred work is silently pulled into the closeout
- parallel worktrees are introduced without necessity

---

## If attachments are missing — assumptions policy
- If older blocked-state bundles conflict with the latest 2026-03-12 green closeout artifacts, prefer the latest green closeout artifacts.
- If the current worktree contains additional dirty delta not represented in the current green pack, freeze it first before edits.
- If no clean commit/reference reconciliation can be made safely, emit a checkpoint patch and stop instead of forcing packaging.
- If `Owner Profit Daily` semantics cannot be fully unlocked without broader upstream changes, keep the explicit provisional banner and stop after documenting the exact limitation.
- If any new red gate appears, stop and emit a fresh divergence/closeout pack before continuing.