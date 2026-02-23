# PLAN — Board V6 Autonomous Scale (Write-Canary APPLY + Daily Ops Autopilot)

## Purpose
Scale the system from “fail-closed dry-run governance” to “bounded, reversible production apply” and then to “one-command daily operations” with multi-store robustness, while preserving single-truth integrity and preventing false-green validations.

This plan explicitly prioritizes:
- fail-closed behavior over speed
- deterministic evidence over subjective “looks good”
- minimal human time (0–5%): only secrets/logins when absolutely required

## Baseline (current merged state)
- V5 board (“prod-write-scale”) merged; no apply execution; evidence exists under exports/validation/board_v5_2026-02-22/.
- Risk-closure merged; scheduler authority, promotion minimum standard, and API assemble state-transition validation are locked.

If baseline differs on disk, STOP and reconcile first (fail-closed).

## Non-Negotiable Operating Rules
1) READCHECK first: verify repo clean, branch, and that required authority docs exist.
2) Single-truth ladder:
   - formulas/specs are canonical: docs/inventory/Master_Inventory_Rules_v8.md
   - operational truth is DB; exports/dashboards are derived only
   - no business math recomputation in UI layers
3) Fail-closed default:
   - missing/stale inputs => stop
   - “unknown” => stop (unless explicit override flag exists and is documented)
4) Writes are opt-in only:
   - dry-run default
   - apply requires BOTH env gate and explicit --apply
   - DB backup is mandatory before apply
5) Evidence is mandatory:
   - every phase has an evidence subfolder
   - board-level final gate transcript must exist as full_gates_green_final.md

## Phase List

### V6-T0 — Board V6 scaffolding + authority contracts
**Goal (measurable)**
- Create Board V6 plan+evidence docs and enforce them via tests so V6 cannot “silently drift.”

**Inputs**
- docs/ops/PROMOTION_MINIMUM_STANDARD.md
- docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md
- docs/WRITE_APPLY_RUNBOOK.md
- existing board naming conventions + evidence patterns in exports/validation/

**Outputs**
- docs/PLAN_BOARD_V6_AUTONOMOUS_SCALE_2026-02-22.md (this file)
- docs/OPS_ROLLOUT_EVIDENCE_BOARD_V6_AUTONOMOUS_SCALE_2026-02-22.md
- tests/test_board_v6_docs_contract.py
- exports/validation/board_v6_<YYYY-MM-DD>/V6-T0_PLAN_AUTHORITY/ (fail-first + green artifacts)

**Definition of Done**
Accepted as done only when:
- docs exist with required headings (Purpose, Phases, DoD, Gates, Rollback)
- docs contain NO placeholder tokens that violate promotion minimum standard (TBD/TODO)
- test_board_v6_docs_contract.py passes and fails when docs are missing/malformed
- docs lint passes

**Validation/Gates**
- bash scripts/lint_docs.sh
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_board_v6_docs_contract.py

**Rollback / Backout**
- git revert the V6-T0 commit(s)

**Stop-the-line**
- Any missing authority doc
- Any placeholder tokens in “active” plan/evidence docs
- Test does not fail when docs are removed (false-green contract)

---

### V6-D1 — Docs hygiene: remove/label stale schedule references
**Goal**
- Ensure operators cannot accidentally follow stale schedule timings from historical docs.

**Inputs**
- docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md (authority)
- config/com.example.kaspi-import.plist + config/com.example.kaspi-waybill-deadline.plist
- docs/DAILY_SOP.md, docs/DAILY_WORKFLOW.md, historical ops docs

**Outputs**
- Updated historical docs with a clear header: “ARCHIVED — see docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md”
- tests/test_docs_scheduler_authority_sweep.py (or equivalent)
- exports/validation/board_v6_<YYYY-MM-DD>/V6-D1_DOCS_HYGIENE/
  - rg outputs proving no active doc contradicts the authority schedule

**Definition of Done**
Accepted as done only when:
- An automated sweep detects and blocks “active” docs referencing timing that contradicts authority
- Historical references are explicitly labeled archived / non-authoritative
- Targeted test fails first (red), then passes (green) with evidence captured

**Validation/Gates**
- rg scan gate: rg -n "(16:05|16:00)" docs/ (must be empty OR only in ARCHIVED sections)
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_docs_scheduler_authority_sweep.py

**Rollback**
- git revert doc updates

**Stop-the-line**
- More than one “authority” schedule exists
- Sweep cannot deterministically distinguish archived vs active docs

---

### V6-W1 — Write Canary APPLY (bounded + reversible) + rollback proof
**Goal**
- Execute exactly ONE production-like DB write canary with full fail-closed controls:
  - bounded scope
  - mandatory DB backup
  - apply requires env gate + --apply
  - rollback is proven (restore backup + re-run gates)

