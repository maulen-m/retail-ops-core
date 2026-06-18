# Orchestrator Handoff - LINE31 Green Except Creative Repair

Created: 2026-06-01 10:24 +05

Gate: ROOT_READY_OWNER_APPROVED_GREEN_REPAIR

## Objective

Execute the next LINE31 readiness wave so the project reaches `GREEN_EXCEPT_CREATIVE`: every non-creative launch-readiness blocker repaired, proven, or explicitly accepted with a durable rule.

## Canonical Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_repair/PLAN.md`

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS`

## Shared Handoff Folder

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair`

## Approval Boundary

The owner approved all required actions for this green-repair wave, including adding the stricter option 2 path to repair unrelated strict-gate failures first.

Allowed:

- repo-local docs/scripts/tests/config repair;
- read-only live source refreshes;
- website deploy only if the LINE31 tracking patch is isolated and deploy proof is recorded;
- production DB/workbook mutation only if necessary, backup-first, narrow, write-gated, and followed by validator replay;
- local evidence and closeout writing.

Not allowed:

- Meta publish;
- final creative declaration;
- internal LINE31 Kaspi isolation;
- campaign bid/budget/state/creative/audience/promo changes;
- price/stock offer changes outside proven source-truth repair;
- cash movement, supplier payment, PO commitment, owner publication, or unrelated external writes.

## Launch Order

Launch Agents 1-3 in parallel:

- Agent 1: Autonomous_business strict-gate/cash/stock repair.
- Agent 2: acmewear_web_v2 isolated deploy/live proof.
- Agent 3: Facebook_ads + Web_automation launch-day source refresh.

Launch Agent 4 only after Agents 1-3 close out.

## Assigned Closeouts

- Agent 1: `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent1_ab_strict_cash_stock_repair_closeout.md`
- Agent 2: `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent2_acmewear_web_deploy_liveproof_closeout.md`
- Agent 3: `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent3_launch_day_source_refresh_closeout.md`
- Agent 4: `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent4_green_except_creative_synthesis_closeout.md`

## Launch Lines

Root agents:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/01_AGENT_1__AB_STRICT_CASH_STOCK_REPAIR__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/02_AGENT_2__ACMEWEAR_WEB_DEPLOY_LIVEPROOF__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/03_AGENT_3__LAUNCH_DAY_SOURCE_REFRESH__PARALLEL_ROOT.md.
```

Synthesis after root:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/04_AGENT_4__GREEN_EXCEPT_CREATIVE_SYNTHESIS__AFTER_1_2_3.md.
```
