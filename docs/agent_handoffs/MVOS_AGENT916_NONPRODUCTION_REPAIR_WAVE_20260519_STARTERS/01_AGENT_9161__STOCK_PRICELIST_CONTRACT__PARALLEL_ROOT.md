# Agent9161 Starter - Stock Pricelist Contract Route

You are Agent9161. Your lane is read-only/evidence-only.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/01_AGENT_9161__STOCK_PRICELIST_CONTRACT__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9141_stock_live_readonly_source_acquisition_closeout.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9161_stock_pricelist_contract_evidence/`

Do not edit repo files, DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Decide whether Agent9141 Merchant Cabinet pricelist packets can support a copied-temp canonical stock snapshot proof.

Do not treat Merchant Cabinet pricelist quantity as physical warehouse stock unless the contract proves that semantic.

Required outputs:

- `MERCHANT_CABINET_PRICELIST_STOCK_CONTRACT_RECOMMENDATION.md`
- `STOCK_PACKET_FIELD_MATRIX.tsv`
- `STOCK_MATERIALIZER_ACCEPTANCE_GATES.tsv`
- `COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9161_stock_pricelist_contract_closeout.md`

The closeout must include:

`Gate: GREEN`

Use `GREEN` only if the copied-temp source contract is fully specified. Use `YELLOW` if stock semantics still need owner/CodeCaptain decision. Use `RED` for boundary violation or false-green risk.