**Inputs**
- docs/WRITE_APPLY_RUNBOOK.md
- docs/ops/WRITE_CANARY_PLAN_V1.md
- docs/ops/WRITE_CANARY_V6_APPLY_BOARD.md
- python3 scripts/validate_write_side_gating.py
- config/write_side_gating_manifest.yaml
- Candidate write script (choose ONE):
  - prefer deterministic “rebuild” script that is idempotent and local-DB only

**Outputs**
- exports/validation/board_v6_<YYYY-MM-DD>/V6-W1_WRITE_CANARY_APPLY/
  - preflight logs
  - DB backup path recorded (db/backups/app.db.pre_v6_canary_<ts>.sqlite)
  - dry-run transcript
  - apply transcript
  - post-apply invariants transcript
  - rollback proof transcript (restore backup + gates)
- docs/OPS_ROLLOUT_EVIDENCE_BOARD_V6_AUTONOMOUS_SCALE_2026-02-22.md updated with:
  - command lines
  - commit SHA
  - backup file path
  - rollback commands

**Definition of Done**
Accepted as done only when:
- Demonstrate fail-closed:
  - running without env gate must not mutate and must exit non-zero (or explicit “blocked”)
  - running with env gate but without --apply must not mutate and must exit non-zero (or explicit “blocked”)
- DB backup is created before apply and path is recorded
- Apply run completes within bounded scope limits (N <= configured threshold)
- Rollback is proven by restoring the backup and re-running minimum gates successfully
- Full gates are green after apply (before any promotion)

**Validation/Gates**
Pre-apply:
- python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
DB backup:
- mkdir -p db/backups && cp db/app.db db/backups/app.db.pre_v6_canary_<ts>.sqlite
Apply:
- ENABLE_<GATE>=1 python3 scripts/<write_script>.py --apply
Post-apply:
- repeat strict gates (same as above)
- bash scripts/check_no_db_tracked.sh

**Rollback**
- restore db/app.db from backup
- git revert canary commit(s) if code changes were required
- re-run minimum gates

**Stop-the-line**
- Any write path mutates in dry-run mode
- Any apply is possible with only one gate (env-only OR flag-only)
- Backup missing or not restorable
- Full gates not green immediately post-apply

---

### V6-O1 — Drift Pack SLO enforcement (fail-closed observability)
**Goal**
- Make drift packs decision-grade by enforcing freshness/completeness SLOs with a strict validator.

**Inputs**
- docs/ops/DRIFT_PACK_SLO_POLICY.md
- scripts/build_ops_drift_pack.py
- scripts/build_single_truth_drift_pack.py

**Outputs**
- scripts/validate_drift_pack_slo.py (or enhancement to existing validator)
- tests/test_validate_drift_pack_slo.py (fail-first cases included)
- exports/validation/board_v6_<YYYY-MM-DD>/V6-O1_DRIFT_PACK_SLOS/
  - red/green transcripts for stale/missing scenarios

**Definition of Done**
Accepted as done only when:
- Validator returns non-zero on stale/missing drift packs
- Validator returns zero only when within SLO
- Unit tests simulate stale/absent files and prove failure
- Daily ops orchestrator (V7-A1) consumes the validator (stop-line on breach)

**Validation/Gates**
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_drift_pack_slo.py
- python3 scripts/validate_drift_pack_slo.py --strict

**Rollback**
- git revert

**Stop-the-line**
- Any “warn and continue” behavior for SLO breaches (must stop)

---

### V7-A1 — Daily Ops Orchestrator v1 (dry-run default)
**Goal**
- Provide a single deterministic command that runs the daily ops chain end-to-end in dry-run:
  - scheduler validate-only
  - anchor health + ops status
  - import + waybill workflow preflight
  - strict waybill status report
  - drift pack build + SLO check
  - summary artifact emitted

**Inputs**
- docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md
- existing scripts:
  - scripts/run_strict_daily_preflight.py
  - scripts/check_anchor_health.py
  - scripts/ops_status.py
  - excel_ui/run_full_import.command
  - excel_ui/run_build_waybills.command
  - scripts/report_waybill_status.py --strict-stopline
  - drift pack builders + drift pack SLO validator (V6-O1)

**Outputs**
- scripts/run_kaspi_daily_ops.py
- docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md
- tests/test_run_kaspi_daily_ops_contract.py (headless + local)
- exports/validation/board_v7_<YYYY-MM-DD>/V7-A1_DAILY_ORCHESTRATOR/
  - deterministic summary.md
  - red/green runs proving fail-closed behavior

**Definition of Done**
Accepted as done only when:
- Orchestrator dry-run succeeds in headless fixture AND local repo run
- Orchestrator fails closed on:
  - stale anchors
  - scheduler contract mismatch
  - missing drift pack / breached SLO
  - waybill strict-stopline failure
