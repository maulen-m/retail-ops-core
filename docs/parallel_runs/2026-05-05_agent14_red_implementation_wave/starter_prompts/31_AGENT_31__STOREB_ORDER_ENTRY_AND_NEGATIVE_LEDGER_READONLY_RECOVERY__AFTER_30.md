# Agent 31 - STOREB Order-Entry And Negative-Ledger Read-Only Recovery

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_storeb_order_entry_negative_ledger_readonly_recovery_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_30.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_30_non_ads_operational_contracts_implementation_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_30_evidence/before_after_residual_counts.json`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_30_evidence/non_ads_resolution_matrix.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/storeb_header_only_quarantine.csv`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/negative_ledger_owner_action_queue.csv`
10. this starter prompt

## Mission

Run a read-only/evidence-only recovery lane for the remaining non-ads blockers:

- `276` STOREB header-only order-entry rows.
- `16` negative-ledger weak/unresolved owner/repair queue rows.

The goal is to determine whether any STOREB rows can be recovered from approved real item-entry evidence and to prepare a plain-English owner/employee action packet for the rows that cannot be solved by source evidence.

## Write Boundary

Allowed:

- assigned closeout;
- evidence files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_evidence/`.

Forbidden:

- production `db/app.db` writes;
- code changes;
- tests changes;
- workbook edits;
- external-system writes;
- ad-platform writes;
- Web_automation writes;
- changing policy gates;
- converting header-only rows into green product evidence.

Read-only Kaspi API/source fetches are allowed only if an existing repo-supported read-only path is available and no state is mutated. If live read-only fetch is attempted, record exact command, date range, store, and proof that no writes occurred.

## Required Work

1. Classify the `276` STOREB rows by date, SKU key, size, order id, and available evidence source.
2. Search approved local evidence sources for real item-entry evidence:
   - production DB read-only;
   - Agent 30 temp DB read-only;
   - `excel_ui/SALES_KSP_CRM_V3.xlsx` if needed through safe read-only parsing;
   - archive/export folders already referenced by the recovery scripts;
   - reserve archive workbook only as last-resort read-only evidence.
3. If repo-supported read-only Kaspi API/source fetch exists, attempt a bounded STOREB read-only fetch for the exact `2026-04-16..2026-05-04` order/date window or exact order ids.
4. Do not mark any row recovered unless there is real item-entry evidence with article/SKU/size or equivalent source payload.
5. Produce:
   - `storeb_order_entry_recovery_classification.csv`;
   - `storeb_recoverable_rows_preview.jsonl`;
   - `storeb_still_quarantined_rows.csv`;
   - `negative_ledger_owner_employee_review_packet.md`;
   - `negative_ledger_owner_employee_review_queue.csv`;
   - `agent31_summary.json`.
6. For negative ledger, separate:
   - exact owner-approved rows already materialized;
   - weak overlap rows needing owner decision;
   - unresolved rows needing employee physical/QC/ledger-source review.
7. Recommend the next action:
   - implementation apply lane if enough real evidence is found;
   - owner/employee review if rows remain source-unrecoverable;
   - keep quarantine if source cannot be recovered.

## Stoplines

- Do not write production DB.
- Do not write workbooks.
- Do not mutate external systems.
- Do not use header-only fallback as real item-entry evidence.
- Do not use fuzzy names as SKU truth.
- Do not request owner action until the exact owner packet is written.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact commands run;
- evidence files written;
- STOREB recovered vs still-quarantined counts;
- negative-ledger action counts;
- whether human owner/employee action is required and the exact packet path if yes;
- exact next implementation prompt if safe.
