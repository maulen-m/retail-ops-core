# Agent795 Starter: Ads Source Capture And Adoption

You are Agent795. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md` if present
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_PLAN_20260513_140535.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_20260513_140535_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent790_ads_source_readiness_packet_20260513_121500_closeout.md`
8. This starter prompt.

## Mission

Use local evidence and bounded read-only source methods to improve ads coverage for the reanchored review-only `04c764...` boundary.

Required work:

- Verify the active DB/workbook boundary before doing mission work.
- Inspect Agent790's approval-ready packet and any existing Web_automation/Facebook_ads source packets.
- Use `~/Docs/Web_automation` read/fetch methods only if they are clearly read-only and non-mutating.
- Capture source packets into your evidence folder only.
- Validate packet manifests where possible.
- If enough source evidence exists, run copied-temp-only ads/source-freshness/policy checks against a DB copy or readonly validators only.
- Do not mutate production DB, workbook, campaign state, bids, budgets, ads, prices, stock, scheduler, or Web_automation production state.

Allowed writes:

- Evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_reanchored_wave/20260513_140535/agent795_ads_source_capture_adoption`
- Closeout file
- Copied DB files inside the evidence folder

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent795_ads_source_capture_adoption_20260513_140535_closeout.md`

Gate guidance:

- `GREEN`: ads source packet is current enough and copied-temp/readonly validators prove the next adoption route.
- `YELLOW`: exact read-only source command, source account/date gap, or packet field remains missing.
- `RED`: boundary mismatch, forbidden write risk, or source capture cannot be proven read-only.
