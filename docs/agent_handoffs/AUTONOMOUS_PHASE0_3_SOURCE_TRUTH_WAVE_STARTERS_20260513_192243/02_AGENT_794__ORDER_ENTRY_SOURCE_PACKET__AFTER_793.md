# Agent794 Starter - Order-Entry Identity Source Packet

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent794_order_entry_source_packet_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT793_ORCHESTRATOR_REVIEW_ACCEPT_BOUNDARY_GREEN_20260513_193650.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent789_stock_order_source_evidence_20260513_121500_closeout.md`
8. this starter prompt

## Mission

Build the fastest safe route to identity-bearing Kaspi order-entry source truth for the missing May 5-current window.

## Scope

Read-only/source-packet work only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent794_order_entry_source_packet/`
- copied DB under that evidence root if needed;
- assigned closeout only.

Forbidden:

- production DB mutation;
- workbook mutation;
- source pointer changes;
- scheduler mutation;
- merchant/admin writes;
- browser-login/session/credential export;
- owner publication.

Read-only Kaspi API/source capture is authorized only if existing repo tooling supports it without external mutation. Preserve immutable JSON/JSONL payloads, request ledgers, hashes, coverage matrix, failed/empty list, and redaction notes.

## Required Work

1. Verify Agent793 `Domain Status: BOUNDARY_GREEN` and the orchestrator routing review above, then use its accepted DB/workbook boundary.
2. Reproduce the current order-entry coverage gap for `2026-05-05` through current date, grouped by date/store.
3. Search existing local evidence for identity-bearing order-entry payloads before making any external read-only calls.
4. If existing tooling can safely capture read-only order details/entries, capture the missing window for `UNIVERSAL`, `ACMEWEAR`, and `STOREB`.
5. If capture succeeds, create a source packet with hashes and coverage proof.
6. If safe, import/recover only into a copied DB under the evidence root and run the focused freshness/materialization validators.
7. If capture cannot complete, write the exact minimal future source request with order/date/store coverage.
8. Closeout must include:
   - `Gate: GREEN` if assignment packet is complete, even if domain remains blocked;
   - `Domain Status: GREEN/YELLOW/RED`;
   - current counts for headers, entries, missing entry coverage;
   - copied-temp proof status;
   - exact remaining blockers;
   - non-mutation statement.
