# Agent 10 - PO Inbound Line-Grain Source Truth

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_10_po_inbound_line_grain_source_truth_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/FULL_ORCHESTRATOR_REVIEW_CURRENT_STATE.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_4_po_inbound_refresh_closeout.md`
8. `~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/LINE31_PO1A_OLIVE_GREEN_PREORDER_AUTONOMOUS_BUSINESS_INGEST_HANDOFF__2026-05-04.md` if present
9. this starter prompt

## Mission

Resolve the root cause of the remaining PO/inbound blockers:

- `PO_INBOUND_REFERENCE_NOT_LINE_GRAIN=312`
- `PO_INBOUND_DOUBLE_COUNT=17`

Your job is to produce source-backed evidence and an executable repair plan for Agent 12. If safe, prove the repair on a temp DB copy. Do not mutate production `db/app.db` or the inbound workbook.

## Canonical Source Context

Inbound workbook:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Owner-confirmed context to preserve:

- PO-4.0 actual arrived truth is the workbook `Actual_qty` column total as currently maintained by the owner.
- PO-4.0 differences between sent and received should be noted, not silently corrected away.
- LINE31 PO1A is paid/preparation state, not received/current sellable stock.
- LINE31 PO1A current operations should preserve historical 450-set paid order truth while separating 338 non-Olive near-dispatch sets and 242 Olive Green exact-color preorder sets until receipt evidence exists.

## Write Boundary

Allowed writes:

- your assigned closeout;
- optional evidence files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_10_evidence/`;
- optional temp DB under `/private/tmp/agent10_po_inbound_line_grain.sqlite`.

Forbidden writes:

- production `~/Docs/Autonomous_business/db/app.db`;
- repo code or tests;
- `.claude/*`;
- inbound workbook or any workbook;
- external repos;
- supplier/cargo/payment systems.

## Required Investigation

Use read-only DB/workbook inspection and validators to answer:

1. Which `stock_ledger` rows are still coarse `reference_type='PO'` and what deterministic `PO_PART` or `PO_LINE` target should each map to?
2. Are `PO_INBOUND_DOUBLE_COUNT=17` rows caused by stale `fact_inventory_snapshot_size.inbound_stock`, open PO projection, line-grain mismatch, or received-vs-open semantics?
3. Does `scripts/sync_po_parts_from_inbound_calendar.py` currently parse the workbook after the owner update? If it fails, why?
4. What is the safest materialization model: update `stock_ledger` references directly, add a supersession/projection table, or rebuild snapshot inbound projection?
5. What exact command sequence should Agent 12 run, including backup/temp DB proof and post validators?

## Suggested Commands

Run from `~/Docs/Autonomous_business`.

```bash
python3 scripts/validate_inbound_sheet_consistency.py --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx" --json
python3 scripts/sync_po_parts_from_inbound_calendar.py --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx" --db db/app.db
python3 scripts/validate_po_money_gate.py --db db/app.db --inbound-workbook "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx" --as-of 2026-05-03 --json
```

```bash
python3 - <<'PY'
import json
from collections import Counter
p='exports/validation/release_agents4_7_20260504/post_operational_stock_integration_gates.json'
data=json.load(open(p))
for code in ['PO_INBOUND_REFERENCE_NOT_LINE_GRAIN','PO_INBOUND_DOUBLE_COUNT']:
    rows=[x for x in data.get('findings', []) if x.get('code')==code]
    print(code, len(rows))
    print(rows[:10])
PY
```

If useful, use a temp DB:

```bash
cp db/app.db /private/tmp/agent10_po_inbound_line_grain.sqlite
python3 scripts/validate_operational_stock_integration_gates.py --db /private/tmp/agent10_po_inbound_line_grain.sqlite --as-of 2026-05-03 --json
```

## Closeout Requirements

Your closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact source/workbook status and any schema drift;
- line-grain mapping strategy with table/column targets;
- double-count root cause and repair strategy;
- exact Agent 12 implementation instructions;
- owner attention required only if source evidence is insufficient.

Gate meaning:

- GREEN: source-backed line-grain and double-count repair path is clear and testable.
- YELLOW: root cause is known but source or implementation ambiguity remains.
- RED: PO/inbound cannot be repaired safely from available evidence.
