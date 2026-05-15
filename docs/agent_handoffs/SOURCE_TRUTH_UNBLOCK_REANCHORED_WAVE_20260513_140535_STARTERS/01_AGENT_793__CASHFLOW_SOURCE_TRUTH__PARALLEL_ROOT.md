# Agent793 Starter: Cashflow Source Truth

You are Agent793. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md` if present
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_PLAN_20260513_140535.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_20260513_140535_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent788_cashflow_copy_temp_replay_20260513_121500_closeout.md`
8. This starter prompt.

## Mission

Unblock cashflow source truth from the reanchored review-only `04c764...` boundary.

Required work:

- Verify the active DB/workbook boundary before doing mission work.
- Preserve source evidence for stale bank/manual cashflow inputs after `2026-05-04`.
- Identify the exact five missing-cost order lines from Agent788 and determine whether existing deterministic repo evidence resolves them.
- If safe, run copied-temp-only cashflow translation/rebuild/source-freshness/policy checks against a DB copy inside your evidence folder.
- Produce the smallest next action if owner/source facts are still required.

Allowed writes:

- Evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_reanchored_wave/20260513_140535/agent793_cashflow_source_truth`
- Closeout file
- Copied DB files inside the evidence folder

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent793_cashflow_source_truth_20260513_140535_closeout.md`

Gate guidance:

- `GREEN`: cashflow source evidence and copied-temp checks are complete enough for the next validation lane.
- `YELLOW`: exact missing owner/source fact or deterministic input is identified.
- `RED`: boundary mismatch, forbidden write risk, or copy isolation failure.
