# Agent832 - Ads STOREB Mapping / Source Decision

Gate target: `GREEN` if the 37 STOREB ads mapping gaps are source-classified with exact decisions and stale source-pointer route is explicit. Use `YELLOW` if owner/source mapping is still required.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_decision_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_DECISION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent819_ads_copied_temp_adoption_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent827_mvos_command_board/MVOS_OWNER_ACTION_LIST.md`
7. this starter prompt

## Assignment

Build the STOREB ads mapping/source decision packet.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent832_ads_storeb_mapping_source_decision/`

Required report:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent832_ads_storeb_mapping_source_decision/ADS_STOREB_MAPPING_SOURCE_DECISION_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_decision_wave/agent832_ads_storeb_mapping_source_decision_closeout.md`

## Required Work

- Preserve business identity `STOREB` separately from access identity `UNIVERSAL_SWITCHER_FOR_STOREB`.
- Reuse Agent819 evidence for the `37` unmapped STOREB source rows and classify each gap.
- Do not treat missing STOREB mapping as zero spend.
- Do not use fuzzy/product-name-only mapping as source truth.
- State the exact stale production source-pointer route: replace, parameterize to packet DB, refresh source, or keep blocked.
- If copied-temp replay is useful, mutate only a copied DB inside evidence root.

## Boundaries

No production DB write, source-pointer write, Web_automation mutation, ad-platform write, bid/budget/campaign change, owner publication, workbook write, scheduler mutation, cash, PO, price, stock, or lifecycle/status production repair.

Gate: GREEN
