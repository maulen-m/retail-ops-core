# SALES_ECONOMICS_TRUTH_CONTRACT

## Purpose
Define one fail-closed contract for sales economics publication and parity checks.
This contract is the authority for:
- delivered-date basis used by monthly sales economics,
- formulas for Net Revenue / COGS / Profit,
- decision-grade vs provisional labeling.

## Canonical Hierarchy
1. `docs/inventory/Master_Inventory_Rules_v9.md` (canonical formulas/parameters)
2. This contract (`docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md`)
3. DB truth views (`view_sales_line_truth`, `view_sales_daily_truth`)
4. Derived reports (`BUSINESS_INSIDES`, scorecards)

If code differs from v9 formulas, update `docs/inventory/Master_Inventory_Rules_v9.md` first, then this contract, then code/tests.

## Delivered Date Basis
- `transaction_date` for archive parity rows is resolved in this order:
  1. `status_change_date` (`Дата изменения статуса`) when present,
  2. `ui_override_status_date` when UI pack enrichment provides a stricter value,
  3. `creation_date_fallback` (`Дата поступления заказа`) only for legacy months before cutover.
- Cutover policy:
  - `statusdate_cutover = 2026-02-27`
  - For delivered rows with `transaction_date >= 2026-02-27`, `creation_date_fallback` is forbidden in strict mode.
  - Rationale:
    - Current locked archive evidence still contains non-zero legacy fallback rows for `STOREB` up to `2026-02-19`.
    - Those rows remain provisional until a full UI status-date refresh replaces them with authoritative `Дата изменения статуса`.

## Economics Formulas (Kaspi, v9)
Per unit:
- `NetRev = (SellPrice * (1 - CommissionRate) - NetDeliveryFee) * (1 - VATRate) - AdsCostUnit`
- `COGS = BaseCostCNY * CNY_KZT + WeightKG * DLV_RATE_USD_KG * USD_KZT`
- `Profit = NetRev - COGS`

Monthly totals:
- `Units_month = SUM(units)`
- `NetRev_month = SUM(NetRev_line)`
- `COGS_month = SUM(COGS_line)`
- `Profit_month = SUM(Profit_line)`

Rounding policy:
- Line-level values stored as numeric KZT in DB.
- Monthly comparisons use absolute KZT tolerance from parity script (`+1 KZT`) and percentage tolerance (`0.5%` default) for exceed checks.

## Decision-Grade Rules
A month/store pair is `decision_grade=true` only when all are true:
- month is closed (`month_end < as_of_until`),
- month is not pre-cutover (`month_end >= statusdate_cutover`),
- delivered rows for that month/store contain no `creation_date_fallback`.

Otherwise pair is `provisional` and must be reported as such.

## Parity Gate
`validate_monthly_economics_parity.py --strict` fails when:
- any decision-grade month/store has `db_units` or `db_net_rev_kzt` exceeding archive-derived totals by tolerance.

Artifacts required:
- `summary.json`
- `report.md`
- `monthly_db.csv`
- `monthly_archive.csv`
- `diffs_by_month.csv`

## Returned-Order Cash Reversal Gate

`scripts/validate_returns_economics_audit.py` validates mature returned orders
at exact order/store grain:

- A returned order with positive recognized D1 `CASH_IN` requires at least one
  linked negative ordinary `CASH_IN` or explicit `REFUND` for the same exact
  `ORDER` reference or an `ORDER_ENTRY` that currently resolves to that order
  and store.
- A returned order with no recognized positive cash has nothing to reverse.
  It must be absent from canonical delivered-sales truth, but the validator
  records `NO_RECOGNIZED_CASH_TO_REVERSE` and does not require or invent a
  refund event.
- An unscoped or unrelated refund in the same calendar month cannot prove a
  return. Monthly event counts are diagnostic only.
