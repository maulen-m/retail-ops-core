# PLAN_SHIPPED_TRUTH_CLOSEOUT_2026-03-03

## Purpose
Finish shipped-truth remediation end-to-end with fail-closed guarantees:
1) Shipped truth definition is unambiguous (contract),
2) Shipped truth validator is correct + tested + wired into strict chains,
3) BUSINESS_INSIDES shipped metrics are aligned (or explicitly blocked),
4) System Doctor is GREEN for as-of 2026-03-02 with required daily artifacts,
5) Evidence is decision-grade (transcripts + artifact packs + commit stamps),
6) Automation exists for ongoing audits (without slowing daily ops).

## Scope Boundaries (single-truth + fail-closed)
- Fail-closed: any missing inputs/secrets/artifacts => STOP with explicit exception artifacts.
- No “best effort” outputs labeled as decision-grade.
- Default is DRY-RUN / validate-only; any DB writes require:
  - explicit flag/env enable,
  - pre-write backup,
  - rollback plan + proof artifact.

## Phase List

### ST0 — READCHECK + Branch/Authority Lock
**Goal (measurable)**
- Establish single-truth refs and a reproducible baseline for remediation work.

**Inputs**
- Repo: `~/Docs/Autonomous_business`
- Branch/worktree: `codex/TASK-shipped-truth-remediation-v1` (or current active WT)
- Authority docs (read-only): `docs/inventory/Master_Inventory_Rules_v8.md`, `docs/00_START_HERE.md`, `docs/ARCHITECTURE.md`, `docs/validation/PO_CONTRACT.md`, `AGENTS.md`

**Outputs (exact paths)**
- Append-only journal: `<REPO>/claude/journal.md` (timestamped entries)
- Baseline stamp artifact:
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/baseline_git_state.json`
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/baseline_env_check.md`

**Definition of Done**
- Accepted as done only when:
  - `git status` is clean OR all dirty files are enumerated in `baseline_git_state.json`.
  - Authority paths are verified (including resolving doc path conflicts like `protocol/active/...` vs `docs/protocol/active/...`).

**Validation/Gates**
- `bash scripts/lint_docs.sh` PASS
- `bash scripts/check_no_db_tracked.sh` PASS
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q` PASS (fast smoke subset is acceptable here if full is too slow; full must pass by ST5)

**Rollback / Backout**
- N/A (no writes)

**Stop-the-line**
- Missing secrets required for shipped validator (fail immediately; do not degrade to partial mode silently).
- Any ambiguity in authority doc paths not documented.

---

### ST1 — Shipped Truth Contract Hardening
**Goal (measurable)**
- Contract explicitly forbids KASPI_DELIVERY-only counting for historical shipped parity and defines shipped_primary vs shipped_secondary.

**Inputs**
- `docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md`
- Any linked contracts updated by remediation:
  - `docs/validation/KASPI_ARCHIVE_API_PACK_CONTRACT.md`
  - `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
  - `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md` (or current canonical daily-ops contract)

**Outputs**
- Updated contract docs (same paths)
- Doc evidence:
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/contract_diff_summary.md`

**Definition of Done**
- Accepted as done only when:
  - Contract includes: shipped_primary/shipped_secondary definitions, required API states (`KASPI_DELIVERY` + `ARCHIVE`), strict behavior for completed days vs today-provisional.
  - Docs lint passes.

**Validation/Gates**
- `bash scripts/lint_docs.sh` PASS
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_shipped_truth_contract.py -q` PASS

**Rollback**
- `git revert <contract_commit>` if contract changes break lint/tests.

**Stop-the-line**
- Contract allows “tolerance” for completed-day primary parity (must remain 0% tolerance unless explicitly allowlisted with evidence).

---

### ST2 — Shipped Truth Validator Remediation (Last30)
**Goal (measurable)**
- Shipped truth validator passes strict for 2026-02-01..2026-03-01 and produces deterministic diff artifacts.

**Inputs**
- `scripts/validate_shipped_truth_crm_waybill.py`
- Inputs the validator reads:
  - Kaspi API (live), or validated archive pack mode
  - CRM workbook snapshots / archive runs
  - Waybill PDFs from archive runs

