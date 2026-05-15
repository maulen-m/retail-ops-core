# Orchestrator Handoff - Order-Entry Apply Gate + Daily Survival Parallel Lane

Run date: `2026-05-15`

Canonical plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_order_entry_apply_and_daily_survival_parallel/PLAN.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/`

Closeout folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_order_entry_apply_and_daily_survival_parallel/`

## Sequence

Option 1 is paused at the exact owner phrase gate. The final pre-owner recapture is green, but no production apply may begin until the human owner sends the exact phrase in the active launch context.

Option 2 can run now as a read-only parallel group:

- Agent809: `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/01_AGENT_809__DAILY_SURVIVAL_BRIEF_REFRESH__PARALLEL_ROOT.md`
- Agent810: `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/02_AGENT_810__ADS_STOREB_GAP_READONLY__PARALLEL_ROOT.md`
- Agent811: `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/03_AGENT_811__CASH_PO_EXCEPTION_BLOCKER_BOARD__PARALLEL_ROOT.md`

Parallel group: `daily_survival_parallel`

## Launch Lines

Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/01_AGENT_809__DAILY_SURVIVAL_BRIEF_REFRESH__PARALLEL_ROOT.md`.

Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/02_AGENT_810__ADS_STOREB_GAP_READONLY__PARALLEL_ROOT.md`.

Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_APPLY_AND_DAILY_SURVIVAL_20260515_STARTERS/03_AGENT_811__CASH_PO_EXCEPTION_BLOCKER_BOARD__PARALLEL_ROOT.md`.

## Owner Phrase Gate

Production apply is allowed only after this exact phrase is sent as its own launch-context message:

```text
AUTHORIZE DB-ONLY ORDER-ENTRY RECOVERY APPLY FOR ~/Docs/Autonomous_business/db/app.db AT PRE-SHA 09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a USING API_RAW_ORDER_ENTRIES ONLY; EXPECTED WOULD-INSERT 426 FACT_ORDER_ENTRIES_KASPI ROWS FOR 419 ORDER-STORE PAIRS WITH 0 QUARANTINE ROWS; NO WORKBOOK, SCHEDULER, EXTERNAL, WEBUI, CASH, PO, ADS, PRICE, STOCK, OWNER-PUBLICATION, OR LIFECYCLE-STATUS AUTHORITY.
```

Gate: GREEN_TO_LAUNCH_OPTION2_READONLY_PARALLEL
