# Agent782 Starter: Ads Source Freshness Packet

You are Agent782. Execute only this assigned review-only lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_REVIEW_ONLY_20260512_194357.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent779_current_boundary_freeze_and_post_root_drift_forensics_20260512_191139_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent780_automation_quiet_window_audit_20260512_191139_closeout.md`
7. This starter prompt: `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/02_AGENT_782__ADS_SOURCE_FRESHNESS_PACKET__PARALLEL_ROOT.md`

## Mission

Build a local/read-only ads source freshness packet for the accepted boundary, with special focus on Meta/Facebook and Web_automation adoption evidence. Use existing local files and repo evidence only unless a blocker proves a separately authorized live-readonly fetch is required.

Required first checks:

- Confirm accepted DB and workbook hashes match the re-anchor artifact.
- Confirm DB integrity is `ok`.
- Confirm no DB/workbook holders or SQLite sidecars if your proof reads the live boundary.

Allowed writes:

- assigned evidence folder under `~/Docs/Autonomous_business/exports/validation/accepted_boundary_proof_wave/20260512_194357/agent782_ads_source_freshness_packet`
- assigned closeout file only

Forbidden:

- live API fetches
- browser/login automation
- Web_automation writes
- production DB/workbook mutation
- scheduler restore or mutation
- credential/session reads or export
- ad spend or external writes
- owner publication or owner approval request

## Output

Write closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent782_ads_source_freshness_packet_20260512_194357_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- local source inventory for ads evidence
- exact stale/missing dates and stores/offers, if any
- whether local Web_automation evidence is enough for copied-temp proof
- exact minimal live-readonly request if local evidence is insufficient
- commands run
- explicit no-write/no-external statement

Gate guidance:

- `GREEN`: local evidence is enough to define the ads source freshness packet for copied-temp replay.
- `YELLOW`: local evidence is incomplete and a bounded live-readonly capture is required.
- `RED`: boundary mismatch, forbidden write risk, or source identity conflict.
