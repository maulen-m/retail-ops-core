# Agent 17 - Ads Evidence Retry And Import Plan

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_17_ads_evidence_retry_import_plan_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_remediation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_11_ads_source_refresh_coverage_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_12_serial_temp_implementation_closeout.md`
8. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/WA1_ACMEWEAR_CLOSEOUT.md`
9. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/WA2_STOREB_CLOSEOUT.md`
10. this starter prompt

## Mission

Read-only ads remediation plan after WA1/WA2 both ended YELLOW due Kaspi Marketing `429` limits.

Focus on:

- whether existing WA1 aggregate-window rows can safely reduce ACMEWEAR blockers without fake zero spend;
- whether STOREB campaign-list/header metrics can be used at any safe grain, or must remain blocked until product rows exist;
- when/how to retry Web_automation product-row fetches without hammering Kaspi;
- exact Autonomous_business import/materialization commands for a future temp proof;
- Meta/Facebook scope: ACMEWEAR only, not STOREB, and do not make stale Meta root block STOREB.

## Write Boundary

Read-only against production `db/app.db` and Web_automation outputs.

Allowed writes:

- your closeout;
- optional read-only query outputs under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_17_evidence/`.

Forbidden:

- production DB writes;
- ad-platform writes;
- Web_automation writes;
- code changes;
- retrying live Kaspi Marketing calls in this lane.

## Required Work

1. Inspect WA1/WA2 closeouts and SQLite/CSV evidence.
2. Compare evidence windows to remaining AB blockers.
3. Decide what can be imported safely as `COVERED` or `NO_SPEND_VERIFIED`.
4. Decide what must remain blocked due missing product rows or rate limits.
5. Propose a rate-limit-safe retry schedule/prompt for Web_automation if needed.
6. Provide exact temp DB commands for the next AB ads materialization proof.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- blocker reduction estimate;
- exact source files/DBs usable;
- exact next commands;
- what not to import;
- whether human owner action is required.
