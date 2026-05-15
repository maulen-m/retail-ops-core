# Agent750 Guardrail Delivery Unit - 2026-05-10 02:23 +05

Status: `PARKED_WAITING_FOR_EXTERNAL_CODECAPTAIN_ANSWER`

## Purpose

This file isolates the current Agent750 -> Agent751/752/753 guardrail slice from the much larger Autonomous Business rollout diff. It is a review/commit aid only. It is not launch authority.

## Current Stopline

Agents751/752/753 must not launch until:

1. exactly one real `Code_Captain*.md` or `CodeCaptain*.md` answer exists in `~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer/`;
2. the answer contains exactly one non-fenced `Decision:` or `Gate:` line with `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`;
3. `python3 scripts/check_agent750_launch_readiness.py` returns `"ok": true`.

Current observed blocker: `missing_codecaptain_answer_file`.

The readiness checker also requires both tmux kill-switch files to exist:

- `config/tmux_orchestrator_visibility_disabled.flag`
- `config/tmux_orchestrator_pings_disabled.flag`

If either file is missing, readiness fails closed even if CodeCaptain returns the GREEN token.

## Runtime Guard Scripts

- `scripts/check_agent750_launch_readiness.py`
- `scripts/ingest_agent750_codecaptain_answer.py`
- `scripts/report_agent750_next_action.py`
- `scripts/wait_for_agent750_codecaptain_answer.py`
- `scripts/list_agent751_753_candidate_panes.py`
- `scripts/resume_agent750_to_753.py`
- `scripts/launch_agent751_753_after_agent750.py`

## Test Coverage

- `tests/test_check_agent750_launch_readiness.py`
- `tests/test_ingest_agent750_codecaptain_answer.py`
- `tests/test_report_agent750_next_action.py`
- `tests/test_wait_for_agent750_codecaptain_answer.py`
- `tests/test_list_agent751_753_candidate_panes.py`
- `tests/test_resume_agent750_to_753.py`
- `tests/test_launch_agent751_753_after_agent750.py`
- `tests/test_agent750_green_only_launch_docs.py`
- `tests/test_validate_agent750_review_pack.py`

## Operator And Review Surfaces

