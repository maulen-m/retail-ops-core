# Agent912B / Transport Agent9122 - C3 Source Contract Split

Gate target: `GREEN` if table-level contract split is documented, fail-closed, and validated by focused checks where practical. Otherwise `YELLOW`.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/02_AGENT_9122__C3_SOURCE_CONTRACT_SPLIT__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9115.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-18/225410_TASK-000_mvos-agent911-yellow-retained-blocker-codecaptain/answer/Code Captain_18.05.2026_23_25_41.md`

## Assignment

Draft and implement the table-aware C3 source contract split so `src_ab_db_operational_truth` is no longer only a blunt monolithic status, while stale child sources still block the publication surfaces that depend on them.

## Scope

Primary write scope:
- `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1.md`
- assigned evidence/closeout folder.

Optional focused code/test scope only if needed and clearly non-conflicting:
- C3 source freshness contract/validator helper code;
- focused tests for child-source/roll-up behavior.

Do not edit PO validator/parser files. You are not alone in the codebase.

## Required Child Sources

- `src_ab_db_order_entry_truth`
- `src_ab_db_cashflow_truth`
- `src_ab_db_stock_truth`
- `src_ab_db_sales_truth`
- `src_ab_db_order_status_truth`
- `src_ab_db_ads_truth`

## Required Roll-Up Rules

- copied-temp proof may show child statuses and retained blockers;
- owner publication for a domain fails if a required child source is stale;
- stock/PO publication fails while stock child source is stale;
- ads/profit publication fails while ads child source is stale;
- stale child sources must never become publication-safe by naming split alone.

## Required Artifacts

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9122_c3_source_contract_split_evidence/`

Artifacts:
- `AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1.md` in repo contract docs;
- `SOURCE_FRESHNESS_CHILD_MATRIX.tsv`;
- `ROLLUP_PUBLICATION_DEPENDENCY_MATRIX.tsv`;
- `VALIDATOR_OR_CODE_IMPACT_NOTES.md`;
- focused test outputs if code changed;
- closeout.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9122_c3_source_contract_split_closeout.md`

The closeout must include:

```text
Gate: <GREEN/YELLOW/RED>
```

State whether Agent9125 can use the split contract in the copied-temp rerun.
