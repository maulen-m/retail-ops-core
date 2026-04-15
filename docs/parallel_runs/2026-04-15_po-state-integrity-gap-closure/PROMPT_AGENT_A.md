PROMPT_AGENT_A

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-04-15_po-state-integrity-gap-closure/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_po-state-integrity-gap-closure`

Your role

- only write-capable execution agent
- only agent allowed to write shared repo state
- only agent allowed to mutate `db/app.db`

Primary objective

- close the PO/cash/stock/sales/cashflow integrity gaps in causal order until the repo is either decision-grade for these domains or honestly narrowed to one explicit remaining blocker

Strict boundaries

- do not touch the Google Sheet API integration track
- do not touch the CRM / WhatsApp / import rollout track
- do not invent direct DB writes from PO-agent chat conversations
- use backup-first discipline before every DB apply path

Execution order

1. Read `agent_b_report.md` and `agent_c_report.md`.
2. Update `status_board.md` to show execution started.
3. Record baseline facts in `agent_a_execution_log.md`.
4. Execute the smallest safe repair sequence:
   - source / funding gap closure
   - cash balance freshness
   - stock freshness
   - sales + cashflow freshness
   - registry / validator closure
5. After every write:
   - log the exact command
   - log the DB backup path if DB touched
   - rerun the smallest relevant validator
6. Finish with final gate results and rollback steps.

Minimum outputs

- `agent_a_execution_log.md`
- updated `status_board.md`
- any new or updated registry / freshness artifacts created by the run

Rules

- do not loosen validators
- do not hide provenance
- do not start DB writes before upstream analysis
- do not leave a silent partial state; if blocked, log the exact blocker

Success

- task is completed or narrowed honestly to a smaller explicit stopline