- `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
- `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/HUMAN_ACTION_REQUIRED_AGENT750_CODECAPTAIN_REVIEW_20260509.md`
- `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/HUMAN_NEXT_ACTION_AGENT750_20260509_231716.md`
- `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_PING_ROUTING_INCIDENT_20260509.md`
- `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_20260510_090511.md`

## External Oracle Pack

- `~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/`
- Optional upload ZIP: `~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review_UPLOAD_ONLY.zip`
- ZIP SHA256: `4e00bfddfd8e3216875ca4776f6e2ade9462e3a2e46161c241fc471f4671b440`
- Latest pack manifest: `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/agent750_review_pack_manifest_20260510_024500.json`

## Safety Properties

- Missing answer blocks launch.
- YELLOW/RED answer blocks launch.
- Fenced, negated, or explanatory GREEN token does not count.
- README placeholder does not count as an answer.
- Misplaced answer files are reported but do not count.
- Duplicate or unexpected answer files block readiness.
- Protected DB/workbook SHA mismatch blocks readiness.
- Proof-window lock blocks readiness.
- Existing downstream Agent751/752/753 artifacts block readiness.
- Pane availability cannot bypass readiness.
- Next-action reporter, resume controller, and guarded launcher independently require the exact GREEN token.
- Guarded launcher uses monitor-only routing and refuses stale human-visible chat routing.
- Readiness requires the visibility and completion-ping kill-switch files to remain present.
- Manual tmux/chat pings by execution agents are forbidden for this rollout.

## Verification Commands

```bash
pytest -q tests/test_ingest_agent750_codecaptain_answer.py tests/test_report_agent750_next_action.py tests/test_wait_for_agent750_codecaptain_answer.py tests/test_list_agent751_753_candidate_panes.py tests/test_validate_agent750_review_pack.py tests/test_agent750_green_only_launch_docs.py tests/test_launch_agent751_753_after_agent750.py tests/test_check_agent750_launch_readiness.py tests/test_resume_agent750_to_753.py
pytest -q ~/.codex/skills/tmux-agent-orchestrator/tests/test_option_d.py
python3 scripts/report_agent750_next_action.py --json-only
./scripts/lint_docs.sh
git diff --check -- . ':!db/app.db'
```

Latest verified result for the focused Agent750/751 suite: `146 passed`.

Latest verified result for the tmux-agent-orchestrator Option D suite: `22 passed`.

The latest added regression proves the optional upload ZIP contains exactly the three flat source files and that each ZIP entry is byte-for-byte identical to the source pack file.

The latest audit quality guard proves the current completion audit preserves ranked blocker triage, the minimum safe command sequence, monitor-only launch routing, and the explicit no-receiver/no-chat/no-manual-ping stoplines.

The stable current stopline pointer and human answer-surface guards prove future resumes have one obvious start-here file and that the human-facing handoffs plus external Answer README all point to it.

The monitor-only prompt-footer guard proves future execution-agent prompts explicitly forbid manual `tmux send-keys`, chat-pane pings, receiver pings, or any other manual completion wake-up when the run is file-marker-only.

The resume-controller source-required import-flag guard proves `--apply-import` and `--replace` cannot be passed without `--source`, preventing false operator confidence that an answer import occurred when no source file was provided.

The resume-controller apply-import and replace-forwarding guards prove a real answer source can be applied, readiness can pass, and the controller can return a guarded launch command without launching unless `--launch` is explicitly provided.

The pane-selection current-pane guards prove candidate discovery excludes the active tmux pane and the guarded launcher rejects reuse panes that include `TMUX_PANE`, preventing accidental prompt delivery into the orchestrator/current chat.

The resume-controller explicit reuse-pane guards prove bad explicit pane selections fail before the controller presents or executes a launch command.

The launcher dry-run live-pane validation guard proves `--dry-run` cannot return a paper-green launch command when the supplied reuse panes are not live Codex panes in the repo.

The resume-controller guarded-launch dry-run preflight guard proves `resume_agent750_to_753.py` cannot present or execute a launch command until the guarded launcher itself has already validated the selected panes in dry-run mode.

The resume-controller ready-is-not-launched guard proves `READY_FOR_GUARDED_LAUNCH` remains an explicit non-launching state with `did_launch=false` and a separate `next_resume_command`.

The resume-controller apply-import-and-launch separation guard proves `--apply-import --launch` is rejected before import, readiness, pane selection, or launch commands run.

The explicit-json launch-success guard proves the guarded launcher emits structured JSON for real launches and the resume controller refuses empty or unclear launcher output even when the exit code is zero.

The structured launcher-failure evidence guard proves tmux launcher failure details remain visible to the resume controller and are not collapsed into an ambiguous failed exit code.

The structured monitor-only command-payload guard proves every guarded launcher JSON payload for dry-run, success, and failure preserves `--orchestrator-ping-mode monitor-only` and excludes `--visibility-pane`, `--orchestrator-pane`, `--auto-create-orchestrator-receiver`, `LIVE`, `chat`, and `receiver`.

The latest timestamped audit/checkpoint pointer guard proves `current_gate_status_agent750_waiting_codecaptain.json` points to the newest `ACTIVE_OBJECTIVE_COMPLETION_AUDIT_*.md` and newest `CURRENT_STOPLINE_CHECKPOINT_AGENT750_WAITING_*.md` file in this run folder.

The kill-switch launch-readiness guards prove `check_agent750_launch_readiness.py`, the next-action reporter, the watcher, the resume controller, and the guarded launcher cannot turn GREEN if either tmux wrong-pane protection file has been removed.

## Not Authorized

- no Agent751/752/753 launch;
- no production DB write;
- no workbook write;
- no scheduler or LaunchAgent mutation;
- no external-system write;
- no owner approval request;
- no `--visibility-pane LIVE`;
- no `orchestrator_ping_mode=chat`;
- no `orchestrator_ping_mode=receiver`;
- no manual chat-pane pings by execution agents.
