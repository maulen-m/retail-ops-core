# Agent784 Starter: Cashflow Publication Proof

You are Agent784. Execute only this assigned review-only lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_REVIEW_ONLY_20260512_194357.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent777_non_ads_publication_blocker_map_20260512_131702_closeout.md`
7. This starter prompt: `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/04_AGENT_784__CASHFLOW_PUBLICATION_PROOF__PARALLEL_ROOT.md`

## Mission

Map cashflow publication readiness for the accepted boundary. Separate actual statement coverage from modelled payout estimates, verify trust-banner/source-freshness blockers locally, and identify the smallest safe next action.

Required first checks:

- Confirm accepted DB and workbook hashes match the re-anchor artifact.
- Confirm DB integrity is `ok`.

Allowed writes:

- assigned evidence folder under `~/Docs/Autonomous_business/exports/validation/accepted_boundary_proof_wave/20260512_194357/agent784_cashflow_publication_proof`
- assigned closeout file only

Forbidden:

- bank/API sync
- cash movement
- production DB/workbook mutation
- scheduler restore or mutation
- external writes
- owner publication or owner approval request

## Output

Write closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent784_cashflow_publication_proof_20260512_194357_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- last statement/source coverage state from local evidence
- ACTUAL vs MODELLED separation status
- trust-banner status
- smallest safe next action to unblock cashflow source truth
- commands run
- explicit no-write/no-external statement

Gate guidance:

- `GREEN`: cashflow proof route is fully mapped and ready for copied-temp or owner-decision next step.
- `YELLOW`: fresh statement/source evidence or owner input is required.
- `RED`: boundary mismatch or unsafe write requirement.
