# Agent 5 - Cashflow, Cargo, Supplier Obligations, And Reserve Gates

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_5_c3_cashflow_cargo_obligations_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/ops/OPERATIONAL_DECISION_POLICY_V1.md`
7. `~/Docs/Autonomous_business/config/operational_decision_policy.yaml`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/OWNER_QA_OPTION_C_INPUTS_20260503_203849_ALMT.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/OWNER_QA_C3_SUPPLIER_LINE31_CONTEXT_20260503_210720_ALMT.md`
10. this assigned starter prompt.

## Mode

Read-only analyst. Do not edit repo files, `.claude/*`, DB, workbooks, payment files, env files, bank data, supplier files, or external systems. The only allowed write is your assigned closeout.

## Mission

Define the C3 cashflow/cargo/obligation model.

Cover:

- latest manual bank account balance ingest at `~/Docs/Autonomous_business/config/bank_accounts_manual_ingest_3.5.2026.yaml`;
- weekly owner balance ingest requirement;
- minimum cash reserve `1,500,000 KZT`;
- Kaspi Pay payout timing after customer receipt;
- cargo arrival, cargo payment, Astana takeover, warehouse receipt, and payment-date distinctions;
- SHR supplier obligation and evidence paths;
- ARC PO1A payment evidence and relation to inbound/cargo calendar;
- unknown COGS and unknown supplier/cargo obligations blocking profit/cashflow green;
- how Agent 7 should avoid double counting bank/cashflow/payment events.

## Required Closeout Content

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files/configs/reports inspected with absolute paths;
- proposed event model and DB/source-pointer needs;
- decision-grade gates for cashflow and purchase approval;
- known stale or missing balance/payment/source blockers;
- Agent 7 test plan;
- confirmation that no repo, DB, env, bank, supplier, payment, or Web_automation files were modified.
