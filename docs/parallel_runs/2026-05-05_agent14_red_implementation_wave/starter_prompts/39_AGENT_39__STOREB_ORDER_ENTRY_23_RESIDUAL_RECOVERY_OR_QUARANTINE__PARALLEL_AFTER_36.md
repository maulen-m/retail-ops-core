# Agent 39 - STOREB 23 Order-Entry Residual Recovery Or Strict Quarantine

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_39_storeb_order_entry_23_residual_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_36.md`
6. this starter prompt

## Mission

Resolve the exact `23` remaining STOREB `ORDER_ENTRY_MISSING` rows from Agent 36 if real evidence exists. If not, produce the narrowest strict quarantine plan that keeps those orders out of product-level stock/COGS/profit publication without guessing SKU/size.

## Write Boundary

Allowed:

- read-only source investigation;
- evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_39_evidence/`;
- assigned closeout.

Forbidden:

- production DB writes;
- workbook edits;
- fuzzy mapping;
- header-only item identity;
- code edits unless tests first prove the existing quarantine contract cannot represent the already owner-authorized fallback safely.

## Required Starting Point

Use Agent 36 temp DB as the current residual source:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db`

Do not mutate it.

## Required Work

1. Extract the `23` exact residual rows from `validate_operational_stock_integration_gates.py`.
2. Cross-check Agent 31 and Agent 33 evidence for each order.
3. For each order, classify:
   - exact recoverable from API/article/size evidence;
   - strict quarantine candidate with no safe product identity;
   - still unknown/blocking.
4. If any exact recoveries exist, create a temp DB copy and prove the exact materialization idempotently.
5. If strict quarantine is the only safe path, produce a proposed contract and machine-readable candidate file, but do not weaken validators without tests and explicit evidence.
6. Preserve all rows fail-closed if any product identity is unclear.

## Required Outputs

- `agent_39_evidence/storeb_23_residual_classification.csv`
- `agent_39_evidence/storeb_23_residual_classification.json`
- if applicable: `agent_39_evidence/storeb_23_strict_quarantine_contract_draft.md`
- assigned closeout with exact next action.

## Required Gates

Run and record:

```bash
python3 scripts/validate_operational_stock_integration_gates.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --json
python3 scripts/validate_order_cashflow_coverage.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --strict --json
```

If a temp DB recovery is attempted, rerun operational integration, order cashflow coverage, and cashflow invariants on that temp DB.

## Expected Gate

`GREEN` only if all 23 are either exactly recovered or represented by a strict, validator-compatible, evidence-backed quarantine with tests.

`YELLOW` is expected if the correct output is an owner/contract decision pack or a partial recovery.

`RED` if any identity is guessed or product-level stock/profit would silently include unknown rows.
