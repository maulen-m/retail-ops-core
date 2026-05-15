# Agent 3 - Cashflow, Bank, And Obligations Analyst

Mode: read-only analyst.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_5_c3_cashflow_cargo_obligations_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_8_c3_daily_runner_owner_brief_closeout.md`
8. This assigned starter prompt.

## Mission

Find the safest, most efficient way to unblock cashflow/bank/obligation truth:

- blocked `src_bank_manual_ingest`;
- stale `fact_cashflow_events`;
- stale `fact_cashflow_daily`;
- malformed or unnormalized `~/Docs/Autonomous_business/config/bank_accounts_manual_ingest_3.5.2026.yaml`;
- open supplier/cargo obligation evidence slots;
- cash reserve gate and supplier/cargo debt visibility.

## Allowed Work

You may read repo files, config files, DB tables through read-only SQLite, and local source evidence paths.

You must not edit configs, DB rows, bank files, payment evidence, supplier files, or external repos.

Do not print sensitive bank/account details unless needed for a validation summary; prefer structural findings and totals/gate state over raw account contents.

## Required Analysis

Determine:

- why the manual bank ingest is blocked;
- the minimal normalization or parser change needed;
- whether existing scripts can ingest the latest bank snapshot into DB safely;
- how to keep bank snapshots as reconciliation evidence, not duplicate cashflow events;
- how to represent SHR supplier debt, ARC PO1A payment evidence, cargo payment due/made state, and open obligations;
- exact command sequence and validators for Agent 6;
- any owner action required to approve ambiguous balances or obligation values.

## Required Output

Write a concise, source-backed closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files/scripts/tables inspected;
- exact recommended Agent 6 command sequence;
- what can be fixed without owner attention;
- what requires owner attention, if anything;
- validation gates;
- rollback/safety notes for any proposed DB/config write.

If owner attention is required, include `OWNER_ATTENTION_REQUIRED` with exact paths and plain-English steps.

Do not read sibling agent reports before writing your own first-pass findings.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_3_cashflow_bank_obligations_closeout.md`
