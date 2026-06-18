# Agent9173 Starter - Ads Packet V1 Adapter

You are Agent9173. Your lane is read-only/evidence-only with respect to repo state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/03_AGENT_9173__ADS_PACKET_V1_ADAPTER__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9167.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/commands/015_validate_ads_source_packet_contract_storeb.stdout.json`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/commands/015_validate_ads_source_packet_contract_acmewear.stdout.json`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9173_ads_packet_v1_adapter_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9173_ads_packet_v1_adapter_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, ad platforms, bids, budgets, campaigns, or spend.

## Task

Design the strict packet-adapter route for Agent9143/Agent9167 ads evidence.

Rules:

- Adapt packet shape to `ads_web_source_packet.v1`; do not weaken `validate_ads_source_packet_contract.py`.
- Preserve `business_store_code=STOREB` separately from Universal/access identity.
- Missing spend is not zero.
- Positive retained STOREB spend remains visible until source-backed mapping exists.
- Do not write Web_automation or live ad platforms.

Targets:

- Agent9167 valid STOREB/ACMEWEAR v1 packet evidence.
- STOREB retained unmapped product-code spend: `3837.32 KZT`.

## Required Outputs

Inside your evidence folder:

- `AGENT9143_TO_ADS_WEB_SOURCE_PACKET_V1_ADAPTER_PLAN.md`
- `ADS_WEB_SOURCE_PACKET_V1_REQUIRED_FIELDS.tsv`
- `STOREB_RETAINED_ADS_SPEND_DECISION_MATRIX.tsv`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if Agent9178 can implement/verify the adapter without validator weakening, identity collapse, zeroing spend, or external writes. Use `YELLOW` if source decisions remain. Use `RED` for boundary violation or false-zero-spend risk.
