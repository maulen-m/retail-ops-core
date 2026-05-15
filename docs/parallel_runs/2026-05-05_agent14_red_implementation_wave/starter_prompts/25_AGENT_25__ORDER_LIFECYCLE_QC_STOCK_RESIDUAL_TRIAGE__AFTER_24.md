# Agent 25 - Order Lifecycle QC Stock Residual Triage

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_25_order_lifecycle_qc_stock_residual_triage_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_24.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_combined_temp_proof_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
7. this starter prompt

## Mission

Read-only triage of the non-ads operational blockers remaining after Agent 24:

- `ORDER_ENTRY_MISSING=1012`;
- `ORDER_LIFECYCLE_MISSING_COMPLETED=60`;
- `RETURN_ACTIVE_WITHOUT_QC=15`;
- ledger-mode snapshot caveat: `18` negative ledger balances.

Determine which rows are auto-repairable from existing canonical evidence, which require code/policy changes, and which require owner/employee action.

## Write Boundary

Allowed writes:

- assigned closeout;
- evidence files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_25_evidence/`.

Forbidden:

- production `db/app.db` writes;
- temp DB writes unless needed for read-only query copies and clearly labelled as such;
- code changes;
- workbook edits;
- external-system writes.

## Required Work

1. Use Agent 24 temp DB and production DB read-only to extract residual blocker rows.
2. For `ORDER_ENTRY_MISSING`, classify whether each row has:
   - exact `fact_order_entries_kaspi` evidence;
   - recoverable source/archive evidence;
   - header-only fallback;
   - no evidence.
3. For `ORDER_LIFECYCLE_MISSING_COMPLETED`, classify whether each row has same-store completed event evidence, different-store evidence, or no completed evidence.
4. For `RETURN_ACTIVE_WITHOUT_QC`, determine whether existing owner policy already allows quarantine/active-zero handling or whether actual QC evidence is required.
5. For the `18` negative ledger balances, list SKU/store/date context and whether they overlap owner-approved active-zero/quarantine decisions.
6. Recommend exact next write lane or owner-action request.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact commands run;
- evidence files written;
- row counts by classification;
- whether each blocker family is auto-repairable, policy-repairable, or owner-action-required;
- exact next prompt for a future implementation agent if safe.
