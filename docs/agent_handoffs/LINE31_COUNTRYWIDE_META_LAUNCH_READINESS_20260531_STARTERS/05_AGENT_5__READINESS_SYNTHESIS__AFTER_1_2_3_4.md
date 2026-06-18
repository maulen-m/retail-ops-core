# Agent 5 Starter - LINE31 Launch-Readiness Synthesis

You are Agent 5. Your lane runs only after Agents 1-4 close out. You synthesize their outputs into one decision-grade readiness packet. No live action is authorized.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-31_line31_countrywide_meta_launch_readiness/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/05_AGENT_5__READINESS_SYNTHESIS__AFTER_1_2_3_4.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent1_facebook_ads_scaffold_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent2_acmewear_web_tracking_qa_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent3_web_automation_line31_context_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent4_ab_daily_bridge_closeout.md`

Do not start if any required closeout is missing.

## Scope

Allowed writes:

- synthesis evidence under `~/Docs/Autonomous_business/exports/validation/line31_countrywide_meta_launch_readiness_20260531/final_synthesis/`;
- final closeout under the shared handoff folder;
- small repo-local docs under the canonical parallel-run folder if needed.

Forbidden:

- production DB/workbook writes;
- source-pointer/scheduler/website deploy changes;
- Meta/Kaspi/WebUI/API/CRM/platform mutations;
- price, stock, cash, supplier, payment, PO, owner-publication, internal LINE31 Kaspi isolation, or Meta publish.

## Task

Synthesize Agents 1-4 into one practical launch-readiness packet.

Required checks:

- read every closeout and extract `Gate`;
- verify each lane produced the required local artifacts;
- create one readiness matrix for `Scaffold`, `Tracking`, `Creative`, `Cash/Inventory`, `Internal Kaspi Noise`, and `Launch`;
- preserve expert rule that LINE31 internal Kaspi marketing and seller bonus stay ON until owner creative-ready declaration;
- list exact retained blockers and the fastest safe next action for each blocker;
- include exact future owner approval phrases for website deploy, Meta publish, internal Kaspi isolation dry-run/apply, and any source-pointer/scheduler/live-write route, but do not execute any.

## Required Outputs

Write these under your synthesis evidence folder:

- `FINAL_LINE31_COUNTRYWIDE_META_READINESS_MATRIX.md`
- `FINAL_LINE31_COUNTRYWIDE_META_READINESS_MATRIX.json`
- `NEXT_OWNER_APPROVAL_PHRASES.md`
- `RETAINED_BLOCKERS_AND_FASTEST_PATH.md`
- `CODECAPTAIN_OR_OWNER_REVIEW_PACKET_DRAFT.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent5_line31_readiness_synthesis_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- readiness score estimate and exact retained blockers;
- exact files created/changed;
- validation commands run;
- explicit confirmation that no live action was performed.

Use `GREEN` only if all root lanes are green and the final readiness matrix is complete. Use `YELLOW` if one or more launch gates remain legitimately blocked. Use `RED` for missing closeouts, boundary violation, or unsafe live-action ambiguity.
