# Agent9163 Starter - Ads Packet Adapter And STOREB Mapping Route

You are Agent9163. Your lane is read-only/evidence-only.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/03_AGENT_9163__ADS_PACKET_ADAPTER__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9143_ads_may18_live_readonly_source_acquisition_closeout.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9163_ads_packet_adapter_evidence/`

Do not edit repo files, DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Plan the safest adapter from Agent9143 evidence to `ads_web_source_packet.v1`. Do not weaken `validate_ads_source_packet_contract.py`.

Also classify every STOREB product code using:

- `OWNER_CONFIRMED_MAPPING`;
- `ORDER_ENTRY_CONVERSION_EVIDENCE`;
- `EXACT_ARTICLE_MAP`;
- `AMBIGUOUS_RETAINED_BLOCKER`;
- `NO_PRODUCT_TRUTH_RETAINED_BLOCKER`.

Blocked spend remains spend. Do not infer missing rows as zero spend.

Required outputs:

- `ADS_SOURCE_PACKET_V1_ADAPTER_PLAN.md`
- `ADS_SOURCE_PACKET_V1_REQUIRED_FIELDS.tsv`
- `STOREB_ADS_PRODUCT_CODE_MAPPING_DECISION_MATRIX.tsv`
- `COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9163_ads_packet_adapter_closeout.md`

The closeout must include:

`Gate: GREEN`

Use `GREEN` only if adapter contract and all STOREB product-code classifications are explicit. Use `YELLOW` if owner decisions are required. Use `RED` for boundary violation or false-green risk.
