# Agent 749 - Scheduler Proof-Window Hardening

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_749_scheduler_proof_window_hardening_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_749_scheduler_proof_window_hardening_evidence/`

Dependency:

Start only after Agents747 and 748 are reviewed as non-RED.

## Mission

Prevent the 21:00 strict daily preflight scheduler path from touching or rewriting `~/Docs/Autonomous_business/db/app.db` during protected proof/release windows.

This is code/test hardening only. Do not mutate live LaunchAgents, production DB, workbook, external systems, or Option C production automation.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_closeout.md`
7. Agent747 and Agent748 closeouts.

## Write Boundary

Allowed writes:

- focused tests under `~/Docs/Autonomous_business/tests/`;
- focused code changes needed to harden `scripts/run_strict_daily_preflight.py` and directly related helper code;
- assigned closeout and evidence folder;
- optional docs note under `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/`.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate `~/Library/LaunchAgents/*.plist`.
- Do not write to external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not install or enable Option C automation.
- Do not ask owner for approval.
- Do not reuse old Agent54 phrase or activate Agent64.

## Required Approach

Tests first:

1. Add a failing test that proves a protected proof-window guard stops `scripts/run_strict_daily_preflight.py` before it opens/touches the DB.
2. Add a failing test or fixture proof that the guard is controlled by an explicit lock file or env var, not by human memory.

Then implement the smallest safe fix.

Recommended design:

- Support an explicit proof-window lock such as `AB_PROOF_WINDOW_LOCK_PATH` or repo-local default `config/proof_window.lock`.
- If the lock exists, strict daily preflight must fail closed or skip safely before opening `db/app.db`, running validators, generating business-insides, or emitting drift packs.
- The output must be loud and machine-greppable, for example `STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK`.
- The exit code should be non-zero but operationally clear. Do not silently pass green.

If you find a better minimal design, implement it only if it is safer and explain why in the closeout.

## Required Verification

Run focused tests and save outputs:

```bash
pytest -q <new_or_focused_test_file>
python3 -m py_compile scripts/run_strict_daily_preflight.py
```

If you add or touch validator/scheduler contracts, also run the smallest relevant existing tests.

Do not run a live production scheduler. Do not run a command that writes to production DB.

## Gate Semantics

`GREEN`:

- failing tests were added first and then pass;
- protected proof-window lock prevents DB touch before any DB open;
- implementation is deterministic and explicit;
- no production DB/workbook/LaunchAgent/external mutation occurred;
- focused tests and compile checks pass.

`YELLOW`:

- hardening mostly works but needs orchestrator review for exit-code semantics, docs wording, or broader scheduler integration.

`RED`:

- proof-window lock is missing or relies on manual memory;
- DB can still be opened/touched before the guard;
- focused tests fail;
- any forbidden mutation occurs.

## Closeout

Write the closeout with READCHECK, tests-first evidence, files changed, commands run, proof-window behavior, limitations, recommended follow-up, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
