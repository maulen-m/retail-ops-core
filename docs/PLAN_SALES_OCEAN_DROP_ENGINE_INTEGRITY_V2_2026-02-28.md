# PLAN_SALES_OCEAN_DROP_ENGINE_INTEGRITY_V2_2026-02-28

## Purpose
Lock a single external “ocean drop” sales reference (official Kaspi archive rows) as a **validation anchor** and use it to repair upstream logic so internal truth (DB-based) matches the anchor **without** reference overrides, manual patching, or BI-layer fixes.

Non-negotiables (fail-closed):
- Published truth must be computed from internal ingest + DB only; reference datasets must never be unioned into truth views. (Truth isolation.)
- Reference datasets may be used only for:
  1) Validation (parity, drift)
  2) Deriving mapping/override tables via explicit gated writes
- No “warn-only” behavior in strict mode for drift.

## Inputs (authoritative priority)
1) Ocean drop mapped CSV (official Kaspi archive + mappings):
   - Example: `<EXTERNAL_SALES_ARCHIVE_ROOT>/mapped_data/ArchiveOrders_ALL_STORES_mapped_20260228_025856.csv`
2) Official Kaspi archive history raw (API extracted):
   - Example: `<EXTERNAL_SALES_ARCHIVE_ROOT>/kaspi_archive_history_<window>/ArchiveOrders_ALL_STORES.csv`
3) CRM shipped archive (NOT authoritative for totals; lookup only for sku_key + MY_SIZE):
   - Example: `<EXTERNAL_SALES_ARCHIVE_ROOT>/Csv_converted_22.2.26/Archive_sales_normalized_backfilled_22.2.26.csv`
4) Repo DB (canonical truth store): <REPO_PATH>/runtime/app_db.sqlite (or configured DB)

## Outputs (artifacts + exact paths)
- Updated/added scripts under:
  - scripts/
- Updated/added tests under:
  - tests/
- Daily/validation artifacts under:
  - exports/validation/...
  - exports/daily/<as_of>/...
- Rollout evidence transcripts:
  - exports/validation/board_sales_ocean_drop_engine_integrity_v2_<YYYY-MM-DD>/full_gates_green_final.md
- Updated docs/contracts:
  - docs/validation/...
  - docs/ops/...

## Phase List

### P0 — Promote + Freeze Ocean-Drop Anchor Contract
**Goal (measurable)**
- Ensure current ocean-drop truth-anchor implementation is promotable and immutable as a baseline.

**Inputs**
- Branch: codex/TASK-sales-ocean-drop-truth-anchor (HEAD dad67bc...)
- Oracle pack: `<ORACLE_ROOT>/Autonomous_business/<date>/045052_TASK-000_sales-ocean-drop-truth-anchor-primary.md`

**Outputs**
- (If not yet merged) PR + merge commit on main/master
- Updated docs entry:
  - docs/validation/SALES_OCEAN_DROP_REFERENCE_CONTRACT.md (no changes unless gaps found)
- Anchor registry file:
  - config/anchors/ocean_drop_sales_anchor.json (path + sha256 + as_of_end + created_at)

**Definition of Done**
Accepted as done only when:
- Full gate chain is green on the merge commit.
- Anchor registry file exists and strict scripts can read it.
- Oracle pack rebuilt for merged state.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

**Rollback / Backout**
- `git revert <merge_sha>` + rerun gates.

**Stop-the-line**
- Any attempt to reintroduce reference override into truth views.

---

### P1 — Safer Repair Apply (Delta, Not Wipe)
**Goal (measurable)**
- Convert ocean-drop apply from “delete-and-replace by date-range” to a safe **delta apply** that only inserts/updates the minimal set required for parity.
- Deletions are forbidden by default.

**Inputs**
- scripts/build_ocean_drop_reference_snapshot.py
- Parity diffs: exports/validation/sales_ocean_drop_parity/<as_of>/diff_*.csv

