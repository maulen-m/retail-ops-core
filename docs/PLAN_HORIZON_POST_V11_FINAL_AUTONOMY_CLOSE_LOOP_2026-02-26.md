# PLAN_HORIZON_POST_V11_FINAL_AUTONOMY_CLOSE_LOOP_2026-02-26

## Purpose
Create a single fail-closed evaluation + execution ladder that:
1) diagnoses “what’s wrong” from any entrypoint (PO / inventory / cashflow / API / docs),
2) prioritizes fixes by capital-risk and operational frequency,
3) closes the loop with staged write canaries (DB-only → prod DB → bounded live API),
4) achieves the repo completion target: 14 consecutive daily cycles with all hard gates green, with <5% human time.

## Branch Execution Scope
- Branch: `codex/TASK-horizon-post-v11-final-autonomy-close-loop`
- Implemented in this execution:
  - H0 baseline doctor snapshot
  - H1 exceptions-driven closure loop (playbook + triage + allowlist contract)
  - H2 as-of consistency validator + system-doctor enforcement
  - H3 canary ladder graduation framework (`db_only` and `prod_db` modes)
- Deferred by contract:
  - H4 live Kaspi canary writes (optional, OFF by default)
  - H5 long-running operational proving window (requires multi-day execution)

## Current Baseline (what already exists on main)
- System Doctor entrypoint + runbook + contract tests:
  - scripts/system_doctor.py
  - docs/ops/SYSTEM_DOCTOR_RUNBOOK.md
