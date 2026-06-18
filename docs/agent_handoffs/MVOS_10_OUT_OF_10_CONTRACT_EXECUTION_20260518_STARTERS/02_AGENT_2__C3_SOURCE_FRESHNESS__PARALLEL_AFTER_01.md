# Agent 2: C3 Source Freshness And Policy Gate Proof

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_closeout.md`
8. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent2_c3_source_freshness_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent2_c3_source_freshness_evidence`

## Task

Build a read-only or copied-temp proof for the Source Truth Freshness Gate and C3 policy gates.

Produce:

- `SOURCE_FRESHNESS_ACCEPTED_PACKETS_MATRIX.tsv`
- `SOURCE_FRESHNESS_BLOCKER_MATRIX.tsv`
- `POLICY_GATE_MATRIX.tsv`
- command outputs supporting each gate result

Run where safe:

```bash
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
```

If a materializer is needed, use only copied-temp DBs under your evidence folder.

## Boundary

Read-only or copied-temp only. Do not edit repo files unless the orchestrator explicitly reassigns you as the serialized writer. Do not mutate production DB, workbook, schedulers, external systems, source pointers, or owner-publication surfaces.

## Gate Guidance

Use `Gate: GREEN` only if all required source rows are fresh for the declared scope or retained blockers correctly block publication.

Use `Gate: YELLOW` if any source gap, retained blocker, missing contract, or owner/CodeCaptain decision remains.

Use `Gate: RED` if source contracts conflict, copied-temp proof accidentally touches production, or freshness cannot be safely determined.
