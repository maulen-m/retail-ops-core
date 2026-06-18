# Orchestrator Handoff - LINE31 Post-Expert Strict Publish Integration

Created: 2026-06-02

Gate: READY_TO_EXECUTE_REPO_DOCS_TESTS_READONLY_INTEGRATION

## Objective

Ingest the 2026-06-02 external expert LINE31 progress review into the Autonomous_business repo as a strict, testable launch-readiness contract.

The orchestrator must make the repo harder to misread:

- `GREEN_EXCEPT_CREATIVE` remains internal prep only;
- owner-facing publish status remains strict `YELLOW` until final creative, mapping, approval evidence, tracking QA, and protected hash recheck pass;
- no live publish or external mutation is authorized by this handoff.

## Canonical Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-06-02_line31_post_expert_strict_publish_integration/PLAN.md`

## Expert Answer

`~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer/Strategy_expert_02.06.2026_11_14_17.md`

## Validation Addendum

`~/Docs/Autonomous_business/docs/validation/LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md`

## Existing Downstream Final-Publish Starter

Use only after this post-expert integration is green and final creative plus exact approval evidence exist:

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md`

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_POST_EXPERT_STRICT_PUBLISH_20260602_STARTERS`

## Launch Order

Single serialized orchestrator lane:

- Agent 1: post-expert strict gate integration, validator/test hardening, current-pointer refresh, and closeout.

If the orchestrator uses tmux subagents for read-only scouting, they must not write repo files. Only the serialized integration agent may patch shared repo state.

## Required Launch Line

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_POST_EXPERT_STRICT_PUBLISH_20260602_STARTERS/01_AGENT_1__POST_EXPERT_STRICT_GATE_INTEGRATION__SERIAL.md.
```

## Required Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-02_line31_post_expert_strict_publish_integration/agent1_post_expert_strict_gate_integration_closeout.md`

Closeout gate must be exactly one of:

- `Gate: GREEN_POST_EXPERT_STRICT_PUBLISH_INTEGRATION_READY`
- `Gate: YELLOW`
- `Gate: RED`

## Boundary

This handoff authorizes only repo-docs/tests/scripts/read-only evidence work under the owner approval phrase for this integration lane.

It does not authorize production DB writes, production workbook writes, source-pointer writes, scheduler changes, Web_automation writes, Kaspi/API/WebUI/Meta writes, campaign bid/budget/state changes, price changes, stock changes, cash movement, supplier payment, PO commitment, owner publication, internal Kaspi campaign pause, final Meta publish, or any non-LINE31 live action.