- Orchestrator writes a summary artifact with explicit PASS/FAIL sections and exit code is non-zero on any hard failure

**Validation/Gates**
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_run_kaspi_daily_ops_contract.py
- (optional) run orchestrator: python3 scripts/run_kaspi_daily_ops.py --dry-run --as-of <date>

**Rollback**
- revert orchestrator commit(s)
- keep existing entrypoints unchanged (no silent scheduler rewires)

**Stop-the-line**
- Orchestrator triggers any apply by default
- Orchestrator returns zero on a known failure mode

---

### V7-S1 — Multi-store scale & resilience
**Goal**
- Make orchestrator multi-store by contract, while preserving fail-closed semantics and deterministic evidence.

**Inputs**
- Store roster authority in docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md
- core/integrations/kaspi_api_client.py
- scripts/download_waybills_api.py, ship_orders_api.py, build_daily_waybills.py

**Outputs**
- config/stores.yaml (or equivalent) with store definitions
- tests/test_store_roster_contract.py (roster must match authority doc)
- evidence under exports/validation/board_v7_<YYYY-MM-DD>/V7-S1_MULTI_STORE/
  - per-store artifacts
  - explicit stop-line if any store fails

**Definition of Done**
Accepted as done only when:
- Multi-store run produces per-store outputs and one consolidated summary
- Any store failure triggers non-zero exit unless an explicit allowlist override is set (default = stop)
- Rate-limit/backoff behavior is deterministic and tested

**Validation/Gates**
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_store_roster_contract.py
- targeted tests for kaspi client + waybill selection filters

**Rollback**
- revert config + multi-store changes

**Stop-the-line**
- Store roster drift between config and authority doc
- Any silent “skip store” behavior without explicit override

---

### V8-F1 — API-native Fact_Sales V16 (Excel elimination)
**Goal**
- Auto-generate Fact_Sales (V16 schema) from API-derived order entries and dims, eliminating Excel dependency for decision-grade sales facts.

**Inputs**
- docs/inventory/Sales_Data_Model_V16.md
- docs/inventory/Master_Inventory_Rules_v8.md
- existing order tables / dims / offer linkage validators

**Outputs**
- scripts/build_fact_sales_v16_from_api.py
- db migration (additive): fact_sales_v16 table (or export to parquet/csv under exports/)
- tests/test_fact_sales_v16_schema_and_reconciliation.py
- exports/validation/board_v8_<YYYY-MM-DD>/V8-F1_FACT_SALES/
  - reconciliation report (units, revenue, row counts)
  - mapping gaps report (must stop-line)

**Definition of Done**
Accepted as done only when:
- Output matches schema contract exactly
- Reconciliation to existing truth sources is within defined tolerance OR stops line with explicit mismatch report
- Missing mappings stop the build (fail-closed), with a machine-readable gaps file for follow-up

**Validation/Gates**
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_fact_sales_v16_schema_and_reconciliation.py
- strict end-to-end: python3 scripts/build_fact_sales_v16_from_api.py --since-days 14 --strict

**Rollback**
- additive migration only; can disable builder and drop derived table if needed
- revert commits

**Stop-the-line**
- Any attempt to recompute business math outside canonical rules
- Any mapping ambiguity resolved by “best effort” instead of explicit stop-line

## If attachments are missing — assumptions policy
- If an oracle pack/evidence reference is missing: continue, but record the assumption in the phase evidence summary and rely on repo state (git + tests) as truth.
- If an AUTHORITY doc is missing (workflow contract, promotion minimum standard, write apply runbook): STOP and recreate it before proceeding.
- If a contract test cannot be made deterministic: STOP and redesign the contract (fail-closed, no “fuzzy green”).

## Promotion / Merge Rules (applies to all phases)
- Do not claim completion unless:
  - all stated gates are green
  - evidence artifacts exist at the declared paths
  - PROMOTION_MINIMUM_STANDARD checklist is satisfied
  - rollback commands are documented and tested where required

## Global Gates
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

## Rollback (board-level)
1. Revert code/doc commits in reverse order:
   - `git revert <newest_sha> ... <oldest_sha>`
2. If V6-W1 apply was executed, restore the recorded backup:
   - `cp db/backups/app.db.pre_v6_canary_<timestamp>.sqlite db/app.db`
3. Re-run minimum recheck gates:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
   - `bash scripts/check_no_db_tracked.sh`

## Stop-line criteria
- Any gate/test failure that cannot be resolved within the same phase.
- Any write path reachable without BOTH env gate and `--apply`.
- Any contract validator that warns and continues where fail-closed behavior is required.
- Any authority doc/runtime mismatch not covered by tests in the same change set.
