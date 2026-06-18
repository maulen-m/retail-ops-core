# Agent9142 Starter: Sales Live Read-Only Source Acquisition

You are Agent9142. Your mission is to use the owner-approved read-only lane to acquire post-`2026-05-04` order-entry, order-status, and SKU identity source evidence for `sales_fact_v2` copied-temp proof.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT914_READONLY_SOURCE_ACQUISITION_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT914_READONLY_SOURCE_ACQUISITION_WAVE_20260519_STARTERS/02_AGENT_9142__SALES_LIVE_READONLY_SOURCE_ACQUISITION__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9132_sales_fact_source_packet_route_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9135_synthesis_agent914_readiness_closeout.md`

## Owner Approval Boundary

The owner approved read-only Kaspi/API/WebUI sales source fetch for Agent9132 or successor, covering post-`2026-05-04` order-entry, order-status, and SKU identity evidence for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.

This is for copied-temp `sales_fact_v2` source-packet proof only.

## Scope

Allowed:

- read local repo/source docs and local sibling repos to find proven read-only sales/order methods;
- fetch/read live order-entry, status, and SKU identity evidence for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`;
- use API, WebUI archive, Chrome, or Playwright only in read-only mode;
- write local evidence only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_evidence/`

Forbidden:

- production DB writes;
- workbook writes;
- scheduler/LaunchAgent/cron changes;
- source-pointer writes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- publication, production-preflight, production-apply, cash, PO, stock, or price actions.

If a method might click Save/Apply/Publish/Upload or otherwise mutate external state, do not use it.

## Task

Acquire and package source evidence sufficient for a later copied-temp `sales_fact_v2` proof:

- post-`2026-05-04` order-entry rows;
- order-status and lifecycle evidence;
- SKU identity evidence: SKU key, size, offer/product identity, quantity, store, order id;
- eligibility mapping for completed/cancelled/shipped/current/archive statuses;
- unmapped/header-only/quarantine policy.

Required evidence:

- exact source windows per store;
- capture timestamp;
- source-visible business date/window;
- source method and command/UI route;
- row count per store/source;
- local evidence file SHA-256;
- mapping to `sales_fact_v2`, order-entry, day-complete, lifecycle/status, and SKU identity validators;
- explicit handling for header-only or identity-missing rows.

## Required Outputs

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_evidence/SALES_FACT_V2_LIVE_READONLY_SOURCE_PACKET.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_evidence/SALES_FACT_V2_SOURCE_PACKET_MANIFEST.json`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_evidence/SALES_FACT_V2_SOURCE_ROUTE_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_evidence/COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use `GREEN` only if source evidence is captured and packet requirements are met. Use `YELLOW` if evidence remains stale, unreachable, header-only, incomplete, or ambiguous. Use `RED` if a boundary violation happens or a method is unsafe.

## Anti-Drift Rules

- Do not infer SKU identity from incomplete headers.
- Do not synthesize WebUI status-change truth from API rows unless the evidence explicitly supports it.
- Do not write production source pointers.
- Do not treat source packet capture as copied-temp proof.
- Do not claim production readiness or publication authority.
