# After CodeCaptain Agent750 Decision Router - 2026-05-09

Status: BLOCKED_BY_DB_BOUNDARY_REVIEW

This router is a deterministic next-action guide for the Agent750 validate-only review. It is not an authorization artifact and must not be used to bypass the CodeCaptain gate.

Current stopline: the Agent750 answer is present and exact-GREEN, but the production DB/workbook boundary has drifted from the boundary reviewed by the original Agent750 pack. The GREEN answer remains necessary, but it is not sufficient while `production_db_sha_mismatch` or `protected_workbook_sha_mismatch` is present.

Current DB-boundary evidence:

- DB-boundary drift triage: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md`
- DB-boundary supplemental review request: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md`

## Input To Watch

Canonical GREEN answer:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer/Code_Captain_10.05.2026_12_35_59.md`

Expected decision tokens from the request:

- `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`
- `YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE`
- `RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE`

## Current Boundary Before Acting

Before any next action, re-sample:

```bash
LC_ALL=C LANG=C shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
test -e config/proof_window.lock && echo proof_window_lock_exists || echo proof_window_lock_absent
```

Expected:

- Original Agent750 reviewed DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Current DB SHA from readiness: `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156`
- Original Agent750 reviewed workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Current workbook SHA from readiness: `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`
- Real `config/proof_window.lock`: absent, unless a later explicitly authorized proof window is active.

If DB/workbook SHA differs from the boundary accepted for launch, stop and review the boundary supplement before launching any agent. Current readiness already reports `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`.

## If CodeCaptain Returns GREEN

Allowed next action only after DB-boundary review is resolved and readiness returns `"ok": true`:

- Launch Agent751 as the only write-capable validate-only implementation agent.
- Launch Agent752 and Agent753 as read-only analysts.
- Use monitor-only tmux completion. Do not use `--visibility-pane LIVE`, `orchestrator_ping_mode=chat`, or `orchestrator_ping_mode=receiver`.

Starter prompts:

- Agent751: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/751_AGENT_751__OPTION_C_VALIDATE_ONLY_RUNNER_CONTRACT__AFTER_750_CODECAPTAIN_REVIEW.md`
- Agent752: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/752_AGENT_752__CASH_RISK_DAILY_SURFACE_SPEC_READONLY__AFTER_750_CODECAPTAIN_REVIEW.md`
- Agent753: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/753_AGENT_753__SOURCE_FRESHNESS_EXCEPTION_QUEUE_MAP_READONLY__AFTER_750_CODECAPTAIN_REVIEW.md`

Launch template:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AFTER_GREEN_AGENT750_LAUNCH_TEMPLATE_751_752_753_20260509.md`

Preferred guarded resume path:

```bash
cd ~/Docs/Autonomous_business
python3 scripts/resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md
python3 scripts/resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md --apply-import
python3 scripts/resume_agent750_to_753.py --launch
```

The first two commands must remain blocked until the DB/workbook-boundary mismatch is resolved. Do not run the launch command unless the apply-import run returns `READY_FOR_GUARDED_LAUNCH`.

Required launch constraints:

- one write-capable lane maximum: Agent751;
- Agents752/753 read-only only;
- no production DB write;
- no workbook write;
- no scheduler or LaunchAgent mutation;
- no external writes;
- no real `config/proof_window.lock` create/remove;
- no owner approval request;
- no owner publication GREEN;
- no old Agent54 phrase reuse;
- no Agent64 activation.
- no manual tmux/chat pane pings by execution agents.

## If CodeCaptain Returns YELLOW

Allowed next action:

- Do not launch Agents751/752/753.
- Read CodeCaptain required fixes.
- Patch only the Agent750 plan, review request, starter prompts, or audit docs needed to address the fixes.
- Re-run doc checks and protected-surface SHA checks.
- Repackage and resend to CodeCaptain.

Required evidence:

- updated plan/starter prompt diff;
- `git diff --check`;
- `scripts/lint_docs.sh`;
- DB/workbook SHA sample;
- new Oracle pack path.

## If CodeCaptain Returns RED

Allowed next action:

- Do not launch Agents751/752/753.
- Write a RED decision memo.
- Triage CodeCaptain blockers into root-cause lanes.
- Keep all production scheduler/write/external/owner-publication lanes blocked.

## Never Do From This Router

- Do not launch stale Agent745.
- Do not launch Agent751/752/753 without the GREEN CodeCaptain decision token.
- Do not launch Agent751/752/753 while `production_db_sha_mismatch` or `protected_workbook_sha_mismatch` is present.
- Do not treat a GREEN answer as sufficient without DB-boundary review.
- Do not production-apply.
- Do not mutate workbook.
- Do not mutate LaunchAgents.
- Do not install or enable scheduler automation.
- Do not write external systems.
- Do not ask the owner for approval.
- Do not treat validate-only GREEN as production business-decision GREEN.
