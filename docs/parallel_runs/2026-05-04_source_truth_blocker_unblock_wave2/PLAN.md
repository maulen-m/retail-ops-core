# Source Truth Blocker Unblock Wave 2

Created: `2026-05-04`

## Objective

Clear the remaining post-Agent-8 operational integration blockers without false-green publication:

- `ADS_REFRESH_MISSING=4138`
- `ADS_COVERAGE_MISSING=4138`
- `ORDER_LIFECYCLE_MISSING_COMPLETED=442`
- `PO_INBOUND_REFERENCE_NOT_LINE_GRAIN=312`
- `PO_INBOUND_DOUBLE_COUNT=17`

Agent 8 already production-applied the accepted order-entry and D1 cashflow chain. This wave must preserve that result and only advance source-backed lifecycle, PO/inbound, and ads truth.

## Source State

Current accepted review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/FULL_ORCHESTRATOR_REVIEW_CURRENT_STATE.md`

Operational integration artifact:

`~/Docs/Autonomous_business/exports/validation/release_agents4_7_20260504/post_operational_stock_integration_gates.json`

Post-Agent-8 review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`

## Topology

First sequence: parallel read-only/source-specific agents.

- Agent 9: lifecycle residual blocker.
- Agent 10: PO/inbound line-grain and double-count blocker.
- Agent 11: ads source refresh and coverage blocker.

Second sequence: one serialized implementation/temp-DB agent after Agents 9-11 are reviewed.

- Agent 12: implement source-backed repairs and prove them on a temp DB or isolated evidence root. No production DB apply.

Third sequence: one serialized production release/apply agent after Agent 12 is reviewed.

- Agent 13: backup-first, env-gated production apply and validator replay.

Fourth sequence: one final rematerialization/owner-brief agent after Agent 13 is reviewed.

- Agent 14: rematerialize C3 policy state and daily owner brief only if source gates support it.

## Hard Rules

- No production `db/app.db` mutation before Agent 13.
- No external-system writes at any point unless a starter explicitly authorizes the exact write. This wave does not authorize ad-setting, merchant, supplier, payment, Google, Meta, Kaspi UI, or workbook writes.
- Missing ads must not be converted to zero cost unless source evidence proves `NO_SPEND_VERIFIED`.
- Delivered/completed lifecycle rows must not be synthesized without real `fact_orders_kaspi`, API, status-observation, or WebUI status evidence.
- PO/inbound repairs must not weaken the validator to accept coarse `PO` references.
- Profit publication stays blocked while ads, PO/inbound, lifecycle, SKU mapping, or cost gates remain red.

## Closeout Folder

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2`

## Expected Sequence

1. Launch Agents 9, 10, and 11 in parallel. Only the last completed agent pings the orchestrator.
2. Orchestrator reviews all three closeouts and validators.
3. Launch Agent 12 only if the first sequence provides enough source-backed repair instructions.
4. Launch Agent 13 only after Agent 12 proves the temp implementation.
5. Launch Agent 14 only after Agent 13 production apply is accepted.
