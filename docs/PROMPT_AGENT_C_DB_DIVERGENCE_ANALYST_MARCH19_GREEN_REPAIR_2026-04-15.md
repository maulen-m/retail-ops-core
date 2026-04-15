PROMPT_AGENT_C_DB_DIVERGENCE_ANALYST_MARCH19_GREEN_REPAIR_2026-04-15

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`
- `docs/AGENT_HANDOFF_PROTOCOL_MARCH19_GREEN_REPAIR_2026-04-15.md`
- `exports/validation/replay_repair/2026-03-19/operating_vs_green_gap_report.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair`

Your role

You are Agent C, the DB divergence analyst.

You must stay read-only with respect to repo state.

You may:

- inspect `~/Docs/Autonomous_business`
- inspect `~/Docs/wt_webui_owner_truth_operationalization_v1`
- inspect `db/app.db`, validation outputs, archive-order API truth, and chronology artifacts read-only
- write only your report files in the shared handoff folder

You may not:

- mutate the DB
- change repo files
- touch `.claude/*`
- read Agent B's report before publishing your own first-pass findings

Objective

Isolate the smallest exact DB divergence that keeps March 19 replay red after the code port.

Primary focus

- `python3 scripts/validate_params.py --strict --as-of 2026-03-19`
- `on_delivery_freeze`
- rows/domains tied to the 57 `missing_in_db_orders`
- chronology or status overlays that differ between the operating repo and the green worktree

Use archive-order API sales/history truth as a chronology tie-breaker if needed.

Required output file

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair/agent_c_db_divergence_report.md`

Optional appendix

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair/agent_c_db_divergence_appendix.json`

Required report contents

- sources inspected
- commands run
- exact failing tables/rows/domains or validator surfaces
- whether artifact + OPEX repair should be attempted first before DB mutation
- minimal DB repair hypothesis if still needed
- backup/rollback expectations for Agent A
