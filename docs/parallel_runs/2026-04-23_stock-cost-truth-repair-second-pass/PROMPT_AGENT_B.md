# PROMPT_AGENT_B — Audit Repo And Pack Cost Truth Surfaces

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PLAN.md`
5. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass`

## Role

You are Agent B, read-only analyst.

Your job is to pin down exactly how landed-cost truth is being lost, mislabeled, or omitted in repo and Oracle-pack consumer surfaces.

## Independence Rule

Do not read Agent C's report before publishing your own first-pass report.

## Primary Question

Is the external expert's understated valuation mainly an analyst error, or is it mostly caused by the cost surfaces we gave him?

Treat that as the core question and answer it with file-backed evidence.

## Inspect What You Need

Likely high-priority surfaces:

- `~/Docs/Autonomous_business/scripts/sync_truth_workbook_to_db.py`
- `~/Docs/Autonomous_business/scripts/sync_dim_sku_from_dim_sku_light.py`
- `~/Docs/Autonomous_business/scripts/sync_po_parts_from_inbound_calendar.py`
- `~/Docs/Autonomous_business/core/cashflow/paid_capital_truth.py`
- `~/Docs/Autonomous_business/scripts/validate_inventory_cost_drift.py`
- `~/Docs/Autonomous_business/docs/ARCHITECTURE.md`
- `~/Docs/Autonomous_business/docs/profit/PROFIT_REALISM_CONTRACT.md`
- `~/Cowork/Projects/Sourcing-Research/docs/inventory/Dim_sku_light_v7.md`
- `~/Cowork/Projects/Sourcing-Research/docs/inventory/Master_Inventory_Rules_v9.md`
- `~/Cowork/Projects/Sourcing-Research/docs/inventory/PO_making_logic_v3.md`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/product_kaspi_offer_mapping_catalog.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/current_stock_rebuild_2026-04-23.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/inventory_business_eval_tables_2026-04-23.xlsx`

Inspect additional consumers only if needed to answer the questions below.

## Required Findings

Your report must answer:

1. Where exactly is `base` being published or consumed as `cogs_kzt`?
2. Which repo surfaces still default to `DIM_SKU_light_v6`, and what is the smallest safe way to retire or bypass that default?
3. Which SKU families flagged by the expert as missing COGS are actually covered in `Dim_sku_light_v7.md`?
4. What is the exact landed-cost formula and parameter surface Agent A should treat as current truth?
5. Which repair can be done without DB mutation, and which surfaces would still require a rebuild or DB update?
6. What is the smallest safe repair sequence for Agent A?
7. Which validations should Agent A run immediately after the repair?

## Constraints

- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not produce final business truth; produce a source-backed repair brief for Agent A.
- Keep the report concise, ranked, and actionable.

## Output

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_b_report.md`

Use this shape:

1. Findings (highest severity first)
2. Exact file/line references
3. Smallest safe repair sequence for Agent A
4. Open questions / residual uncertainty
5. Commands run
