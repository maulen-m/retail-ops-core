# Agent F - Validators And Review Packet

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/06_AGENT_F__VALIDATORS_AND_PACKET__AFTER_05.md`
7. Agent E closeout path after completion.

## Assignment

Run the validator matrix for the copied-temp re-anchor outputs, produce the retained-blocker board, and prepare the CodeCaptain/owner review packet. Stop before production preflight/apply.

No production DB writes, workbook mutation, source-pointer writes, scheduler changes, external writes, merchant stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Outputs

Write closeout and evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/agent_f_validators_and_packet/`

Required files:

- `agent_f_validators_and_packet_closeout.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- `RETAINED_BLOCKER_BOARD.md`
- `APRIL23_REANCHOR_VALIDATOR_SUMMARY.md`
- `APRIL23_REANCHOR_DECISION_SUMMARY.md`
- `APRIL23_REANCHOR_QUARANTINE_MATRIX.tsv`
- CodeCaptain/owner review packet folder or draft path.

## Gate

Use `Gate: GREEN` only if all required validators pass for the copied-temp scope and no production/publication authority is claimed.

Use `Gate: YELLOW` if any required validator is absent, source gap remains, retained blocker remains, or CodeCaptain review is still needed.

Use `Gate: RED` for boundary violation, hidden blockers, production mutation, or false green claim.
