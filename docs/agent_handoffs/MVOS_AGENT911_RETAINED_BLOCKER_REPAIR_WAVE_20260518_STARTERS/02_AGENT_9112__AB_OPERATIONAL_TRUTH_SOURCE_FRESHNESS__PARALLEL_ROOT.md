# Agent911B / Transport Agent9112 - AB Operational Truth Source Freshness

Gate target: `GREEN` if `src_ab_db_operational_truth` can be cleared on a copied DB from accepted evidence, otherwise `YELLOW` with exact retained blocker and required source.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/02_AGENT_9112__AB_OPERATIONAL_TRUTH_SOURCE_FRESHNESS__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/AGENT910_COPIED_TEMP_CONTRACT_PROOF_CLOSEOUT.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/SOURCE_FRESHNESS_BRIDGE_COPIED_TEMP_V1.md`

## Assignment

Resolve or classify the Agent910 `src_ab_db_operational_truth` freshness blocker for copied-temp proof.

Agent910 failure:

```text
Required source src_ab_db_operational_truth freshness for requested as-of 2026-05-18 is BLOCKED and blocks publication
```

## Required Work

1. Verify protected boundary before analysis.
2. Inspect policy source registry and latest `source_freshness_result` rows for `src_ab_db_operational_truth`.
3. Determine which operational tables drive this source and why the source is blocked.
4. Identify whether already accepted Agent910 materializations are enough to clear this source on a copied DB.
5. If yes, create an accepted copied-temp bridge/materializer input and prove with:
   - `validate_policy_source_freshness.py --db <copy> --as-of 2026-05-18 --strict --json`
   - `validate_policy_gate_results.py --db <copy> --strict --json`
6. If no, produce the exact source requirement and do not claim green.

## Outputs

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911b_ab_operational_truth_source_freshness_closeout.md`

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911b_ab_operational_truth_source_freshness_evidence`

Required artifacts:

- `AB_OPERATIONAL_TRUTH_SOURCE_MATRIX.tsv`
- `SOURCE_FRESHNESS_ROWS_BEFORE_AFTER.tsv`
- `POLICY_GATE_ROWS_BEFORE_AFTER.tsv`
- `BRIDGE_OR_MATERIALIZER_RECOMMENDATION.md`
- validator outputs and exit matrix

## Stoplines

- Do not bridge unaccepted source packets.
- Do not treat missing stock freshness as operational truth freshness.
- Do not claim production source freshness from copied-temp rows.
- Do not production-apply anything.
