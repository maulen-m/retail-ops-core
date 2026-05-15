# Agent 40 - Exception Queue 16 Owner Resolution Pack

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_40_exception_queue_16_owner_resolution_pack_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
5. `~/Docs/Autonomous_business/docs/ops/OPERATIONAL_DECISION_POLICY_V1.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_36.md`
7. this starter prompt

## Mission

Classify the `16` unresolved high-severity exception rows into exact already-owner-approved controls, source-repair candidates, or plain-English human-owner questions.

## Write Boundary

Allowed:

- read-only DB/source analysis;
- evidence and owner review pack under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_40_evidence/`;
- assigned closeout.

Forbidden:

- production DB writes;
- workbook edits;
- code edits;
- auto-clearing weak family overlaps;
- inventing owner approvals.

## Required Work

1. Extract the current `16` unresolved rows from Agent 36 temp DB policy gate evidence.
2. Map each row to exact owner decisions if and only if the SKU/size/family condition matches explicitly.
3. Separate source-repair candidates from true owner-decision questions.
4. Produce a plain-English owner review pack only for rows still needing human attention.
5. Include exact rows that can be resolved by existing owner policy and the evidence path proving it.

## Required Outputs

- `agent_40_evidence/exception_queue_16_classification.csv`
- `agent_40_evidence/exception_queue_16_classification.json`
- `agent_40_evidence/OWNER_REVIEW_EXCEPTION_QUEUE_16_PLAIN_ENGLISH.md`
- assigned closeout.

## Required Gates

Run and record:

```bash
python3 scripts/validate_policy_gate_results.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --strict --json
python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --strict --json
```

## Expected Gate

`GREEN` only if all 16 are resolved by exact existing owner evidence or source-repair evidence without code/DB writes.

`YELLOW` is expected if human owner review remains required for some rows.

`RED` if any row is auto-cleared by weak/fuzzy owner-policy overlap.
