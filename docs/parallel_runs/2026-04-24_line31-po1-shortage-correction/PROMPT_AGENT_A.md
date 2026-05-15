# Prompt Agent A - LINE31 PO-ARC-1 Shortage Correction

You are the single write-capable execution agent for this run.

Work in:

`~/Docs/Autonomous_business`

Read first:

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/.claude/OPERATING.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-24_line31-po1-shortage-correction/PLAN.md`
- `~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/LINE31_INITIAL_PO_SHORTAGE_AUTONOMOUS_BUSINESS_CONTEXT__2026-04-24.md`

Goal: update Autonomous Business so it no longer assumes the first LINE31 PO arrived as 265 complete sets without shortage.

Important facts to preserve:

- `PO-ARC-1`
- shipped `2026-02-07`
- received `2026-03-02`
- final count `2026-04-10`
- request date `2026-04-13`
- ordered `795 pcs` = `265 sets x 3 garments`
- received `638 pcs`
- net shortage `157 pcs`
- compensation claim `177 exact replacement pcs`
- compensation claim split: `MTW01 64`, `JYM005 53`, `MT20 60`
- compensation value `3008.50 CNY`
- old Li Sijia / PO-1 recovery route remains separate from current Tracy / Wuchun route

Non-negotiables:

- Inspect Autonomous Business DB/schema/current LINE31 inventory and sales truth before writing anything.
- Do not assume current stock from Sourcing-Research.
- Do not import the 2026-04-13 Sourcing stock snapshot as current stock.
- Do not treat `177` as sets.
- Do not collapse the old PO-1 recovery route into current/new supplier negotiations.
- If DB writes are needed, use backup-first, explicit write gate plus apply flag, and write rollback steps.
- Keep changes minimal and traceable.

Execution sequence:

1. Read the context listed above.
2. Inspect repo and DB:
   - Search for `LINE31`, `PO-ARC-1`, `MTW01`, `JYM005`, `MT20`, inventory correction patterns, PO receipt patterns, and stock adjustment/event tables.
   - Inspect relevant SQLite schemas before deciding where to write.
   - Log findings to:
     `~/Docs/Autonomous_business_agent_handoffs/2026-04-24_line31-po1-shortage-correction/agent_a_execution_log.md`
3. Tests first:
   - Add or identify a failing test/invariant that proves the correction is needed.
   - If the current repo does not yet model PO-ARC-1 explicitly, test the new event contract instead.
4. Implement the smallest correction:
   - Prefer existing event/correction mechanisms.
   - Preserve both net shortage `157 pcs` and compensation claim `177 pcs`; they answer different questions.
   - Store evidence paths and confidence notes.
   - Make pieces vs sets explicit.
5. Recompute/report LINE31 current state:
   - Use Autonomous Business DB inventory/sales truth after correction.
   - Do not use Sourcing-Research current stock.
   - Clearly label whether output is pieces, sets, or incomplete/orphan pieces.
6. Validate:
   - targeted tests
   - `scripts/check_no_db_tracked.sh`
   - `scripts/lint_docs.sh` if docs touched
   - relevant inventory/PO validators discovered in this repo
7. Update:
   - `~/Docs/Autonomous_business_agent_handoffs/2026-04-24_line31-po1-shortage-correction/agent_a_execution_log.md`
   - `~/Docs/Autonomous_business_agent_handoffs/2026-04-24_line31-po1-shortage-correction/status_board.md`

Expected result:

- Autonomous Business has a traceable historical correction/economic event for LINE31 PO-ARC-1.
- The repo does not silently treat the initial LINE31 receipt as `795 pcs` / `265 complete sets`.
- Current LINE31 stock is recomputed only from Autonomous Business truth after the correction.
- The change is backed by tests, evidence, and rollback steps.

Stop and log instead of guessing if:

- There is no safe event/correction surface.
- DB write gates are unclear.
- Current LINE31 stock cannot be recomputed from Autonomous Business truth.
- Any gate fails.
