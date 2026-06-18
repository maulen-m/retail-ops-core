# Agent 3 Starter - Web_automation LINE31 Internal Kaspi Context

You are Agent 3. Your lane captures current LINE31 internal Kaspi campaign and promo context as read-only attribution-noise evidence. No Kaspi mutation is authorized.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Web_automation/AGENTS.md`
2. `~/Docs/Web_automation/Docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-31_line31_countrywide_meta_launch_readiness/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/03_AGENT_3__WEB_AUTOMATION_LINE31_CONTEXT__PARALLEL_ROOT.md`

## Source Inputs

Read:

1. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/SOURCE_TRUTH_AND_CONFLICTS.md`
2. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/ATTRIBUTION_AND_ISOLATION_POLICY.md`
3. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/LAUNCH_GATES_AND_MONITORING_RULES.md`
4. `~/Docs/Web_automation/Docs/kaspi_marketing_directapi_control_contract.md` if present

## Scope

Allowed writes:

- repo-local docs/scripts/tests/config in `~/Docs/Web_automation` only when they support read-only LINE31 context evidence;
- local generated evidence under `~/Docs/Web_automation/runs/line31_countrywide_meta_launch_readiness/20260531_readonly_context/`;
- assigned closeout under the shared handoff folder.

Forbidden:

- Kaspi Marketing campaign or promo mutation;
- campaign enable/disable, bid/budget/state/product changes;
- WebUI/API writes;
- price, stock, offer, supplier, payment, PO, cash, CRM, Meta, website, scheduler, DB, or workbook writes.

## Task

Capture the current attribution-noise context for LINE31 internal Kaspi marketing and seller bonus:

- campaign IDs `2695637`, `2752402`, `2752405`, `2752406`, `2862392`, `2856404`, `2858476`;
- promo `202353`;
- current campaign state, budget, bid, product state, spend/order context when read-only methods are available;
- note whether evidence is fresh live read-only, local historical, or unavailable;
- label how this affects Meta attribution: directional only while internal LINE31 Kaspi surfaces are active.

Prefer existing API/direct-read methods. Use UI only if the repo already has a safe read-only route. If credentials or access are missing, produce a `YELLOW` freshness gap instead of improvising.

## Required Outputs

Write these under your local evidence folder:

- `line31_internal_kaspi_campaign_context.csv`
- `line31_seller_bonus_promo_context.md`
- `line31_attribution_noise_labels.md`
- `line31_context_source_freshness.json`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent3_web_automation_line31_context_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact files created/changed;
- validation commands run;
- explicit confirmation that no Kaspi/WebUI/API/platform write was performed.

Use `GREEN` only if current read-only context was captured or existing current evidence is sufficient. Use `YELLOW` if freshness is incomplete. Use `RED` for any mutation attempt.
