# Agent 45 - Option A/B Cashflow Actual-Cash Reconciliation Read-Only Analysis

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_45_option_a_b_cashflow_actual_cash_recon_readonly_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_42.md`
7. Agent 37 cashflow evidence, especially `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/logs/47_manual_bank_anchor_comparison.txt`
8. this starter prompt

## Mission

Explain the actual-cash mismatch before Option B production apply:

- manual bank/cash anchor: `7,750,833.10 KZT` as of `2026-05-03 19:59 GMT+5`;
- rebuilt `fact_cashflow_daily.cash_close` on `2026-05-03`: `70,671,251.80 KZT`;
- difference: about `62.9M KZT`.

The goal is not to force cashflow green. The goal is to identify whether this is a known opening-balance/modeling issue, a missing bank anchor adjustment, an old historical ledger artifact, or a real business-cash exposure.

## Write Boundary

Allowed:

- read-only DB/config/source inspection;
- evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_45_evidence/`;
- assigned closeout.

Forbidden:

- repo code edits;
- production `db/app.db` writes;
- bank/config writes;
- workbook edits;
- external/live calls.

## Required Work

1. Trace `fact_cashflow_daily.cash_close` from the latest trusted opening balance to `2026-05-03`.
2. Compare DB cash daily rows against:
   - `config/bank_accounts.yaml`;
   - `config/bank_accounts_history.yaml`;
   - `~/Docs/Autonomous_business/config/bank_accounts_manual_ingest_3.5.2026.yaml` if present;
   - Kaspi Pay cash anchor artifacts from the 2026-05-04 order-entry/cashflow wave;
   - Agent 37 cashflow logs.
3. Identify the first date where modeled cash diverges materially from manual/bank truth.
4. Classify the mismatch:
   - source-repairable;
   - needs owner bank statement/account truth;
   - expected model-vs-actual difference that must be labeled;
   - unsafe/unknown.
5. Produce a plain-English owner summary plus machine-readable evidence.
6. Recommend whether Option B can apply structural cashflow fixes while keeping actual cash publication blocked or bannered.

## Expected Gate

`GREEN` if the mismatch cause is fully explained with no writes and an exact repair/banner path exists.

`YELLOW` if the mismatch is narrowed but needs owner/source evidence.

`RED` if cashflow actual-cash cannot be safely interpreted.
