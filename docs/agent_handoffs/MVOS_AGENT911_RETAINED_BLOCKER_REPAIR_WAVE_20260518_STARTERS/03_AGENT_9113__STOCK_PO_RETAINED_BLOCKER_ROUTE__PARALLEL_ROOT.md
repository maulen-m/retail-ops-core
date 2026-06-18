# Agent911C / Transport Agent9113 - Stock/PO Retained Blocker Route

Gate target: `YELLOW` unless a real source-backed stock freshness route already exists. Owner says no fresher stock source currently exists.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/03_AGENT_9113__STOCK_PO_RETAINED_BLOCKER_ROUTE__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/AGENT910_COPIED_TEMP_CONTRACT_PROOF_CLOSEOUT.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/PO_LINE61_REAL_SHORTAGE_COPIED_TEMP_V1.md`
8. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`

## Assignment

Make the stock/PO blocker honest and machine-readable without pretending that stale stock is fresh.

Owner truth:

- No fresher stock source than the already-available evidence exists yet.
- PO-4.0 Line61 ordered `115`, actual received `92`, shortage `23` is true business fact.
- Known shortages: XL `7`, 2XL `5`, 3XL `6`, 4XL `5`.

## Required Work

1. Verify protected boundary before analysis.
2. Inspect Agent910 PO failures:
   - stale stock snapshot;
   - `validate_po_dashboard_invariants`;
   - `validate_po_money_gate`.
3. Preserve no-fresher-stock-source as a retained blocker, not a fake green.
4. Prove that the Line61 `23` delta is consistently represented as real shortage in local evidence and contracts.
5. Produce a recommended validator/source-contract route:
   - what can be yellow-retained now;
   - what exact fresh stock source is required for future green;
   - what must not be changed until that source exists.

## Outputs

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911c_stock_po_retained_blocker_route_closeout.md`

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911c_stock_po_retained_blocker_route_evidence`

Required artifacts:

- `STOCK_SOURCE_FRESHNESS_REQUIREMENT.md`
- `PO4_LINE61_SHORTAGE_RECONFIRMED_MATRIX.tsv`
- `PO_VALIDATOR_BLOCKER_MATRIX.tsv`
- `RETAINED_BLOCKER_CONTRACT_RECOMMENDATION.md`
- command logs and boundary hashes

## Stoplines

- Do not claim stock freshness green without a fresher source.
- Do not treat the Line61 23-unit shortage as workbook error.
- Do not mutate stock, PO, workbook, or production DB.
