# Agent846 - Full Copied-Temp MVOS Proof

You are Agent846 in the May 16 MVOS source-fact resolution wave.

Do not start until Agents842-845 closeouts have been reviewed by the orchestrator.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-16_mvos_source_fact_resolution_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_RESOLUTION_WAVE_20260516_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_RESOLUTION_WAVE_20260516_STARTERS/05_AGENT_846__FULL_COPIED_TEMP_MVOS_PROOF__AFTER_842_843_844_845.md`
7. Agents842-845 closeouts listed in the plan.
8. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent841_current_16c2_partial_copied_temp_proof/CURRENT_16C2_BLOCKER_VISIBLE_PARTIAL_COPIED_TEMP_PROOF.md`

## Assignment

Run one full copied-temp MVOS proof attempt using the accepted source decisions from Agents842-845.

You must:

- sample current production DB/workbook hashes, file stats, lsof, SQLite sidecars, and DB integrity before copying;
- label the exact proof boundary;
- mutate only copied DBs inside the assigned evidence root;
- run the relevant policy/source/sales/exception/cashflow/PO/ads/lifecycle validations available in the repo;
- keep unresolved blockers visible;
- never treat copied-temp proof as production truth.

## Write Scope

You may write only:

- `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_resolution_wave/20260516_121753/agent846_full_copied_temp_mvos_proof/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_resolution_wave/agent846_full_copied_temp_mvos_proof_closeout.md`

No production DB writes. No workbook writes. No source-pointer writes. No scheduler writes. No external writes.

## Stoplines

Stop `RED` if production DB/workbook mutation would be required.

Stop `YELLOW` if a source decision from Agents842-845 is missing, conflicting, or non-authorizing.

Stop `YELLOW` if the current production boundary drifts and the proof cannot be safely reanchored as copied-temp only.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact boundary hashes;
- copied DB path;
- commands run;
- validator results;
- source freshness result;
- owner-publication gate result;
- remaining blockers;
- exact production candidates if any;
- explicit non-authorization statement.
