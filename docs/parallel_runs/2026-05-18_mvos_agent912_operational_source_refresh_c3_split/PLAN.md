# Agent912 Operational Source Refresh and C3 Split Plan

Created: 2026-05-18 23:28 +05

## Status

Status: `AGENT912_APPROVED_FOR_READONLY_COPIED_TEMP_AND_NARROW_CODE_TEST_EXECUTION`

CodeCaptain answer ingested:
- `~/Docs/Oracle/Autonomous_business/2026-05-18/225410_TASK-000_mvos-agent911-yellow-retained-blocker-codecaptain/answer/Code Captain_18.05.2026_23_25_41.md`

Controlling prior proof:
- Agent9115 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911e_combined_synthesis_rerun_closeout.md`
- Agent9115 evidence: `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911e_combined_synthesis_rerun_evidence`

Current top-level gate:
- `YELLOW_OPERATIONAL_SOURCE_REFRESH_NEXT`

## Owner Approval

The human owner approved Option 1 and all required approvals for this wave.

Allowed:
- read-only analysis;
- copied-temp DB copies and materialization under evidence roots;
- local evidence and contract docs;
- focused code and tests for narrow parser/validator repairs;
- validator reruns on copied DB;
- CodeCaptain packet preparation.

Not authorized:
- production DB writes;
- workbook writes;
- scheduler, LaunchAgent, or cron changes;
- source-pointer writes;
- Web_automation writes;
- Kaspi/API/WebUI writes;
- external writes;
- ad-platform writes;
- cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication;
- production preflight;
- production apply.

Green rule:
- only call `GREEN` when assigned checks pass and protected surfaces remain unchanged;
- otherwise call `YELLOW` with exact blockers;
- never convert retained blockers into green language.

## CodeCaptain Accepted Diagnosis

Agent9115 is a useful `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`, not a failed run and not a green copied-temp proof.

Accepted improvements:
- order-entry freshness passes after Agent905 `164` rows plus Agent911A `15` STOREB identity-bearing API rows;
- day-complete passes;
- COGS completeness passes with Agent873 copied-temp unit evidence;
- exception queue validator passes while retaining visible exceptions;
- cashflow invariants and order-cashflow coverage pass;
- ads offer-universe coverage and ads spend reality pass;
- Agent911D migrated `To_pay_* (live)` parser/schema fix passes focused tests.

Retained blockers:
- `src_ab_db_operational_truth` remains blocked;
- stale operational tables are `fact_inventory_snapshot_size`, `stock_ledger`, `sales_fact_v2`, `order_status_event`, `ads_source_refresh_runs`, and `ads_campaign_product_daily`;
- policy gates `ads_source_truth`, `source_freshness`, and `stock_source_truth` remain blocked;
- PO dashboard fails because stock snapshot is stale: `stock_date=2026-05-04`, cutoff `2026-05-17`;
- PO money gate still fails `inbound_sheet_consistency`, `single_truth_system`, `cogs_integrity`, and `single_truth_alignment`;
- `sync_po_parts_from_inbound_calendar.py` dry-run still fails on `DIM_SKU_light` header parser issue.

Owner facts to preserve:
- PO-4.0 Line61 ordered/cargo `115`, actual received `92`, shortage `23`;
- known shortages: XL `7`, 2XL `5`, 3XL `6`, 4XL `5`;
- no fresher stock source exists yet.

## Execution Structure

Parallel root group `agent912_root`:

| Agent | Role | Write scope |
| --- | --- | --- |
| `9121` | Operational source refresh copied-temp packet | Assigned evidence/closeout only; no shared repo code/docs writes. |
| `9122` | C3 table-level source contract split | `docs/contracts/mvos_source_contracts/AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1.md`, source-contract registry draft artifacts, focused source-freshness contract docs/tests if needed. |
| `9123` | PO Line61 accepted-shortage classification | PO shortage contract docs plus focused PO validator code/tests only. |
| `9124` | `DIM_SKU_light` parser repair | `scripts/sync_po_parts_from_inbound_calendar.py` and focused parser tests/docs only. |

Gated synthesis:

| Agent | Role | Dependency |
| --- | --- | --- |
| `9125` | Combined copied-temp rerun and CodeCaptain packet recommendation | Run only after `9121`-`9124` closeouts are reviewed. |

## Root Lane Requirements

### Agent9121

Goal:
- create a copied-temp operational source refresh packet for the six stale tables.

Tables:
- `fact_inventory_snapshot_size`;
- `stock_ledger`;
- `sales_fact_v2`;
- `order_status_event`;
- `ads_source_refresh_runs`;
- `ads_campaign_product_daily`.

Also observe already-fresh tables:
- `fact_cashflow_daily`;
- `fact_cashflow_events`;
- `fact_order_entries_kaspi`.

Required outputs:
- `BOUNDARY_SNAPSHOT_AGENT9121.json`;
- `OPERATIONAL_TABLE_REFRESH_BEFORE_AFTER.tsv`;
- `OPERATIONAL_SOURCE_REFRESH_ROUTE_MATRIX.tsv`;
- `SOURCE_PACKET_OR_MATERIALIZER_ROUTE.md`;
- `VALIDATOR_REPLAY_RECOMMENDATION.md`;
- closeout.

### Agent9122

Goal:
- split monolithic `src_ab_db_operational_truth` into child source contract semantics without weakening publication safety.

Child sources:
- `src_ab_db_order_entry_truth`;
- `src_ab_db_cashflow_truth`;
- `src_ab_db_stock_truth`;
- `src_ab_db_sales_truth`;
- `src_ab_db_order_status_truth`;
- `src_ab_db_ads_truth`.

Required outputs:
- `AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1.md`;
- child-source matrix;
- roll-up/publication dependency matrix;
- validator/code impact notes;
- closeout.

### Agent9123

Goal:
- classify exact Line61 `23` shortage as accepted owner-confirmed business truth without turning PO money gate green.

Required facts:
- ordered/cargo `115`;
- actual received `92`;
- shortage `23`;
- XL `7`;
- 2XL `5`;
- 3XL `6`;
- 4XL `5`.

Required behavior:
- removes this exact delta from unknown mismatch;
- leaves unrelated PO money failures visible;
- does not authorize stock, PO, workbook, or production mutation.

### Agent9124

Goal:
- tests-first narrow repair for `DIM_SKU_light` header parser used by `sync_po_parts_from_inbound_calendar.py` dry-run.

Required behavior:
- no workbook mutation;
- no production DB mutation;
- no broad PO refactor;
- focused tests pass.

### Agent9125

Goal:
- rerun combined copied-temp proof after accepted root inputs.

Required output:
- `PROOF_BOARD.json`;
- `PROOF_BOARD.md`;
- `VALIDATOR_EXIT_MATRIX.tsv`;
- `RETAINED_BLOCKER_MATRIX.tsv`;
- `CODECAPTAIN_PACKET_RECOMMENDATION.md`;
- closeout.

## Stoplines

Stop `RED` if:
- production DB is mutated;
- workbook is mutated;
- scheduler/source pointer/external system is mutated;
- copied-temp proof is described as production truth;
- any source child is marked fresh without source evidence;
- Line61 shortage is used to green unrelated PO failures;
- `DIM_SKU_light` repair expands into broad PO rewrite;
- owner publication or production preflight is implied.
