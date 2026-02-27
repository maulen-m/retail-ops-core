Risks + likely regressions to watch

Truth mixing: Any pipeline that uses view_sales_line_truth while that view unions fact_sales_external_ref will remain non‑diagnostic (you can’t tell if the engine is correct, because reference data can mask bugs).

app_db_schema_catalog_2026-02-27

Volatility window (returns/cancellations): Official archive can revise up to the return window; parity must either (a) exclude last N days or (b) treat them as provisional, otherwise daily strict gates will flap.

Legacy overlap boundaries: The view uses “v2 bounds” logic (min sale date) to decide where legacy fact_sales applies; boundary bugs can cause double‑counts or missing early history.

app_db_schema_catalog_2026-02-27

SKU/size identity: Canonical SKU resolution relies on mapping tables (e.g., dim_kaspi_article_map) and may be overloaded with raw “article” strings; any parser/mapping drift can cascade into COGS/profit and size-engine logic.

Biggest unknowns (state assumptions; ask no questions unless truly blocking)

Anchor file availability/immutability: In this environment I cannot open the large CSV/XLSX attachments that were flagged as not accessible; the plan assumes your “ocean drop” file exists at the stated path and is treated as read‑only during validation runs.

Return semantics by product_type: The system needs an explicit policy for ELS long return windows; current parity work likely assumes a 14‑day volatility window for most SKUs.

Whether internal ingest already has complete per‑order “status change date” semantics for all historical orders. If not, parity will fail until API history ingestion is repaired.

ASCII Roadmap Tree (Next Phases)

P0: Ocean-Drop Reference Contract Lock [Coding Agent] {Contract + fixture parsers + immutable manifest}
  |
P1: Split “Published Truth” vs “Reference” (No Mixing) [Coding Agent] {view_sales_line_truth has 0 refs to fact_sales_external_ref}
  |
P2: Full-History Ocean-Drop Parity Harness [Coding Agent] {Order-ID + daily totals parity reports; strict fail-closed}
  |
P3: Internal Sales Engine Repair (API history ingest + status/date + returns) [Coding Agent] {Parity PASS without reference overrides}
  |
P4: SKU + Size Identity Convergence [Coding Agent] {Delivered rows: 0 missing sku_key; size overrides deterministic}
  |
P5: Drift Detection + Autopilot Wiring [Coding Agent] {Daily last-14-day parity gate in system_doctor --strict}
  |
P6: Promotion + Proving-Run Restart [Coding Agent] {14-day GREEN streak with new truth gates}

Agent Markdown Plan (to be saved in <autonomous_business/DOCS/>)

# PLAN_SALES_OCEAN_DROP_TRUTH_ANCHOR_2026-02-27

## Purpose
Establish a single “reference anchor” (“ocean drop”) for Kaspi sales truth and use it to repair upstream sales/order processing so the system produces correct results *without* patching/overriding truth views.

Non-negotiables:
- Fail-closed everywhere.
- Do not mix truth sources: published truth must be computed from internal ingest + DB, not overridden by reference datasets.
- Reference datasets may be used ONLY for validation and for deriving mapping tables (explicit-gate write).

## Context / Evidence
- Kaspi archive export web UI is limited (90-day blocks); manual long-range export is ~40 exports for 5 stores; API-first extraction is deterministic but must chunk 14-day windows due to API limit. (See KASPI_ARCHIVE_EXTRACTION_METHODS_REPORT.md and KASPI_ARCHIVE_WEB_EXTRACTION_PLAYBOOK_2026-02-27.md)
- Current DB `view_sales_line_truth` can union `fact_sales_external_ref` and suppress internal rows by day+store when reference exists, enabling “patched truth” and masking upstream bugs.

## Inputs (authoritative priority)
1) Official Kaspi archive history (API-extracted; cancellations/returns accounted up to 2026-02-26)
   - Example path (provided by user): 
     /Users/.../Sales_archive/kaspi_archive_history_2024-06-06_to_2026-02-26_20260227_233318/ArchiveOrders_ALL_STORES.csv
2) Merged mapped “ocean drop” candidate (official rows + mapping + MY_SIZE truth overrides)
   - Example path (provided by user):
     /Users/.../Sales_archive/mapped_data/ArchiveOrders_ALL_STORES_mapped_20260228_025856.csv
3) Internal CRM historical shipped archive (NOT authoritative for totals; used only for sku_key + MY_SIZE lookup)
   - Example path (provided by user):
     /Users/.../Csv_converted_22.2.26/Archive_sales_normalized_backfilled_22.2.26.csv

## Outputs (artifacts + paths)
- Contract doc:
  - docs/validation/SALES_OCEAN_DROP_REFERENCE_CONTRACT.md
- New validators / scripts:
  - scripts/validate_sales_truth_ocean_drop_parity.py
  - scripts/build_ocean_drop_reference_snapshot.py
  - scripts/sync_dim_kaspi_article_map_from_ocean_drop.py (dry-run default; gated apply)
  - scripts/sync_order_size_overrides_from_ocean_drop.py (dry-run default; gated apply)
