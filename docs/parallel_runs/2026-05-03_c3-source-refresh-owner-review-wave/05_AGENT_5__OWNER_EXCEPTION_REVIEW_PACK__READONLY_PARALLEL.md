# Agent 5 - Owner Exception Review Pack Analyst

Mode: read-only analyst with handoff-folder output only.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
7. `~/Docs/Autonomous_business/exports/operational_stock_daily_truth/2026-05-03/orchestrator-agent8-review-check/owner_blocked_brief.md`
8. This assigned starter prompt.

## Mission

Prepare the exact owner-review surface for the 9 high stock exceptions that now have DB metadata but still require owner decision or explicit carry-forward.

The goal is to avoid vague owner asks. If owner attention is needed, make it exact, short, and actionable.

## Allowed Work

You may read DB exception rows through read-only SQLite, owner blocked brief artifacts, Agent 6/7/8 reports from the prior wave, and source evidence paths.

You may write:

- your assigned closeout file;
- optionally one owner review pack markdown file in `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave`.

You must not mutate DB rows, repo files, external repos, workbooks, source evidence, or external systems.

## Required Analysis

For each of the 9 high stock exceptions, determine:

- SKU/family/size;
- reason;
- owner currently assigned in DB;
- recommended action currently assigned in DB;
- evidence paths;
- what decision is required;
- whether the system can safely continue blocked if no decision is made;
- whether the exception can be resolved by source refresh versus human approval.

## Required Output

Write a concise, source-backed closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact list of exceptions reviewed;
- exact owner action pack path if created;
- which decisions are owner-required versus source-refresh-required;
- `OWNER_ATTENTION_REQUIRED` only if a human owner task is truly required, with exact paths and plain-English steps.

Do not read sibling agent reports before writing your own first-pass findings.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_5_owner_exception_review_pack_closeout.md`
