# Agent 72D / Launcher 727 - Cashflow Calendar Gate Hardening

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72d_cashflow_calendar_gate_hardening_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72d_evidence/`

Parallel group:

`agent72b_e_write_gate_hardening`

Dependency:

Run only after Agent72A closeout is reviewed as non-RED.

## Mission

Patch `scripts/rebuild_cashflow_calendar.py` so no schema mutation or DB write can happen before `ENABLE_CASHFLOW_WRITE=1` and `--apply` are both present. Agent72A found a possible `_ensure_daily_columns()` `ALTER TABLE` before the env gate. This must become fail-closed.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others. Own only the cashflow calendar script and focused tests.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_contract_hardening_write_gate_verification_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/SCRIPT_WRAPPER_DECISION.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/WRITE_GATING_VERIFICATION.tsv`
9. `~/Docs/Autonomous_business/scripts/rebuild_cashflow_calendar.py`
10. `~/Docs/Autonomous_business/tests/test_cashflow_rebuild_idempotent.py`
11. `~/Docs/Autonomous_business/tests/test_cashflow_calendar.py`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business/scripts/rebuild_cashflow_calendar.py`
- a focused new test file if needed, preferably `~/Docs/Autonomous_business/tests/test_rebuild_cashflow_calendar_write_gate.py`
- assigned closeout and evidence folder only

Do not edit `config/write_side_gating_manifest.yaml`; Agent729 owns final manifest integration.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers, external repos, browser, Kaspi/API, Google, Meta, banks, Web_automation, or live workbooks.
- Do not ask owner for authorization.
- Do not production-apply or activate any owner phrase.

## Required Implementation

Patch `scripts/rebuild_cashflow_calendar.py` so:

- Dry-run remains read-only.
- `--apply` without `ENABLE_CASHFLOW_WRITE=1` fails before any write, including schema `ALTER TABLE`.
- Missing schema columns in dry-run produce a fail-closed validation error or a clear migration-required error, not implicit mutation.
- If schema migration is still needed, it must be behind the same apply/env gate or a separate explicit migration gate; do not create broad migration logic unless the current script already expects it.
- Existing successful behavior for valid schemas remains intact.

Prefer the smallest patch that moves all write-capable behavior behind the gate.

## Required Tests

Write/update tests proving:

- A DB missing one required `fact_cashflow_daily` column is not altered in dry-run.
- A DB missing one required column with `--apply` but without env gate fails before mutation.
- Existing idempotency/calendar tests still pass.
- If env-gated apply can still add missing columns, test that explicitly; if it now fails closed with migration-required, test that behavior explicitly.

Run at minimum:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_cashflow_rebuild_idempotent.py tests/test_cashflow_calendar.py tests/test_rebuild_cashflow_calendar_write_gate.py
python3 -m py_compile scripts/rebuild_cashflow_calendar.py
```

If a listed test file does not exist, adapt to the repo's current focused tests and record the exact commands.

## Closeout

Write the closeout with:

- READCHECK
- files changed
- tests run and outputs
- exact gate behavior before/after
- residual blockers
- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`

Gate GREEN only if the write-before-gate risk is closed and tests pass.
