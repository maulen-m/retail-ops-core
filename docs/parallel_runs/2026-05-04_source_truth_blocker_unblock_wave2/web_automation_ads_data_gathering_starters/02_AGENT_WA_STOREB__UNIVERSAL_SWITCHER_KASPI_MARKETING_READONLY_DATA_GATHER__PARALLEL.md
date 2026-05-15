# Web Automation Agent WA-2 - STOREB Universal-Switcher Kaspi Marketing Read-Only Data Gather

Assigned closeout:

`~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/WA2_STOREB_CLOSEOUT.md`

## Bootstrap Context

Run from:

`~/Docs/Web_automation`

Before executing, read:

1. `~/Docs/Web_automation/AGENTS.md`
2. `~/Docs/Web_automation/Docs/00_START_HERE.md`
3. `~/Docs/Web_automation/Docs/kaspi_marketing_local.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_11_ads_source_refresh_coverage_closeout.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
6. this starter prompt

## Mission

Gather source-backed, read-only Kaspi Marketing evidence for AB logical store `STOREB` so Autonomous_business Agent 12 can repair:

- `ADS_REFRESH_MISSING=4138`
- `ADS_COVERAGE_MISSING=4138`

Do not change any campaign, product, bid, budget, name, targeting, enabled state, merchant setting, or external account state.

## Critical Access Instruction

Log in through the Universal marketing account if that is the available credential path.

After login, use the store/account switcher in the top upper corner of the Kaspi Marketing cabinet and switch to `STORE-B` / `STOREB` before fetching any STOREB data.

Before capturing source data, verify and record non-secret identity evidence:

- visible selected store/account label is `STORE-B` / `STOREB`;
- merchant/store UID is `30000002` if visible or present in requests;
- API merchant ID is freshly observed and recorded.

Universal is only the access account. All AB-facing source rows and closeout language must use:

- `business_store_code=STOREB`
- `access_store_code=UNIVERSAL_SWITCHER_FOR_STOREB`

Do not publish switched STOREB source rows as AB logical `UNIVERSAL`.

## Scope

Business store: `STOREB`

Known identities from older evidence:

- seller-cabinet merchant/store UID candidate: `30000002`
- historical API merchant ID candidate: `1065684`
- AB logical store code: `STOREB`

Treat the API merchant ID as a candidate until verified in the fresh switched-account session. If the fresh switched-account session shows a different API merchant ID, record it with evidence and use the fresh value.

Primary evidence window for current Autonomous_business C3 blockers:

- active scope start: `2026-03-08`
- current AB sales max date in Agent 11 evidence: `2026-04-15`
- required active-window coverage: `2026-03-08..2026-04-15`

STOREB is Kaspi-internal marketing only for this task. Meta/Facebook funnel ads apply only to ACMEWEAR, not STOREB.

## Required Data Gathering

Capture the strongest read-only evidence available, in this order:

1. Fresh switched-account proof that the active marketing cabinet context is `STOREB` / merchant UID `30000002`.
2. Full campaign list for `STOREB` for `2026-03-08..2026-04-15`, or the fullest available date probes that prove whether campaigns/products exist.
3. Campaign product rows for every STOREB campaign discovered.
4. Campaign header/detail rows showing campaign state, budget, default bid, dates, and merchant identity.
5. Raw payloads, normalized CSVs, and SQLite rows in a dedicated run folder.

If there are zero campaigns or zero product rows, that can only support `NO_SPEND_VERIFIED` when full-store completeness is evidenced for the store/date. A targeted or partial fetch absence remains blocked.

## Suggested Read-Only Commands

Use the repo-local `.env` if it contains the marketing keys. If not, the known prior fallback is `~/Docs/Autonomous_business/.env`; do not print, copy, or store secret values.

Start with help and source discovery:

```bash
./web-auto kaspi-marketing fetch-campaigns --help
./web-auto kaspi-marketing watch --help
```

If the existing CLI requires explicit campaign IDs, first use the switched STOREB browser/session or DirectAPI campaign-list read to discover current STOREB campaign IDs. Only then run product fetches.

Once STOREB campaign IDs are discovered, targeted fetch shape:

```bash
./web-auto --json --env-file ~/Docs/Autonomous_business/.env kaspi-marketing fetch-campaigns \
  --store STOREB \
  --merchant-id 1065684 \
  --store-code 30000002 \
  --campaign-ids <fresh_storeb_campaign_ids_from_switched_account> \
  --date 2026-04-15 \
  --headless \
  --run-dir runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/fetch_2026-04-15 \
  --db-path runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite
