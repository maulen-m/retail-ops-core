# PO Planning Freshness Closeout Contract

Date: `2026-03-18`
As-of evaluated: `2026-03-09`

## Goal

Define when `po_sku_daily` and `inventory_capital_radar` may stop presenting planning freshness as stale.

## Closure preconditions

Planning freshness may be called closed only when all of the following are true:

1. the canonical DB has a stock snapshot aligned to the owner as-of window,
2. `exports/po_dashboard_data.json` is rebuilt from that canonical snapshot,
3. the rebuilt dashboard still passes `python3 scripts/validate_po_dashboard_invariants.py`,
4. `po_sku_daily` and `inventory_capital_radar` regenerate from the rebuilt dashboard,
5. owner surfaces no longer claim freshness from a workbook or file that has not been ingested into DB truth.

## Current decision

`NO_CHANGE_BLOCKED`.

For `2026-03-09`:

- current `base_stock_date` remains `2026-02-09`
- current owner-visible staleness is therefore real and must stay visible
- a newer workbook candidate exists (`stock_snapshot_2.3.2026.xlsx`), and a dry-run import succeeds, but it is not yet canonical DB truth in this worktree
- even if the `2026-03-02` snapshot were imported, it would still not fully close freshness for `2026-03-09`

## Required owner-surface behavior

Until closure is proven:

- `po_sku_daily.trust_banner` must keep the stale-planning warning
- `inventory_capital_radar.trust_banner` must remain monitoring-only
- no wording in the owner brief may imply execution-grade freshness

## Safe next step

When a fresher canonical stock snapshot exists for the current as-of window, import it through the guarded stock sync path first, then rebuild the PO dashboard and owner surfaces.