**Outputs**
- Script enhancements:
  - scripts/build_ocean_drop_reference_snapshot.py
    - `--apply-delta` (default when --apply is used)
    - `--apply-replace` (old behavior) requires TWO env gates:
      - ENABLE_OCEAN_DROP_APPLY=1 AND ENABLE_OCEAN_DROP_DELETE=1
    - `--dry-run-diff` always produces a deterministic “plan” file
- New artifacts:
  - exports/validation/sales_ocean_drop_parity/<as_of>/apply_plan.json
  - exports/validation/sales_ocean_drop_parity/<as_of>/apply_plan.md
- Tests:
  - tests/test_ocean_drop_apply_delta.py

**Definition of Done**
Accepted as done only when:
- Delta apply can bring parity to PASS on a known fixture without deleting unrelated rows.
- Replace apply cannot run unless both env gates are present.
- Apply plan always enumerates affected rows (insert/update/delete counts).

**Validation/Gates**
- Unit tests for delta planning & application.
- Parity validator:
  - `python3 scripts/validate_sales_truth_ocean_drop_parity.py --strict ...`
- Full suite + strict params.

**Rollback**
- Restore DB from backup created during apply
- Revert commit and rerun parity.

**Stop-the-line**
- Any apply mode that deletes rows without explicit second gate + explicit plan file.

---

### P2 — Upstream Engine Fix (Build Internal Sales Facts From Order Entries + Status Change Date)
**Goal (measurable)**
- Internal sales facts (`sales_fact_v2`) are rebuilt from internal order/entry sources (Kaspi API → DB), matching ocean-drop parity **without running --apply**.

**Inputs**
- Kaspi API client constraints: 14-day window; entries endpoint for line items.
- Existing exporter: scripts/export_kaspi_archive_history.py (or internal DB tables populated by sync).
- Grain requirements: order line (order_id × sku_id × store_code). (Per V16-style contracts.)

**Outputs**
- One of:
  - New builder: scripts/rebuild_sales_fact_v2_from_kaspi_entries.py
  - Or refactor existing ingest pipeline to produce sales_fact_v2 deterministically.
- New/updated internal raw tables if missing:
  - fact_orders_kaspi (order headers)
  - fact_order_entries_kaspi (line items)
  - status history / status_change_date capture (if not present)
- Tests:
  - tests/test_sales_fact_v2_builder_grain.py
  - tests/test_sales_fact_v2_sale_date_semantics.py

**Definition of Done**
Accepted as done only when:
- On a clean DB (or isolated test DB), rebuild produces parity PASS vs the ocean drop for a fixed as_of date.
- Parity PASS requires no reference override and no ocean-drop apply.
- Multi-line orders produce correct units (sum of entries) and no duplicate key collisions.

**Validation/Gates**
- `python3 scripts/validate_sales_truth_ocean_drop_parity.py --strict ...` (PASS)
- Targeted builder tests + full suite
- Strict doctor chain:
  - `python3 scripts/system_doctor.py --strict --as-of <day>`

**Rollback**
- DB restore from pre-rebuild backup
- Code revert.

**Stop-the-line**
- Any solution that computes published truth directly from the ocean-drop file (validation-only boundary violation).

---

### P3 — Observability + Drift Autopilot Wiring
**Goal (measurable)**
- Daily drift detection becomes a hard gate in strict mode: last-14-days parity is checked automatically and blocks decision-grade artifacts on drift.

**Inputs**
- scripts/system_doctor.py strict chain
- H5 proving contract/runbook
- Ocean drop slice source (API-export incremental mode or existing exporter with --since/--until)

**Outputs**
- scripts/build_sales_truth_drift_report.py
- exports/daily/<as_of>/sales_truth_drift_report.{json,md}
- exceptions integration:
  - exports/exceptions/<as_of>/exceptions.json includes drift blockers

**Definition of Done**
Accepted as done only when:
- Drift report runs inside strict chain daily.
- Any drift beyond volatility tolerance fails with non-zero exit and is recorded in exceptions.

