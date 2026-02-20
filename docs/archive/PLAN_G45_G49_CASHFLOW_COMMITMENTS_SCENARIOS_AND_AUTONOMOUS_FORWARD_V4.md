# PLAN G45–G49 — Cashflow V4: Commitments realism + scenarios + autonomous forward (API) + trusted UI

Repo: ~/Docs/Autonomous_business  
Branch currently in use: integration/plan2-doc-floor-po5  
Owner intent: cashflow is the capital control plane (cash is oxygen). The system must prevent “looks fine today → bankrupt in 20 days” decisions.

## Why this exists (physics, not preferences)

Kaspi reality:
- Sales do NOT instantly become cash.
- Sales create receivables, then later payouts become cash.
- Orders can be cancelled/returned (especially before/within the 14-day window).
- POs create large cash-out commitments that can lag or split.

Therefore, decision-grade cashflow requires:
1) a trusted cash anchor (statements or balance checks),
2) forward modelling from orders + payout lag,
3) realistic commitments (PO payments + OPEX),
4) a preflight gate that blocks unsafe exports unless explicitly overridden.

## Current state (what is already DONE)

G40–G44 are complete and safe-shipped:
- Cashflow preflight gate integrated into run_end_of_day.
- PO payment plan commitments exist (currently deferred to 2026-03-01 due to CNY).
- Balance checks import from config/bank_accounts.yaml works (timestamp-safe).
- On-delivery econ export runs daily in EOD.
- Kaspi “Артикул” numeric prefix normalization and “Podium RASH-32 → LINE52” override added.
- Gates PASS, oracle packs exist.

## What is still missing (why we need V4)

### Problem A — Commitments are not “realistic enough”
If we defer 100% PO payments to March, preflight can be green while cash is actually tight in February due to partial payments, deposits, freight, or unforeseen expenses.

**We need commitments that reflect reality: split payments + scenarios.**

### Problem B — On-delivery should influence planning without contaminating truth
We should not treat ON_DELIVERY as sold, but we need visibility + optional scenario credit (aggressive) so preflight isn’t overly pessimistic.

### Problem C — Trust banner must explain what’s REAL vs MODELLED vs FORECAST
A decision dashboard must clearly label:
- last statement-backed day,
- last balance-check snapshot,
- last orders sync age per store,
- how many days are modelled vs actual.

## Target end state (most efficient “correct” V4)

1) Commitments are scenario-based:
   - Base commitments (best guess)
   - Conservative commitments (earlier PO payments / extra buffer)
   - Preflight FAILS if conservative goes below cash_floor.

2) Orders API drives forward receivables modelling daily:
   - Delivered/Completed → receivable accrual
   - ON_DELIVERY → tracked separately (not counted as sold), optionally used only in “aggressive scenario”.

3) Trust is explicit:
   - ACTUAL days: statement-backed or balance-check matched
   - MODELLED days: post-statement, relying on orders + payout model
   - FORECAST: beyond known orders

4) UI is decision-grade:
   - clear summary (cash, receivables, inventory cost, capital)
   - min cash date/amount for base + conservative
   - upcoming commitments table (PO/OPEX)
   - on-delivery totals visible

---

# Phase plan

## G45 — Commitments realism (split payments + conservative scenario)
### Deliverables
- Extend PO payment plan format to support split payments and scenario tags:
  - `data/cashflow/po_payment_plan.csv` should allow multiple rows per PO with dates/amounts and (scenario=base|conservative).
- Update importer to load both scenarios and store them separately (or tag commitments).
- Update `cashflow_preflight_po.py` (or equivalent) to compute:
  - min_cash_base
  - min_cash_conservative
  - FAIL if min_cash_conservative < cash_floor_kzt (configurable)

### Acceptance criteria
- With a “deposit now + remainder later” schedule, preflight reflects the dip.
- Conservative scenario is what blocks exports (unless explicitly overridden).
- Output file: `exports/min_cash_summary.txt` shows both scenarios clearly.

## G46 — On-delivery policy: visibility + optional scenario credit
### Deliverables
- Define canonical mapping in ONE place (doc + code) for status categories:
  - COMPLETED/DELIVERED/CLOSED → accrual eligible
  - SENT/ON_DELIVERY → “at-risk receivable” bucket (not sold)
  - CANCELLED/RETURNED → reversal rules
- Update cashflow dashboard HTML to display:
  - on-delivery order count + expected net value (as separate section)
- Add an optional aggressive scenario that includes on-delivery as partial credit:
  - e.g., credit_rate = 0.6 (configurable)

### Acceptance criteria
- Base scenario remains cash-safe (no on-delivery counted as sold).
- Aggressive scenario exists for “what if most on-delivery converts”.
- Trust report shows the split.

## G47 — Trust banner v4 (statement vs balance-check vs modelled)
### Deliverables
- Upgrade trust report + banner:
  - last_statement_date (if any)
  - last_balance_check_ts
  - last_orders_sync_ts per store
  - modelled_days count
  - warning if any store sync stale beyond threshold (warn vs fail decision stays in AGENTS/cashflow contract)

### Acceptance criteria
- Dashboard always states: “ACTUAL until X”, “MODELLED after X”, and why.
- EOD gate behavior is explicit (fail vs warn).

## G48 — Calibration + reconciliation (keep model grounded without daily statements)
### Deliverables
- Add a report that compares:
  - expected payouts (from modelled orders) vs reality when statements exist
  - drift metrics over the last N days
- Add guidance workflow:
  - “Import statements monthly or when drift > threshold”
  - “Import balance check weekly” (manual snapshot via config/bank_accounts.yaml)

### Acceptance criteria
- A single report answers: “Is the model drifting? By how much? Since when?”

## G49 — Merge readiness + governance hygiene
### Deliverables
- Ensure all new rules live in the correct owning docs and AGENTS.md stays minimal.
- Add/extend tests for:
  - commitment scenario split import
  - on-delivery classification
  - trust banner derivation
  - preflight dual-scenario failure behavior

### Acceptance criteria
- `python3 scripts/run_end_of_day.py --verbose` passes.
- `python3 scripts/validate_cashflow_invariants.py` passes.
- `pytest -q` passes.
- Oracle pack created with:
  - changed files
  - exports (dashboard, calendar, min_cash_summary, trust report)
  - DB backup path

---

# Required gates (do not claim done without these)

1) python3 scripts/validate_params.py --strict
2) ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose
3) python3 scripts/validate_cashflow_invariants.py
4) pytest -q
5) scripts/check_no_db_tracked.sh
6) scripts/lint_docs.sh (if docs touched)

Stop immediately on first failure. Log failure in .claude/ISSUES.md and .claude/SESSION_LOG.md.

# Rollback
- Always DB-backup before any write.
- If any regression: `git revert <commit>` and restore DB backup.
# SUPERSEDED (Truth Contract 2026-01-26)
This plan assumes receivables + payout lag. Current truth contract uses **D1 cash-in at DELIVERED** (no receivables model).  
Use for historical context only. See: `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`.
