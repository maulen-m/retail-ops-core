# Agent 72B / Launcher 725 - Rebuild Snapshot Production-Safe Wrapper

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72b_rebuild_snapshot_prod_safe_wrapper_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72b_evidence/`

Parallel group:

`agent72b_e_write_gate_hardening`

Dependency:

Run only after Agent72A closeout is reviewed as non-RED.

## Mission

Implement the production-safe snapshot rebuild surface required by Agent72A. The goal is to make the snapshot step safe enough for a later owner-request preflight and production apply contract. This lane must not production-apply.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others. Own only the snapshot wrapper/script and its focused tests.

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
9. `~/Docs/Autonomous_business/scripts/rebuild_snapshot.py`
10. `~/Docs/Autonomous_business/tests/test_agent22_snapshot_and_cashflow_routing.py`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business/scripts/apply_rebuild_snapshot_production_safe.py`
- `~/Docs/Autonomous_business/tests/test_apply_rebuild_snapshot_production_safe.py`
- assigned closeout and evidence folder only

Do not edit `config/write_side_gating_manifest.yaml`; Agent729 owns final manifest integration.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers, external repos, browser, Kaspi/API, Google, Meta, banks, Web_automation, or live workbooks.
- Do not ask owner for authorization.
- Do not production-apply or activate any owner phrase.

## Required Implementation

Create a production-safe wrapper or equivalent patch. Preferred path:

`scripts/apply_rebuild_snapshot_production_safe.py`

Required behavior:

- Dry-run by default; no production write without `--apply`.
- Requires `ENABLE_REBUILD_SNAPSHOT_PRODUCTION_APPLY=1` when `--apply` is used.
- Requires `--expected-pre-sha256`.
- Requires `--date`, `--store`, `--mode ledger`, `--backup-dir`, and `--output-root`.
- Creates a timestamped backup before any target replacement/write.
- Checks backup integrity.
- Rejects SQLite WAL/SHM/journal sidecars before replacing/writing target DB.
- Applies the snapshot rebuild to a staging copy first, not directly to production.
- Checks staging integrity.
- Requires expected row count and/or expected delta controls before target replacement. If exact delta cannot be known generically, expose explicit expected values as required CLI flags and tests.
- Verifies target DB SHA still equals `--expected-pre-sha256` immediately before final replacement/write.
- Writes summary JSON with pre/post SHA, backup path, rollback command, row counts, integrity results, and `production_db_modified`.
- Keeps underlying `scripts/rebuild_snapshot.py` behavior intact unless a minimal patch is unavoidable.

## Required Tests

Write tests before or alongside implementation that prove:

- Dry-run does not change the DB and writes summary.
- `--apply` without `ENABLE_REBUILD_SNAPSHOT_PRODUCTION_APPLY=1` fails before mutation.
- Wrong `--expected-pre-sha256` fails before mutation.
- Sidecar files block apply.
- Successful apply uses backup/staging and writes rollback metadata.
- Expected row-count/delta mismatch fails before target replacement.

Run at minimum:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py tests/test_agent22_snapshot_and_cashflow_routing.py
python3 -m py_compile scripts/apply_rebuild_snapshot_production_safe.py
```

## Closeout

Write the closeout with:

- READCHECK
- files changed
- tests run and outputs
- exact env gate and CLI shape
- residual blockers
- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`

Gate GREEN only if the wrapper and tests pass and no forbidden mutation occurred.
