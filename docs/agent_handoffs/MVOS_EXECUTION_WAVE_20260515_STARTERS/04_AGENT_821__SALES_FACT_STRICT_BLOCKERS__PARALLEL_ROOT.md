# Agent821 - Sales-Fact Strict Blocker Resolver

Gate target: `GREEN` if you produce a complete blocker map and copied-temp strict replay route for `sales_fact_v2`, without inventing SKU identity.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_execution_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent813_copied_temp_downstream_replay_closeout.md`
6. this starter prompt

## Assignment

Find every exact blocker preventing strict `sales_fact_v2` rebuild after order-entry recovery.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent821_sales_fact_strict_blockers/`

Required report:

`SALES_FACT_STRICT_BLOCKER_MAP.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent821_sales_fact_strict_blockers_closeout.md`

## Required Content

- Full blocker list, including `order_id=913421682 store=UNIVERSAL offer_id=132822924_328581041` if still active.
- STOREB rows missing required `sku_identity` evidence.
- Action per blocker: map, quarantine, exclude, owner/source review, or code/test lane.
- Strict copied-temp replay route and required inputs.

## Boundaries

Read-only analysis plus optional copied DB dry-runs only. Do not edit code, config, production DB, workbook, scheduler, external systems, prices, stock, cash, PO, ads, or owner-publication surfaces.

Gate: GREEN
