# PLAN_SALES_OCEAN_DROP_ENGINE_CLOSURE_V3_2026-02-28

## Purpose
Establish a durable “ocean-drop” truth anchor workflow that fixes upstream sales-truth engine logic end-to-end,
so internal truth matches official Kaspi archive outputs without patching/overlays, while remaining fail-closed,
reproducible, and low-human-touch.

This plan explicitly closes remaining integrity gaps observed in the primary oracle packs:
- truth/reference isolation is present, but cycle order + status mapping + size propagation + anchor hash validation
  still leave risk of false-green and future drift.

## Context / Evidence (READCHECK)
Oracle packs reviewed:
- <ORACLE_ROOT>/Autonomous_business/2026-02-28/045052_TASK-000_sales-ocean-drop-truth-anchor-primary.md
- <ORACLE_ROOT>/Autonomous_business/2026-02-28/070606_TASK-000_sales-ocean-drop-engine-integrity-v2-primary-db-schemas.md

Known commits referenced in packs:
- dad67bc1631c8dd8507ce17bb1da0d9156015272 (sales: ocean-drop anchor parity + truth isolation)
- 3727128 (export: API-first historical ARCHIVE export + tests)
NOTE: v2 branch commit SHA for the new engine-integrity work must be captured in P0 (pack showed dirty git status).

## Phase List

### P0 — Freeze + Reproducibility Lock
**Goal (measurable)**
- Convert current working state into a reproducible commit (clean working tree) and rerun mandatory gates on that SHA.

**Inputs**
- Repo: <REPO_PATH>
- Branch/worktree: codex/TASK-sales-ocean-drop-engine-integrity-v2
- Existing artifacts referenced:
  - exports/validation/board_sales_ocean_drop_engine_integrity_v2_2026-02-28/full_gates_green_final.md

**Outputs**
- New commit SHA recorded in:
  - docs/PLAN_SALES_OCEAN_DROP_ENGINE_CLOSURE_V3_2026-02-28.md (this file)
  - claude/journal.md (append-only, timestamped)
- Freeze SHA (P0 baseline): `2eca780a380b252e111c3dce5633f83c3c25270f`
- Closure implementation SHA (P1-P5): `ebe6063767578fcc033e8592088931ca3e8619a7`
- Fresh evidence transcript:
  - exports/validation/board_sales_ocean_drop_engine_integrity_v3_2026-02-28/full_gates_green_final.md
- Fresh oracle pack:
  - <ORACLE_ROOT>/Autonomous_business/2026-02-28/<timestamp>_TASK-000_sales-ocean-drop-engine-closure-v3-primary-db-schemas.md

**Definition of Done**
Accepted as done only when:
- `git status --porcelain` is empty
- Commit SHA exists and is referenced in docs + journal
- All required gates are green and transcript path exists

**Validation/Gates**
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
- python3 scripts/validate_params.py --strict
- python3 scripts/validate_single_truth_system.py
- bash scripts/lint_docs.sh

**Rollback / Backout**
- If any gate fails, do not merge; keep changes on branch.
- If DB writes occur during later phases, require backup before apply.

**Stop-the-line**
- Dirty working tree after supposed “freeze”
- Missing transcript or missing commit SHA reference

---

### P1 — Correctness Fixes: Status + Size Propagation + Anchor Hash Validation
**Goal (measurable)**
- Remove known correctness hazards that can produce false-green parity or incorrect size/identity downstream.

**Inputs**
- scripts/rebuild_sales_fact_v2_from_kaspi_entries.py
- scripts/sync_order_size_overrides_from_ocean_drop.py
- core/sales/ocean_drop_anchor.py
- scripts/run_sales_truth_ocean_drop_cycle.py
- config/anchors/ocean_drop_sales_anchor.json

**Outputs**
- Code changes (paths):
  - scripts/rebuild_sales_fact_v2_from_kaspi_entries.py
  - scripts/run_sales_truth_ocean_drop_cycle.py
  - core/sales/ocean_drop_anchor.py
  - tests/ (new regression tests)
- New/updated artifacts:
  - exports/validation/sales_ocean_drop_parity/<as_of>/parity_report.json + .md
  - exports/daily/<as_of>/sales_truth_drift_report.json (+ optional md)

**Definition of Done**
Accepted as done only when:
1) Status mapping:
   - SHIPPED is NOT treated as DELIVERED in rebuild logic.
2) Size propagation:
   - If fact_orders_kaspi.assigned_size is present, sales_fact_v2.my_size uses it (preferred over my_size).
3) Anchor integrity:
   - Ocean drop file sha256 is computed and must match config/anchors/ocean_drop_sales_anchor.json; mismatch fails closed.
4) Cycle safety:
   - Parity/drift checks run after any rebuild (or parity runs both pre and post rebuild), so rebuild cannot introduce silent drift.

**Validation/Gates**
- Unit tests:
  - tests/test_rebuild_sales_fact_v2_status_mapping.py (new)
  - tests/test_rebuild_sales_fact_v2_size_prefers_assigned_size.py (new)
  - tests/test_ocean_drop_anchor_sha256_enforced.py (new)
  - tests/test_run_sales_truth_ocean_drop_cycle_orders_checks_after_rebuild.py (new)
