# Human Action Required - Agent750 CodeCaptain Review

Status: HUMAN_OWNER_ACTION_REQUIRED

Last verified: `2026-05-10T10:23:03+0500`

Current blocker: the canonical `Answer/` folder now contains exactly one real GREEN answer, but readiness remains blocked on `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`; the current DB SHA is `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156` and the current workbook SHA is `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`, while the original Agent750 pack reviewed DB SHA `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64` and workbook SHA `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`.

Canonical answer: `~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer/Code_Captain_10.05.2026_12_35_59.md`; SHA256 `154e179a59a19f35605c154efcb1c7aea95717868e791b762291665b9eb4a0e4`; token `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`.

Stable current stopline pointer:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CURRENT_AGENT750_STOPLINE.md`

Latest completion audit:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_20260510_090511.md`

Current objective audit:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CURRENT_OBJECTIVE_AUDIT_AGENT750_BLOCKED_20260510_124512.md`

Latest stopline triage / next best step:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750_20260510_124512.md`

DB-boundary drift triage:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md`

DB-boundary supplemental review request:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md`

## What You Need To Do

Send this Oracle pack to CodeCaptain:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/`

The folder contains:

- `224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md`
- `ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`

Use the Markdown file as the main prompt/request and attach the CSV as the required source sidecar if the external project supports file attachments.

Optional single-file upload ZIP, if the external tool supports ZIP upload:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review_UPLOAD_ONLY.zip`

ZIP SHA256:

`2973d8747072a2fd4a8b5cba43971363ba3977eec0bd9f5c059a4699c3cacc9a`

ZIP manifest:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review_UPLOAD_ONLY_MANIFEST.md`

Important: use the refreshed pack in that folder, not an older exported copy. The current prompt SHA is:

`c013a318893110ec60666029db3bd39b032dcf65129fa20c265e76ce3e0b007b`

Latest validator manifest:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/agent750_review_pack_manifest_20260510_024500.json`

The refreshed pack explicitly requires the exact CodeCaptain GREEN token before Agent751/752/753 can launch. A YELLOW/non-RED answer is not launch authority.

Also include the DB-boundary drift triage and supplemental boundary review request above as context. A GREEN answer to the original pack remains necessary, but it is not sufficient by itself while `production_db_sha_mismatch` or `protected_workbook_sha_mismatch` is present.

## What Answer We Need Back

Ask CodeCaptain to return one of these exact decision tokens:

- `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`
- `YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE`
- `RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE`

The answer must place the selected token on an explicit `Decision:` or `Gate:` line. The line value must be exactly one token and nothing else, and it must be outside a fenced code block.

Example valid line:

`Gate: GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`

Examples that will not count:

- `Gate: approved GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`
- `Gate: do not use GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE yet`

## Where To Save The Answer

Save the answer under the same Oracle task folder, preferably:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer/`

Suggested filename:

`Code_Captain_AGENT750_VALIDATE_ONLY_PLAN_REVIEW_2026-05-09.md`

Save the answer inside the `Answer/` folder, not beside the Oracle prompt in the parent review-pack folder. If the readiness checker reports `misplaced_codecaptain_answer_files_present`, move the listed `misplaced_answer_files` into `Answer/` and rerun the checker.

Safer import option from `~/Docs/Autonomous_business`:

```bash
python3 scripts/ingest_agent750_codecaptain_answer.py --source /path/to/CodeCaptain_answer.md
```

That command is dry-run by default. If the JSON output is `"ok": true`, copy the answer with:

```bash
python3 scripts/ingest_agent750_codecaptain_answer.py --source /path/to/CodeCaptain_answer.md --apply
```

The helper validates the exact decision line and duplicate-answer state before copying. It does not launch Agents751/752/753.

To see the current safe next action at any time, run:

```bash
python3 scripts/report_agent750_next_action.py --json-only
```

To wait read-only for the answer/readiness transition without manual rechecking, run:

```bash
python3 scripts/wait_for_agent750_codecaptain_answer.py --timeout-seconds 3600 --interval-seconds 30
```

The watcher does not import files, launch Agents751/752/753, mutate production state, or ping tmux panes.

Optional safe resume controller after you have an answer file:

```bash
python3 scripts/resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md
python3 scripts/resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md --apply-import
```

The controller is dry-run/readiness-first by default. It does not launch Agents751/752/753 unless `--launch` is explicitly added after readiness passes.

Preferred launch command after the apply-import run returns `READY_FOR_GUARDED_LAUNCH`:

```bash
python3 scripts/resume_agent750_to_753.py --launch
```

That command reruns readiness, refreshes pane selection, and runs guarded launcher dry-run preflight before any launch.

`READY_FOR_GUARDED_LAUNCH` is not a launch result. The controller will show `did_launch=false` in that state and print the exact `next_resume_command` to run if you choose to launch.

Do not combine answer import and launch in one command. `--apply-import --launch` is intentionally rejected; first apply the answer import and confirm `READY_FOR_GUARDED_LAUNCH`, then run the separate `--launch` command.

## Important Boundary

Until that answer exists and contains the GREEN decision token, do not launch:

- Agent751;
- Agent752;
- Agent753;
- stale Agent745;
- production scheduler automation;
- LaunchAgent mutation;
- production DB write;
- workbook write;
- external-system writes;
- owner approval request;
- owner-facing production GREEN publication.

After the readiness checker returns `"ok": true`, prefer the resume controller:

```bash
python3 scripts/resume_agent750_to_753.py --launch
```

Lower-level manual fallback:

```bash
python3 scripts/list_agent751_753_candidate_panes.py --json-only
```

Then pass exactly three selected `%number` Codex panes into the guarded launcher.

The guarded launcher must remain monitor-only for Agent751/752/753. Do not add `--visibility-pane LIVE`, do not use `orchestrator_ping_mode=chat` or `orchestrator_ping_mode=receiver`, and do not ask execution agents to manually ping any chat pane. The current tmux orchestrator footer tests include both initial launch and later gated-send prompts, so agents should record closeouts/marker JSON instead of sending pane messages.

The readiness checker also requires both tmux guard files to exist before launch can turn green:

- `~/Docs/Autonomous_business/config/tmux_orchestrator_visibility_disabled.flag`
- `~/Docs/Autonomous_business/config/tmux_orchestrator_pings_disabled.flag`

If either file is missing, readiness fails closed even if CodeCaptain returns the GREEN token.

## Current Expected Boundary Before Launch

- Reviewed Agent750-pack DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Current DB SHA: `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156`
- Reviewed Agent750-pack workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Current workbook SHA: `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`
- Real `config/proof_window.lock`: absent unless a later explicitly authorized proof window is active.
- Tmux kill switches: both present.

Launch remains blocked until the current DB/workbook boundary is reviewed/re-anchored and `scripts/check_agent750_launch_readiness.py` returns `"ok": true`.
