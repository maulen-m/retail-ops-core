# Agent862 Starter: Cash And Payment Source Truth

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent862_cash_payment_source_truth_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_freeze_to_codecaptain_wave/20260517_183241/agent862_cash_payment_source_truth`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent859_synthesis_copied_temp_rerun_closeout.md`

## Assignment

Resolve or narrow `cashflow_source_truth` and `src_payment_evidence_root` blockers for copied-temp MVOS proof.

Important source:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Known operator truth:

- current manual account and cash balances were entered in that workbook;
- a separate `1,500,000 KZT` reserve deposit must count toward untouched reserves/buffer.

Do:

- Inspect payment evidence root, bank/manual balance config, and latest manual balance sheets.
- Compare with Agent848/Agent859 cash routes.
- Determine if `src_payment_evidence_root` can become copied-temp FRESH with current local evidence, or what exact source is missing.
- Run safe read-only/copy-only cashflow validators where useful.
- Build a source-decision packet for Agent867.

Do not:

- write bank files, payment records, production DB, workbook, scheduler, or external systems.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- cash/payment evidence source matrix;
- exact reserve handling;
- recommended copied-temp overlay or explicit blocker.