- Runtime:
  - python3 scripts/run_sales_truth_ocean_drop_cycle.py --as-of 2026-02-26 --strict \
      --ocean-drop <path> --crm-archive-lookup <path>
  - parity_report.json: nonvolatile_mismatch_count == 0

**Rollback / Backout**
- Pure code changes: git revert.
- Any DB write step must create a backup under runtime/backups/ with timestamp before apply.

**Stop-the-line**
- Any mismatch outside volatility window
- Any sha256 mismatch between anchor registry and on-disk file
- Any rebuild alters sales truth but post-rebuild parity is not revalidated

---

### P2 — Engine Self-Sufficiency Gate (Proves “Not Patching”)
**Goal (measurable)**
- Prove the system can regenerate correct sales truth from internal raw Kaspi tables without using ocean-drop data inside truth.

**Inputs**
- db/app.db
- scripts/rebuild_sales_fact_v2_from_kaspi_entries.py
- scripts/validate_sales_truth_ocean_drop_parity.py

**Outputs**
- New validator script:
  - scripts/validate_sales_engine_self_sufficient.py
- Artifact:
  - exports/validation/sales_engine_self_sufficient/<as_of>/self_sufficient_report.json (+ md)

**Definition of Done**
Accepted as done only when:
- Validator copies DB to a temp file, wipes sales_fact_v2 in temp, rebuilds from raw orders/entries in temp,
  then runs parity vs ocean-drop and returns PASS (nonvolatile=0).
- This gate is wired into System Doctor strict chain.

**Validation/Gates**
- PYTEST test for validator (uses temp sqlite fixture)
- python3 scripts/validate_sales_engine_self_sufficient.py --as-of 2026-02-26 --strict \
    --ocean-drop <path> --crm-archive-lookup <path>

**Rollback / Backout**
- Validator uses temp DB only (no rollback needed).
- If implementing any “apply” mode later, require explicit env gate + backup + diff manifest.

**Stop-the-line**
- Self-sufficiency fails (means we are still “patching leakage” rather than fixing engine)

---

### P3 — Observability + Drift Canaries (Daily)
**Goal (measurable)**
- Daily drift detection artifacts exist, are deterministic, and block decision-grade outputs when red.

**Inputs**
- scripts/build_sales_truth_drift_report.py
- scripts/system_doctor.py

**Outputs**
- exports/daily/<as_of>/sales_truth_drift_report.json
- system_doctor includes drift report + parity + identity coverage in strict mode

**Definition of Done**
Accepted as done only when:
- Drift report says mismatch_days=0 for nonvolatile window
- System Doctor returns GREEN only when all sales truth checks pass

**Validation/Gates**
- python3 scripts/system_doctor.py --strict --as-of 2026-02-26 --project-root .

**Rollback / Backout**
- Code-only revert.

**Stop-the-line**
- Any “GREEN” when parity is failing (false-green)

---

### P4 — Ops Autopilot Integration
**Goal (measurable)**
- Daily ops run blocks downstream PO/cash decisions when sales truth is not decision-grade.

**Inputs**
- docs/ops/H5_DAILY_EXECUTION_RUNBOOK.md
- docs/validation/SALES_OCEAN_DROP_REFERENCE_CONTRACT.md
- scheduler entrypoints (existing daily orchestrator)

**Outputs**
- Runbook update to include:
  - required sales parity gates
  - “volatile window” semantics (last 14 days not decision-grade)
- Exceptions emitted on failures:
  - exports/exceptions/<as_of>/exceptions.json (if using existing exception stream)

**Definition of Done**
Accepted as done only when:
- Runbook explicitly states the stop-the-line conditions.
- A failed parity run prevents BUSINESS_INSIDES / decision outputs from being marked green.

**Validation/Gates**
- Contract suite + System Doctor strict.

**Rollback / Backout**
- Docs revert.
- Scheduler job can be switched back to validate-only mode if instability occurs.

**Stop-the-line**
- Any unattended run produces decision-grade artifacts while parity is RED

---

### P5 — Scale + Maintenance (Anchor Rotation)
**Goal (measurable)**
- Ocean-drop reference can be refreshed safely (weekly/monthly), with stable checksum + provenance.

**Inputs**
- scripts/export_kaspi_archive_history.py (existing exporter)
- config/anchors/ocean_drop_sales_anchor.json

**Outputs**
- A standard “refresh protocol”:
  - new anchor file in the Sales_archive mirror
  - updated registry sha256 and as_of_end
  - archived previous anchor registry snapshot

**Definition of Done**
Accepted as done only when:
- Refresh produces reproducible artifacts and parity remains PASS.
- Old anchor remains available for audit.

**Validation/Gates**
- sha256 match enforced
- parity PASS on new anchor for nonvolatile window

**Rollback / Backout**
- Revert registry to previous anchor snapshot and rerun parity.

**Stop-the-line**
- Anchor refresh without checksum match or without archived backup

## If attachments are missing — Assumptions Policy
Fail-closed defaults:
- If ocean-drop CSV path is missing/unreadable OR sha256 mismatch: STOP (no apply, no green).
- CRM archive lookup is optional for parity-only, but required for size/identity sync steps:
  - If CRM lookup missing: run parity-only and mark identity/size sync as SKIPPED; System Doctor strict should fail
    if identity coverage is required for decision-grade mode.