- A negative `CASH_IN` whose `source='ORDER_CASH_REPAIR'` and notes identify a
  superseded cash row is a ledger correction, not a customer refund, so it
  cannot satisfy this gate.
- A current first-party `RETURNED` row can close a missing terminal-history
  gap only when one exact prior positive `ORDER_ENTRY` cash row resolves through
  the current entry table to the same order and store. Its reversal preserves
  the positive amount and reference on the current return-observation date.
  Requiring the delivery cash date to equal the later return date is invalid;
  ambiguous entry scope or multiple exact positive rows is fail-closed.
- Missing linked reversal evidence is
  `RETURNS_CASH_REVERSAL_GAP`. Returned rows still present in canonical sales
  beyond the volatility window remain the separate
  `RETURNS_LEAK_STALE` failure.

## Monthly Cash Reconciliation (D1)

`scripts/validate_monthly_cash_reconciliation.py` reconciles delivered-sales
economics to the current API-first D1 cash ledger. Its cohort and precedence
rules are:

- The comparison cohort comes from `view_sales_line_truth` by exact `order_id`,
  sale month, and store for the requested sale-date range.
- Cash evidence is `fact_cashflow_events.event_type='CASH_IN'`. Positive D1
  recognition and negative D1 reversal rows are summed together for the chosen
  order reference. Legacy `SALE_ACCRUED` and separate `REFUND` events are not
  current D1 reconciliation inputs.
- `ORDER_ENTRY` cash rows resolve to the sale order through
  `fact_order_entries_kaspi.entry_id -> order_id`. Entry-level cash is chosen
  only when its distinct entry-reference set exactly covers the order's current
  entry-reference set, all entry stores match the sale store, and entry
  quantity equals delivered-sales units. If that proof passes, all positive and
  negative cash rows for those entries are used and `ORDER` rows are ignored.
  An incomplete entry set, recovered-entry duplication, quantity mismatch, or
  mixed partial `ORDER_ENTRY`/`ORDER` evidence is ambiguous and uncovered; it
  must not silently fall back or add the two reference types together. Only an
  order with no `ORDER_ENTRY` cash evidence may use `ref_type='ORDER'` as a
  fallback.
- `event_date` represents delivery/reversal timing; it does not select the sale
  cohort. Chosen cash is assigned back to the sale order's sale month and store.
  The report is nevertheless point-in-time: cash rows dated after `--as-of` are
  excluded, so a future reversal cannot rewrite an earlier report.
- A decision-grade month/store pair is cash-covered only when every sales order
  in the pair has one unambiguous sale month/store, has chosen D1 cash evidence,
  and every chosen event store matches the sales-truth store. Missing entry
  mappings, missing cash, cross-month/store order identity, and event-store
  mismatch are fail-closed coverage errors.
- Current D1 coverage and tolerance are separate gates. A pair is compared for
  monetary tolerance only after its order coverage is complete. Reports must
  disclose fallback and dual-reference counts even when the preferred
  `ORDER_ENTRY` evidence makes the monetary result deterministic.
- Cash-reference coverage does not by itself prove the sales amount. For every
  line selected by `view_sales_line_truth`, decision-grade reconciliation must
  follow that row's declared `source_table` and reproduce the effective-dated
  canonical `calc_net_rev` result from unit sell price, line quantity, and the
  seller delivery fee allocated exactly once across the order. In
  `sales_fact_v2`, `delivery_fee` is a line total and must be divided by line
  quantity before calling the unit formula; in canonical `fact_sales`,
  `delivery_fee` is already a unit value. The line amount is
  `unit_net_rev * quantity`. A mixed or unsupported source, a legacy formula,
  an unavailable price/quantity/date basis, a selected/source line-count
  mismatch, or an absolute difference greater than `0.01 KZT` leaves that
  order uncovered.
