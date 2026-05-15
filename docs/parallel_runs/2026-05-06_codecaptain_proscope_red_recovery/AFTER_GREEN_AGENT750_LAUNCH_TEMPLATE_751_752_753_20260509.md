# After GREEN Agent750 Review Launch Template - Agents751/752/753

Status: INERT_TEMPLATE_DO_NOT_RUN_UNTIL_DB_BOUNDARY_REVIEW_CLEARS

This document is a launch template only. It must not be treated as authorization. Use it only after CodeCaptain GREEN is preserved and DB/workbook readiness returns `ok=true` for:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/`

Current stopline: the GREEN answer exists, but it is not sufficient while `production_db_sha_mismatch` or `protected_workbook_sha_mismatch` is present. The current DB-boundary drift triage and supplemental review request must be handled before this template can be used:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md`

## Required Preflight Before Launch

1. Read the CodeCaptain answer and verify the decision token is exactly `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`.
2. Resolve the DB/workbook-boundary review so `production_db_sha_mismatch` and `protected_workbook_sha_mismatch` are no longer reported by readiness.
3. Update the current gate audit with the CodeCaptain answer path, decision, and DB/workbook-boundary review outcome.
4. Do not use human-visible `LIVE` ping routing for this rollout, because repeated wrong-pane wake-ups have now occurred even after live-pane re-registration.

The next launch must use monitor-only completion markers plus `watch_tmux_agents.py` / closeout review. Human-visible chat pings are disabled for Agent751-753.

5. Re-sample protected surfaces:

```bash
cd ~/Docs/Autonomous_business
LC_ALL=C LANG=C shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
test -e config/proof_window.lock && echo proof_window_lock_exists || echo proof_window_lock_absent
```

Expected:

- Original Agent750 reviewed DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Current DB SHA before DB-boundary review: `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156`
- Original Agent750 reviewed workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Current workbook SHA before workbook-boundary review: `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`
- Real `config/proof_window.lock`: absent, unless a later explicit proof window is active.

If readiness still reports `production_db_sha_mismatch` or `protected_workbook_sha_mismatch`, stop. Do not launch Agents751/752/753.

6. Run the consolidated read-only readiness checker:

```bash
cd ~/Docs/Autonomous_business
python3 scripts/check_agent750_launch_readiness.py
```

Proceed only if it returns JSON with `"ok": true`. Treat any listed `errors` as launch stoplines.

Preferred guarded resume controller:

```bash
cd ~/Docs/Autonomous_business
python3 scripts/resume_agent750_to_753.py --launch
```

Run this only after the answer import step has already returned `READY_FOR_GUARDED_LAUNCH`. `READY_FOR_GUARDED_LAUNCH` is not a launch result.

## Pane Selection

Do not hard-code old pane IDs. Select live Codex panes at launch time.

Inspect current panes:

```bash
tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{pane_id} #{pane_current_command} #{pane_current_path} #{pane_title}'
```

Safer read-only candidate list:

```bash
python3 scripts/list_agent751_753_candidate_panes.py --json-only
```

Use only panes where:

- the pane ID is a unique `%number` value, for example `%326`;
- `pane_current_command` is `codex`;
- `pane_current_path` is `~/Docs/Autonomous_business`;
- the pane is idle or ready for a new prompt;
- the prior role will not confuse closeout ownership.

Do not reuse plain `zsh` panes as agent chats.

## Launch Command Shape

Use monitor-only routing. This prevents agent completion messages from going into any stale or unrelated Codex chat. The orchestrator must review completion through the manifest, closeout files, completion markers, and watcher output.

Replace `<PANE_751>,<PANE_752>,<PANE_753>` with three unique freshly verified `%number` Codex pane IDs.

Preferred guarded helper:

```bash
cd ~/Docs/Autonomous_business
python3 scripts/launch_agent751_753_after_agent750.py \
  --reuse-panes <PANE_751>,<PANE_752>,<PANE_753>
```

The helper runs `scripts/check_agent750_launch_readiness.py` first and refuses to launch unless it returns `"ok": true`.

The helper also fails closed before real launch unless the three reuse panes are unique `%number` pane IDs, resolve through tmux, run `codex` or `codex-aarch64-a`, and are currently in `~/Docs/Autonomous_business`.

Underlying launch shape:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts \
  --session autonomous_business \
  --orchestrator-ping-mode monitor-only \
  --agents 751,752,753 \
  --reuse-panes <PANE_751>,<PANE_752>,<PANE_753> \
  --no-start-sessions \
  --parallel-groups 751=agent751_752_753_validate_only_root,752=agent751_752_753_validate_only_root,753=agent751_752_753_validate_only_root \
  --run-id codecaptain_agent751_752_753_validate_only_wave_YYYYMMDD \
  --mode hybrid \
  --submit-delay 0.35
```

Do not manually paste completion text into random panes. Use the closeout files plus `watch_tmux_agents.py` as authority.

## Expected Closeouts

- Agent751: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_751_option_c_validate_only_runner_contract_closeout.md`
- Agent752: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_752_cash_risk_daily_surface_spec_readonly_closeout.md`
- Agent753: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_753_source_freshness_exception_queue_map_readonly_closeout.md`

## Advancement Rule

After Agents751/752/753 complete:

- read all closeouts;
- treat any `RED` as stopline;
- if none are RED and every YELLOW condition is explicitly carried as a blocker/warning, package a new CodeCaptain review before any production scheduler lane.

## Non-Negotiable Stoplines

Even after CodeCaptain GREEN:

- Agent751 is the only write-capable lane;
- Agents752/753 are read-only;
- no production DB write;
- no workbook write;
- no scheduler or LaunchAgent mutation;
- no external writes;
- no real `config/proof_window.lock` create/remove;
- no owner approval request;
- no owner publication GREEN;
- no old Agent54 phrase reuse;
- no Agent64 activation.
