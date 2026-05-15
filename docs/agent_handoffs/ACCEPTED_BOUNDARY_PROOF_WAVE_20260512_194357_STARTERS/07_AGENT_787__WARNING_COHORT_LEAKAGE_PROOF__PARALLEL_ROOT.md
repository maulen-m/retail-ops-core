# Agent787 Starter: Warning Cohort Leakage Proof

You are Agent787. Execute only this assigned review-only lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_REVIEW_ONLY_20260512_194357.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent777_non_ads_publication_blocker_map_20260512_131702_closeout.md`
6. This starter prompt: `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/07_AGENT_787__WARNING_COHORT_LEAKAGE_PROOF__PARALLEL_ROOT.md`

## Mission

Prove whether warning cohorts such as `23`, `252`, `249`, and related header-only/non-product rows leak into owner-publication or operational product truth on the accepted boundary. Preserve warning visibility; do not repair or hide warning rows.

Required first checks:

- Confirm accepted DB and workbook hashes match the re-anchor artifact.
- Confirm DB integrity is `ok`.

Allowed writes:

- assigned evidence folder under `~/Docs/Autonomous_business/exports/validation/accepted_boundary_proof_wave/20260512_194357/agent787_warning_cohort_leakage_proof`
- assigned closeout file only

Forbidden:

- warning row repair
- warning suppression
- production DB/workbook mutation
- scheduler restore or mutation
- external writes
- owner publication or owner approval request

## Output

Write closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent787_warning_cohort_leakage_proof_20260512_194357_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- exact warning cohort counts observed
- queries/scripts run to test leakage
- whether warning rows are excluded from product truth and owner-publication surfaces
- any missing guard or test recommendation
- explicit no-write/no-external statement

Gate guidance:

- `GREEN`: leakage proof is complete and warning visibility remains intact.
- `YELLOW`: proof is incomplete or a missing guard/test should be added later.
- `RED`: warning rows leak into publication/product truth or boundary mismatch occurs.
