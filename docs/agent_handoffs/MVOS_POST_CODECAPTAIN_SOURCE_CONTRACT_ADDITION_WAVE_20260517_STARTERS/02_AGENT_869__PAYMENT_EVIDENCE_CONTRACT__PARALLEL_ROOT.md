# Agent869 Starter: Payment Evidence Contract

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/agent869_payment_evidence_contract_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent869_payment_evidence_contract`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-17/190620_TASK-000_mvos-freeze-to-codecaptain-current-boundary-yellow-review/answer/Code Captain - Branch_17.05.2026_20_58_49.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/AGENT867_SYNTHESIS_FOR_CODECAPTAIN.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent867_synthesis_codecaptain_packet_closeout.md`
9. this starter prompt.

## Assignment

Produce the payment evidence addition needed before a copied-temp MVOS proof rerun.

You may read local payment evidence roots, repo configs, the manual balance workbook, and prior closeouts. You may write only to your assigned evidence folder and assigned closeout.

Manual balance workbook:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Owner truth to preserve:

- current manual balances were entered by the owner;
- an unmentioned `1,500,000 KZT` reserve deposit must remain counted as untouched reserve buffer;
- no bank/cash movement is authorized.

Do:

- Identify the exact freshness floor and payment evidence root CodeCaptain requires.
- Inspect the eligible payment evidence root read-only and record file hashes or absence of eligible files.
- If fresh payment-root evidence exists, package it locally.
- If no fresh payment-root evidence is required for copied-temp proof, draft a no-new-payment contract that states the exact window, inspected root, hashes or no-files proof, and no cash-movement authority.
- Separate bank manual balance evidence from payment-root evidence.
- Run safe read-only/copy-temp cashflow source-truth checks if available.

Do not:

- move money;
- mutate bank files, production DB, workbook, scheduler, configs, or external accounts;
- claim owner-publication or production-readiness.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- inspected payment root path and freshness floor;
- file hashes or no-eligible-file proof;
- manual balance treatment and reserve-buffer note;
- copied-temp materialization recommendation;
- remaining CodeCaptain questions, if any.
