# Agent878 Starter: Day-Complete And Status-Ledger Contract Repair

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent878_day_complete_status_ledger_repair_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_owner_qa_repair_wave/20260517_2223/agent878_day_complete_status_ledger_repair`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent875_contract_registry_closeout.md`
9. this starter prompt.

## Assignment

This is the only root write-capable repo lane for the current wave. Make the smallest correct repo changes needed to implement the owner-approved day-complete contract and the status-ledger provenance contract.

Owner-approved day-complete behavior:

- `CANCELLED/ARCHIVE` and `RETURNED/ARCHIVE` rows may be excluded from size-complete requirements.
- Blank SKU / `nan` offer rows may be treated as missing-line-item exceptions, not employee size-entry failures.
- Order `861147900` may be manually classified from offer text `Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48`.

Status-ledger behavior:

- Import-existing/manual WebUI archive runs may carry requested `--since/--until` into manifests only when source file hashes are recorded and the wrapper emits those values, not when they are hand-edited.
- Scope is copied-temp proof for STOREB, ACMEWEAR, and UNIVERSAL. Omitted 11KZ and MELVIS must stay disclosed unless same-window source files are provided.

You may edit focused repo docs, tests, validators, wrappers, and local evidence artifacts needed for this assignment. Do not edit unrelated files.

Do:

- Update the owning docs before changing validator/business-rule behavior.
- Add or update focused tests for the day-complete exclusions/classifications and status-ledger window provenance if code changes are needed.
- Run the smallest relevant targeted tests/validators.
- Run `scripts/lint_docs.sh`.
- Run `scripts/check_no_db_tracked.sh`.
- Write exact command outputs and evidence paths in the closeout.

Do not:

- write production DB;
- write workbook;
- change scheduler/LaunchAgent/cron;
- write source pointers;
- mutate Web_automation;
- write to Kaspi/API/WebUI beyond read-only fetching;
- hide true size-entry failures;
- hand-edit status-ledger window provenance.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- files changed;
- tests/commands run with exits;
- validator result for day-complete if runnable;
- validator result for status-ledger continuity if runnable;
- exact remaining blockers for Agent880.
