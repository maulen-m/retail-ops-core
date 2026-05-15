# Agent 9 - Lifecycle Residual Source Truth

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_9_lifecycle_residual_source_truth_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/FULL_ORCHESTRATOR_REVIEW_CURRENT_STATE.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_6_source_refresh_execution_closeout.md`
8. `~/Docs/Autonomous_business/docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md` if present
9. this starter prompt

## Mission

Resolve the root cause of the remaining `ORDER_LIFECYCLE_MISSING_COMPLETED=442` blocker after Agent 8.

Your job is to produce source-backed evidence and an executable repair plan for Agent 12. If you can safely prove the repair on a temp DB copy using existing scripts, do so. Do not mutate production `db/app.db`.

## Write Boundary

Allowed writes:

- your assigned closeout;
- optional evidence files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_9_evidence/`;
- optional temp DB under `/private/tmp/agent9_lifecycle_residual.sqlite`.

Forbidden writes:

- production `~/Docs/Autonomous_business/db/app.db`;
- repo code or tests;
- `.claude/*`;
- workbooks;
- external repos;
- live Kaspi/merchant/ads/payment/supplier systems.

## Required Investigation

Use read-only DB inspection and validators to answer:

1. Which exact delivered `sales_fact_v2` rows still lack completed lifecycle events?
2. Are those 442 rows missing because of store-code mismatch, order-id mismatch, status-stage mapping, date-window cutoff, stale `order_status_event`, or true missing source evidence?
3. Can `scripts/materialize_order_status_events_from_kaspi_orders.py` clear them on a temp DB with different parameters, or does it need a code change?
4. Which source table proves completion for each residual row: `fact_orders_kaspi`, `fact_order_status_observations`, WebUI status evidence, or none?
5. What exact command sequence should Agent 12 run, including temp DB proof and post validators?

## Suggested Commands

Run from `~/Docs/Autonomous_business`.

```bash
python3 - <<'PY'
import json
from collections import Counter
p='exports/validation/release_agents4_7_20260504/post_operational_stock_integration_gates.json'
data=json.load(open(p))
rows=[x for x in data.get('findings', []) if x.get('code')=='ORDER_LIFECYCLE_MISSING_COMPLETED']
print(len(rows))
print(Counter((x.get('evidence') or {}).get('store_code') for x in rows))
print(rows[:10])
PY
```

```bash
sqlite3 -readonly db/app.db "SELECT COUNT(*) FROM order_status_event; SELECT lifecycle_stage, COUNT(*) FROM order_status_event GROUP BY lifecycle_stage ORDER BY 2 DESC;"
python3 scripts/validate_operational_stock_integration_gates.py --db db/app.db --as-of 2026-05-03 --json > /private/tmp/agent9_gate.json
```

If useful, copy the DB and run existing lifecycle materialization against the copy only:

```bash
cp db/app.db /private/tmp/agent9_lifecycle_residual.sqlite
python3 scripts/materialize_order_status_events_from_kaspi_orders.py --db /private/tmp/agent9_lifecycle_residual.sqlite --as-of 2026-05-03 --run-id agent9-lifecycle-residual --strict --json
ENABLE_ORDER_STATUS_EVENT_WRITE=1 python3 scripts/materialize_order_status_events_from_kaspi_orders.py --db /private/tmp/agent9_lifecycle_residual.sqlite --as-of 2026-05-03 --run-id agent9-lifecycle-residual --strict --replace-run-id --apply --json
python3 scripts/validate_operational_stock_integration_gates.py --db /private/tmp/agent9_lifecycle_residual.sqlite --as-of 2026-05-03 --json
```

## Closeout Requirements

Your closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- residual count by store and root-cause category;
- exact evidence paths and SQL/scripts run;
- whether temp DB proof exists;
- exact Agent 12 implementation instructions;
- explicit stopline if any lifecycle rows lack real source evidence.

Gate meaning:

- GREEN: source-backed repair path is proven on temp DB or fully specified with no source ambiguity.
- YELLOW: root cause is known but implementation/source evidence remains incomplete.
- RED: lifecycle blocker cannot be safely repaired from available evidence.
