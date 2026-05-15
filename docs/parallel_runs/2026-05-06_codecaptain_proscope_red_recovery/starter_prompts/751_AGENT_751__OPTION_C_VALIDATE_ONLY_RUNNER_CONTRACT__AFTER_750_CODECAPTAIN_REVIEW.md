# Agent 751 - Option C Validate-Only Runner Contract

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_751_option_c_validate_only_runner_contract_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_751_option_c_validate_only_runner_contract_evidence/`

Dependency:

- Start only after the Agent750 CodeCaptain review pack returns the GREEN decision token, the DB/workbook-boundary review has resolved `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`, the guarded orchestrator launch has already recorded pre-launch `scripts/check_agent750_launch_readiness.py` `"ok": true`, and your post-launch boundary check below returns `"ok": true`.

## Hard Launch Stopline

Before doing any work, run from `~/Docs/Autonomous_business`:

```bash
./scripts/check_agent750_launch_readiness.py --allow-existing-downstream-artifacts
```

This is a post-launch child-agent boundary check. The flag only tolerates the Agent751/752/753 downstream artifacts created by the guarded monitor-only launch; all other readiness errors remain hard blockers.

If it does not return `"ok": true`, stop before mission work. This includes `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`. Do not manually ping, paste, or send any tmux/chat message to the orchestrator or any other pane. Write only the assigned closeout with the readiness JSON/errors, a standalone `Gate: RED` line, and a clear `ReadinessStopline:` section; do not create extra evidence beyond what is needed for that closeout. Do not bypass this with manual memory of a review answer.

## Mission

Implement the smallest tests-first validate-only runner contract for Option C on the readiness-approved DB/workbook boundary. This is validate-only code/test work, not production scheduler authorization. Do not assume the original `dec77` DB boundary or reviewed workbook boundary is current unless the boundary review explicitly re-anchors launch readiness to it or readiness confirms it.

The runner must support copied-DB or explicit read-only operation, proof-window lock fail-closed behavior before production DB open, deterministic evidence folders, trust banner emission, and a Cash Risk Daily draft stub.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OPTION_C_VALIDATE_ONLY_IMPLEMENTATION_PLAN_AFTER_DEC77_REANCHOR_20260509.md`
7. Agent750 closeout.
8. Agent750 CodeCaptain review answer.
9. Agent747, Agent748, and Agent749 closeouts.
10. `~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_current_dec77_reanchor/CURRENT_DEC77_RELEASE_ANCHOR.md`
11. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md`
12. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md`
13. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_AGENT750_20260510_153410.md`

## Current Boundary

- Original Agent750 reviewed DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Supplement DB SHA before launch-time re-anchor: `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156`
- Re-anchored launch-readiness DB SHA: `44426216a026c3ab4f7c658e4950421446b99bae99e7cf704db8e2c96d35cc91`
- Launch-time DB SHA: use the `db_sha256` from the launch-time readiness JSON that returns `"ok": true`.
- Original Agent750 reviewed workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Supplement workbook SHA before launch-time re-anchor: `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`
- Re-anchored launch-readiness workbook SHA: `bd7c5bb3e336f0cf35423ad00e7e6f25fa5ae41cdeb3ceb51075e09047f613b9`
- Launch-time workbook SHA: use the `workbook_sha256` from the launch-time readiness JSON that returns `"ok": true`.
- Strict daily preflight proof-window lock behavior: `AB_PROOF_WINDOW_LOCK_PATH` or default `config/proof_window.lock`, exit `75`, output `STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK`.

## Write Boundary

Allowed writes:

- focused tests under `~/Docs/Autonomous_business/tests/`;
- focused validate-only runner code under `~/Docs/Autonomous_business/scripts/` if needed;
- assigned closeout and evidence folder.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers, LaunchAgents, or plist files.
- Do not create or remove the real `config/proof_window.lock`.
- Do not install or enable Option C automation.
- Do not write external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not ask owner for approval.
- Do not reuse the old Agent54 phrase or activate Agent64.

## Required Approach

Tests first:

1. Add a failing test proving a proof-window lock stops the validate-only runner before production DB open.
2. Add a failing test proving every validator receives an explicit copied-DB/read-only target or the runner blocks with a clear unsupported-validator status.
3. Add a failing test proving owner draft/trust banner output writes only inside the deterministic evidence folder.

Then implement the smallest safe fix.

Required behavior:

- Default mode is validate-only and non-writing.
- Production DB copy/read is blocked if a proof-window lock exists.
- Already-copied DB mode may run without opening production DB and must record that production was not touched.
- Owner outputs are local draft files only.
- Cash Risk Daily is the first stub surface.
- Warning cohorts remain visible and machine-readable.

## Required Verification

Run focused tests and compile checks:

```bash
pytest -q <new_or_focused_test_file>
python3 -m py_compile <touched_scripts>
```

If runner code touches validator contracts, also run the smallest existing validator tests that cover those contracts.

Do not run a live production scheduler. Do not run a command that writes production DB/workbook/external systems.

## Gate Semantics

`GREEN`:

- tests were added first and then pass;
- proof-window lock prevents production DB open;
- copied-DB/read-only target is deterministic and explicit;
- owner outputs are evidence-folder drafts only;
- no production DB/workbook/scheduler/external mutation occurred.

`YELLOW`:

- implementation is mostly safe but needs review for validator target support, exit code semantics, or broader integration.

`RED`:

- lock is bypassable before DB open;
- validators can silently use production DB;
- focused tests fail;
- any forbidden mutation occurs.

## Closeout

Write closeout with READCHECK, tests-first evidence, files changed, commands run, proof-window behavior, copied-DB/read-only behavior, limitations, recommended follow-up, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