- Tests:
  - tests/test_ocean_drop_contract_parser.py
  - tests/test_sales_truth_ocean_drop_parity.py
  - tests/test_view_sales_truth_no_reference_override.py
- Deterministic reports (per as_of):
  - exports/validation/sales_ocean_drop_parity/<as_of>/parity_report.json
  - exports/validation/sales_ocean_drop_parity/<as_of>/parity_report.md
  - exports/validation/sales_ocean_drop_parity/<as_of>/diff_missing_order_ids.csv
  - exports/validation/sales_ocean_drop_parity/<as_of>/diff_extra_order_ids.csv
  - exports/validation/sales_ocean_drop_parity/<as_of>/diff_date_mismatches.csv
- Updated runbooks (strict gate wiring):
  - docs/ops/H5_DAILY_EXECUTION_RUNBOOK.md (add ocean-drop parity gate policy + volatility window)

## Phase List

### P0 — Ocean-Drop Reference Contract Lock
**Goal (measurable)**
- Define an explicit contract for the “ocean drop” dataset (schema + semantics) and implement a deterministic parser that produces normalized reference facts:
  - daily totals by store
  - per-order delivered set
  - optional per-line items

**Inputs**
- Ocean drop mapped CSV (read-only)
- Exported Kaspi archive CSV (read-only)
- Existing DB schema catalogs for field mapping

**Outputs**
- docs/validation/SALES_OCEAN_DROP_REFERENCE_CONTRACT.md
- scripts/build_ocean_drop_reference_snapshot.py
- tests/test_ocean_drop_contract_parser.py
- A small, committed fixture subset:
  - tests/fixtures/ocean_drop_small.csv (sanitized sample)
  - tests/fixtures/ocean_drop_small_expected.json

**Definition of Done**
Accepted as done only when:
- Contract doc defines:
  - what “sale_date” is (delivered/completed date, not creation date)
  - return/cancel inclusion rules
  - treatment of last-N-day volatility window
  - store_code canonicalization rules
- Parser outputs are deterministic and match fixture expected outputs exactly.
- `pytest -q` includes new tests and they are green.

**Validation / Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `bash scripts/lint_docs.sh`

**Rollback**
- Code-only: `git revert <sha>`.

**Stop-the-line**
- Any ambiguity in the contract doc that would allow multiple interpretations.
- Any parser that silently drops rows (must emit explicit error list and fail in strict mode).

---

### P1 — Split “Published Truth” vs “Reference” (No Mixing)
**Goal (measurable)**
- Ensure published truth views are computed ONLY from internal ingest sources.
- Reference tables/views exist ONLY for validation comparisons.

**Inputs**
- core/sales/truth_views.py (or wherever view SQL is generated)
- DB schema definitions (db/schema.sql or runtime view builder)
- Current view definition (view_sales_line_truth unions fact_sales_external_ref)

**Outputs**
- Updated view logic:
  - view_sales_line_truth: internal-only
  - view_sales_daily_truth: derived from internal-only
  - view_sales_line_reference (new): reference-only
  - view_sales_daily_reference (new): derived from reference-only
- tests/test_view_sales_truth_no_reference_override.py

**Definition of Done**
Accepted as done only when:
- Grep-based + SQL-based tests confirm:
  - view_sales_line_truth has NO reference to fact_sales_external_ref
  - business-insides default path reads published truth only
- CI/contract suite green

**Validation / Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`

**Rollback**
- If view change breaks ops: revert code, restore prior view builder, rerun gates.

**Stop-the-line**
- Any reintroduction of reference tables into published truth.
- Any fallback behavior that “best-effort” substitutes reference data when internal truth fails.

---

### P2 — Full-History Ocean-Drop Parity Harness
**Goal (measurable)**
- Produce a fail-closed validator that compares:
  - internal published truth vs ocean drop reference
  - at both daily totals and order_id set levels
- Exclude (or separately report) the volatility window days.

**Inputs**
- Ocean drop mapped file
- view_sales_daily_truth (internal)
- view_sales_daily_reference (reference)

**Outputs**
- scripts/validate_sales_truth_ocean_drop_parity.py
- exports/validation/sales_ocean_drop_parity/<as_of>/... (reports + diffs)
- tests/test_sales_truth_ocean_drop_parity.py

**Definition of Done**
Accepted as done only when:
- Validator fails when a deliberate perturbation is injected in fixture.
- Validator produces:
  - missing/excess order_id lists
  - per-day drift table
  - explicit “skipped volatile days” list
- Strict mode returns non-zero on any non-volatile mismatch.

**Validation / Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_sales_truth_ocean_drop_parity.py --as-of 2026-02-26 --strict --ocean-drop <PATH>`

**Rollback**
- Code-only revert.

**Stop-the-line**
- Any parity mismatch outside volatility window that cannot be explained by contract semantics.

---

### P3 — Internal Sales Engine Repair (API history ingest + status/date + returns)
**Goal (measurable)**
- Make internal truth match ocean drop reference WITHOUT using reference overrides.
- Fix root causes (status mapping, delivered date, cancellations/returns, dedupe).

