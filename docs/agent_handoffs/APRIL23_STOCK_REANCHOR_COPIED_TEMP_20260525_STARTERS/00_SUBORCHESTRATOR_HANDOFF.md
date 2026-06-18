# April 23 Stock Re-Anchor Copied-Temp Sub-Orchestrator Handoff

Created: `2026-05-25 14:43 +0500`
Repo: `~/Docs/Autonomous_business`
Mode: `read-only and copied-temp only`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/APRIL23_STOCK_ANCHOR_OWNER_APPROVED_FOR_REANCHOR_COPIED_TEMP_20260525.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-25/125117_TASK-000_CaptainRequestEvaluation_april23_stock_reanchor_execution_plan/Answer/Code Captain_25.05.2026_13_22_05.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`

## Mission

Execute the April 23 stock re-anchor lane end-to-end through CodeCaptain/owner review packet preparation, then stop.

The April 23 workbook is the owner-approved physical-stock anchor for this lane. Rebuild current stock by replaying source-backed post-anchor sales/depletion through `2026-05-25`, generate review-only workbooks, run validators, and package retained blockers honestly.

## Canonical Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`

Validator matrix:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`

Source contract:

`~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/APRIL23_STOCK_ANCHOR_OWNER_APPROVED_FOR_REANCHOR_COPIED_TEMP_20260525.md`

Code Captain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-25/125117_TASK-000_CaptainRequestEvaluation_april23_stock_reanchor_execution_plan/Answer/Code Captain_25.05.2026_13_22_05.md`

## Authority Boundary

Authorized:

- repo documentation;
- source-contract planning;
- starter/handoff creation;
- read-only source inspection;
- local evidence generation;
- copied-temp DB/materialization proof planning and execution;
- validators;
- review packet preparation.

Not authorized:

- production DB writes;
- workbook mutation;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation changes;
- Kaspi/API/WebUI writes;
- ad-platform writes;
- merchant stock changes;
- price changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- downstream dashboard publication;
- production preflight;
- production apply.

## Expected Output Root

Use a timestamped local evidence root under:

`~/Docs/Autonomous_business/exports/validation/april23_stock_reanchor_copied_temp/`

Closeouts should be written under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/`

## Agent Sequence

Parallel root:

- Agent A: anchor workbook schema/SHA/risk audit.
- Agent B: post-anchor source-window coverage audit.

After A:

- Agent C: anchor normalization and contract consistency.

After A and B:

- Agent D: post-anchor depletion extraction/ranking and quarantine table.

After C and D:

- Agent E: copied-temp replay and workbook generation.

After E:

- Agent F: validators, retained-blocker board, and CodeCaptain/owner packet.

## Gate Labels

Use:

`COPIED_TEMP_GREEN_PROOF_FOR_REANCHOR_SCOPE_ONLY`

only if all required validators pass for the claimed scope and protected surfaces remain unchanged.

Otherwise use:

`YELLOW_RETAINED_BLOCKER_BOARD_PROOF`

Use:

`RED_BOUNDARY_VIOLATION`

for production mutation attempt, external write attempt, hidden blocker, or protected-surface mutation.

## Launch Lines

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/01_AGENT_A__ANCHOR_WORKBOOK_AUDIT__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/02_AGENT_B__SOURCE_WINDOW_COVERAGE_AUDIT__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/03_AGENT_C__ANCHOR_NORMALIZATION__AFTER_01.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/04_AGENT_D__DEPLETION_EXTRACTION_RANKING__AFTER_01_02.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/05_AGENT_E__COPIED_TEMP_REPLAY_AND_WORKBOOKS__AFTER_03_04.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/06_AGENT_F__VALIDATORS_AND_PACKET__AFTER_05.md
```
