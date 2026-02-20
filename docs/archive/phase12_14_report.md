# Phase 12–14 Report (2026-01-14)

Scope: Plan vs Real PO separation, correctness gates, size canonicalization and DB-first sizing, parallel-agent workflow.

## Phase 12 — Reality Bridge: Plan → Real PO + Arrivals
- Dashboard labels are now PLAN-0..PLAN-6 (plans), not PO-5..PO-10.
- A Real POs section is added, sourced from `po_header` + `po_line`.
- UI shows an explicit disclaimer that plans are recommendations only.
- New CLI:
  - `python scripts/po_cli.py materialize-plan --plan PLAN-0 --name PO-5 --supplier SUPP_A`
  - `python scripts/po_cli.py arrive-csv --csv arrivals.csv --type AST --date 2026-01-14`

## Phase 13 — Prove Correctness
- Added invariant gate: `scripts/validate_po_dashboard_invariants.py`
  - Checks size-level totals, negative qty, duplicate sizes, and D_size sum vs D_sku.
- Portfolio completeness:
  - New `portfolio_active` table (migration script).
  - Readiness checks require stock + demand coverage for all portfolio-active SKUs.
- Ledger health:
  - Snapshot rebuild now fails on negative ledger balances unless explicitly run in simulate mode.
  - Diagnostic report written to `exports/ledger_negative_balances_YYYY-MM-DD.md`.

## Phase 14 — Reduce Manual Ops
- Size canonicalization:
  - New `dim_size_synonyms` table (migration script).
  - Size normalization applied on ingest and SKU parsing.
- DB-first sizing:
  - Manual and auto sizing inputs are normalized before writing to DB.
  - Optional DB-first auto sizing step is available in `run_end_of_day.py`:
    - `python scripts/run_end_of_day.py --auto-assign-sizes`
- Parallel agents:
  - Added `.claude/PARALLEL_AGENTS.md` protocol.
  - Updated references in `.claude/OPERATING.md`, `.claude/GIT_HYGIENE.md`, and `AGENTS.md`.

## Migrations / One-time setup
- `python scripts/migrate_014_portfolio_active.py --seed-from-dim-sku`
- `python scripts/migrate_015_dim_size_synonyms.py --seed-defaults`

## Rollback plan
- Use `git revert <commit>` to roll back any phase-specific commit.
- For schema changes, re-run migrations with empty tables or remove rows if required.

## Notes
- PLAN naming is a UI/data-layer change only; real POs remain in `po_header/po_line`.
- Readiness gate behavior is stricter for portfolio SKUs; ensure portfolio_active is seeded.