```

If the fresh switched-account session proves a different API merchant ID than `1065684`, replace `--merchant-id 1065684` with the freshly verified ID and explain the change in the closeout.

Recommended date probes:

- `2026-03-08`
- `2026-03-15`
- `2026-03-31`
- `2026-04-15`

If a date-range campaign-list endpoint is available through the existing network capture or DirectAPI read, prefer `2026-03-08..2026-04-15` over isolated probes.

## Mapping Evidence To Preserve

For every captured STOREB product row, preserve these non-secret fields where available:

- `business_store_code=STOREB`
- `access_store_code=UNIVERSAL_SWITCHER_FOR_STOREB`
- selected visible store/account label
- source merchant/store UID
- API merchant ID
- campaign ID
- campaign name
- campaign state
- product SKU from Kaspi Marketing
- merchant article / merchant SKU / article text
- Kaspi product code
- date or source `StartDate`/`EndDate`
- cost/spend KZT
- views/impressions
- clicks
- orders/order count
- revenue/GMV
- bid/default bid/product bid
- raw payload path
- normalized CSV path
- SQLite DB path

Autonomous_business mapping strategy downstream:

- map source merchant article / merchant SKU to `dim_kaspi_article_map.kaspi_article`;
- then map to AB `sku_key`;
- do not use fuzzy product names as the only mapping basis.

## Coverage Classification For Closeout

For every date/store/SKU area you can support, classify:

- `COVERED`: exact source product row maps by stable article/product identity and cost is positive.
- `NO_SPEND_VERIFIED`: exact mapped product row has zero cost, or full-store source proof shows the SKU absent from all campaign products for that store/date.
- `BLOCKED`: targeted-only absence, stale source, missing full-store proof, unmapped source row, auth/session uncertainty, Universal still selected instead of STOREB, merchant identity mismatch, or no switched-account proof.

## Write Boundary

Allowed writes:

- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/**`

Forbidden writes:

- `~/Docs/Autonomous_business/**`
- `~/Docs/Autonomous_business/db/app.db`
- Web_automation code/tests/config/docs outside the assigned run folder
- `.env`, cookies, storageState, tokens, or secret material
- Kaspi campaign state, bids, budgets, products, names, targeting, enablement, or merchant settings
- any Meta/Facebook work for STOREB

## Closeout Requirements

Your closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Gate meanings:

- `GREEN`: switched STOREB identity is verified and read-only source data captured with enough full-store completeness to let AB Agent 12 truthfully materialize `COVERED` and `NO_SPEND_VERIFIED` for the requested STOREB blocker window.
- `YELLOW`: STOREB identity or targeted data is partially captured, useful for exact `COVERED` rows, but not enough to prove full-store absence.
- `RED`: unable to switch from Universal to STOREB, unable to verify STOREB identity, unable to fetch source data, or any source integrity risk.

Include:

- commands/UI steps run;
- explicit Universal login plus top upper-corner switcher verification;
- source freshness timestamp and run folder;
- raw/CSV/SQLite artifact paths;
- row counts by date, campaign, product, and source table;
- campaign IDs discovered;
- verified API merchant ID and seller/store UID;
- evidence completeness: `full_store_universe` or `targeted_campaign_only`;
- exact fields available for AB `sku_key` mapping;
- rows/date ranges that can be `COVERED`;
- rows/date ranges that can be `NO_SPEND_VERIFIED`;
- explicit stopline for anything still blocked;
- confirmation that no external writes, Meta work, or secrets were stored.
