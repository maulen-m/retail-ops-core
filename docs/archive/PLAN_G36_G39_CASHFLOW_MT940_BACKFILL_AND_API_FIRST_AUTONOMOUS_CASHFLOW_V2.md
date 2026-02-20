# PLAN G36–G39 — Cashflow MT940 backfill + API-first autonomous cashflow (no daily Kaspi Pay)

**Repo:** ~/Docs/Autonomous_business  
**Today context:** Kaspi Pay web cannot be automated daily (QR login + session expiry).  
**New principle:** Statements are **one-time historical backfill**; future is **Kaspi Orders API rolling sync + payout model + commitments**.

## Why we are doing this (physics)
Cashflow is a daily roll-forward state machine:
- Cash(t) = Cash(t−1) + CashIn(t) − CashOut(t)
We cannot keep Cash(t) correct without observing cash-in (payout timing) and cash-out (PO payments/OPEX).
Kaspi Pay statements are the only ground-truth for cash-in/out, but daily downloads are not maintainable.
So:
1) Import statements once to learn truth and calibrate payout timing.
2) For future, model cash-in from order lifecycle + payout-lag model and keep cash-out via commitments/PO payments.
3) Show TRUST explicitly (actual vs modelled), so we don't confuse a projection with reality.

## Current state (already exists)
- Append-only cashflow events spine with idempotency via event_hash + guarded writes.
- Cashflow daily rollup + dashboard export exists.
- Kaspi Orders API rolling 14-day sync is required (API limit) and documented.
- docs/KASPI_ORDER_CASHFLOW_TRACKING.md defines:
  - commission refunded on returns
  - delivery fees not refunded
  - 14-day refund window / closure
  - daily rolling sync is mandatory.

## Scope changes vs old plan
Old: ingest bank statements daily (not feasible).  
New:
- **G36:** One-time MT940 backfill from 2024-08-01 → yesterday for all store accounts.
- **G37:** Autonomous future cashflow via daily rolling Orders API sync + payout model.
- **G38:** Trust + reconciliation layer (actual vs modelled vs manual).
- **G39:** Trusted dashboard V2 (clear, decision-grade UI).

---

# G36 — One-time MT940 statement backfill (2024-08-01 → yesterday)

## Inputs
- Folder with MT940 statement TXT files, e.g.:
  ~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/kaspi_pay/statements/kaspi_stores
- config/kaspi_pay_accounts.yaml maps store_code -> account_id (IBAN). Must include *all* accounts we ingest.

## Deliverables
1) `scripts/import_kaspi_pay_mt940.py`
   - Reads MT940 files and produces normalized rows:
     - account_id, store_code, value_date, dc_mark, amount_kzt, code_86, description, customer_ref, bank_ref
   - Idempotent import into fact_cashflow_events using event_hash.
   - DRY-RUN default; apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
2) `config/kaspi_mt940_codes.yaml` (or .json)
   - Maps :86: codes (e.g. 190, 851, 858, 191, 342, 421, 841, 880, …) into categories:
     - PAYOUT_RECEIVED, KASPI_FEES, DELIVERY_FEES, ADS, BONUS, TRANSFER, LOAN_PAYMENT, REFUND, UNKNOWN
   - Unknown codes are allowed but must be tagged UNKNOWN and surfaced in the report.
3) `exports/mt940_backfill_report_<cutoff>.md`
   - Counts by account + code + category
   - Date range covered
   - List of unknown codes with sample descriptions
4) `exports/mt940_cash_recon_<cutoff>.csv`
   - For each imported account:
     - statement opening balance, statement closing balance
     - computed cash delta from imported txns
     - recon_error (must be 0 within tolerance)
   - If not 0 → STOP and debug parser.

## Implementation notes (important)
- These MT940 files are a single continuous statement per account (not daily segments):
  they contain one :60F (opening) and one :62F (closing) and many :61/:86 transactions.
- We must parse:
  - :25: account
  - :60F: opening balance
  - :62F: closing balance
  - :61: value_date + D/C + amount + refs
  - :86: code + text (?00/?21/etc)
- We must store enough metadata to audit a transaction later (refs + description).

## Acceptance criteria
- Import completes for all accounts with no duplicates (event_hash unique).
- Recon passes: opening + sum(txns) = closing for each account.
- Unknown codes list exists (if any), but does not block import.

---

# G37 — Autonomous future cashflow from Kaspi Orders API (no statements)

