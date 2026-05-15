# Agent837 - STOREB Ads Fresh Source + Mapping Evidence Packet

Gate target: `GREEN` if fresh read-only STOREB source capture plus deterministic product-code mapping evidence is sufficient for copied-temp proof. Use `YELLOW` if fresh source exists but exact mapping remains blocked.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_fact_implementation/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_IMPLEMENTATION_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_NEXT_CODECAPTAIN_PACKET.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_OWNER_WEB_AUTOMATION_SUPPLEMENT_20260515_143545.md`
7. this starter prompt

## Assignment

Collect fresh read-only STOREB ads source evidence and exact mapping evidence for the positive-spend product codes:

`11120372b`, `11122298b` for `2026-05-15` only, `11391205b`, `11391711b`, `11942309b`, `11956144b`.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent837_storeb_ads_source_mapping/`

Required packet:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent837_storeb_ads_source_mapping/STOREB_ADS_SOURCE_MAPPING_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent837_storeb_ads_source_mapping_closeout.md`

## Required Work

- Verify current DB SHA/integrity at start and write it to evidence.
- Preserve business identity `STOREB`; preserve access identity `UNIVERSAL_SWITCHER_FOR_STOREB` only as access/login context.
- Read Web_automation source route context:
  - `~/Docs/Web_automation/Docs/kaspi_marketing_storeb_readonly_capture.md`
  - `~/Docs/Web_automation/config/experiments/storeb_ads_tracking.yaml`
  - prior evidence under `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/`
- Fetch current-window STOREB source read-only using the documented API/report path or existing Web_automation method when available.
- If direct read-only fetch is blocked, use approved Headless Playwright or Chrome AutoConnect fallback only for read-only capture.
- Build an immutable packet: raw source files, normalized CSV/JSON if available, source path/stat/SHA, command log, positive-spend row summary, and exact mapping matrix.
- Do not treat product names alone as mapping authority. If exact article/SKU join is still missing, say so explicitly and keep `YELLOW`.

## Boundaries

No ad-platform writes, bid/budget changes, source-pointer replacement, production DB writes, workbook writes, Web_automation mutation, scheduler mutation, owner publication, cash/PO/stock/price actions, or lifecycle/status production repair.

Existing scripts may read `.env` or existing local auth state for read-only access, but secrets must not appear in logs or artifacts.

You are not alone in the codebase. Do not revert or overwrite edits made by others.

Gate: YELLOW