- Formula proof must bind the exact selected order/store/source-line multiset,
  including the declared source table, effective source/sale date, raw source
  SKU key and ID, size, source units, and source net revenue. The selected
  line's published units and net revenue must equal those declared source
  values within their canonical tolerances. A workbook-anchor or other
  publication override cannot borrow formula proof from a different source
  date or amount: it remains uncovered with an explicit selected-amount/source
  or source-multiset mismatch until a separate governed publication repair
  proves that value.
- Reconciliation reports must expose raw source-formula proof separately from
  publication binding. `source_formula_proven` means the underlying source
  rows independently reproduce the effective-dated canonical formula;
  `publication_binding_proven` means the selected published date, units,
  amount, and source-line multiset are exact. These are diagnostic components,
  not alternative pass paths: an order is decision-grade only when both are
  true. Reporting source proof must never allow a stale workbook anchor or
  other publication override to pass by itself.
- A historical formula-provenance sidecar may prove raw formula inputs, but it
  cannot self-promote a stored legacy amount. The sidecar must be bound to the
  exact copied-DB SHA-256, selected-view line-multiset SHA-256, effective-date
  economics-policy hash, and byte hash of every frozen source packet. Each
  proof key must include an immutable API entry ID or the physical CSV/workbook
  sheet+row locator plus a canonical source-row hash. `sale_id`, `order_id`, a
  derived CRM field, or a mutable workbook path alone is never proof.
- When an otherwise unexplained selected/source mismatch already has a unique
  `source_entry_id` and exact `ENTRY:<source_entry_id>` line key on every
  selected source row, source-line identity is proven only if each entry is
  corroborated one-to-one by a first-party API order row with exact
  order/store, SKU key, SKU ID, size, quantity, unit price, and article. Such
  identity proof must not be mislabeled as economics proof: a null fee or net
  amount remains an explicit source-line economics blocker.
- Sidecar generation is read-only and all-or-nothing at order/store grain.
  It must bind the complete selected source-line multiset, allocate one
  order-level seller delivery fee across every order line exactly once by
  gross-line proportion, and exclude the complete order on missing/extra
  lines, conflicting same-rank evidence, source/DB/view hash drift, unreadable
  source packets, absent seller fee, or effective-date formula ambiguity.
  Buyer delivery cost, inferred delivery fee, and inversion from stored
  `net_rev` are forbidden fallbacks.
- A CRM-workbook formula-provenance sidecar is limited to a byte-pinned private
  copy of the source workbook and must emit no customer PII. It may use only the
  raw Kaspi seller-fee field `Стоимость доставки для продавца`; the derived
  legacy `Delivery_fee_kzt` column is never evidence or a fallback. This
  conservative CRM lane may corroborate, but may not bootstrap or replace, the
  stored `sales_fact_v2.delivery_fee`: the raw seller fee and existing stored
  line-total fee must agree exactly at KZT-cent precision. A missing or
  different stored fee excludes the order for a separately reviewed repair.
  The exact
  physical workbook row must match order, store, order date, raw gross, raw and
  derived quantity, `SKU_key`, `SKU_ID`, and `MY_SIZE`, and its cancellation
  reason must be blank. Two matching rows are ambiguous and exclude the order.
  Positive lifecycle-state evidence may come from API/WEBUI terminal status
  observations or from a complete current `fact_orders_kaspi` order whose rows
  are `COMPLETED`/`ARCHIVE` and first-party sourced. Those observations prove
  the state was seen, not the exact status-change or publication-effective
  date. Append-only events without a source status-change timestamp are only a
  state/temporal guard: a later cancellation or return excludes the order,
  while an event row alone cannot create exact effective-date truth.
- A terminal status observation timestamp is lifecycle evidence, not by itself
  proof of the exact status-change timestamp or the canonical publication
  effective date. A resolver may rank WEBUI `DELIVERED`, API `COMPLETED`, and a
  complete current API order for deterministic candidate construction, but it
  must disclose the evidence kind and all later terminal observations. It must
  not silently choose an earlier WEBUI observation over a later API completion
  as decision-grade economic timing. A current `fact_orders_kaspi` candidate is
  rank-eligible only when every order row is `COMPLETED`, `ARCHIVE`, API-sourced,
  and has one unambiguous date. Until an owning policy explicitly selects an
  observation-date rule or exact first-party status-change evidence is present,
  the resulting date and cohort transition remain inactive candidates.
