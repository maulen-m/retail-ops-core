# Agent881 Starter: STOREB Ads Mapping Source Decision

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent881_storeb_ads_mapping_source_decision_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent881_storeb_ads_mapping_source_decision_evidence`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-17/231037_TASK-000_mvos-owner-qa-board-proof-codecaptain-final/ANSWER/Code Captain_18.05.2026_09_08_18.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent880_synthesis_copied_temp_board_proof_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/mvos_owner_qa_repair_wave/20260517_2223/agent880_synthesis_copied_temp_board_proof/ads_materializer_agent876_sources/storeb_product_code_mapping.csv`
9. `~/Docs/Autonomous_business/exports/validation/mvos_owner_qa_repair_wave/20260517_2223/agent880_synthesis_copied_temp_board_proof/ads_materializer_agent876_sources/ads_campaign_product_daily_unmapped.csv`
10. this starter prompt.

## Assignment

Resolve or preserve the STOREB ads mapping retained blocker from Agent880.

Produce:

- `STOREB_PRODUCT_CODE_MAPPING_SOURCE_DECISIONS.csv`
- `STOREB_UNMAPPED_POSITIVE_SPEND_RETAINED_BLOCKERS.csv`
- any source manifests/hashes needed to support the decision table
- assigned closeout with a standalone `Gate: <GREEN/YELLOW/RED>` line

The decision table must include at minimum:

- `kaspi_product_code`
- `product_name`
- `blocked_spend_kzt`
- `proposed_sku_key`
- `evidence_source`
- `evidence_path`
- `decision_status`
- `decision_reason`
- `proof_scope`
- `production_authority`

Read order / methods:

1. Start from Agent880 mapping and unmapped spend artifacts.
2. Inspect `Autonomous_business` DB/read-only evidence and existing mapping tables.
3. Inspect `~/Docs/Web_automation` read-only if useful.
4. Use existing API/repo methods first.
5. If needed, use read-only Chrome/Computer/Playwright fallback to enter with `UNIVERSAL` marketing account credentials and switch to STOREB store for source discovery. This is read-only discovery only.

Do not:

- mutate Web_automation;
- write ad-platform state;
- change bids, budgets, prices, stock, DB, workbook, scheduler, source pointers, cash, PO, owner publication, or external systems;
- treat missing/unmapped spend as zero;
- force fuzzy mappings just to make the board green.

Gate guidance:

- `GREEN` if every blocked STOREB code is either source-resolved or explicitly retained with complete evidence and no ambiguity.
- `YELLOW` if any product code still requires owner/source decision.
- `RED` only if an authority boundary is violated or evidence is unusable.
