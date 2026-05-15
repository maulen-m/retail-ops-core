# Agent 72C / Launcher 726 - Header-Only Source-Gap Production-Safe Wrapper

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72c_header_only_prod_safe_wrapper_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72c_evidence/`

Parallel group:

`agent72b_e_write_gate_hardening`

Dependency:

Run only after Agent72A closeout is reviewed as non-RED.

## Mission

Implement the production-safe wrapper for the `252` STOREB header-only source-gap quarantine contract. The direct materializer is temp-only; production must use a staging-copy/backup-first wrapper. This lane must not production-apply.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others. Own only the header-only production wrapper and focused tests.

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
9. `~/Docs/Autonomous_business/scripts/materialize_header_only_source_gap_quarantine.py`
10. `~/Docs/Autonomous_business/scripts/apply_storeb_product_identity_quarantine_production_safe.py`
11. `~/Docs/Autonomous_business/tests/test_header_only_source_gap_quarantine.py`
12. `~/Docs/Autonomous_business/tests/test_storeb_product_identity_quarantine_prod_wrapper.py`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business/scripts/apply_header_only_source_gap_quarantine_production_safe.py`
- `~/Docs/Autonomous_business/tests/test_header_only_source_gap_quarantine_prod_wrapper.py`
- assigned closeout and evidence folder only

Do not edit `config/write_side_gating_manifest.yaml`; Agent729 owns final manifest integration.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers, external repos, browser, Kaspi/API, Google, Meta, banks, Web_automation, or live workbooks.
- Do not ask owner for authorization.
- Do not production-apply or activate any owner phrase.

## Required Implementation

Create:

`scripts/apply_header_only_source_gap_quarantine_production_safe.py`

Required behavior:

- Dry-run by default; no production write without `--apply`.
- Requires `ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_PRODUCTION_APPLY=1` when `--apply` is used.
- Requires `--expected-pre-sha256`.
- Requires `--classification`, `--output-root`, and `--backup-dir`.
- Requires explicit expected values:
  - `--expected-candidate-rows`
  - `--expected-product-cashflow-delete-rows`
  - `--expected-stock-ledger-delete-rows`
  - `--expected-sales-fact-product-profit-null-rows`
- Creates timestamped backup before target replacement/write.
- Checks backup and staging integrity.
- Rejects SQLite sidecars before target replacement/write.
- Applies the temp-only materializer to a staging copy first.
- Preserves order-level `CASH_IN` rows.
- Verifies target DB SHA still equals `--expected-pre-sha256` immediately before final replacement/write.
- Writes summary JSON with pre/post SHA, backup path, rollback command, expected/actual deltas, cash preservation, and `production_db_modified`.
- Does not productize header-only rows.

Use the STOREB product-identity production wrapper as the pattern, but keep this wrapper separate.

## Required Tests

Write tests proving:

- Dry-run does not change DB.
- `--apply` without env gate fails before mutation.
- Wrong pre-SHA fails before mutation.
- Sidecar files block apply.
- Successful apply uses backup/staging, deletes/nulls only expected product-level leakage, preserves order-level `CASH_IN`, and writes rollback metadata.
- Expected delta mismatch fails before target replacement.

Run at minimum:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_header_only_source_gap_quarantine.py tests/test_header_only_source_gap_quarantine_prod_wrapper.py
python3 -m py_compile scripts/apply_header_only_source_gap_quarantine_production_safe.py
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
