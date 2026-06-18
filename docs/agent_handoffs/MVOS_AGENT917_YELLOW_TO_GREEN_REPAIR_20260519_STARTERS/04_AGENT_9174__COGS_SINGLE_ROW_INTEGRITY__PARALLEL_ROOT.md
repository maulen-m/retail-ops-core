# Agent9174 Starter - COGS Single-Row Integrity Route

You are Agent9174. Your lane is read-only/evidence-only with respect to repo state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/04_AGENT_9174__COGS_SINGLE_ROW_INTEGRITY__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9167.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/validator_outputs/032_validate_cogs_integrity.stdout.txt`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/validator_outputs/033_validate_cogs_completeness_with_unit_evidence.stdout.txt`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9174_cogs_single_row_integrity_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9174_cogs_single_row_integrity_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, cash, PO, stock, prices, or owner publication.

## Task

Design the copied-temp-only COGS route for the remaining strict integrity blocker.

Target:

- `909054064 / ACMEWEAR / SUIT-31-TS_3XL`

Rules:

- Copied-temp unit evidence may support a proof route only if explicit and validator-visible.
- Do not silently relax production COGS integrity.
- Do not zero missing COGS.
- Keep production economics truth blocked unless formula/source truth is refreshed or separately accepted.

Inspect `scripts/validate_cogs_integrity.py`, `scripts/validate_cogs_completeness_by_month.py`, existing tests, and Agent9164/9167 evidence. Recommend the smallest Agent9178 patch and focused tests.

## Required Outputs

Inside your evidence folder:

- `COGS_UNIT_EVIDENCE_COPIED_TEMP_V1.md`
- `COGS_INTEGRITY_PATCH_PLAN.tsv`
- `COGS_PRODUCTION_STRICTNESS_GUARD.md`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if the copied-temp validator route is exact and preserves production strictness. Use `YELLOW` if stronger formula/economics truth is still required. Use `RED` for boundary violation or silent COGS relaxation risk.
