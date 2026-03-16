# WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT

## Purpose
Define the fail-closed source hierarchy for promoting Kaspi WebUI archive exports into the owner-truth pipeline without bypassing DB-backed validation or publication.

## Source Hierarchy
1. Historical candidate source: normalized WebUI archive packs and the merged WebUI status ledger.
2. Historical control anchor: CRM North Star workbooks remain the floor/ceiling guardrail for delivered-day reality until promotion gates are green.
3. Operational system of record: `db/app.db` remains the only publication-grade source for owner surfaces.

## Canonical Historical Flow
1. Immutable WebUI archive downloads are normalized into `exports/webui_archive_packs/<PACK_ID>/`.
2. Normalized rows are merged into `exports/order_status_ledger/<RUN_ID>/webui_status_ledger.csv`.
3. DB-backed truth projections join ledger delivered dates to operational order lines by `order_id` and `store_code`.
4. Validators, owner review, and owner PnL consume DB-backed projections only.

Raw downloaded files are evidence inputs only. They are never published directly.

## Required Pack Guarantees
- Every source file must have manifest traceability, hash, store attribution, and row counts.
- Delivered/completed rows missing `status_change_at` fail strict integrity.
- Overlap windows may coexist, but dedup and first/last seen pack lineage must be deterministic.
- Missing required store blocks must emit explicit manifest failures.

## Required Ledger Guarantees
- Ledger grain is `store_code`, `order_id`, `status_internal`, `status_change_at`.
- `delivered_at` and `returned_at` are derived from ledger status events, not API fallbacks.
- API observations are stored with `observed_at` and never overwrite WebUI historical status-change dates.
- Continuity gaps for enabled stores inside the active proving window are stop-the-line until explained.

## Promotion Gates
WebUI archive can act as the candidate historical truth source only when all are green for the proving window:
- WebUI pack integrity
- status ledger continuity
- WebUI vs CRM band
- WebUI vs current DB chronology improvement
- ads offer coverage
- ads spend reality
- COGS completeness
- COGS realism
- order status audit history
- owner review / owner PnL strict checks
- `system_doctor --strict`

If any gate is red, owner publication remains locked.

## Frozen UI Pack Governance
- After the chronology authority is explicitly locked to CRM/workbook and the WebUI full-parse seed is frozen, `system_doctor --truth-source db` validates the configured UI seed pack for structural integrity only.
- In that DB-mode governance path, the UI integrity check must not fail solely because the frozen UI pack `until` date is older than the doctor `as_of` date.
- Current-day freshness for historical WebUI source refresh remains a separate operational concern and must not be silently inferred from the frozen-pack integrity check.

## Publication Rule
- Owner-facing outputs continue to publish from DB views and DB-backed aggregations only.
- When `truth_source=webui_archive`, publication code must require green WebUI promotion artifacts in addition to existing DB/ads/OPEX prerequisites.
- Legacy CRM restate artifacts remain shadow evidence until the WebUI cutover is proven green.

## Write Safety
No DB write is allowed for this migration unless all are true:
- `python3 scripts/backup_db.py --db db/app.db` completed successfully
- an explicit env gate is enabled
- `--apply` is present
- before/after diff artifacts are written
- rollback steps are documented in evidence artifacts

## Rollback Anchor
- Green rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- Red scaffold remains preserved: `exports/validation/crm_north_star_restate/2026-03-06/`

## Active-Doc Hygiene
Active docs must stay repo-relative and must not embed absolute personal filesystem paths.
