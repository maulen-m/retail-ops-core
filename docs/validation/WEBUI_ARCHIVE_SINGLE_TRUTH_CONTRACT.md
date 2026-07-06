# WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT

## Purpose
Define the fail-closed source hierarchy for promoting Kaspi WebUI archive exports into the owner-truth pipeline without bypassing DB-backed validation or publication.

## Source Hierarchy
1. Historical candidate source: normalized WebUI archive packs and the merged WebUI status ledger.
2. Historical control anchor: CRM North Star workbooks remain the floor/ceiling guardrail for delivered-day reality until promotion gates are green.
3. Operational system of record: `db/app.db` remains the only publication-grade source for owner surfaces.

## Date Vocabulary Lock
- `order_intake_date`: customer order/creation date, WebUI `Дата поступления заказа`, API `createdAt` / `creationDate`. Demand/intake only.
- `ship_date`: courier handoff, waybill, Telegram PDF shipped-workflow, or actual shipped workflow date. Warehouse on-hand depletion only.
- `sale_date` / `transaction_date` / `delivered_at`: WebUI `Дата изменения статуса` for `Выдан` / delivered / completed rows. COGS, cash, PnL, sales economics, and final-sales stock only.
- `cancel_date`: status-change date for cancelled rows. Not a positive sale.
- `return_date`: status-change date for returned rows. Not active sellable stock unless a return-QC/source rule accepts it.

Warehouse stock and final-sales stock are separate views. A stock re-anchor that
answers warehouse on-hand must deduct by `ship_date`; a stock re-anchor that
answers final sales/economics must deduct by `sale_date`. `order_intake_date`
must never be promoted into final sale truth after the strict status-date cutover.

## Canonical Historical Flow
1. Immutable WebUI archive downloads are normalized into `exports/webui_archive_packs/<PACK_ID>/`.
2. Normalized rows are merged into `exports/order_status_ledger/<RUN_ID>/webui_status_ledger.csv`.
3. DB-backed truth projections join ledger delivered dates to operational order lines by `order_id` and `store_code`.
4. Validators, owner review, and owner PnL consume DB-backed projections only.

Raw downloaded files are evidence inputs only. They are never published directly.

## Monthly Economics Projection Implementation Note
Monthly sales economics parity must bucket DB economics by WebUI delivered
status-change date after the strict status-date cutover. The validator-owned
projection surface is `monthly_sales_economics_statusdate_projection`: it is
built from delivered rows in
`exports/sales_archive_statusdate_mapped/<RANGE>/ArchiveSales_ALL_STORES_statusdate_mapped.csv`
and joins to `view_sales_line_truth` by `order_id`, `store_code`, and line
identity (`mapped_sku_id` first, then `mapped_sku_key` plus `mapped_size`).
If the mapped archive row has no usable line identity, the validator may use an
order/store status-date fallback only for orders that have no other line-identity
archive anchors; that fallback must be counted in projection metadata and any
resulting residual must be reported as a source/DB line-grain limitation, not
silently treated as clean line-grain parity.

The projection's `sale_date` is the archive `transaction_date`; its economics
amounts remain DB-backed from `view_sales_line_truth`. This is an additive
consumer-specific projection. It must not silently change
`view_sales_line_truth` or switch unrelated consumers away from the published DB
view.

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
- Delivered/completed rows on or after `2026-02-27` must not use `created_at`,
  `creationDate`, or `Дата поступления заказа` as `sale_date` / `transaction_date`
  in strict mode.

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

## Read-Only Source Refresh Wrapper
- Canonical operator entrypoint: `python3 scripts/run_webui_archive_source_refresh.py --since <YYYY-MM-DD> --until <YYYY-MM-DD> --stores <STORE,STORE> --mode auto --strict`.
- The wrapper is read-only by contract. It may import existing manual `ArchiveOrders` downloads, run 90-day WebUI archive blocks through existing Playwright methods, normalize packs, validate `status_change_at`, and emit immutable evidence.
- The wrapper must not mutate `db/app.db`, Excel workbooks, scheduler state, external accounts, prices, stocks, ads, cash, PO state, or owner publication surfaces.
- The wrapper must not update source-pointer anchors when it is used as a read-only source-refresh proof path.
- Safe mode order for `--mode auto`: import an explicit existing source root first, then use saved Playwright session state/headless Chrome. Headful/manual login requires explicit operator intent. Chrome CDP attach remains fail-closed until the repo-owned downloader supports it.
- For import-existing/manual source roots, requested `--since` and `--until` may be carried into download, pack, and ledger manifests only when the wrapper records source-file hashes and emits the window provenance itself. Operators must not hand-edit manifest windows after import.
- A status-ledger manifest window is validator-trustworthy only when the corresponding pack-window entry carries source-file hash provenance. Scoped copied-temp proofs that include only `STOREB`, `ACMEWEAR`, and `UNIVERSAL` must keep omitted stores such as `11KZ` and `MELVIS` disclosed unless same-window source files are provided.
- Raw downloaded files remain evidence inputs only. Any CodeCaptain or external packet that uses this data must include only the needed sanitized sidecars unless a reviewer explicitly requests raw workbook inspection.
- Promotion or DB apply from refreshed WebUI evidence is a separate reviewed lane with backup-first, env-gated apply rules.

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
