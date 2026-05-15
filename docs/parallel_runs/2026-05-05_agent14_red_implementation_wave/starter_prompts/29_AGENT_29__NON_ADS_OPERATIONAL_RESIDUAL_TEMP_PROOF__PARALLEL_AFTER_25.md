# Agent 29 - Non-Ads Operational Residual Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_non_ads_operational_residual_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_24.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_25_26_27.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_combined_temp_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_25_order_lifecycle_qc_stock_residual_triage_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_25_evidence/agent25_residual_triage_summary.json`
9. this starter prompt

## Mission

Run a temp-DB-only proof for the non-ads operational residuals after Agent 25. The goal is to determine exactly which non-ads blockers can be cleared with existing evidence and which still require a later code/policy/owner lane.

## Write Boundary

Allowed:

- temp DB copies under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/`;
- reports/evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- code changes;
- tests changes;
- workbook edits;
- external-system writes;
- ad-platform writes;
- Web_automation writes;
- modifying Agent 28 files.

If code changes are required to clear a blocker, do not implement them. Write the exact follow-up implementation prompt instead.

## Required Work

1. Copy production `db/app.db` to an evidence temp DB and record integrity before/after.
2. Rebuild or replay the Agent 24 temp chain as needed to reproduce the non-ads residuals on the temp DB.
3. Apply order-entry recovery only for the rows classified as recoverable from existing `CURRENT_CRM` evidence. Do not invent item entries for the `276` STOREB header-only rows.
4. For the `276` STOREB header-only rows, recover real item-entry evidence only from approved source paths if already available locally; otherwise leave them quarantined from product-level stock/profit publication.
5. For the `60` lifecycle rows, do not synthesize completion events. Classify whether an explicit same-store header-completed contract would clear them, and write the required test/code prompt if so.
6. For the `15` return/QC rows, prove quarantine/active-zero handling as policy evidence. Do not make returns active sellable without QC acceptance.
7. For the `18` negative ledger balances, separate exact owner-approved active-zero/quarantine rows from unresolved rows and produce a ledger/source repair or owner-action queue.
8. Re-run the relevant Agent 24 strict validator set on the temp DB and return a pass/fail matrix.

## Stoplines

- No production apply.
- No header-only order-entry fallback as green evidence.
- No completed lifecycle synthesis without a tested source contract.
- No returned stock as active sellable without QC acceptance.
- No simulate-mode snapshot as production stock truth.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact commands run;
- temp DB path;
- evidence files written;
- before/after residual counts;
- validation outputs;
- rollback note;
- exact next implementation prompt if code/policy changes are required.
