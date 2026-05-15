# C3 Source Refresh And Owner Review Wave Plan

Status: active starter pack for source-refresh wave after C3 foundation.

Generated: `2026-05-03 22:38 +0500`

Repo: `~/Docs/Autonomous_business`

Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave`

## Goal

Turn the current `RED_BLOCKED` C3 state into a source-backed, decision-grade path by refreshing the stale or missing operational sources, preserving fail-closed truth, and preparing exact owner-review actions only where human approval is genuinely required.

This wave is not a green-publication wave. It is the source-refresh and owner-review wave that must happen before any green owner publication attempt.

## Current Starting State

Accepted C3 foundation evidence:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_8_c3_daily_runner_owner_brief_closeout.md`

Current owner brief:

- `~/Docs/Autonomous_business/exports/operational_stock_daily_truth/2026-05-03/orchestrator-agent8-review-check/owner_blocked_brief.md`

Current trust status:

- `owner_trust_status=RED_BLOCKED`
- C3 foundation complete at `YELLOW`
- source-refresh and owner-review blockers remain.

## Parallel Topology

Launch Agents 1-5 in parallel as read-only analysts.

Do not launch Agent 6 until Agents 1-5 closeouts are reviewed.

Do not launch Agent 7 until Agent 6 closeout is reviewed.

## Agents

1. Agent 1: AB operational source refresh analyst.
2. Agent 2: Ads source refresh analyst.
3. Agent 3: Cashflow, bank, supplier obligation analyst.
4. Agent 4: PO, inbound, supplier route analyst.
5. Agent 5: Owner exception review pack analyst.
6. Agent 6: Serialized source-refresh execution agent, blocked until Agents 1-5 are reviewed.
7. Agent 7: C3 rematerialize and owner brief verification agent, blocked until Agent 6 is reviewed.

## Write Rules

Agents 1-5:

- read-only with respect to repo state, DB, external repos, and external systems;
- write only assigned closeout files in the shared handoff folder;
- may inspect local files, DB read-only, scripts, workbooks, existing exports, and local logs;
- must not read secret values unless a source-refresh method cannot be evaluated without confirming variable names. If env inspection is necessary, report variable names only, never secret values.

Agent 6:

- only write-capable execution agent for this wave;
- only agent allowed to mutate `~/Docs/Autonomous_business/db/app.db`;
- all DB writes must be backup-first, dry-run by default, additive/idempotent, and env-gated;
- no live external writes unless the prompt and owner have explicitly authorized that exact write.

Agent 7:

- validation and C3 rematerialization after Agent 6;
- may write only through repo-approved backup-first/env-gated materialization paths.

## Human Owner Attention Rule

Agents should not ask the owner to help unless the task truly requires human review or approval.

If owner attention is required, the agent must provide:

- exact folder/file paths to review;
- plain-English steps the owner should perform;
- what decision is needed;
- what happens if the owner does nothing;
- whether the system can continue in blocked mode without the owner action.

## Stoplines

- No green owner publication until strict source freshness and policy gate validators are genuinely green.
- No fake PASS rows.
- No treating missing ads/spend/orders/cashflow as zero.
- No concurrent DB writes.
- No external-system write without explicit owner authorization.
- No source freshness downgrade or validator weakening to make a report look green.
