# Agent 44 - Option A Exception Queue 14 Source-Repair Read-Only Analysis

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_44_option_a_exception_14_source_repair_readonly_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_42.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_40_evidence/exception_queue_16_classification.csv`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_40_evidence/OWNER_REVIEW_EXCEPTION_QUEUE_16_PLAIN_ENGLISH.md`
9. this starter prompt

## Mission

Analyze the `14` source-repair candidate exception rows from Agent 40 and produce exact source-backed repair actions.

Do not ask the owner to approve broad exceptions until source repair fails. The job is to determine whether each negative/blocked row is caused by stock anchor, inbound, adjustment, SKU mapping, sales/order lifecycle, or return/QC source truth.

## Write Boundary

Allowed:

- read-only DB/workbook/source inspection;
- evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_44_evidence/`;
- assigned closeout.

Forbidden:

- repo code edits;
- production `db/app.db` writes;
- workbook edits;
- external/live calls;
- changing owner decisions;
- clearing weak family overlaps.

## Required Work

1. Extract the `14` source-repair candidates from Agent 40 classification.
2. For each row, trace:
   - current ledger balance;
   - initial/anchor quantity;
   - inbound quantity;
   - adjustment quantity;
   - sales quantity;
   - returns/QC quantity;
   - last relevant source event;
   - whether a SKU mapping or source ledger error is likely.
3. Produce a CSV and Markdown matrix with one of these recommended actions per row:
   - source-repairable with exact evidence;
   - needs warehouse/QC evidence;
   - needs exact owner approval;
   - should remain blocking.
4. If exact SQL or script commands can safely repair rows later, write them as dry-run-only instructions, not executed writes.
5. Preserve the `2` exact owner questions separately and do not expand them.

## Expected Gate

`GREEN` if every one of the `14` rows has a deterministic next action with evidence and no repo/DB writes occurred.

`YELLOW` if some rows still need source evidence or owner review.

`RED` if evidence is missing, fuzzy, or would require unsafe write assumptions.