- Domain scorecards + truth drift:
  - scripts/build_domain_scorecards.py
  - exports/daily/<YYYY-MM-DD>/*_scorecard.json
- Daily ops performance budgets:
  - scripts/build_daily_ops_timings.py
  - docs/ops/DAILY_OPS_PERFORMANCE_BUDGETS.md
  - exports/perf/<YYYY-MM-DD>/daily_ops_timings.json
- Endgame autonomy components:
  - scripts/run_daily_autopilot.py (exceptions + daily report artifacts)
  - scripts/validate_cashfloor.py (cashfloor gate)
  - scripts/translate_transfer_ledger_to_cashflow.py (ledger translation)
- Close-loop scaffolding:
  - scripts/resolve_as_of_date.py (as-of authority)
  - scripts/validate_exceptions_schema.py (exceptions schema contract)
  - scripts/run_write_canary.py (DB-only canary framework)
  - scripts/validate_kaspi_state_transition.py (state transition contract)

## Phase List

### Phase H0 — Baseline “Doctor Snapshot” (triage foundation)
**Goal (measurable)**
- Produce a fresh, reproducible baseline run that can be used to compare every future change.
- Ensure artifacts exist for: system health, exceptions, scorecards, timing, weekly health.

**Inputs**
- Repo scripts + contracts:
  - scripts/system_doctor.py
  - scripts/run_daily_autopilot.py
  - scripts/build_domain_scorecards.py
  - scripts/build_daily_ops_timings.py
  - scripts/build_weekly_health_scorecard.py

**Outputs**
- Evidence folder:
  - exports/validation/horizon_h0_<YYYY-MM-DD>/baseline_run_1.md
  - exports/validation/horizon_h0_<YYYY-MM-DD>/baseline_run_2.md
  - exports/validation/horizon_h0_<YYYY-MM-DD>/baseline_comparison.md
  - exports/validation/horizon_h0_<YYYY-MM-DD>/environment_snapshot.json
- Required artifacts (as-of authoritative day):
  - exports/diagnostics/<AS_OF>/system_health.json
  - exports/exceptions/<AS_OF>/exceptions.json
  - exports/daily/<AS_OF>/{po,inventory,cashflow}_scorecard.json
  - exports/perf/<AS_OF>/daily_ops_timings.json
  - exports/health/weekly/<YYYY-W##>/weekly_health_scorecard.json

**Definition of Done**
Accepted as done only when:
- baseline_run_1 and baseline_run_2 are both green,
- baseline_comparison shows parity on required outputs,
- system_doctor --strict PASS, and artifacts listed above exist.

**Validation/Gates**
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
- python3 scripts/run_contract_suite.py --fixture small
- python3 scripts/validate_single_truth_system.py
- bash scripts/lint_docs.sh
- bash scripts/check_no_db_tracked.sh
- python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>

**Rollback / backout**
- git revert any merge commits for this phase; re-run H0 gates.

**Stop-the-line**
- Any missing required artifact path.
- Any failure in system_doctor --strict.
- Any attempt to “fix” by loosening gates without a contract/test change + evidence.

---

### Phase H1 — “What’s still wrong” closure loop (exceptions-driven)
**Goal (measurable)**
- Reduce critical exceptions to zero (or explicitly reclassify with contract + justification).
- Ensure each domain (PO/inventory/cashflow/API/docs) has a crisp “red means stop” signal.

**Inputs**
- exports/exceptions/<AS_OF>/exceptions.json
- docs/authority/INDEX.md (active authority map)
- Domain contracts listed in docs/authority/INDEX.md

**Outputs**
- docs/ops/EXCEPTION_PLAYBOOK.md (new): mapping from exception_code → owner_action → safe remediation.
- scripts/triage_exceptions.py (new): deterministic summary from exceptions.json → triage markdown.
- exports/exceptions/<AS_OF>/exceptions_triage.md (new).

**Definition of Done**
Accepted as done only when:
- triage tool exists + contract-tested,
- every exception_code in schema maps to a remediation step in EXCEPTION_PLAYBOOK.md,
- critical exceptions are either:
  - eliminated by fixes, OR
  - explicitly allowlisted in a contract doc with tests (never silent).

**Validation/Gates**
- New contract test: tests/test_exceptions_playbook_contract.py
- Existing: validate_params --strict, pytest full, system_doctor --strict, lint_docs.

**Rollback / backout**
- Revert playbook/triage changes; artifacts are additive only.

**Stop-the-line**
- Introducing “manual tribal knowledge” outside the playbook.
- Any exception reclassification without contract + test.

---

### Phase H2 — As-of authority everywhere (eliminate date skew)
**Goal (measurable)**
- Guarantee every “daily” artifact uses the same AS_OF resolution path, and tooling refuses mixed-date outputs.

**Inputs**
- scripts/resolve_as_of_date.py
- scripts that write exports/* daily artifacts (doctor, scorecards, autopilot, cashflow, ledger translation)

**Outputs**
- docs/ops/AS_OF_DATE_AUTHORITY_CONTRACT.md updated with:
  - precedence rules (explicit --as-of > resolved latest complete > fail)
  - “no mixed-date writes” rule
- New validator:
  - scripts/validate_as_of_consistency.py
- Evidence:
  - exports/validation/horizon_h2_<YYYY-MM-DD>/asof_consistency_replay.md

**Definition of Done**
Accepted as done only when:
- validate_as_of_consistency passes on a clean run,
- system_doctor enforces as-of consistency (fails closed when violated),
- at least one RED→GREEN evidence trail exists in exports/validation.

**Validation/Gates**
- New tests:
  - tests/test_as_of_consistency_contract.py
- Existing full gate chain + system_doctor strict.

**Rollback / backout**
- Revert changes; date consistency rules must never be weakened without replacing with stronger evidence.

**Stop-the-line**
- Any tool writing artifacts to a date different from resolved AS_OF without explicit override.

---

### Phase H3 — Canary ladder graduation (DB-only → prod DB)
**Goal (measurable)**
- Add a *reversible* production-DB canary mode (bounded, backed up, validated), while keeping defaults safe:
  - dry-run default,
  - explicit env enable,
  - backup required,
  - post-apply gates must be green.

**Inputs**
- scripts/run_write_canary.py
- docs/ops/WRITE_CANARY_RUNBOOK_V2.md
- DB: db/app.db

**Outputs**
- scripts/run_write_canary.py updated with modes:
  - --mode db_only (existing behavior)
  - --mode prod_db (new; requires ENABLE_PROD_DB_CANARY_WRITE=1)
- docs/ops/WRITE_CANARY_RUNBOOK_V3.md (new) describing prod_db mode and rollback steps.
- Contract tests:
  - tests/test_write_canary_prod_db_gating_contract.py
  - tests/test_write_canary_prod_db_backup_required.py
- Evidence:
  - exports/validation/horizon_h3_<YYYY-MM-DD>/prod_db_canary_dry_run.md
  - exports/validation/horizon_h3_<YYYY-MM-DD>/prod_db_canary_apply.md
  - exports/validation/horizon_h3_<YYYY-MM-DD>/prod_db_canary_rollback_proof.md

**Definition of Done**
Accepted as done only when:
- prod_db mode cannot execute unless:
  - ENABLE_PROD_DB_CANARY_WRITE=1 and
  - explicit --apply and
  - backup created and recorded
- Apply run is demonstrated on a bounded reversible action, then rollback proof succeeds (restored DB passes gates).
- Full gate chain is green after rollback proof.

**Validation/Gates**
- Full required gates + system_doctor --strict.
- Additionally:
  - “apply” evidence must include:
    - backup path
    - post-apply validation transcript
    - rollback transcript

**Rollback / backout**
- Always: restore db/app.db from the recorded backup.
- Code rollback: git revert.

**Stop-the-line**
- Any write to db/app.db without a backup.
- Any canary apply that cannot be rolled back deterministically.

---

### Phase H4 — Live Kaspi canaries (bounded + state transition proof; OPTIONAL / last)
**Goal (measurable)**
- Demonstrate bounded live API “canary writes” only after prod_db canaries are proven.
- Each write must prove state transition, not HTTP success.

**Inputs**
- scripts/validate_kaspi_state_transition.py
- Kaspi client integration scripts (existing)
- Store credentials (human only supplies secrets)

**Outputs**
- docs/ops/KASPI_LIVE_WRITE_CANARY_RUNBOOK.md (new)
- scripts/run_kaspi_live_write_canary.py (new) with:
  - dry-run default
  - explicit ENABLE_LIVE_KASPI_WRITE=1 + --apply required
  - --order-ids allowlist (mandatory)
  - per-order state-transition verification
- Contract tests using mocks/fixtures:
  - tests/test_kaspi_live_write_canary_gating.py
  - tests/test_kaspi_live_write_canary_state_transition_mock.py
- Evidence:
  - exports/validation/horizon_h4_<YYYY-MM-DD>/dry_run.md
  - exports/validation/horizon_h4_<YYYY-MM-DD>/apply_one_order.md (only if explicitly authorized)

**Definition of Done**
Accepted as done only when:
- Code cannot write live without explicit env + --apply + allowlisted order IDs.
- State transition proof is recorded (before/after status) for each allowlisted order.
- No new critical exceptions are introduced by the canary run.

**Validation/Gates**
- Full gates + system_doctor strict + kaspi state transition validator.
- “apply” run must be opt-in and separately approved (human time is limited to the approval action).

**Rollback / backout**
- No true rollback for external side effects; mitigation is bounded scope + pre-validation + post-validation.
- If unexpected change occurs: stop automation, document incident, and revert code changes.

**Stop-the-line**
- Any attempt to expand scope beyond explicit order allowlist.
- Any failure to verify state transition after a write.

---

### Phase H5 — Operational proving run (“Done means done”)
**Goal (measurable)**
- Achieve the completion criterion:
  - 14 consecutive daily cycles complete with all hard gates green,
  - unattended except structured exception handling,
  - decision-grade reproducible artifacts.

**Inputs**
- Daily scheduler jobs + pinned runtime + secrets configured by human.
- system_doctor strict, daily autopilot outputs, weekly scorecard.

**Outputs**
- A date window folder of daily artifacts (14 consecutive days) and a weekly scorecard trend.
- Operational proving contract:
  - `docs/ops/H5_OPERATIONAL_PROVING_RUN_CONTRACT.md`
- A final evidence doc:
  - docs/OPS_EVIDENCE_14_DAY_GREEN_STREAK_<START>_TO_<END>.md

**Definition of Done**
Accepted as done only when:
- 14-day green streak is shown by artifact evidence and green-streak tracker output.
- Human time stays within the stated cap (secrets/logins + approvals only).

**Validation/Gates**
- Daily: system_doctor --strict PASS
- Weekly: weekly_health_scorecard PASS
- No “yellow” releases (red = stop).

**Rollback / backout**
- N/A (operational proving). If failures occur: stop-the-line, fix root cause under a new board, resume streak.

**Stop-the-line**
- Any day with critical exceptions or failed hard gates.
- Any evidence gap (missing artifacts for a day).

## If attachments are missing — assumptions policy
- If a referenced doc/script/test is missing locally, treat it as a STOP-THE-LINE unless:
  1) the active authority index (docs/authority/INDEX.md) marks it as archived/non-authoritative, OR
  2) a newer authoritative replacement is found and linked in INDEX.md.
- If commits/PR SHAs are missing from evidence, proceed with file-path-based truth, and record the discrepancy in:
  - docs/ops/KNOWN_TRUTH_GAPS.md (new), with a remediation task and contract test if applicable.
