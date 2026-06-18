# Agent 1 Starter - Autonomous_business Strict Gate Repair

You are Agent 1. Your lane is the serialized write-capable Autonomous_business strict-gate repair lane for LINE31 `GREEN_EXCEPT_CREATIVE` readiness.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_repair_round2/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_ROUND2_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_ROUND2_20260601_STARTERS/01_AGENT_1__AB_STRICT_GATE_REPAIR__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent1_ab_strict_cash_stock_repair_closeout.md`
7. `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.md`
8. `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_20260601/final_synthesis/RETAINED_BLOCKERS.md`
9. `~/.codex/skills/write-gated-db-repair/SKILL.md`

## Objective

Repair or durably classify the remaining `validate_params.py --strict` failures so the strict repo gate no longer blocks LINE31 launch-readiness.

## Current Known Retained Failures

From the prior synthesis:

- `inbound_sheet_consistency`: Line61 accepted-real-shortage is owner-confirmed but current durable contract is copied-temp only.
- `single_truth_system`: historical DB/workbook/dashboard mismatches remain:
  - 17 historical DB-only part ids missing from workbook;
  - `PO-5.2` payable mismatch, workbook `3342312.0` vs DB `4350312.0`;
  - `PO-4.0` dashboard lifecycle weight mismatch, dashboard `1223.05` vs DB expected `1338.6`.
- `on_delivery_freeze`: 3 compact SKU shipped rows lack production unit-cost source:
  - `938256969` / `LINE-31-TS`
  - `940453925` / `SUIT-31-LS`
  - `941824782` / `SUIT-31-LS`
- `cogs_integrity` and `profit_publication_integrity`: unresolved `SUIT-31-TS` production COGS/publication authority remains.

## Owner Facts To Preserve

- Line61 shortage fact is true: ordered/cargo `115`, actual received `92`, shortage `23`, with shortages XL `7`, 2XL `5`, 3XL `6`, 4XL `5`.
- Current cash/SHR source is the `Cash_Balances` sheet and SHR payment log in `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`.
- SHR payment #18, `7000 CNY`, counts as paid and supplier-paid even if receipt screenshot is pending.
- Protected reserve is `800000 KZT`.
- LINE31 stock uses exact rebuild from April leftovers plus PO1-A arrival.

## Authorized Surface

You may perform the minimum necessary production repair for the named strict-gate blockers only:

- `db/app.db` write-gated repair, but only with pre-write backup, explicit apply gate, before/after evidence, validator replay, and rollback instructions.
- Production workbook repair, but only if necessary to clear the named PO/single-truth blockers, with pre-write backup, before/after evidence, and workbook reopen/ZIP validation.
- Repo docs/config/scripts/tests updates needed to make the validators truthful and durable.

You may not perform external writes, Kaspi/WebUI/API/CRM mutations, Meta publish, website deploy, internal LINE31 Kaspi isolation, seller-bonus changes, price/stock offer changes, cash movement, supplier payment, PO commitment, owner publication, or broad unrelated cleanup.

## Required Work

1. Capture fresh before-state:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/validate_inbound_sheet_consistency.py --xlsx config/anchors/INBOUND_CALENDAR_LATEST.xlsx --json`
   - `python3 scripts/validate_single_truth_system.py`
   - `python3 scripts/validate_on_delivery_freeze.py --until 2026-05-31`
   - `python3 scripts/validate_cogs_integrity.py --as-of 2026-05-31`
   - `python3 scripts/validate_profit_publication_integrity.py --as-of 2026-05-31`
2. Resolve compact child COGS using repo-owned and owner-backed durable authority. Do not invent costs. If the only found authority is explicitly copied-temp-only and cannot be durably upgraded under the current owner approval, stop that item as retained YELLOW.
3. Resolve or durably classify the Line61 accepted shortage as production-safe truth. Do not hide the shortage; the accepted shortage should remain visible.
4. Resolve or durably classify the PO single-truth mismatches. Prefer canonical source repair over validator weakening. If a mismatch is historical and not LINE31-launch-relevant, create explicit durable classification and make the validator reflect that truth transparently.
5. Rerun dependent cashflow/COGS/PO validators after any write.
6. If `validate_params.py --strict` can pass honestly, make it pass. If not, close YELLOW with exact remaining blockers and why they still cannot be safely cleared.

## Required Evidence Folder

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_round2_20260601/agent1_strict_gate_repair/`

Required files:

- `before_after_strict_gate.md`
- `retained_blocker_resolution_matrix.csv`
- `production_mutation_ledger.md`
- `db_or_workbook_backup_manifest.md`
- `validator_replay_summary.md`
- `COMMANDS_RUN.tsv`

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair_round2/agent1_strict_gate_repair_closeout.md`

The closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` only if the strict repo gate is green or all retained strict failures have durable launch-accepted authority and the final synthesis can use them safely.
