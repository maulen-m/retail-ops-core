# Autonomous Phase 0-3 Source-Truth Wave Handoff

Created: `2026-05-13 19:22:43 +05`

Plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243`

Closeout root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave`

## Launch Order

1. Launch Agent793 only.
2. If Agent793 closeout has `Gate: GREEN`, launch Agents794-798 in parallel.
3. If Agents794-798 closeouts all have `Gate: GREEN`, launch Agent799.
4. Stop automatic advancement on any `Gate: YELLOW` or `Gate: RED`.

## Starter Prompts

- Agent793 boundary re-anchor:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/01_AGENT_793__BOUNDARY_REANCHOR__SEQUENTIAL.md`
- Agent794 order-entry source:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/02_AGENT_794__ORDER_ENTRY_SOURCE_PACKET__AFTER_793.md`
- Agent795 ads source:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/03_AGENT_795__ADS_SOURCE_PACKET__AFTER_793.md`
- Agent796 PO/inbound:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/04_AGENT_796__PO_INBOUND_SOURCE_PACKET__AFTER_793.md`
- Agent797 cashflow:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/05_AGENT_797__CASHFLOW_COST_BANK_PACKET__AFTER_793.md`
- Agent798 exceptions:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/06_AGENT_798__EXCEPTION_OWNER_SOURCE_PACKET__AFTER_793.md`
- Agent799 synthesis:
  `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_STARTERS_20260513_192243/07_AGENT_799__SYNTHESIS_AND_NEXT_APPLY_PLAN__AFTER_794_795_796_797_798.md`

## Orchestrator Notes

- Use tmux manifest and closeout files as authority.
- Completion pings are wake-up signals only.
- Do not infer completion from pane text.
- Do not start Agent799 if any source-lane assignment gate is `YELLOW` or `RED`; review the closeout first.