**Validation/Gates**
- Targeted tests for drift builder + wiring
- `python3 scripts/system_doctor.py --strict ...` (PASS)

**Rollback**
- Revert code; rerun strict chain.

**Stop-the-line**
- Warn-only drift behavior in strict mode.

---

### P4 — SKU + Size Identity Convergence (Minimize Human Time)
**Goal (measurable)**
- Deterministic `sku_key` coverage and accurate clothes `MY_SIZE` in delivered rows, using:
  - derived mapping tables from ocean drop (explicit-gate)
  - CRM archive lookup only as secondary evidence (explicit-gate)

**Inputs**
- Ocean drop mapped CSV (includes mapping confidence fields)
- dim_kaspi_article_map
- CRM lookup CSV

**Outputs**
- scripts/sync_dim_kaspi_article_map_from_ocean_drop.py (dry-run default; apply gate)
- scripts/sync_order_size_overrides_from_ocean_drop.py (dry-run default; apply gate)
- Validator:
  - scripts/validate_no_missing_identity_in_delivered_window.py
- Reports:
  - exports/validation/identity_coverage/<as_of>/...

**Definition of Done**
Accepted as done only when:
- For the reference range:
  - 0 delivered rows with empty sku_key
  - clothes rows have MY_SIZE populated when available in ocean drop / CRM lookup
- Validator fails if identity coverage regresses.

**Validation/Gates**
- `python3 scripts/validate_no_missing_identity_in_delivered_window.py --strict ...`
- Full suite + strict params

**Rollback**
- DB backup restore.

**Stop-the-line**
- Any schema misuse (e.g., stuffing raw article into sku_key without adding raw_article columns).

---

### P5 — Automation + Scale
**Goal (measurable)**
- Incremental archive pulls + rebuild are scheduled/repeatable with deterministic manifests and restartability.

**Inputs**
- scripts/export_kaspi_archive_history.py (incremental slice mode)
- Builder from P2
- Drift wiring from P3

**Outputs**
- Makefile/task runner entries or a single orchestrator script:
  - scripts/run_sales_truth_ocean_drop_cycle.py
- Deterministic manifests:
  - exports/validation/.../manifest.json

**Definition of Done**
Accepted as done only when:
- Rerunning same day inputs yields identical outputs (modulo timestamps).
- Any partial run leaves a resumable manifest and fails closed.

**Validation/Gates**
- Determinism check on manifests
- Strict chain green.

**Rollback**
- Code revert; DB restore if writes occurred.

**Stop-the-line**
- Silent store/window gaps.

---

### P6 — Proving Run Restart
**Goal (measurable)**
- Restart 14-day GREEN streak with new ocean-drop parity and drift gates enforced.

**Inputs**
- H5 proving run contract/runbook
- Strict chain with drift

**Outputs**
- exports/health/streak/<day>/green_streak.json
- Evidence transcript:
  - exports/validation/board_sales_ocean_drop_engine_integrity_v2_<YYYY-MM-DD>/full_gates_green_final.md

**Definition of Done**
Accepted as done only when:
- 14 consecutive days are green with the new gates.
- No decision-grade artifact is produced on a red day.

**Validation/Gates**
- `python3 scripts/run_h5_proving_day.py --strict --project-root . --as-of <day>`
- Streak tracker meets target.

**Rollback**
- Stop operations; fix root cause; restart streak.

**Stop-the-line**
- Any gate failure; any attempt to bypass drift/parity.

---

## If attachments are missing — assumptions policy (fail-closed)
- If ocean-drop CSV or CRM lookup CSV is missing/unreadable: stop and fail with a clear error listing required paths and expected columns.
- If only a partial fixture is available: run only unit tests + fixture-based parity tests; do not apply writes to real DB.
- Never “guess” store mappings, status mappings, or date semantics; unknowns must raise in strict mode.
