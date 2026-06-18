# Agent9144 Starter: Source Packet Synthesis And Agent915 Readiness

You are Agent9144. Launch only after the orchestrator has reviewed Agent9141-9143 closeouts.

Your mission is to synthesize the read-only stock, sales, and ads source packets and decide whether Agent915 can run copied-temp proof/materialization next.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT914_READONLY_SOURCE_ACQUISITION_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT914_READONLY_SOURCE_ACQUISITION_WAVE_20260519_STARTERS/04_AGENT_9144__SOURCE_PACKET_SYNTHESIS_AGENT915_READINESS__AFTER_9141_9142_9143.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT914_ROOT.md`
8. Agent9141 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_closeout.md`
9. Agent9142 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_closeout.md`
10. Agent9143 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9143_ads_may18_live_readonly_source_acquisition_closeout.md`

## Scope

Read-only synthesis only. You may create local evidence files under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_evidence/`

Do not mutate production DB, workbook, source pointers, schedulers, Web_automation, Kaspi/API/WebUI, ad platforms, external systems, stock, price, cash, PO, or owner publication.

## Task

Combine Agent9141-9143 outputs and answer:

- Which source packets are acceptable for copied-temp proof?
- Which source packets remain incomplete, stale, header-only, or unavailable?
- Can Agent915 run copied-temp source refresh/materialization/proof now?
- Which validators should Agent915 run if launched?
- Which production gates remain explicitly unauthorized?
- Should the next artifact be Agent915 copied-temp proof, another source acquisition wave, a CodeCaptain packet, or human clarification?

## Required Outputs

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_evidence/SOURCE_PACKET_ACCEPTANCE_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_evidence/AGENT915_READINESS_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_evidence/NEXT_AGENT915_BOOTSTRAP_RECOMMENDATION.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use `GREEN` only if Agent915 can safely run copied-temp proof using accepted packets and no missing source is being called fresh. Use `YELLOW` if one or more packets remain unresolved but precisely retained. Use `RED` if any boundary violation or false-green route is detected.

## Anti-Drift Rules

- Do not call missing source fresh.
- Do not call retained-blocker proof `GREEN`.
- Do not treat source packet capture as production truth.
- Do not recommend production preflight or production apply.
- Do not hide incomplete rows, stale dates, delayed ads finalization, header-only rows, or unresolved identity gaps.
