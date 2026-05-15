# Agent794 Starter: Stock/Order Source Capture

You are Agent794. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_PLAN_20260513_140535.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_20260513_140535_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent789_stock_order_source_evidence_20260513_121500_closeout.md`
7. This starter prompt.

## Mission

Find or capture identity-bearing order-entry source evidence needed to clear the stock/order blocker from the reanchored review-only `04c764...` boundary.

Required work:

- Verify the active DB/workbook boundary before doing mission work.
- Focus on at least `2026-05-05..2026-05-12`, preserving exact source coverage by store/order/date.
- Search repo-local and Web_automation-local evidence first.
- If a bounded read-only source capture command already exists and is clearly non-mutating, run it into your evidence folder only.
- Do not import into production DB or workbook.
- If enough source evidence exists, prove the copied-temp route on a DB copy only.
- Produce the exact next command/source requirement if capture cannot be safely completed.

Allowed writes:

- Evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_reanchored_wave/20260513_140535/agent794_stock_order_source_capture`
- Closeout file
- Copied DB files inside the evidence folder

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent794_stock_order_source_capture_20260513_140535_closeout.md`

Gate guidance:

- `GREEN`: identity-bearing order-entry evidence is captured/proven and copied-temp replay route is ready.
- `YELLOW`: exact read-only source command, source file, or owner/source input remains missing.
- `RED`: boundary mismatch, forbidden write risk, or source capture cannot be proven read-only.