**Outputs**
- Last30 PASS artifacts:
  - `exports/validation/shipped_truth_crm_waybill/triage_last30_2026-03-02/2026-02-01_to_2026-03-01/summary.json`
  - `exports/validation/shipped_truth_crm_waybill/triage_last30_2026-03-02/triage_report.md`
- Closeout rerun artifacts (new run date):
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/last30_rerun/summary.json`
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/last30_rerun/report.md`

**Definition of Done**
- Accepted as done only when:
  - `python3 scripts/validate_shipped_truth_crm_waybill.py --since 2026-02-01 --until 2026-03-01 --strict` exits 0.
  - Artifacts include: daily+store summaries + mismatch IDs lists (even if empty) and a human-readable report.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_shipped_truth_crm_waybill.py -q` PASS
- `python3 scripts/validate_shipped_truth_crm_waybill.py --since 2026-02-01 --until 2026-03-01 --strict` PASS

**Rollback**
- `git revert <validator_commit>`; remove gate wiring if causing false failures (only if proven false-positive with evidence).

**Stop-the-line**
- Any code path that silently falls back to KASPI_DELIVERY-only for historical days.
- Any missing-token behavior that continues execution (must exit non-zero).

---

### ST3 — BUSINESS_INSIDES Shipped Alignment (Last30)  **(CURRENT STOP-LINE)**
**Goal (measurable)**
- BUSINESS_INSIDES shipped totals match shipped_primary truth for 2026-02-01..2026-03-01, per validator.

**Inputs**
- `scripts/validate_business_insides_shipped_truth.py`
- BUSINESS_INSIDES generator + data source:
  - `scripts/generate_business_insides.py`
  - `config/business_insides/BUSINESS_INSIDES_*.md` (latest snapshot)

**Outputs**
- Validation artifacts:
  - `exports/validation/business_insides_shipped_truth/2026-02-01_to_2026-03-01/summary.json`
  - `exports/validation/business_insides_shipped_truth/2026-02-01_to_2026-03-01/report.md`
  - If mismatches: `mismatch_days.csv` and `mismatch_order_ids.csv` (exact naming up to agent, but must be deterministic + documented)

**Definition of Done**
- Accepted as done only when:
  - `python3 scripts/validate_business_insides_shipped_truth.py --since 2026-02-01 --until 2026-03-01 --strict` exits 0.
  - BUSINESS_INSIDES shipped numbers are explicitly sourced from the canonical shipped_primary definition (documented in code + doc).
  - No mixing of truth sources: if BI uses API-derived shipped truth, it must be through a canonical module shared with the shipped validator (not by reading ad-hoc CSV exports as “truth”).

**Validation/Gates**
- New/updated unit tests prove:
  - BI shipped computation uses the same shipped_primary predicate as the contract.
  - Regression case: KASPI_DELIVERY-only undercount cannot pass.
- Required commands:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_business_insides_shipped_truth.py -q` PASS
  - `python3 scripts/validate_business_insides_shipped_truth.py --since 2026-02-01 --until 2026-03-01 --strict` PASS

**Rollback**
- If BI changes are wrong: revert BI generator changes and keep BI shipped blocked (N/A) rather than publish incorrect shipped totals.

**Stop-the-line**
- Any attempt to “paper over” mismatch by loosening strictness/tolerances for completed days.
- Any BI output marked decision-grade while validator is red.

---

### ST4 — Daily Artifact Completeness + Doctor GREEN (as-of 2026-03-02)  **(CURRENT STOP-LINE)**
**Goal (measurable)**
- `system_doctor` is GREEN for `--as-of 2026-03-02`, with required daily artifacts present.

**Inputs**
- `scripts/system_doctor.py`
- Daily artifacts contract/validator:
  - `scripts/validate_daily_ops_report.py`
  - `exports/daily/2026-03-02/daily_ops_report.json` (currently missing per agent report)

**Outputs**
- Daily report artifacts (must exist):
  - `exports/daily/2026-03-02/daily_ops_report.json`
  - `exports/daily/2026-03-02/daily_ops_report.md`