- A sidecar row records the source inputs and canonical recomputation target;
  it does not make the current production or copied sales row formula-proven
  when the stored amount differs. Promotion requires a separately reviewed
  copied-DB repair manifest, exact target/non-target proof, validator replay,
  and production-write approval where applicable.
- A copied-DB promotion may update only the proof-bound `sales_fact_v2`
  `delivery_fee` line total and `net_rev` line total. When `cogs` is present it
  must also set `profit = canonical net_rev - cogs`; when `cogs` is absent,
  `profit` remains `NULL`. The writer must refuse the canonical production DB,
  verify every complete preimage before beginning its transaction, refuse
  table triggers, preserve every non-target row, and read back every target.
  It may not change lifecycle, SKU identity, source identity, quantities,
  prices, cash events, stock, or any external system. A production promotion
  remains a distinct owner-approved write lane.
- Chosen cash evidence must also be unique. Two rows with the same event date,
  amount, store, reference type, reference ID, `sku_key`, and `sku_id` are an
  ambiguous duplicate even when their source labels differ; the validator must
  fail closed instead of counting both.
- The default relative tolerance is `0.01` (1%). The CLI accepts a fraction,
  so `--tolerance-pct 0.01` means 1%, not 0.01%. A wider tolerance must be an
  explicit evidence-lane choice and cannot be used to publish decision-grade
  economics under the 1% acceptance gate.
- Strict mode requires at least one fully covered decision-grade month/store
  pair; an empty or wholly uncovered comparison cannot pass by omission.
- Unsupported-reference and unmapped-entry integrity errors are fail-closed
  only when their event date falls inside the requested reporting event window.
  Older unrelated diagnostics may be counted separately but cannot invalidate a
  selected cohort merely because they exist elsewhere in history.
- An unmapped recovered-entry event may be classified as a closed historical
  obligation, rather than an active unmapped event, only when the ledger contains
  exactly one positive `ORDER_MODELLED` row and exactly one negative
  `ORDER_IDENTITY_REPAIR` row for the same recovered reference. The two rows must
  have exact date/store/SKU identity, distinct valid event hashes, equal and
  opposite amounts, and nonblank run IDs; the reversal note must name the exact
  positive event ID through `supersedes_cash_id` and both notes must name the same
  numeric order ID. Any partial, extra, mismatched, unhashed, or non-zero group
  remains fail-closed as `CASH_RECON_UNMAPPED_ORDER_ENTRY`. Reports must disclose
  the neutralized group/event counts and net amount separately; neutralization
  never creates cash or order-entry truth.
- A historical `INVENTORY_SETTLEMENT` cannot stand beside newly reconstructed
  canonical COGS for the same order/SKU without an append-only reversal. When
  the pre-canonical on-delivery balance is zero only because of exactly one
  negative settlement, the translator may append one positive
  `INVENTORY_SETTLEMENT_REVERSAL` and then the canonical negative
  `COGS_RECOGNIZED`. The reversal must preserve the exact order, SKU, amount,
  account, and date-scoped lifecycle context and name the prior settlement row
  ID and valid 64-hex event hash in its note. Missing, extra, future-dated,
  unhashed, non-negative, or amount-mismatched settlements are not repairable by
  inference and must stop the translation. The resulting balance must be zero,
  and an unchanged replay must be idempotent.
- A publication/anchor reconciliation must preserve the complete selected
  order/store set and the original workbook-anchor rows as immutable lineage.
  Deleting an anchor, adding an order to whole-order anchor quarantine, or
  otherwise reducing the mismatch count by removing an order from
  `view_sales_line_truth` is forbidden.
