# Agent9141 Starter: Stock Live Read-Only Source Acquisition

You are Agent9141. Your mission is to use the owner-approved read-only lane to acquire stock source evidence for the stock source packet lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT914_READONLY_SOURCE_ACQUISITION_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT914_READONLY_SOURCE_ACQUISITION_WAVE_20260519_STARTERS/01_AGENT_9141__STOCK_LIVE_READONLY_SOURCE_ACQUISITION__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9131_stock_source_packet_route_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9135_synthesis_agent914_readiness_closeout.md`

## Owner Approval Boundary

The owner approved read-only live stock source acquisition for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`, with local evidence capture only.

You may use existing repo methods, read-only API/WebUI/Kaspi fetches, or Chrome/Playwright fallback only if they are read-only and do not mutate anything.

## Scope

Allowed:

- read local repo/source docs and local sibling repos to find proven read-only stock methods;
- fetch/read live stock evidence for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`;
- write local evidence only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_evidence/`

Forbidden:

- production DB writes;
- workbook writes;
- scheduler/LaunchAgent/cron changes;
- source-pointer writes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- stock, price, PO, cash, supplier-payment, owner-publication, production-preflight, or production-apply actions.

If a method might click Save/Apply/Publish/Upload or otherwise mutate external state, do not use it.

## Task

Acquire and package stock source evidence sufficient for a later copied-temp source packet proof for:

- `fact_inventory_snapshot_size`;
- `stock_ledger`;
- the existing `9` high-stock exceptions, which must remain visible.

Required evidence:

- store scope: `STOREB`, `ACMEWEAR`, `UNIVERSAL`;
- source method and command/UI route;
- capture timestamp;
- source-visible business date/as-of date;
- SKU key and size identity;
- stock category separation if available: on-hand, inbound, reserved, unavailable, owner-OOS, exception;
- row count per store/source;
- local evidence file SHA-256;
- source owner/source system;
- mapping to downstream tables;
- explicit statement that evidence is source-captured, not a derived dashboard recomputation.

## Required Outputs

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_evidence/STOCK_LIVE_READONLY_SOURCE_PACKET.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_evidence/STOCK_SOURCE_PACKET_MANIFEST.json`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_evidence/STOCK_SOURCE_ROUTE_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_evidence/COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use `GREEN` only if source evidence is captured and packet requirements are met. Use `YELLOW` if evidence remains stale, unreachable, header-only, incomplete, or ambiguous. Use `RED` if a boundary violation happens or a method is unsafe.

## Anti-Drift Rules

- Do not call current stock fresh if the source date is stale or ambiguous.
- Do not backdate current live evidence.
- Do not hide high-stock exceptions.
- Do not write any production source pointer.
- Do not claim production readiness or publication authority.
