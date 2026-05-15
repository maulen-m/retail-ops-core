# Agent 14 RED Implementation Wave Plan

Generated: `2026-05-05`

## Objective

Implement and prove the minimum safe repairs needed after Agent 14's RED stopline:

- refresh derived sales, stock-ledger, snapshot, and cashflow daily tables to the latest complete as-of in an isolated temp DB;
- correct C3 source freshness and exception semantics without weakening fail-closed gates;
- import/prove usable ACMEWEAR ads evidence from Web_automation, including aggregate absence/no-spend support, without faking STOREB coverage.

This wave is a temp-proof implementation wave. It must not production-apply DB writes.

## Inputs

Read-only closeouts:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_15_derived_table_freshness_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_16_c3_policy_exception_semantics_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_17_ads_evidence_retry_import_plan_closeout.md`

Owner truth:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`

Current accepted production state after Agent 13:

- lifecycle residual cleared;
- PO/inbound line-grain blockers cleared;
- production DB integrity passed;
- operational gate narrowed to ads-only before Agent 14 C3 rematerialization exposed broader policy/source freshness issues.

## Agent Split

Agent 18: derived table temp proof.

Agent 19: C3 policy and exception semantics temp proof.

Agent 20: ads materializer temp proof.

Agent 21: serial combined proof after Agents 18-20.

## Parallel Safety

Agents 18-20 can run in parallel only because:

- their write sets are disjoint;
- no production DB writes are allowed;
- no workbook/external-system writes are allowed;
- each agent must test first and close out if unexpected concurrent edits appear.

## Success Criteria For Agents 18-20

Each agent must:

- write focused tests before implementation changes;
- keep dry-run/apply write paths env-gated;
- run focused tests for its surface;
- prove behavior against an isolated temp DB where applicable;
- leave a closeout with `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- list exact files changed and commands run.

## Success Criteria For Agent 21

Agent 21 may recommend production apply only if a combined temp DB proves:

- `sales_fact_v2` reaches `2026-05-04`;
- `stock_ledger` reaches `2026-05-04`;
- `fact_inventory_snapshot_size` has a `2026-05-04` rebuilt snapshot;
- `fact_cashflow_events` and `fact_cashflow_daily` reach `2026-05-04`;
- C3 exception semantics separate accepted controls from unresolved blockers;
- ACMEWEAR ads blockers reduce according to source evidence;
- STOREB remains honestly blocked unless fresh product evidence is available;
- strict validators pass or any remaining blocker is explicitly classified.

Production apply remains a separate serialized lane.