- Publication repair is a two-proof sequence, not an override shortcut. The
  immutable source row and its original chronology remain unchanged. A separate
  line-level binding must reproduce the canonical formula at the proven
  terminal status-change date from the exact source inputs, then publish only
  that manifest-bound effective date, units, and amount instead of a stale
  workbook-anchor value. Source-line proof and publication binding require
  separate manifest sections and exact readback.
- Every publication-binding record must pin the complete preimage of the
  current workbook anchor, the exact selected source-line multiset hash, the
  terminal-date evidence hash and rank, the economics-policy hash, the copied
  DB pre-hash, canonical-hash serialization version, immutable source row IDs
  and preimages, and the originating manifest hash. At most one active binding
  is allowed per order/store. Opaque hashes alone are insufficient: relational
  anchor/source preimages must also be compared by the published view or its
  required validator. Any preimage, source, terminal-date, or policy drift must
  preserve membership but surface an explicit invalid-binding blocker.
- Pre-cutover rows that rely on creation-date fallback may be reconciled only
  as explicitly provisional and must retain the formula-proven source date
  unless economics are independently recomputed at a different effective date.
  They cannot satisfy decision-grade date coverage.
  Post-cutover rows require direct terminal effective-date proof and a formula
  replay at that date. An observation-date candidate can support inactive
  schema/view mechanics and counterfactual formula evidence, but cannot activate
  a publication binding or satisfy decision-grade date coverage. Missing or
  observation-only terminal evidence, conflicting later terminal observations,
  invalid raw source lines, ambiguous identity, or source-formula failure
  remains unwritten and uncovered.
- The published view must retain workbook-anchor membership semantics needed to
  include source rows, even when an exact binding supersedes the anchor's date,
  units, or net amount. A binding must publish exact per-line source units and
  formula amounts; it must not proportionally allocate an order-level total.
  The view and every decision-grade consumer must expose binding status and
  provisional status. Before/after validation must prove identical full
  order/store and line membership, exact manifest-authorized target cohort
  transitions, identical non-target cohorts, and conserved target counts.
- Publication manifest construction and apply require two separately proven
  prerequisites before any binding write: the exact minimal 7-column/3-index
  source-identity schema contract and the exact six-view runtime contract for
  `view_sales_line_truth_unbound`, binding validation, line truth, daily truth,
  line reference, and daily reference. The manifest pins both contracts and
  their internal hashes. A legacy or drifted stored view cannot be refreshed
  implicitly by the builder or applier. On a copied DB, the only supported
  route is a read-only reviewed plan followed by the separately gated
  `scripts/apply_sales_truth_view_refresh.py` apply. That apply must preserve
  every pre-existing table logical hash and match the reviewed schema and
  selected-row deltas exactly. Production use requires separate exact owner
  approval; copied success is not production authority.

## Stop-the-line
- Any decision-grade month published with fallback transaction dates.
- Any decision-grade month where DB economics exceed archive-derived delivered totals beyond tolerance.
- Any publication of profit as decision-grade when required COGS/identity coverage gates are red.
- Any decision-grade cash-reconciliation pair with incomplete or ambiguous
  order coverage, or any implementation that double-counts `ORDER_ENTRY` and
  `ORDER` cash for the same order.
- Any decision-grade cash reconciliation whose sales amount does not reproduce
  the canonical effective-dated formula, or whose chosen cash contains an
  exact duplicate identity.
- Any publication/anchor repair that deletes or quarantines an anchor to make
  an order disappear, changes selected order/store membership, lacks exact
  source/anchor/terminal/policy hashes, or applies a post-cutover amount without
  direct terminal-date formula proof.
- Any binding implementation that overwrites raw source chronology, uses only
  opaque hashes without relational preimage validation, proportionally
  allocates line economics, silently falls back from an invalid binding, or
  moves a non-target cohort.
