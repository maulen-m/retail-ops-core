# Agent 1 Starter - Post-Expert Strict Gate Integration

You are Agent 1. You are the serialized LINE31 post-expert strict publish integration agent.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-02_line31_post_expert_strict_publish_integration/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_POST_EXPERT_STRICT_PUBLISH_20260602_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/validation/LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md`
6. `~/Docs/Autonomous_business/docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md`
7. `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
8. `~/Docs/Autonomous_business/docs/current/LINE31_NEXT_INPUTS_AND_READY_TO_RUN.md`
9. `~/Docs/Autonomous_business/docs/current/LINE31_ACTIVE_GOAL_COMPLETION_AUDIT_CURRENT.md`
10. `~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer/Strategy_expert_02.06.2026_11_14_17.md`

## Mission

Implement the recommended Option 1 integration:

- make the expert answer part of the repo's current LINE31 launch-readiness contract;
- harden docs/tests/scripts against false green publish declarations;
- preserve speed by avoiding broad repo cleanup;
- stop before any live Meta/Kaspi/WebUI/price/stock/cash/PO/scheduler/source-pointer/write action.

## Current Expected State

Before final creative exists:

- `report_line31_next_inputs_status.py --json` should detect the expert answer and must not imply publish readiness;
- pending-creative readiness may be `GREEN_EXCEPT_CREATIVE`;
- strict publish readiness must remain `YELLOW`;
- current final creative drop validation should be `NOT_READY`;
- no live action is authorized.

## Required Implementation Work

1. Capture baseline:
   - run `git status --short`;
   - record SHA-256 for `db/app.db`;
   - record SHA-256 for `excel_ui/SALES_KSP_CRM_V3.xlsx`;
   - note existing dirty worktree but do not revert unrelated changes.

2. Refresh current LINE31 status:
   - run `python3 scripts/report_line31_next_inputs_status.py --json`;
   - run `python3 scripts/build_line31_current_noncreative_gate_matrix.py --json`;
   - run `python3 scripts/validate_line31_owner_objective_source_freshness.py --json`;
   - run `python3 scripts/build_line31_launch_preflight_packet.py --json`;
   - run `python3 scripts/write_line31_current_launch_status.py --json`.

3. Patch current docs if needed:
   - ensure `docs/current/LINE31_NEXT_INPUTS_AND_READY_TO_RUN.md` says the expert answer is present and ready to ingest/integrated;
   - ensure owner-facing wording says `YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA`;
   - ensure the next action is final creative plus strict live QA, not a fake publish-ready state.

4. Patch validator/script behavior if needed:
   - reject any `REPLACE_WITH` placeholder values in final mapping or final drop intake;
   - require local thumbnail SHA-256 when the thumbnail path is local;
   - require current tracking/redirect QA evidence before strict publish turns green;
   - keep internal Kaspi LINE31 campaigns ON unless a separate exact owner approval phrase exists;
   - keep old candidate/noindex route maps quarantined as history/context only.

5. Patch or add focused tests:
   - test that local thumbnail without SHA cannot pass strict mapping;
   - test that missing tracking/redirect QA keeps strict publish `YELLOW`;
   - test that expert-answer presence changes the next-input status without changing `ready_to_publish=false`;
   - test that pending-creative mode can remain green while strict publish stays yellow.

6. Run verification:

```bash
python3 scripts/report_line31_next_inputs_status.py --json
python3 scripts/build_line31_current_noncreative_gate_matrix.py --json
python3 scripts/validate_line31_owner_objective_source_freshness.py --json
python3 scripts/build_line31_launch_preflight_packet.py --json
python3 scripts/audit_line31_active_goal_completion.py --json
python3 scripts/validate_line31_current_final_creative_drop.py --json
python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative --json
python3 scripts/validate_line31_launch_readiness.py --json
pytest -q tests/test_report_line31_next_inputs_status.py tests/test_validate_line31_final_creative_mapping.py tests/test_validate_line31_final_creative_drop_intake.py tests/test_validate_line31_launch_readiness.py tests/test_build_line31_launch_preflight_packet.py tests/test_line31_final_creative_launch_docs_contract.py
bash scripts/lint_docs.sh
git diff --check
```

Expected command behavior before final creative:

- `validate_line31_current_final_creative_drop.py --json` may fail as `NOT_READY`;
- strict `validate_line31_launch_readiness.py --json` must fail as `YELLOW`;
- those expected failures are not errors if they are caused by missing final creative and approval evidence.

7. Capture after-work protected hashes:
   - record SHA-256 for `db/app.db`;
   - record SHA-256 for `excel_ui/SALES_KSP_CRM_V3.xlsx`;
   - stop `RED` if this lane caused protected drift.

8. Write closeout:
   - use the assigned closeout path;
   - include commands run;
   - include expected failures;
   - include protected hashes before/after;
   - include exact retained blockers;
   - include the next one-sentence pointer to the final creative/publish starter if the integration is green.

## Success Gate

Use `Gate: GREEN_POST_EXPERT_STRICT_PUBLISH_INTEGRATION_READY` only if:

- expert answer is integrated into current docs/contracts;
- false-green guards are encoded in docs and tests/scripts as applicable;
- pending-creative readiness remains valid;
- strict publish remains blocked until final creative, approval evidence, tracking QA, and protected hash recheck;
- no protected DB/workbook or external mutation occurred;
- closeout is complete.

## Stop Conditions

Stop `YELLOW` if:

- final creative and approval evidence are still missing, but integration work is otherwise safe;
- tracking QA cannot be implemented as a strict gate without more context;
- broad repo advisory failures remain but are not LINE31 launch-blocking;
- exact next live approval requirements are clear.

Stop `RED` if:

- protected DB/workbook drift is observed from this lane;
- any tool attempts live Meta/Kaspi/WebUI/API/price/stock/cash/PO/scheduler/source-pointer mutation;
- the task expands beyond LINE31 post-expert strict publish integration;
- owner-facing docs imply publish authority before exact approval.

## Boundary

Do not run final Meta publish. Do not pause internal Kaspi LINE31 campaigns. Do not change campaign bids, budgets, state, price, stock, cash, PO, supplier, scheduler, source-pointer, production DB, production workbook, Web_automation, Kaspi/API/WebUI, owner publication, or any non-LINE31 live surface.

## Approval Phrase For This Lane

The owner approval phrase for this lane is:

```text
I approve integrating the 2026-06-02 external expert LINE31 progress evaluation into Autonomous_business as a repo-docs/tests/read-only execution plan and orchestrator starter pack. This authorizes local docs/config/test/script updates, read-only evidence refresh, synthetic tracking QA planning, validator hardening for thumbnail SHA/local asset proof, and handoff creation only. It does not authorize production DB/workbook writes, scheduler/source-pointer changes, Web_automation writes, Kaspi/API/WebUI/Meta writes, campaign/bid/budget/state changes, price changes, stock changes, cash movement, supplier payment, PO commitment, owner publication, internal Kaspi campaign pause, or final Meta publish.
```