**Inputs**
- core/integrations/kaspi_api_client.py
- core/ingest/sales_ingest.py
- scripts/sync_kaspi_orders.py
- scripts/export_kaspi_archive_history.py output (for debugging and replay)

**Outputs**
- Code changes in ingest pipeline to:
  - compute sale_date from correct status transition date
  - incorporate archive history backfill (chunking) as a first-class ingest path
  - ensure dedupe keys are correct and stable across stores
- New regression tests for:
  - date semantics
  - cancellation/return handling
  - dedupe across windows

**Definition of Done**
Accepted as done only when:
- `validate_sales_truth_ocean_drop_parity --strict` is PASS for the full reference range excluding volatility window.
- Diff reports show 0 missing and 0 extra order_ids (non-volatile).
- Any remaining mismatches are explicitly categorized as “volatile-window” or “ELS-long-return” and excluded by contract.

**Validation / Gates**
- `python3 scripts/validate_sales_truth_ocean_drop_parity.py --strict ...`
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>`

**Rollback**
- Always create DB backup before any apply writes.
- Code revert + restore DB backup if apply-ingest writes were performed.

**Stop-the-line**
- Any attempt to “fix parity” by reintroducing reference override into truth views.
- Any ingest that silently drops windows or stores.

---

### P4 — SKU + Size Identity Convergence
**Goal (measurable)**
- Ensure internal delivered rows have deterministic `sku_key` and accurate clothes `MY_SIZE`, using:
  - derived mapping tables from ocean drop (explicit-gate)
  - CRM archive as lookup only (explicit-gate)

**Inputs**
- Ocean drop mapped CSV (contains mapping confidence fields)
- dim_kaspi_article_map table
- Internal sales/order tables

**Outputs**
- scripts/sync_dim_kaspi_article_map_from_ocean_drop.py (dry-run default; apply gate)
- scripts/sync_order_size_overrides_from_ocean_drop.py (dry-run default; apply gate)
- Validator:
  - scripts/validate_no_missing_identity_in_delivered_window.py
- Reports:
  - exports/validation/identity_coverage/<as_of>/...

**Definition of Done**
Accepted as done only when:
- For the reference range, internal truth has:
  - 0 delivered rows with empty sku_key
  - clothes rows have MY_SIZE populated when available in ocean drop / CRM lookup
- Strict validator fails if identity regressions occur.

**Validation / Gates**
- `python3 scripts/validate_no_missing_identity_in_delivered_window.py --strict ...`
- Full test suite + strict params

**Rollback**
- DB backup before apply; provide restore command path in evidence.

**Stop-the-line**
- Any schema misuse (e.g., storing raw article in sku_key fields) without explicitly adding raw_article columns.

---

### P5 — Drift Detection + Autopilot Wiring
**Goal (measurable)**
- Add daily “last-14-days” parity check (API-export slice vs internal truth) into strict system doctor / H5 chain.

**Inputs**
- scripts/system_doctor.py
- docs/ops/H5_OPERATIONAL_PROVING_RUN_CONTRACT.md
- scripts/export_kaspi_archive_history.py (incremental mode or new slice exporter)

**Outputs**
- scripts/build_sales_truth_drift_report.py
- exports/daily/<as_of>/sales_truth_drift_report.{json,md}
- Updated system_doctor strict chain to fail closed on drift beyond tolerance.

**Definition of Done**
Accepted as done only when:
- Drift report generated every day as part of strict chain.
- Any drift causes non-zero exit and appears in exceptions.json.

**Validation / Gates**
- `python3 scripts/system_doctor.py --strict ...`
- Targeted tests for drift builder + wiring

**Rollback**
- Code revert.

**Stop-the-line**
- Any “warn-only” behavior for drift in strict mode.

---

### P6 — Promotion + Proving-Run Restart
**Goal (measurable)**
- Promote the repaired sales truth engine, then restart the 14-day proving streak using updated gates.

**Outputs**
- docs/PLAN_BOARD_SALES_OCEAN_DROP_TRUTH_ANCHOR_YYYY-MM-DD.md
- docs/OPS_ROLLOUT_EVIDENCE_BOARD_SALES_OCEAN_DROP_TRUTH_ANCHOR_YYYY-MM-DD.md
- exports/validation/board_sales_ocean_drop_truth_anchor_YYYY-MM-DD/full_gates_green_final.md

**Definition of Done**
Accepted as done only when:
- Mandatory gates are green.
- Evidence transcript exists.
- H5 streak rules include new ocean-drop parity/daily drift gates.

**Validation / Gates**
- Same mandatory gates set used in prior boards plus new parity validator.

**Rollback**
- `git revert <sha>` + rerun full gates.

**Stop-the-line**
- Any gate failure.
- Any decision-grade artifact produced on a red day.

---

## If attachments are missing — assumptions policy
Fail-closed by default:
- In strict mode, missing ocean drop file => validator exits non-zero with explicit message.
- In CI, tests use `tests/fixtures/ocean_drop_small.csv` only.
- For local/prod runs, ocean drop path must be provided explicitly (CLI flag or env var); no silent default to arbitrary local paths.