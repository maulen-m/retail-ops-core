# Agent788 Starter: Cashflow Copied-Temp Replay

You are Agent788. Execute only this assigned lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ACCEPTED_BOUNDARY_PROOF_WAVE_RECHECK_20260513_103706.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_LIVE_ORCHESTRATOR_PING_POLICY_20260513_121305.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_WAVE_20260513_121500_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent784_cashflow_publication_proof_20260512_194357_closeout.md`
8. This starter prompt.

## Mission

Run a copied-temp-only cashflow replay for `2026-05-05..2026-05-11` using the accepted boundary. Do not mutate production DB or workbook.

Required first checks:

- Confirm accepted DB and workbook hashes.
- Confirm DB integrity is `ok`.
- Confirm no DB/workbook holders or SQLite sidecars before copying.

Allowed writes:

- assigned evidence folder: `~/Docs/Autonomous_business/exports/validation/source_truth_unblock_wave/20260513_121500/agent788_cashflow_copy_temp_replay`
- assigned closeout file
- copied DB files inside the evidence folder

Allowed copied-DB actions:

- copy `db/app.db` to evidence
- run cashflow translation/rebuild/source-freshness/policy-gate materializers against the copy only, with required env gates set only for the copy
- preserve any missing-cost/order-line blockers explicitly

Output closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent788_cashflow_copy_temp_replay_20260513_121500_closeout.md`

Gate guidance:

- `GREEN`: copied-temp cashflow replay and validators pass, with source-freshness/policy-gate result clear on the copy.
- `YELLOW`: copied-temp replay is blocked by missing deterministic inputs or owner/source labeling.
- `RED`: boundary mismatch, forbidden write risk, or copy isolation failure.
