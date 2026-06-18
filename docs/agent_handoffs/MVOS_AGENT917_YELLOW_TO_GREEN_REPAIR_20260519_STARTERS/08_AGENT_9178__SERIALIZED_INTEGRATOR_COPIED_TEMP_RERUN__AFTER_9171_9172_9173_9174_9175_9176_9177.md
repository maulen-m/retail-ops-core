# Agent9178 Starter - Serialized Integrator And Copied-Temp Rerun

You are Agent9178. You are the only write-capable Agent917 lane. Do not start until the orchestrator has reviewed Agents9171-9177 closeouts and explicitly unlocked you.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/08_AGENT_9178__SERIALIZED_INTEGRATOR_COPIED_TEMP_RERUN__AFTER_9171_9172_9173_9174_9175_9176_9177.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT917_ROOT.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9171_stock_offer_availability_contract_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9172_sales_identity_matrix_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9173_ads_packet_v1_adapter_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9174_cogs_single_row_integrity_closeout.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9175_day_complete_current_result_closeout.md`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9176_po_single_truth_reconciliation_closeout.md`
15. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9177_proof_board_c3_integration_closeout.md`

## Start Conditions

Do not start unless all are true:

- owner Agent917 non-production envelope is recorded;
- Agents9171-9177 closeouts exist;
- the orchestrator review exists at `ORCHESTRATOR_REVIEW_AFTER_AGENT917_ROOT.md`;
- the orchestrator review explicitly unlocks Agent9178;
- no Phase 1 lane is `RED`;
- any `YELLOW` Phase 1 lane has exact retained blockers and a safe integration decision.

## Scope

Allowed under the owner non-production envelope:

- source contract docs;
- focused code/test patches;
- copied DB creation;
- copied-temp-only materialization;
- validator reruns against copied DB/source packets;
- local evidence packaging;
- next CodeCaptain packet draft.

Forbidden:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Kaspi/API/WebUI writes or mutations;
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

Implement the smallest safe non-production route from Agent917 root findings and run one fresh copied-temp MVOS proof rerun.

Expected implementation areas, only if supported by root closeouts:

1. Merchant Cabinet/pricelist `offer_availability_snapshot` contract and tests, without physical stock claims.
2. Sales identity mapping/quarantine route, preserving Universal XL-vs-3XL if unresolved.
3. Agent9143/9167 ads packet v1 adapter route, without validator weakening or spend zeroing.
4. Copied-temp COGS unit-evidence integrity route for `909054064 / ACMEWEAR / SUIT-31-TS_3XL`, without production-economics authority.
5. Day-complete current result cleanup for the next packet.
6. PO/single-truth copied-temp-safe reconciliation route, preserving Line61 accepted shortage.
7. C3 source-freshness bridge and proof-board registry updates, without physical-stock false green.

## Required Outputs

Write under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9178_integrator_copied_temp_rerun_evidence/`

Required files:

- `AGENT9178_IMPLEMENTATION_MATRIX.tsv`
- `AGENT9178_VALIDATOR_MATRIX.tsv`
- `AGENT9178_RETAINED_BLOCKER_COUNTS.tsv`
- `COMMANDS_RUN.tsv`
- `CODECAPTAIN_PACKET_DRAFT.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9178_serialized_integrator_copied_temp_rerun_closeout.md`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if copied-temp validators pass, protected surfaces remain unchanged, and no retained blocker affects the claimed green scope. Use `YELLOW` if retained blockers remain explicit. Use `RED` for boundary violation or false-green risk.

## Anti-Drift Rules

- Do not call copied-temp proof production truth.
- Do not call retained-blocker proof green.
- Do not call missing source fresh.
- Do not treat offer availability as physical stock.
- Do not update `stock_ledger` or `fact_inventory_snapshot_size.current_stock` from Merchant Cabinet/pricelist PP quantities.
- Do not map Universal `132822924_328581041` silently.
- Do not zero retained STOREB spend.
- Do not weaken ads packet validators.
- Do not zero missing COGS.
- Do not use Line61 shortage to green unrelated PO failures.
- Do not start production preflight/apply.
