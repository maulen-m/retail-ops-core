# Dirty Worktree Cleanup Plan

Generated: `2026-05-15T21:36:22`

## Policy

- Use controlled commit splits, not `git add .`.
- Do not commit local Playwright session JSON; they are now ignored and removed from the git index only.
- Keep production DB and CRM workbook out of commits.
- Keep evidence/run surfaces traceable in explicit docs/orchestration commits.

## Counts

| Status | Class | Action | Count |
| --- | --- | --- | ---: |
| ` M` | `ads_source_truth` | `commit_code_tests_docs` | 6 |
| `??` | `ads_source_truth` | `commit_code_tests_docs` | 7 |
| `??` | `agent_handoff_docs` | `commit_as_traceable_plan_surface` | 116 |
| ` M` | `cash_bank_source_state` | `commit_with_cashflow_source_truth` | 3 |
| `??` | `cash_bank_source_state` | `commit_with_cashflow_source_truth` | 1 |
| ` M` | `cashflow_order_cash_truth` | `commit_code_tests_docs` | 6 |
| `??` | `cashflow_order_cash_truth` | `commit_code_tests_docs` | 12 |
| ` M` | `config_other` | `commit_with_relevant_group` | 3 |
| `??` | `config_other` | `commit_with_relevant_group` | 5 |
| ` M` | `daily_ops_automation` | `commit_code_tests_docs` | 8 |
| `??` | `daily_ops_automation` | `commit_code_tests_docs` | 7 |
| ` M` | `db_schema` | `commit_with_schema_group` | 1 |
| ` M` | `docs_contracts` | `commit_docs` | 9 |
| `??` | `docs_contracts` | `commit_docs` | 2 |
| ` M` | `inventory_po_economics` | `commit_code_tests_docs` | 26 |
| `??` | `inventory_po_economics` | `commit_code_tests_docs` | 7 |
| `D ` | `local_sensitive_runtime_session` | `do_not_commit_local_runtime` | 3 |
| ` M` | `mutable_agent_state` | `commit_as_traceable_state` | 7 |
| ` M` | `other` | `manual_review` | 3 |
| `??` | `parallel_run_docs` | `commit_as_traceable_plan_surface` | 398 |
| ` M` | `policy_operational_stock_exception` | `commit_code_tests_docs` | 1 |
| `??` | `policy_operational_stock_exception` | `commit_code_tests_docs` | 28 |
| ` M` | `sales_lifecycle_truth` | `commit_code_tests_docs` | 3 |
| `??` | `sales_lifecycle_truth` | `commit_code_tests_docs` | 2 |
| ` M` | `scripts_other` | `commit_with_relevant_group` | 11 |
| `??` | `scripts_other` | `commit_with_relevant_group` | 27 |
| ` M` | `tests_other` | `commit_with_relevant_group` | 10 |
| `??` | `tests_other` | `commit_with_relevant_group` | 29 |
| `??` | `tmux_orchestration_logs` | `commit_as_traceable_orchestration_surface` | 595 |

## Planned Commit Order

- security/git hygiene for local Playwright sessions
- business automation and daily ops runbook/control surfaces
- ads source truth and active-scope contracts
- policy/C3, operational stock, exception queue, and source freshness foundation
- cashflow/order-entry/sales lifecycle truth and validators
- inventory/PO/economics/dim-sku contracts
- source replay / preflight guard tooling
- Agent750 guarded launch readiness tooling
- documentation, starter packs, orchestration manifests, and mutable state traceability

## Cleanup Decisions

- The untracked `tests/test_agent750_green_only_launch_docs.py` file was intentionally not committed and was removed from the working tree because it asserted the old all-pings-disabled / DB-boundary-stopline policy after the owner-approved receiver/live ping-back workflow and later source-truth waves had superseded that state.
- Raw local `runs/` orchestration folders were intentionally ignored instead of bulk-committed because their manifests/events can include local tmux pane identities and attestation tokens. Traceable human-readable evidence remains in `docs/parallel_runs/` and `docs/agent_handoffs/`.
