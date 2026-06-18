# Agent9132 Starter: Sales Fact V2 Source Packet Route

You are Agent9132. Your mission is to resolve or precisely preserve the `src_ab_db_sales_truth` blocker after Agent9125.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT913_SOURCE_ACQUISITION_CONTRACT_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT913_SOURCE_ACQUISITION_CONTRACT_WAVE_20260519_STARTERS/02_AGENT_9132__SALES_FACT_SOURCE_PACKET_ROUTE__PARALLEL_ROOT.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-19/001205_TASK-000_mvos-agent9125-yellow-retained-blocker-codecaptain/Answer/Code_captain_19.05.2026_10_02_24.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/ORCHESTRATOR_REVIEW_AFTER_AGENT9125.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/RETAINED_BLOCKER_MATRIX.tsv`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/SOURCE_FRESHNESS_CHILD_STATUS.tsv`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/OPERATIONAL_TABLE_OBSERVATIONS.tsv`

## Scope

Read-only and copied-temp planning only. You may inspect local repo files, local evidence, and local sibling repos if needed. You may create local evidence files under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9132_sales_fact_source_packet_route_evidence/`

Do not mutate production DB, workbook, source pointers, schedulers, external systems, Web_automation, Kaspi/API/WebUI, ads platforms, stock, price, cash, PO, or owner publication.

Do not run live external fetches. If a live read-only source fetch is required, stop `YELLOW` and state the exact required approval phrase.

## Task

Determine whether an accepted local strict sales/SKU identity source exists for rebuilding `sales_fact_v2` beyond `2026-05-04`.

Required source packet fields:

- post-`2026-05-04` order/sales source rows;
- source-backed SKU identity for each sales line;
- store code;
- order ID;
- offer/article/product code;
- size identity;
- quantity;
- status eligibility;
- source packet hash;
- exact handling of unmapped rows: mapped, quarantined, retained blocker, or excluded by accepted contract.

## Required Outputs

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9132_sales_fact_source_packet_route_evidence/SALES_FACT_V2_SOURCE_PACKET_REQUIREMENTS_20260518.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9132_sales_fact_source_packet_route_evidence/SALES_FACT_V2_SOURCE_ROUTE_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9132_sales_fact_source_packet_route_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use `GREEN` if the route is complete or the blocker is precisely retained with no ambiguity. Use `YELLOW` if more source approval/live read is required. Use `RED` if a boundary violation or false sales rebuild route is detected.

## Anti-Drift Rules

- Do not call non-strict sales rebuild output production-ready truth.
- Do not accept a sales route without SKU mapping source.
- Do not invent SKU, size, status, or quantity.
- Do not hide unmapped rows.
- Do not claim production or publication authority.