## Problem
After cutover, we cannot observe real payouts/cash directly without statements.
We will model cash-in using Orders API + payout-lag model calibrated from G36.

## Deliverables
1) Hard gate: **daily rolling 14-day sync must run, no exceptions**
   - Add/extend a sync-log table or file that records per store:
     - last_success_ts, min_date_seen, max_date_seen, rows_inserted/updated
   - Add invariant: FAIL EOD if last_success_ts > 25h for any store.
2) `scripts/build_payout_model_from_history.py`
   - Uses historical MT940 category PAYOUT_RECEIVED (code 190) and historical order accrual
     to infer payout lag distribution (e.g. median, p80).
   - Outputs a small config:
     - payout_lag_days_base, payout_lag_days_conservative
3) `core/cashflow/payout_model.py` (or similar)
   - Deterministically assigns payout dates for order net-revenue accruals.
4) Update cashflow rebuild:
   - Use Orders API-derived economics for:
     - net sale to seller
     - commission
     - delivery fees
     - refunds + commission reversal rule (delivery not refunded)
   - Generate:
     - SALE_ACCRUED (Receivables +)
     - PAYOUT_EXPECTED (Cash +, Receivables -) for post-cutover
     - Keep existing commitments for OPEX and PO payments as cash-out truth.

## Acceptance criteria
- run_end_of_day produces non-empty cashflow_calendar beyond the cutover without requiring statements.
- validate_cashflow_invariants passes.
- A “last order sync age” check is enforced and can block the pipeline if stale.

---

# G38 — Trust layer: ACTUAL vs MODELLED vs MANUAL

## Deliverables
1) Tagging
   - Ensure every cashflow event is tagged by source class:
     - STATEMENT_ACTUAL, ORDER_MODELLED, MANUAL
   - (Prefer not to change schema; encode in source field or add a small enum column if safe.)
2) `exports/cashflow_trust_report_<cutoff>.md`
   - last_statement_date
   - number of days fully statement-backed
   - for modelled days: cash-in uncertainty band (base vs conservative payout lag)
3) Optional low-friction “cash reality check”
   - Template: data/cashflow/cash_balance_checks.csv
   - Script imports a single daily balance number and creates a MANUAL adjustment event:
     - This is NOT a statement ingest, just a quick anchor for accuracy.

## Acceptance criteria
- Dashboard clearly indicates what is actual vs modelled.
- No silent mixing: all charts/summary show trust label.

---

# G39 — Trusted Cashflow Dashboard V2 (decision-grade UI)

## Deliverables
1) Update `scripts/update_cashflow_dashboard.py` output HTML to include:
   - Summary cards:
     - Cash now (and whether actual/modelled)
     - Min cash in next 60/90 days (base + conservative)
     - Next 14 days expected payouts
     - Total PO payments planned next 30/60 days
   - A visible banner:
     - “Last statement-backed date: YYYY-MM-DD”
     - “Order sync last success: X hours ago”
   - Filters:
     - show/hide statement-backed days
     - per store_code/account_id
2) Exports:
   - exports/cashflow_calendar.csv
   - exports/cashflow_dashboard.html
   - exports/min_cash_summary.txt (already exists; ensure it reflects trust bands)

## Acceptance criteria
- A non-technical operator can answer:
  - “How much cash do I have today (and do I trust it)?”
  - “If I pay PO X on date Y, do I hit zero cash?”
  - “How much of this is real vs modelled?”

---

# Execution guardrails (non-negotiable)
- DB backup BEFORE any apply/import.
- All write scripts DRY-RUN by default.
- Apply requires:
  - ENABLE_CASHFLOW_WRITE=1
  - explicit --apply
- Stop on first gate failure.
- Keep commits atomic; no unrelated changes.

# Gates
- python3 scripts/validate_cashflow_invariants.py
- python3 scripts/run_end_of_day.py --verbose
- pytest -q
- scripts/check_no_db_tracked.sh
- scripts/lint_docs.sh (if docs changed)

# Evidence pack
Create an Oracle pack including:
- all changed files
- mt940_backfill_report + recon csv
- cashflow_dashboard.html + cashflow_calendar.csv
- trust report
- sync-log evidence
- DB backup path
# SUPERSEDED (Truth Contract 2026-01-26)
This plan assumes payout-lag modelling after statements. Current truth contract uses **D1 cash-in at DELIVERED** (no receivables model).  
Use for historical context only. See: `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`.
