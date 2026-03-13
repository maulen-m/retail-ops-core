## Plan: Owner Outputs Decision Activation

### Goal
Turn the current green owner-truth chain into a genuinely useful owner operating layer every 3 days, without reopening source-truth work or broad subsystem scopes.

### Phase order
1. M0 freeze the current green activation delta and preserve rollback
2. M1 classify owner questions into answered / partial / missing
3. M2 add a proper cashflow calendar daily surface
4. M3 upgrade PO / SKU daily into a clearer inventory / capital radar
5. M4 upgrade the owner daily brief to combine profit, cash, capital, and actions
6. M5 harden the 3-day review cycle so one command refreshes the surfaces, brief, and scorecard
7. M6 leave profit semantics unchanged unless the upgrade is required to keep the brief truthful
8. M7 keep scheduler/import parity proving separate
9. M8 keep broader module reactivation explicitly queued

### Test strategy
- Add `tests/test_cashflow_calendar_daily.py` before implementing the new cashflow surface.
- Add `tests/test_inventory_capital_radar.py` before refining PO / SKU daily.
- Update `tests/test_owner_daily_brief.py` before wiring the new cashflow surface into the brief.
- Update `tests/test_run_owner_review_cycle.py` before wiring the review-cycle refresh path.
- Re-run the existing green chain after all owner-surface changes to confirm no regression.

### Scope constraints
- No DB writes.
- No WebUI source work.
- No replay-only live fallback.
- No scheduler/import parity work in this phase.
