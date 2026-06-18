# Agent9167 Starter - Serialized Implementation And Copied-Temp Rerun

You are Agent9167. You are the only write-capable lane for Agent916, and you may start only after the orchestrator has reviewed Agents9161-9166 closeouts.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/07_AGENT_9167__IMPLEMENTATION_AND_COPIED_TEMP_RERUN__AFTER_9161_9162_9163_9164_9165_9166.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT916_ROOT.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9161_stock_pricelist_contract_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9162_sales_identity_repair_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9163_ads_packet_adapter_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9164_cogs_one_row_closeout.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9165_day_complete_two_row_closeout.md`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9166_po_single_truth_closeout.md`

## Start Conditions

Do not start unless all are true:

- owner non-production envelope is recorded in the orchestrator review or session log;
- Agents9161-9166 closeouts exist;
- the orchestrator explicitly unlocked Agent9167;
- no Phase 1 lane is `RED`;
- any `YELLOW` Phase 1 lane has exact retained blockers.

These conditions are recorded in:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT916_ROOT.md`

## Scope

Allowed under the owner non-production envelope:

- contract patches;
- focused code/test patches;
- copied DB creation;
- copied-temp-only materialization;
- validator reruns;
- local evidence packaging.

Forbidden:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- external writes;
- ad-platform writes;
- ad spend;
- stock changes;
- price changes;
- cash movement;
- PO commitment;
- owner publication;
- production preflight;
- production apply.

## Task

Integrate the Phase 1 findings into the smallest safe non-production implementation and copied-temp proof rerun.

Priorities:

1. Use Agent9161 only for copied-temp `offer_availability_snapshot` synthesis. Do not write `fact_inventory_snapshot_size.current_stock` or `stock_ledger` from Merchant Cabinet PP quantities, and do not claim physical stock freshness from this source.
2. If resolved by Agent9162, apply copied-temp sales identity mappings/quarantines without weakening global evidence rules.
3. Implement the Agent9143-to-`ads_web_source_packet.v1` adapter if Agent9163 confirms the contract.
4. Resolve or preserve the COGS one-row blocker from Agent9164.
5. Resolve or preserve the day-complete two-row blocker from Agent9165.
6. Apply only non-production/copy-safe PO/single-truth contract changes from Agent9166.
7. Run one copied-temp MVOS proof rerun and record all retained blockers.

## Required Outputs

Write under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/`

Required files:

- `AGENT9167_IMPLEMENTATION_MATRIX.tsv`
- `AGENT9167_VALIDATOR_MATRIX.tsv`
- `AGENT9167_RETAINED_BLOCKER_COUNTS.tsv`
- `COMMANDS_RUN.tsv`
- `CODECAPTAIN_PACKET_DRAFT.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`

The closeout must include:

`Gate: GREEN`

Use `GREEN` only if copied-temp validators pass and protected surfaces remain unchanged. Use `YELLOW` if retained blockers remain explicit. Use `RED` for boundary violation or false-green risk.

## Anti-Drift Rules

- Do not call copied-temp proof production truth.
- Do not call missing source fresh.
- Do not call retained-blocker proof green.
- Do not turn blocked STOREB ads spend into zero spend.
- Do not insert header-only rows into product truth.
- Do not use Line61 accepted shortage to green unrelated PO failures.
- Preserve STOREB business identity separately from Universal access identity.
- Do not map Universal offer `132822924_328581041` silently if the XL vs 3XL conflict remains unresolved.
- Do not close the `9` `STOCK/HIGH/OPEN` exceptions from Merchant Cabinet pricelist evidence.
