# Web Automation Agent WA-1 - ACMEWEAR Kaspi Marketing Read-Only Data Gather

Assigned closeout:

`~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/WA1_ACMEWEAR_CLOSEOUT.md`

## Bootstrap Context

Run from:

`~/Docs/Web_automation`

Before executing, read:

1. `~/Docs/Web_automation/AGENTS.md`
2. `~/Docs/Web_automation/Docs/00_START_HERE.md`
3. `~/Docs/Web_automation/Docs/kaspi_marketing_local.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_11_ads_source_refresh_coverage_closeout.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
6. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/00_AB_KASPI_MARKETING_DIRECT_API_HANDOFF.md`
7. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/acmewear_child_bundle_campaign_registry.csv`
8. this starter prompt

## Mission

Gather source-backed, read-only Kaspi Marketing evidence for `ACMEWEAR` so Autonomous_business Agent 12 can repair:

- `ADS_REFRESH_MISSING=4138`
- `ADS_COVERAGE_MISSING=4138`

Do not change any campaign, product, bid, budget, name, targeting, enabled state, merchant setting, or external account state.

## Scope

Business store: `ACMEWEAR`

Known identities:

- seller-cabinet merchant/store UID: `30137883`
- Kaspi Marketing API merchant ID from prior evidence: `759051`
- AB logical store code for all output rows: `ACMEWEAR`

Known ACMEWEAR campaign IDs from current evidence:

- `2380614`
- `2545773`
- `2626530`
- `2629982`
- `2690256`
- `2695637`
- `2794142`
- `2794144`
- `2794146`
- `2794148`
- `2794149`
- `2794150`
- `2794152`
- `2794153`

Primary evidence window for current Autonomous_business C3 blockers:

- active scope start: `2025-01-01`
- current AB sales max date in Agent 11 evidence: `2026-04-15`
- highest-priority freshness gap: `2026-04-05..2026-04-15`

Secondary evidence window:

- child-bundle campaign evidence from `2026-05-03` onward, for future Agent 12 ingestion and monitoring.

## Required Data Gathering

Capture the strongest read-only evidence available, in this order:

1. Full campaign list for `ACMEWEAR` for the blocker window, enough to know whether campaign/product absence is true full-store absence or only targeted-fetch absence.
2. Campaign product rows for each known in-scope campaign/date window.
3. Campaign header/detail rows showing campaign state, budget, default bid, dates, and merchant identity.
4. Raw payloads, normalized CSVs, and SQLite rows in a dedicated run folder.

If the existing CLI can only fetch targeted campaigns by ID, run that targeted fetch, but mark it as `targeted_campaign_only`. Do not claim absent sold SKUs are `NO_SPEND_VERIFIED` unless you also have full-store campaign/product-universe proof for that store/date.

## Suggested Read-Only Commands

Use the repo-local `.env` if it contains the marketing keys. If not, the known prior fallback is `~/Docs/Autonomous_business/.env`; do not print, copy, or store secret values.

Start with help and a dry source check:

```bash
./web-auto kaspi-marketing fetch-campaigns --help
```

Targeted current-window fetch shape:

```bash
./web-auto --json --env-file ~/Docs/Autonomous_business/.env kaspi-marketing fetch-campaigns \
  --store ACMEWEAR \
  --campaign-ids 2380614,2545773,2626530,2629982,2690256,2695637,2794142,2794144,2794146,2794148,2794149,2794150,2794152,2794153 \
  --date 2026-04-15 \
  --headless \
  --run-dir runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/fetch_2026-04-15 \
  --db-path runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing.sqlite
```

If the CLI supports date-range or campaign-list capture beyond the example above, prefer the fuller read-only capture and document exact commands.

Recommended date probes if time allows:

- `2026-04-05`
- `2026-04-10`
- `2026-04-15`
- `2026-05-03`

## Mapping Evidence To Preserve

For every captured product row, preserve these non-secret fields where available:

- `business_store_code=ACMEWEAR`
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
- `BLOCKED`: targeted-only absence, stale source, missing full-store proof, unmapped source row, auth/session uncertainty, or identity mismatch.

## Write Boundary

Allowed writes:

- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/**`

Forbidden writes:

- `~/Docs/Autonomous_business/**`
- `~/Docs/Autonomous_business/db/app.db`
- Web_automation code/tests/config/docs outside the assigned run folder
- `.env`, cookies, storageState, tokens, or secret material
- Kaspi campaign state, bids, budgets, products, names, targeting, enablement, or merchant settings

## Closeout Requirements

Your closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Gate meanings:

- `GREEN`: read-only source data captured with enough full-store completeness to let AB Agent 12 truthfully materialize `COVERED` and `NO_SPEND_VERIFIED` for the requested ACMEWEAR blocker window.
- `YELLOW`: targeted or partial read-only source data captured, useful for `COVERED` rows, but not enough to prove full-store absence.
- `RED`: unable to verify ACMEWEAR identity, unable to fetch source data, or any source integrity risk.

Include:

- commands run;
- source freshness timestamp and run folder;
- raw/CSV/SQLite artifact paths;
- row counts by date, campaign, product, and source table;
- campaign IDs found versus expected;
- evidence completeness: `full_store_universe` or `targeted_campaign_only`;
- exact fields available for AB `sku_key` mapping;
- rows/date ranges that can be `COVERED`;
- rows/date ranges that can be `NO_SPEND_VERIFIED`;
- explicit stopline for anything still blocked;
- confirmation that no external writes or secrets were stored.