- Doctor evidence:
  - `exports/diagnostics/2026-03-02/system_health.json`
  - `exports/diagnostics/2026-03-02/system_health.md`
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/doctor_asof_2026-03-02/full_doctor_run.md`

**Definition of Done**
- Accepted as done only when:
  - `python3 scripts/validate_daily_ops_report.py --strict --path exports/daily/2026-03-02/daily_ops_report.json` exits 0.
  - `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-02` exits 0 (GREEN).
  - If the day truly cannot be generated (missing inputs), doctor remains RED with explicit exception output; do not mark complete.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_system_doctor_contract.py -q` PASS
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-02` PASS

**Rollback**
- If doctor was made green by weakening requirements: revert those changes immediately; missing daily report must remain a hard signal.

**Stop-the-line**
- Any “auto-generate placeholder daily report” behavior that makes doctor green without a real run (false-green).

---

### ST5 — Closeout Pack + Commit Stamp + PR-Ready Merge
**Goal (measurable)**
- Produce a decision-grade closeout pack: all strict gates green, commits stamped, and an Oracle pack index exists.

**Inputs**
- All modified scripts/docs/tests from ST1–ST4.

**Outputs**
- Evidence transcript:
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/full_gates_green_final.md`
- Open items list (must be empty or explicitly deferred):
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/open_stopline_items.md`
- Oracle pack (repo-local index + external copy steps documented):
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/oracle_pack_index.md`

**Definition of Done**
- Accepted as done only when:
  - Full strict suite is green:
    - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
    - `python3 scripts/validate_params.py --strict`
    - `python3 scripts/validate_single_truth_system.py`
    - `bash scripts/lint_docs.sh`
    - `python3 scripts/validate_shipped_truth_crm_waybill.py --since 2026-02-01 --until 2026-03-01 --strict`
    - `python3 scripts/validate_business_insides_shipped_truth.py --since 2026-02-01 --until 2026-03-01 --strict`
    - `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-02`
  - `full_gates_green_final.md` includes command lines + exit codes.

**Validation/Gates**
- Above commands are the gates.

**Rollback**
- If a regression is found post-merge: revert the merge commit; keep shipped truth gate in strict mode (do not disable without replacement).

**Stop-the-line**
- Any claim of completion without a GREEN `system_doctor --as-of 2026-03-02`.
- Any unstamped commit IDs in closeout index.

---

### ST6 — Automation + Scale (monthly full-range replay)
**Goal (measurable)**
- Move full-range replay (2024-06-06..today) into a scheduled/offline job that produces window summaries + exceptions, without blocking daily ops.

**Inputs**
- `scripts/validate_shipped_truth_crm_waybill.py` (range mode)
- Existing evidence pack patterns in `exports/validation/...`

**Outputs**
- Monthly run artifacts:
  - `exports/validation/shipped_truth_crm_waybill/monthly_replay_<YYYY-MM-DD>/window_summary.md`
  - `exports/exceptions/<YYYY-MM-DD>/exceptions.json` includes shipped_truth replay summary

**Definition of Done**
- Accepted as done only when:
  - Replay job runs deterministically and produces artifacts.
  - Daily ops gates remain scoped (e.g., last30) to avoid runtime explosion.
  - Any missing historical inputs are classified explicitly (INCONCLUSIVE) and create exceptions.

**Validation/Gates**
- Add a lightweight CI test that asserts:
  - replay command can run in `--validate-only` mode without secrets (skips live API and reports “missing secrets” as expected).
  - date-windowing logic has no gaps/overlaps.

**Rollback**
- Disable scheduler entry (not the validator) if runtime becomes unacceptable; keep manual replay ability.

**Stop-the-line**
- Any scheduling that silently stops producing artifacts.
- Any drift where daily gates start depending on full-range replay.

## If attachments are missing — assumptions policy
- If referenced files/artifacts are missing, proceed by:
  1) Marking the phase output as NOT COMPLETE,
  2) Emitting an exception artifact under `exports/exceptions/<date>/...`,
  3) Returning non-zero for strict gates (fail-closed),
  4) Never fabricating placeholder “green” artifacts.