# Agent915 Starter: Copied-Temp MVOS Proof

You are Agent915. Your mission is to run the copied-temp-only MVOS proof using accepted Agent914 source packets and the owner-confirmed STOREB mapping.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent915_copied_temp_proof_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT915_COPIED_TEMP_PROOF_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT915_COPIED_TEMP_PROOF_20260519_STARTERS/01_AGENT_915__COPIED_TEMP_MVOS_PROOF__ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9144.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/OWNER_CONFIRMED_STOREB_OFFER_116515378_626543467_MAPPING.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9144_source_packet_synthesis_agent915_readiness_evidence/NEXT_AGENT915_BOOTSTRAP_RECOMMENDATION.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_closeout.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9143_ads_may18_live_readonly_source_acquisition_closeout.md`

## Owner Approval Boundary

The owner approved Agent915 copied-temp-only MVOS proof using:

- accepted Agent914 stock source packets;
- accepted Agent914 sales source packet;
- accepted Agent914 May 18 ads source packets;
- owner-confirmed STOREB mapping for offer `116515378_626543467` / product `MTE2NTE1Mzgz` as `CL_OC_MEN_LINE52_BLACK_XL`.

The owner did not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Scope

Allowed:

- create a fresh copied DB under your evidence root;
- materialize source packets into copied DB only;
- apply the owner-confirmed STOREB mapping inside copied-temp proof only:

```text
store=STOREB
offer_id=116515378_626543467
product_id=MTE2NTE1Mzgz
sku_key=CL_OC_MEN_LINE52_BLACK
sku_id=CL_OC_MEN_LINE52_BLACK_XL
my_size=XL
```

- run validators against copied DB and local evidence;
- write evidence, closeout, and CodeCaptain packet draft under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/`

Forbidden:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- external writes;
- ad-platform writes;
- stock changes outside copied DB proof;
- price changes;
- cash movement;
- PO commitment;
- owner publication;
- production preflight;
- production apply.

If existing tooling requires source-code changes or production/source-pointer writes to proceed, stop `YELLOW` with exact blocker. Do not edit repo code for this lane.

## Task

Run the copied-temp MVOS proof as far as safely possible.

Minimum work:

1. Record starting protected-surface hashes for `db/app.db` and the canonical CRM workbook.
2. Create a fresh copied DB in the Agent915 evidence root.
3. Record source packet hashes and row counts from Agent914 evidence.
4. Apply or stage the owner-confirmed STOREB mapping only in copied-temp proof.
5. Materialize accepted stock, sales, and ads packets into the copied DB if existing tooling supports it without protected writes.
6. Run the validator matrix from Agent9144 recommendation where applicable.
7. Record all commands, exits, outputs, row counts, copied DB hashes, and retained blocker counts.
8. Write a CodeCaptain packet draft summarizing proof result and next required review.

## Required Validator Matrix

Run the smallest valid equivalent if a listed command has changed, but record exact command and reason.

- `python3 scripts/validate_policy_source_freshness.py --as-of 2026-05-18 --strict --json`
- `python3 scripts/validate_policy_gate_results.py --strict --json`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `python3 scripts/validate_exception_queue_db.py`
- `python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db <copied_db> --as-of 2026-05-18 --start-date 2026-05-05 --output-root <agent915_evidence>/strict_sales_fact_v2 --strict`
- `python3 scripts/validate_order_entries_freshness.py`
- `python3 scripts/validate_day_complete.py`
- `python3 scripts/validate_sales_vs_workbook_anchor.py`
- `python3 scripts/validate_ads_source_packet_contract.py`
- `python3 scripts/validate_ads_sidecar_readiness.py`
- `python3 scripts/validate_ads_spend_reality.py`
- `python3 scripts/validate_ads_offer_universe_coverage.py`
- `python3 scripts/validate_inbound_sheet_consistency.py --xlsx <canonical_inbound_workbook> --json`
- `python3 scripts/sync_po_parts_from_inbound_calendar.py --xlsx <canonical_inbound_workbook> --db <copied_db>` as dry-run first
- `python3 scripts/validate_single_truth_system.py --db <copied_db> --xlsx <canonical_inbound_workbook>`
- `python3 scripts/validate_cogs_integrity.py --db <copied_db> --days 30 --max-unresolved-rows 0 --max-unresolved-skus 0 --as-of 2026-05-18`
- `python3 scripts/validate_single_truth_alignment.py --db <copied_db> --input <generated_dashboard>`
- `python3 scripts/validate_po_money_gate.py --db <copied_db> --inbound-workbook <canonical_inbound_workbook> --as-of 2026-05-18 --json`
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_order_cashflow_coverage.py`

## Required Outputs

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/PROTECTED_SURFACE_HASHES.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/SOURCE_PACKET_HASHES_AND_COUNTS.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/COPIED_DB_MANIFEST.json`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/MATERIALIZATION_RESULT_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/VALIDATOR_RESULT_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/RETAINED_BLOCKER_COUNTS.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_evidence/CODECAPTAIN_PACKET_DRAFT.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use `GREEN` only if copied-temp materialization and validators pass without hidden blockers and protected surfaces remain unchanged. Use `YELLOW` for partial proof, tooling gaps, or validator failures. Use `RED` for boundary violation or false-green risk.

## Anti-Drift Rules

- Do not call source packet capture production truth.
- Do not call copied-temp proof production readiness.
- Do not hide `9` `STOCK/HIGH/OPEN` exceptions.
- Do not merge STOREB business identity into Universal access identity.
- Do not infer missing rows as zero spend.
- Do not mutate protected surfaces.
- Do not ask the owner again about offer `116515378_626543467` unless new contradictory source evidence appears.
- After Agent915, the next gate is CodeCaptain review, not production preflight/apply.
