# PLAN G40–G44 — Cashflow Trusted Dashboard V3 (API-forward)

## Why this exists
Cash is oxygen. We need a cashflow control plane that:
1) is **autonomous** (no daily Kaspi Pay statement downloads),
2) is **decision-grade** for PO payments and OPEX,
3) is **explicit about trust** (statement-backed vs modelled).

We accept small deviations vs the bank ledger in exchange for always-on maintenance,
but we must be honest about which days are modelled.

## Current state (as of 2026-01-24)
Two states exist and must be unified:
- Main repo has the API-first doctrine (orders → events mapping, 14-day rolling sync constraint, refund rules).
- Cashflow worktree has MT940 backfill + CASH_OPENING fix, trust layer, inventory cost anchor+delta, and bank_accounts.yaml.

This plan starts with unifying those so we build V3 on one canonical codebase.

## Locked rules (do not reinterpret later)
### Orders → cashflow
- Sales accrual trigger: **COMPLETED** (delivered) → receivable increases.
- Refund/return: reverse receivable; reverse commission; delivery fee remains a cost.
- Cash payouts: model as **expected inflows** using payout lag model; reconcile to statements when available.

### 14-day API constraint (hard rule)
Kaspi API only supports max 14 days per query. Therefore:
- Every day, we run a full rolling 14-day sync for all stores.
- If the sync is stale, cashflow is no longer decision-grade.

### Inventory cost (cheap + validated)
- Inventory cost in cashflow = warehouse current_stock at cost (not inbound).
- Anchor once from snapshot; delta via PO arrivals and COGS.
- Drift validator compares cashflow inventory_cost_close vs snapshot-at-cost.

### Cash reality
- MT940 statements are the highest fidelity and are ingested for historical backfill.
- After the last statement date, cash is modelled unless a manual balance check is imported.
- `config/bank_accounts.yaml` is treated as a manual balance check input.

## Phases

### G40 — Unify truth surface (merge worktree + lock policies)
Deliver:
- Merge/cherry-pick MT940 backfill + trust layer + inventory scripts + bank_accounts.yaml into main.
- Normalize MT940 code mapping in one place.
Gate:
- pytest, cashflow invariants, EOD run all PASS; repo clean.

### G41 — API-forward translator (orders → receivables + expected payouts)
Deliver:
- Translator that converts Kaspi order transitions into idempotent cashflow events.
- Expected payouts scheduled by payout lag model (base + conservative).
- Hard gate: stale store sync fails EOD.
Gate:
- Translator idempotency test; invariants PASS.

### G42 — Cash anchoring (MT940 + manual balance checks)
Deliver:
- MT940 recon report + trust report shows last_statement_date and coverage.
- bank_accounts.yaml importer produces “balance check” events for non-statement accounts.
Gate:
- Recon within tolerance; trust report updates deterministically.

### G43 — Dashboard V3
Deliver:
- Owner-grade HTML with trust banner + scenario toggles + min cash.
Gate:
- Dashboard export stable; visual sanity pass.

### G44 — PO affordability gate
Deliver:
- Preflight script: PASS/FAIL + explanation; integrated into EOD.
Gate:
- Tests PASS; EOD PASS; failure logs to .claude/ISSUES.md.

## How to execute this plan without losing track
### Use the agent memory files (single-source-of-truth)
- `.claude/GOALS.md` — phases (G40–G44) and gates (definition of done).
- `.claude/TASKS.md` — the “next 3 concrete tasks” only; keep it short.
- `.claude/PROGRESS.md` — record gate outputs (command + PASS/FAIL + date).
- `.claude/ISSUES.md` — every blocker; include exact error excerpts.
- `.claude/SESSION_LOG.md` — commands run, important paths, DB backups created.

### Session discipline
1) Read AGENTS.md (operating contract).
2) Pick the next goal from GOALS.md.
3) Update TASKS.md with only the next 3 tasks.
4) Execute until a gate fails; log failures to ISSUES.md; fix; rerun gates.
5) Record PASS evidence in PROGRESS.md.

## Key entrypoints
- `python3 scripts/run_end_of_day.py --verbose`
- `python3 scripts/rebuild_cashflow_calendar.py`
- `python3 scripts/update_cashflow_dashboard.py`
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_inventory_cost_drift.py`
# SUPERSEDED (Truth Contract 2026-01-26)
This plan assumes receivables + payout lag. Current truth contract uses **D1 cash-in at DELIVERED** (no receivables model).  
Use for historical context only. See: `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`.
