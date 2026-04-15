PROMPT_AGENT_C

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-04-15_po-state-integrity-gap-closure/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_po-state-integrity-gap-closure`

Your role

- read-only analyst
- focus: freshness/completeness across cash, stock, sales, cashflow, ops, and the domain-registry / validator surface

Your job

- produce a current freshness map of the business system
- identify the smallest set of source refreshes and rebuilds needed to make the system decision-grade across finance, inventory, and ops
- define the visible domain-registry / freshness board requirements

Required sources to inspect

- `config/bank_accounts.yaml`
- `config/bank_accounts_history.yaml`
- `config/total_balance.md`
- `config/inventory_totals.md`
- `db/app.db` read-only
- `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`
- `docs/PLAN_INBOUND_FULL_REPO_STATE_SYNC_2026-03-02.md`
- any current validators / runbooks needed to prove freshness

Questions you must answer

1. What is the latest trusted date for:
   - bank balances
   - inventory snapshot
   - harmonized sales facts
   - raw Kaspi order facts
   - cashflow events
   - cashflow daily
2. Which gaps are pure freshness lag versus true missing pipelines?
3. What is the minimum execution order Agent A should follow to refresh these surfaces safely?
4. What should the domain registry include so future gaps are instantly visible?

Rules

- do not modify repo files
- do not mutate the DB
- do not read Agent B's report before publishing your own first-pass findings

Output

- write findings to `agent_c_report.md`
- keep findings concise, source-backed, and actionable for Agent A
- include exact validator commands Agent A should rerun after each domain refresh
