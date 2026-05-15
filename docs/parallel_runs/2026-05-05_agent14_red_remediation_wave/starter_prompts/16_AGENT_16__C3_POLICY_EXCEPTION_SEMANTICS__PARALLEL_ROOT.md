# Agent 16 - C3 Policy Source Freshness And Exception Semantics

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_16_c3_policy_exception_semantics_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_remediation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_14_c3_owner_brief_rematerialization_closeout.md`
7. `~/Docs/Autonomous_business/config/operational_decision_policy.yaml`
8. this starter prompt

## Mission

Read-only diagnosis of C3 policy/source freshness and exception queue semantics after Agent 14 RED.

Focus on:

- `src_ecommerce_po_artifacts` stale directory mtime;
- `src_sourcing_research_supplier_routes` stale directory mtime;
- `src_facebook_ads_external_ads` stale directory mtime;
- `src_inbound_workbook` future-dated relative to `2026-05-03`;
- open high-severity owner override/quarantine exceptions that block `exception_queue`.

Decide whether these are true business blockers, policy-source pointer bugs, as-of-date bugs, or accepted active controls that should be represented differently.

## Write Boundary

Read-only against production `db/app.db`.

Allowed writes:

- your closeout;
- optional read-only query outputs under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_16_evidence/`.

Forbidden:

- production DB writes;
- policy YAML edits;
- code changes;
- external repo writes.

## Required Work

1. Inspect `core/ops/policy_registry_c3.py`, `core/ops/policy_materialization_c3.py`, and policy validators.
2. Classify each source freshness blocker as true blocker vs stale pointer/as-of issue.
3. Inspect the 9 open high-severity exceptions and classify whether each should remain publication-blocking or become an accepted active control.
4. Propose exact test-first implementation tasks for the next lane.
5. Provide stoplines for owner attention, if any.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- blocker classification table;
- exact code/policy docs that need changes later;
- tests to write before changes;
- whether human owner action is required.
