# Agent 33 - STOREB API Order-Entry Temp Apply

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_33_storeb_api_order_entry_temp_apply_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_30.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_storeb_order_entry_negative_ledger_readonly_recovery_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_31.md`
7. this starter prompt

## Mission

On a fresh temp DB only, materialize the `253` exact STOREB API item-entry rows recovered by Agent 31, then rerun the sales/order-entry/stock/cashflow validators to prove the remaining non-ads residuals.

This is not a production apply. This lane should reduce `ORDER_ENTRY_MISSING` without weakening truth rules.

## Coordination

You are not alone in the codebase. Agent 32 is working on ads temp materialization, and a Facebook_ads agent is working outside this repo. Do not revert or overwrite edits made by other agents.

Avoid ads-owned files unless a validator import makes a read necessary. If you encounter unexpected concurrent edits in a file you need to modify, stop and close out YELLOW instead of merging blindly.

## Write Boundary

Allowed:

- tests written first for the STOREB API evidence temp-apply contract;
- one narrow non-ads materializer script if needed;
- tiny changes to existing non-ads order-entry/rebuild validators only if tests prove the current path cannot consume Agent 31 evidence safely;
- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_33_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- live Kaspi API calls;
- ad-platform writes;
- Web_automation writes;
- Facebook_ads writes;
- ads materializer/canonical-reader changes;
- product-name or fuzzy-size mapping;
- clearing the `23` quarantined STOREB rows;
- blind clamping of negative ledger rows.

## Inputs

Use Agent 30 temp proof as the baseline temp DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_30_evidence/agent30_non_ads_contracts_temp_proof_20260504.db`

Use Agent 31 evidence:

- summary: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_evidence/agent31_summary.json`
- safe rows: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_evidence/storeb_recoverable_rows_preview.jsonl`
- sanitized API entries: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_evidence/storeb_kaspi_api_readonly_entries_sanitized.jsonl`
- quarantine rows: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_evidence/storeb_still_quarantined_rows.csv`
- negative-ledger queue: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_evidence/negative_ledger_owner_employee_review_queue.csv`

## Required Work

1. Write tests first for the materialization contract:
   - only `API_ITEM_ENTRY_SKU_ID_SIZE_MAPPED` rows are inserted;
   - `23` blocked rows remain quarantined;
   - header-only target SKU/name/size fields are not used as truth;
   - the script is idempotent;
   - writes require an explicit env gate plus `--apply`.
2. Copy the Agent 30 temp DB to a fresh Agent 33 temp DB under the assigned evidence folder.
3. Record before counts and validator residuals.
4. Apply only the `253` safe STOREB rows into `fact_order_entries_kaspi` on the Agent 33 temp DB.
5. Rebuild `sales_fact_v2` from Kaspi entries using the repo-owned rebuild path.
6. Rerun order-entry, stock, and cashflow validators against the Agent 33 temp DB through `2026-05-04`.
7. Produce a before/after residual matrix that makes these counts explicit:
   - `ORDER_ENTRY_MISSING`;
   - remaining STOREB quarantine rows;
   - negative-ledger rows;
   - any cashflow/order-entry validator changes.
8. Keep ads residuals out of scope except as unchanged blockers.

## Expected Decision

GREEN is allowed only if the temp DB proves:

- `253` safe STOREB rows were materialized from exact API item-entry evidence;
- the `23` blocked rows are still quarantined;
- temp validators pass or only known ads/negative-ledger/manual-review blockers remain;
- no production DB, workbook, or external-system write occurred.

YELLOW is correct if code/evidence works but strict publication remains blocked by the `23` mapping rows, `16` negative-ledger review rows, ads source gates, or other known manual-review blockers.

RED is correct if the temp apply cannot be made deterministic without fuzzy mapping or if any required gate fails unexpectedly.

## Required Verification

Run the smallest relevant gates and record exact commands/results:

```bash
python3 -m py_compile <changed-python-files>
pytest -q <new-or-affected-tests>
sqlite3 -readonly <agent33-temp-db> "PRAGMA integrity_check;"
python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db <agent33-temp-db> --as-of 2026-05-04 --strict
python3 scripts/validate_operational_stock_integration_gates.py --db <agent33-temp-db> --as-of 2026-05-04
python3 scripts/validate_cashflow_invariants.py --db <agent33-temp-db>
```

If a listed CLI has different flags, discover the actual `--help` and use the repo-supported equivalent. Do not skip a validator silently.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run with pass/fail;
- temp DB path;
- before/after residual table;
- exact count of inserted/idempotently skipped rows;
- exact count of rows left quarantined;
- remaining blocker list;
- explicit production apply status.
