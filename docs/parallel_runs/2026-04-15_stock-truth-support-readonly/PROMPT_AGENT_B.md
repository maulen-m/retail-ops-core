PROMPT_AGENT_B

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-04-15_stock-truth-support-readonly/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_stock-truth-support-readonly`

Your role

- read-only source-comparison analyst

Your job

- compare the known stock sources and judge which are closest to warehouse truth
- focus on exact SKU-size disagreements, OOS transitions, and operator-fact conflicts

Required sources

- `~/Docs/Web_automation/exports/stock_snapshots/2.3.26/stock_snapshot_2.3.2026_1.xlsx`
- `~/Docs/Autonomous_business/excel/stock_snapshot_2.3.2026.xlsx`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/stock_audit_2026-04-04.xlsx`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/backups/stock_audit_2026-04-04.20260404_225313_235600.xlsx`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/MEMO_stock_audit_handoff_2026-04-15.md`

Required questions

1. Which source pair is closest on March 2, 2026?
2. Which SKU-size rows diverge most between March 2 and the reconstructed current stock?
3. Do the known operator facts around:
   - `LINE52 4XL`
   - `T-SHIRT BLACK S/M/L`
   match warehouse truth, offer truth, neither, or remain ambiguous?
4. Which exact SKU-size rows should the owner manually review first?

Rules

- do not modify repo files
- do not mutate any DB
- do not read Agent C's report before publishing your own first-pass findings

Output

- write findings to `agent_b_report.md`
- end with one short recommendation:
  - `CONTINUE_PROVISIONAL`
  - `CONTINUE_AFTER_NAMED_REVIEW`
  - `STOP_UNTIL_CANONICAL_STOCK`
