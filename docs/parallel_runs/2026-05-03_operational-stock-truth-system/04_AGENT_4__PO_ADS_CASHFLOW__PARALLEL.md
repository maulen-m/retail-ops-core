# Agent 4 - PO, Inbound, Ads, Cashflow Analyst

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/04_AGENT_4__PO_ADS_CASHFLOW__PARALLEL.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-03/101657_TASK-000_operational-stock-orders-sales-system-review/Answer/Code_Captain_answer_2026-05-03_12_05_00.md`

Role:

- Read-only analyst.
- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not read sibling reports before publishing your first-pass report.

Focus:

- PO part/line grain and inbound calendar truth.
- Ads active-scope and STOREB coverage gaps.
- D1 Kaspi Pay cashflow semantics.
- Cargo/payment/cashflow decision gates.

Inspect:

- `~/Docs/Autonomous_business/docs/validation/PO_CONTRACT.md`
- `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
- `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- `~/Docs/Autonomous_business/docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`
- `~/Docs/Autonomous_business/config/ads_active_scope.yaml`
- PO sync, ads scrape, and cashflow scripts.

Output:

- Write closeout/report to `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_4_po_ads_cashflow_closeout.md`.

Required report sections:

- READCHECK.
- PO/inbound truth model and gaps.
- Ads coverage gate recommendation.
- D1 cashflow implementation risks.
- Tests Agent 7 should write first.
- Stoplines before PO/cargo/product-test decisions.
- Standalone line: `Gate: <GREEN/YELLOW/RED>`.
