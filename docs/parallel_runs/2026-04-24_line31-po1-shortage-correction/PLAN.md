# LINE31 PO-ARC-1 Shortage Correction Plan

## Purpose

Create a traceable Autonomous Business inventory/economic correction for the first LINE31 PO shortage so the repo no longer assumes the initial LINE31 PO arrived as 265 complete sets.

## Source Handoff

Primary source:

`~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/LINE31_INITIAL_PO_SHORTAGE_AUTONOMOUS_BUSINESS_CONTEXT__2026-04-24.md`

This source is historical incident evidence only. It must not be imported as current stock truth.

## Business Facts To Preserve

- Product family: ACMEWEAR LINE31.
- Reference PO: `PO-ARC-1`.
- Shipment date: `2026-02-07`.
- Receipt date: `2026-03-02`.
- Final physical count date: `2026-04-10`.
- Compensation request date: `2026-04-13`.
- Ordered quantity: `795 pcs`, equal to `265 sets x 3 garments`.
- Actually received: `638 pcs`.
- Net shortage: `157 pcs`.
- Compensation claim: `177 exact replacement pcs`, not sets.
- Claim detail: `MTW01 64`, `JYM005 53`, `MT20 60`.
- Compensation value: `3008.50 CNY`.
- Old route: Li Sijia / PO-1 recovery route.
- Current Tracy / Wuchun route must remain separate.

## Execution Model

Use one write-capable execution agent only. This task can touch DB truth, so do not run parallel DB writers.

## Required Work Sequence

1. Read repo bootstrap context:
   - `~/Docs/Autonomous_business/AGENTS.md`
   - `~/Docs/Autonomous_business/docs/00_START_HERE.md`
   - `~/Docs/Autonomous_business/.claude/OPERATING.md`
   - this plan
   - the Sourcing-Research handoff above

2. Inspect first, no writes:
   - Search repo and DB for LINE31, PO-ARC-1, MTW01, JYM005, MT20, and existing PO/inventory correction patterns.
   - Inspect relevant schemas before choosing where the event belongs.
   - Produce a short preflight summary in the handoff log.

3. Tests first:
   - Add or identify a failing test/invariant proving the repo currently treats PO-ARC-1 as fully received or lacks a shortage correction.
   - If no exact current assumption exists, test the new correction parser/event contract instead.

4. Implement the smallest correction surface:
   - Prefer an existing inventory/economic event or adjustment table if one exists.
   - If no suitable table exists, create the smallest repo-consistent correction sidecar/table path, with tests.
   - Preserve all facts listed above.
   - Link source evidence paths.
   - Do not import current LINE31 stock from Sourcing-Research.

5. Apply safely if DB mutation is needed:
   - Back up `db/app.db` first.
   - Require explicit write gate and apply flag.
   - Record backup path, commands, row counts, and rollback command.

6. Recompute / report current LINE31:
   - Recompute current LINE31 stock only from Autonomous Business DB inventory/sales truth after applying the correction.
   - Clearly separate pieces vs sets.
   - Clearly separate historical receipt correction from current live stock.

7. Run gates:
   - Targeted tests for the new correction/event path.
   - `scripts/check_no_db_tracked.sh`
   - `scripts/lint_docs.sh` if docs were touched.
   - Relevant inventory / PO validators discovered during inspection.
   - Full strict gates only if the change scope makes them appropriate; otherwise report inherited stoplines honestly.

## Deliverables

- Updated repo state or correction artifact.
- Test(s) / invariant(s).
- Execution log:
  - `~/Docs/Autonomous_business_agent_handoffs/2026-04-24_line31-po1-shortage-correction/agent_a_execution_log.md`
- Status board:
  - `~/Docs/Autonomous_business_agent_handoffs/2026-04-24_line31-po1-shortage-correction/status_board.md`
- If DB touched:
  - DB backup path.
  - exact apply command.
  - rollback command.

## Stop Conditions

- Stop if the DB schema does not have a safe place for the correction and a new schema path would exceed this task.
- Stop if tests/gates fail after the correction.
- Stop if the only way to proceed is to import Sourcing-Research current stock.
- Stop if pieces vs sets cannot be preserved clearly.
