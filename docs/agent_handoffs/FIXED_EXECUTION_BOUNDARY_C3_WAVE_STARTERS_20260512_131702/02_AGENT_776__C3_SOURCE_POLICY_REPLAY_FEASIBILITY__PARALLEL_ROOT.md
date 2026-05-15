# Agent776 - Copied-Temp C3 Source + Policy Replay Feasibility

## Mission

Determine, on copied-temp evidence only, what it would take to rematerialize C3 source freshness and policy gates for the intended `2026-05-11` owner-publication cutoff after the STOREB ads fix.

This is not a production apply lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/FIXED_EXECUTION_BOUNDARY_C3_WAVE_PLAN_20260512_131702.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/FIXED_EXECUTION_BOUNDARY_C3_WAVE_ORCHESTRATOR_HANDOFF_20260512_131702.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/FIXED_EXECUTION_BOUNDARY_C3_WAVE_STARTERS_20260512_131702/02_AGENT_776__C3_SOURCE_POLICY_REPLAY_FEASIBILITY__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/owner_publication_readiness_delta_after_storeb_prod_apply_20260512_122050_agent774_closeout.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_OWNER_MAPPING_PRODUCTION_APPLY_CLOSEOUT_20260512_102321.md`

Sibling Agents775 and 777 run in parallel. Treat your result as provisional until Agent775 resolves the current boundary drift.

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent776_c3_source_policy_replay_feasibility_20260512_131702_closeout.md`

## Assigned Evidence Root

`~/Docs/Autonomous_business/exports/validation/fixed_execution_boundary_c3_wave/20260512_131702/agent776_c3_replay_feasibility`

Create this folder if needed. You may write only inside this evidence root and to the assigned closeout.

## Scope

Allowed:

- Read scripts, docs, current DB, and existing evidence.
- Copy `db/app.db` into the assigned evidence root and run copied-temp experiments on that copy only.
- Run validators/materializers only if all outputs and mutations stay under the assigned evidence root.
- Write evidence files under the assigned evidence root.
- Write the assigned closeout.

Forbidden:

- No production DB mutation.
- No protected workbook mutation.
- No `--apply` against `db/app.db`.
- No scheduler, LaunchAgent, plist, cron, Web_automation, browser/session, external writes, owner publication, owner approval request, cash, PO, ad-spend, price, or stock action.
- No claim that owner publication is green.

## Required Checks

At minimum:

- Capture current boundary hashes and note that Agent775 owns final drift classification.
- Inspect available C3 scripts and their help text before running them.
- Copy `db/app.db` to the evidence root before any experimental write-capable replay.
- Run source freshness / policy gate validators against production DB read-only and/or the copied DB.
- If safe, attempt copied-temp materialization or dry-run for `2026-05-11` to identify what gates can clear and what source evidence is missing.

Relevant script candidates to inspect:

```bash
python3 scripts/materialize_policy_source_freshness.py --help
python3 scripts/materialize_policy_gate_results.py --help
python3 scripts/validate_policy_source_freshness.py --help
python3 scripts/validate_policy_gate_results.py --help
python3 scripts/run_operational_stock_daily_truth.py --help
```

If a command requires env gates, use them only against the copied DB under the assigned evidence root. If you cannot prove a command is copied-temp-only, skip it and record why.

## Required Analysis

Closeout must answer:

- Which C3 source freshness rows are missing/stale for `2026-05-11`.
- Whether the STOREB ads fix can clear `ads_source_truth` after policy-gate rematerialization.
- Which C3 gates remain blocked after any copied-temp replay.
- Which exact inputs/evidence are needed for a production-safe future rematerialization lane.
- The minimum safe command sequence for the next agent, explicitly distinguishing copied-temp proof from production apply.

## Gate Rules

Use:

- `Gate: GREEN` if copied-temp feasibility is fully mapped and a safe next command sequence is clear.
- `Gate: YELLOW` if feasibility is mostly mapped but some inputs or command contracts need review.
- `Gate: RED` if copied-temp isolation cannot be proven, production was touched, or the result would mislead owner-publication readiness.

The closeout must include a standalone line exactly like:

`Gate: YELLOW`

## Completion

After writing the closeout, run the tmux completion command appended by the orchestrator. Do not manually ping any pane.
