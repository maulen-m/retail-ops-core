# OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT

## Purpose

Define what `Owner Profit Daily` means when the live owner-truth chain is green but the upstream monthly review rows still carry `profit_locked=true` and null profit columns.

## Contract

`Owner Profit Daily` may publish a provisional profit surface when all of the following are true:

1. `exports/daily/<AS_OF>/owner_truth_summary.json` has `status=PASS`
2. `exports/diagnostics/<AS_OF>/system_health.json` has `status=GREEN`
3. `exports/north_star_owner_review/<AS_OF>/publication_readiness.json` has `status=PASS`
4. Monthly review rows contain numeric:
   - `net_rev_kzt`
   - `cogs_kzt`
   - `ads_kzt`
   - `opex_kzt`
5. Profit columns are null only because the upstream monthly review surface is still locked, not because the underlying economics are missing

When those conditions hold, `Owner Profit Daily` is allowed to derive:

- `profit_after_ads_kzt = net_rev_kzt - cogs_kzt - ads_kzt`
- `profit_after_ads_and_opex_kzt = profit_after_ads_kzt - opex_kzt`

## Required labeling

The daily surface must carry:

- `trust_banner=PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN`
- `semantics_mode=PROVISIONAL_DERIVED_FROM_LOCKED_MONTHLY_REVIEW`
- `semantics_contract=docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md`

## Allowed use

This provisional surface is acceptable for:

- daily owner monitoring
- short-horizon profit direction checks
- comparing months using the same derived method

This provisional surface is **not** the contract that unlocks upstream monthly review semantics by itself.

## Upgrade path

The provisional banner may be removed only when the upstream monthly review source itself emits decision-grade unlocked profit fields for the same period.
