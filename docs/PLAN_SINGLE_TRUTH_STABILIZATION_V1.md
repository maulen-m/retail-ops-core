# PLAN_SINGLE_TRUTH_STABILIZATION_V1
As-of: 2026-02-09
Owner: Main repo only (~/Docs/Autonomous_business)
Status: PROPOSED

## Why this plan exists
We already added a “stop-the-bleeding” workbook anchor validator that prevents published sales truth
from exceeding the CRM workbook by > tol% (anti-inflation). The strict chain is still RED due to:
1) on_delivery_freeze residual balances on completed/cancelled/returned orders
2) workbook breach on 2026-02-07 (>5% published net_rev over workbook)
3) 2 failing tests in tests/test_crm_transactional_promote.py

This plan turns those into GREEN strict gates with the smallest safe changes possible.

## Single-truth principles (non-negotiable)
- Keep one published interface for sales truth (daily + line) used by Business-Insides and dashboards.
- Workbook is an anchor/guardrail: DB MAY be lower (returns/cancels), DB MUST NOT be higher beyond tolerance.
- No write-side actions unless BOTH:
  - env flag is enabled, AND
  - explicit CLI flag (e.g. --apply) is provided
- Tests first (fail-first evidence).
- Use worktrees to keep main clean; do not run DB write actions concurrently across worktrees.

## Success criteria (measurable)
A. Strict gates GREEN:
- python3 scripts/validate_params.py --strict  -> PASS
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q   -> PASS
- python3 scripts/run_contract_suite.py --fixture small -> PASS

B. Single-truth integrity GREEN (with workbook gate enabled):
- AB_CRM_WORKBOOK_PATH=<real path> python3 scripts/validate_sales_vs_workbook_anchor.py -> PASS
- python3 scripts/validate_on_delivery_freeze.py -> PASS (no completed/cancelled/returned residuals)
- python3 scripts/validate_single_truth_system.py -> PASS

C. Operator outputs sane:
- BUSINESS_INSIDES last-7-days table does not inflate beyond workbook guardrail
- No single-day “spikes” caused by restamping/duplication.

## Work method (to avoid dirty repo blockers)
Follow .claude/PARALLEL_WORK.md and .claude/GIT_HYGIENE.md:
- One worktree per task branch
- One “scribe” branch touches .claude logs; other branches avoid editing .claude/*
- No concurrent DB writes across worktrees; isolate AB_DATA_DIR if needed

## Phase 1 — Unblock strict gate: on_delivery_freeze residual settlement
Goal: make validate_on_delivery_freeze PASS.

1) Tests first
- Add a failing unit test that constructs a tiny DB where:
  - order is COMPLETED (or CANCELLED/RETURNED)
  - INVENTORY_ON_DELIVERY_COST has a non-zero residual
  - validator fails
- Add a failing test for the reconcile script:
  - dry-run produces a deterministic remediation plan
  - apply requires ENABLE_CASHFLOW_WRITE=1 and --apply
  - repeated apply is idempotent (0 new events on second run)

2) Implementation (smallest safe change)
- Add (or extend) a script:
  scripts/reconcile_on_delivery_freeze_residuals.py
  - Default dry-run
  - Detect residuals by (order_id, sku_id) for terminal statuses
  - Generate balancing settlement events (idempotent keys)
  - Apply only with ENABLE_CASHFLOW_WRITE=1 and --apply
  - Emit a report file (exports/on_delivery_residuals_<asof>.md)

3) Verification
- python3 scripts/validate_on_delivery_freeze.py -> PASS
- python3 scripts/validate_params.py --strict -> moves past the previous blocker (or next blockers become visible)

## Phase 2 — Fix workbook anchor breach day (2026-02-07) at the source
Goal: AB_CRM_WORKBOOK_PATH=... validate_sales_vs_workbook_anchor.py PASS.

1) Diagnostics (read-only)
- Use/extend scripts/compare_sales_sources_to_workbook.py to output:
  - workbook totals
  - sales_fact_v2 totals
  - published truth totals
  - optional store-level breakdown (if store_code available)
- Add a “breach explainer” mode:
  scripts/explain_workbook_breach_day.py --date 2026-02-07
  Output a diff table:
  - top SKUs by net_rev delta
  - top orders by delta if order_id exists in DB truth
  - shows whether delta comes from:
    (a) duplicate rows
    (b) wrong date dimension (shipped vs delivered)
    (c) wrong store scope vs workbook
    (d) wrong net_rev formula input

2) Tests first
- Add a failing regression test that reproduces the 2026-02-07 breach pattern
  (small fixture DB + minimal workbook rows) and asserts validator fails.
- Then implement the smallest fix that makes it pass.

3) Implementation
- Prefer fixing published truth view/table construction or date filtering/joins,
  not “tweaking tolerance”.
- If the breach is due to workbook scope mismatch:
  - add explicit config to define which stores/channels workbook represents
  - compare like-for-like and document it

4) Verification
- AB_CRM_WORKBOOK_PATH=<real path> python3 scripts/validate_sales_vs_workbook_anchor.py --as-of 2026-02-08 -> PASS

## Phase 3 — Restore full green pytest (test_crm_transactional_promote.py)
Goal: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q PASS.

1) Identify why the 2 tests fail (schema drift, new published truth rules, date window).
2) Fix with minimal scope:
- Update test fixtures or code path to reflect the new published sales truth contract.
- Ensure tests are deterministic and do not require external files or seeded local DBs.

## Phase 4 — COGS quality hardening (after 1–3 are green)
Goal: profit realism and near-zero unresolved rows.

1) Enforce “no silent zero COGS” in published truth windows:
- unresolved rows must be explicit and surfaced (NULL + surfaced counts)
2) Improve inputs:
- ensure dim_sku has base_cost + weight_kg + mapping coverage
- keep write-gated sync for restoring missing weights from Dim_SKU_Light
3) Add a strict threshold gate:
- cogs_resolved_pct >= target for the last N days
- unresolved_rows == 0 for published window when required inputs exist

## Phase 5 — Operationalize workbook gate (ops/runbook)
Goal: workbook anchor is consistently enforced in real daily runs.

- Update runbooks (DAILY SOP / ops docs) to set AB_CRM_WORKBOOK_PATH in the environment.
- Provide a single canonical command for operators:
  AB_CRM_WORKBOOK_PATH=... python3 scripts/validate_params.py --strict

## Phase 6 — Ads integration (defer until green)
- Keep ads as sidecar metrics only until sales truth + on-delivery are stable.
- Do not promote profit-after-ads to operator truth until Phase 1–3 are GREEN.

## Required gates (must be green before merge)
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
- python3 scripts/run_contract_suite.py --fixture small
- python3 scripts/validate_single_truth_system.py
- scripts/lint_docs.sh
- scripts/check_no_db_tracked.sh

## Rollback
- git revert <commits...>
- restore db/app.db from the pre-change backup recorded in SESSION_LOG
