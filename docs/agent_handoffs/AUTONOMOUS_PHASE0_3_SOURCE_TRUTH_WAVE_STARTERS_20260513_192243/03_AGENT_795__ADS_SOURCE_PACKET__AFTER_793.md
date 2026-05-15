# Agent795 Starter - Ads Source Packet Refresh

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent795_ads_source_packet_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT793_ORCHESTRATOR_REVIEW_ACCEPT_BOUNDARY_GREEN_20260513_193650.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent790_ads_source_readiness_packet_20260513_121500_closeout.md`
8. this starter prompt

## Mission

Clear or precisely narrow the ads source-truth blocker for current Option C readiness.

## Scope

Read-only/source-packet work only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent795_ads_source_packet/`
- copied DB under that evidence root if needed;
- assigned closeout only.

Forbidden:

- production DB mutation;
- workbook mutation;
- Web_automation state mutation beyond immutable read-only packet outputs;
- ad-platform writes;
- browser-login/session/credential export;
- owner publication.

Read-only ads source capture is authorized only through existing repo tooling and only if it performs no external writes.

## Required Work

1. Verify Agent793 `Domain Status: BOUNDARY_GREEN` and the orchestrator routing review above, then use its boundary.
2. Inventory existing validated packets for ACMEWEAR, STOREB, Web_automation DirectAPI, and Meta/Facebook.
3. Determine the exact required as-of window through current date.
4. Packetize or validate local May 12/May 13 watcher evidence if safe and complete.
5. If existing tooling supports read-only capture, capture missing DirectAPI rows for ACMEWEAR and STOREB and Meta/Facebook freshness for ACMEWEAR.
6. Run relevant validators on packet/copy only:
   - `validate_ads_source_packet_contract.py`
   - `validate_ads_sidecar_readiness.py`
   - `validate_ads_offer_universe_coverage.py`
   - `validate_ads_spend_reality.py`
   - `validate_policy_source_freshness.py` if safe on copy.
7. Closeout must include:
   - `Gate: GREEN` if assignment packet is complete, even if ads domain remains blocked;
   - `Domain Status: GREEN/YELLOW/RED`;
   - exact store/date/campaign coverage;
   - missing packet inputs;
   - copied-temp validator status;
   - non-mutation statement.
