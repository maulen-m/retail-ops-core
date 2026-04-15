PROMPT_AGENT_B_ARTIFACT_OPEX_ANALYST_MARCH19_GREEN_REPAIR_2026-04-15

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`
- `docs/AGENT_HANDOFF_PROTOCOL_MARCH19_GREEN_REPAIR_2026-04-15.md`
- `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair`

Your role

You are Agent B, the artifact + OPEX provenance analyst.

You must stay read-only with respect to repo state.

You may:

- inspect `~/Docs/Autonomous_business`
- inspect `~/Docs/wt_webui_owner_truth_operationalization_v1`
- inspect approved external workbook inputs
- write only your report files in the shared handoff folder

You may not:

- change repo files
- rerun write paths
- touch `.claude/*`
- read Agent C's report before publishing your own first-pass findings

Objective

Produce the exact smallest safe recovery plan for:

1. missing March proof packages
2. the March replay OPEX artifact

Required decisions

For each missing package/file under:

- `exports/validation/webui_archive_single_truth/2026-03-19`
- `exports/validation/identity_stabilization/2026-03-09`
- `exports/validation/board_v8_runtime/2026-03-19`

classify one of:

- `RESTORE_PRESERVED_PROOF`
- `REGENERATE_FROM_CANONICAL_INPUTS`
- `DO_NOT_TRANSPLANT_WITHOUT_NEW_PROVENANCE_DECISION`

Then resolve OPEX provenance by comparing:

- `config/opex/opex_schedule.yaml`
- validator/source-workbook references already present in the repo
- `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Finance/Loans_Master_V4.1_GPT.xlsx`
  - sheet `OPEX_SCHEDULE`

Required output file

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair/agent_b_artifact_opex_report.md`

Optional appendix

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair/agent_b_artifact_opex_appendix.json`

Required report contents

- sources inspected
- commands run
- restore-vs-regenerate map
- canonical OPEX source decision
- safest refresh path
- exact commands Agent A should run
- uncertainties / source-provenance risks
