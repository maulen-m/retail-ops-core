# Agent 57 - Option B Current-Baseline Temp Proof + Validator Hardening

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_57_option_b_current_baseline_temp_proof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_57_evidence/`

## Mission

Execute WS3 of the CodeCaptain RED recovery plan.

Use the current May 6 production DB/workbook boundary as the baseline candidate, then prove the Option B replay on a copied temp DB only. Also harden the C3 source-freshness validator so explicit `--as-of` validation cannot silently validate a different stored as-of window.

This is not Agent 54. This is not production apply. This is the proof that tells the orchestrator whether we can safely write a new readiness contract next.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-06/120135_TASK-000_codecaptain-proscope-system-review/answer/Code_Captain_2026-05-06_12_32_00_GMT+5.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54a_may6_freshness_asof_preflight_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_option_b_agent31_production_safe_wrapper_temp_proof_after_52_green_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/AGENT54_PRODUCTION_APPLY_READINESS_CONTRACT.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_55_drift_forensics_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_56_source_freshness_repair_analysis_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/replay/commands_run.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/validator_exit_summary.tsv`

## Write Boundary

Allowed repo writes:

- source-freshness validator tests under `tests/**`;
- source-freshness validator implementation under `core/ops/policy_registry_c3.py` and/or `scripts/validate_policy_source_freshness.py`;
- minimal supporting code only if needed to make the validator contract executable.

Allowed evidence/temp writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_57_option_b_current_baseline_temp_proof_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_57_evidence/**`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not edit `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not write to external repos.
- Do not call live APIs, browser sessions, Kaspi, Meta, bank, or marketing systems.
- Do not ask the owner for the old Agent 54 authorization phrase.
- Do not launch Agent 54 or prepare a production apply.
- Do not widen into Option C automation.
- Do not overwrite or delete another agent's evidence.

You are not alone in the codebase. Do not revert unrelated changes. If you discover conflicting local edits in files you need, stop and explain the conflict in the closeout.

## Required Sequence

### 1. READCHECK

Write a READCHECK section into the closeout with the files read, assumptions, and exact write boundary.

### 2. Current Baseline Preflight

Record read-only evidence for:

- current local time;
- `db/app.db` SHA-256, mtime, size, integrity, lsof status, WAL/SHM sidecars;
- `excel_ui/SALES_KSP_CRM_V3.xlsx` SHA-256, mtime, size;
- git status for protected DB/workbook paths;
- current policy version and relevant source-freshness row snapshot.

If production DB is actively held open, WAL/SHM sidecars are present, or integrity fails, stop `RED`.

### 3. Workbook Sanity Check

Perform a read-only sanity check on the May 6 CRM workbook append mentioned by Agent 55:

- verify the current workbook dimensions and modified timestamp;
- inspect available logs/backups enough to determine whether the 69 appended rows look like intentional scheduler intake or an obvious duplicate/partial append;
- do not edit the workbook.

This does not need to become a full workbook-forensics incident unless you find evidence of duplicate/partial append risk. If risk remains ambiguous but not contradictory, close `YELLOW` with the exact next workbook-forensics task.

### 4. Tests First: Source-Freshness As-Of Contract

Before changing implementation, add focused failing tests for the validator bug Agent 56 identified.

Minimum expected contract:

- when `validate_policy_source_freshness(db_path, as_of="YYYY-MM-DD")` is called, it must validate source rows for that requested `as_of_date`, not silently validate the latest stored row from another date;
- if a required source has no row for the requested as-of, the error must explicitly name the source and requested as-of;
- if the requested as-of row exists but is blocking, the error must explicitly name the source, requested as-of, status, and publication block;
- `as_of=None` should preserve the existing latest-row behavior unless the owning docs demand otherwise;
- CLI JSON from `scripts/validate_policy_source_freshness.py --json` must include at least `ok`, `errors`, `db_path`, `db_sha256`, `requested_as_of`, and `strict`.

Keep the implementation small and deterministic. Do not rewrite the whole C3 registry.

### 5. Implement Validator Hardening

Implement the smallest code change that makes the tests pass and makes the CLI evidence explicit. Preserve existing call sites.

Run at least:

```bash
pytest -q tests/test_policy_registry_c3_contract.py tests/test_policy_materialization_c3.py
python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --strict --json
```

The production validation command is read-only. It may fail before temp proof; if it fails, capture JSON and continue only if the failure is the expected current-baseline/blocker state and not a validator regression.

### 6. Current-Baseline Temp DB Proof

Create a fresh temp DB copy under the Agent57 evidence folder from the current production DB. Record the source DB SHA before and after copy.

Replay the Agent53 Option B full replay sequence on the temp DB only, adapting:

- temp DB path;
- output folders;
- backup folders;
- run IDs;
- expected pre-SHA values to the current May 6 baseline.

Use Agent53's `replay/commands_run.md` and closeout as the template. Do not skip validators. If a command is intentionally expected to fail as a known dry-run limitation, document why and match Agent53's accepted behavior.

The target as-of contract remains `2026-05-04` unless an owning spec or CodeCaptain document explicitly says to advance the as-of. Because the baseline contains May 6 scheduler intake, explicitly prove or document whether the replay filters prevent post-as-of leakage into the `2026-05-04` decision surface.

### 7. Required Final Gates

On the temp DB, run and record:

```bash
sqlite3 -readonly <temp_db> 'PRAGMA integrity_check;'
python3 scripts/validate_operational_stock_integration_gates.py --db <temp_db>
python3 scripts/validate_policy_source_freshness.py --db <temp_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_order_cashflow_coverage.py --db <temp_db>
python3 scripts/validate_cashflow_invariants.py --db <temp_db>
python3 scripts/validate_cashflow_actual_model_separation.py --db <temp_db>
python3 scripts/validate_ads_sidecar_readiness.py --db <temp_db>
python3 scripts/validate_ads_offer_universe_coverage.py --db <temp_db>
python3 scripts/validate_ads_spend_reality.py --db <temp_db>
```

Also run the focused validator tests and any focused wrapper/replay tests touched by this lane.

### 8. Production Untouched Proof

At closeout, re-check production:

- DB/workbook SHA-256;
- DB integrity;
- git status for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`;
- no WAL/SHM sidecars.

Production must remain untouched by this lane. If the production SHA changes because a scheduler runs while you work, do not call it your write; capture it as live drift and close `YELLOW` unless you can still prove the temp baseline boundary and next action safely.

## Success Criteria

Closeout must include:

- standalone `Gate: GREEN/YELLOW/RED`;
- READCHECK;
- exact baseline DB/workbook SHAs;
- workbook sanity result;
- tests added and tests run;
- validator contract changes;
- temp DB path and SHA;
- replay command/evidence summary;
- final validator/gate matrix;
- production untouched proof;
- recommendation: whether WS4 new readiness contract can be launched, or what blocker remains.

## Gate Semantics

`GREEN`:

- validator as-of bug is fixed with tests;
- current-baseline temp proof passes required gates for `2026-05-04`;
- production DB/workbook are not mutated by this lane;
- closeout clearly recommends launching WS4 readiness contract.

`YELLOW`:

- validator is fixed but temp proof is blocked with a specific, repairable issue;
- workbook sanity is ambiguous but no destructive risk is found;
- scheduler drift changes production during the run but temp evidence remains usable only after a reanchor.

`RED`:

- production DB/workbook mutation occurs from this lane;
- production integrity/lock/sidecar state is unsafe;
- validator cannot be made as-of safe;
- temp proof is unreproducible or hides a blocking gate;
- any result tries to authorize Agent 54 or production apply directly.
