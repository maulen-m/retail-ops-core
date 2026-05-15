# Agent826 - Stock-Ledger Materializer Hardening

Gate target: `GREEN` if you implement a small code/test hardening that prevents header-only quarantine rows from leaking into product stock, then prove it on copied DB only.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_execution_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent813_copied_temp_downstream_replay_closeout.md`
6. this starter prompt

## Assignment

You are the only write-capable implementation lane in this wave.

Own only the minimal stock-ledger materializer and focused tests needed to prevent `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_STOCK_LEAK`.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent826_stock_ledger_hardening/`

Required report:

`STOCK_LEDGER_HARDENING_PROOF.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent826_stock_ledger_hardening_closeout.md`

## Required Work

- Identify the minimal materializer path responsible for header-only source-gap product stock leakage.
- Write or update a focused test proving header-only quarantine rows cannot create product stock ledger rows.
- Patch the smallest code surface needed.
- Rerun focused tests.
- Rerun copied-temp stock-ledger proof using a copied DB under your evidence root only.
- Preserve warning cohorts `249` or `252` and `23` as visible warnings, not hidden rows.

## Boundaries

Allowed writes: code/tests required for this hardening, assigned evidence root, assigned closeout.

Forbidden writes: production `db/app.db`, protected workbook, scheduler/LaunchAgent/cron/plist, external systems, Web_automation, Kaspi/API, ad platform, bank, owner publication/send, cash movement, supplier payment, PO commitment, ad spend, stock changes, price changes.

If the fix requires a business-rule/doc contract change beyond obvious leakage prevention, stop `YELLOW` and draft the required review packet instead of patching.

Gate: GREEN
