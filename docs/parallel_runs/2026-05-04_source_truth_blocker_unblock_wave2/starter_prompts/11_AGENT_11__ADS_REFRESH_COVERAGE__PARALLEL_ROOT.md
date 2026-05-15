# Agent 11 - Ads Source Refresh And Coverage Truth

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_11_ads_source_refresh_coverage_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/FULL_ORCHESTRATOR_REVIEW_CURRENT_STATE.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_4_c3_ads_marketing_directapi_truth_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_2_ads_source_refresh_closeout.md`
9. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/00_AB_KASPI_MARKETING_DIRECT_API_HANDOFF.md`
10. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/acmewear_child_bundle_campaign_registry.csv`
11. this starter prompt

## Mission

Resolve the root cause of the remaining ads blockers:

- `ADS_REFRESH_MISSING=4138`
- `ADS_COVERAGE_MISSING=4138`

Your job is to produce source-backed evidence and an executable repair plan for Agent 12. If a read-only live source call is necessary and clearly no external state is mutated, you may perform it. Do not write ads settings, budgets, bids, campaigns, merchant state, Meta state, Web_automation repo files, or production `db/app.db`.

## Source Scope

Active Kaspi internal ads stores:

- `ACMEWEAR`
- `STOREB`

Access context:

- ACMEWEAR runs Kaspi internal ads for ACMEWEAR products.
- STOREB runs Kaspi internal ads for generic LINE52 offers.
- STOREB marketing access may be available through the Universal marketing cabinet store switcher. If so, source rows must still be represented as AB logical `STOREB`, not `UNIVERSAL`.
- Meta/Facebook to Kaspi funnel ads apply only to `ACMEWEAR`, not STOREB.

## Write Boundary

Allowed writes:

- your assigned closeout;
- optional evidence files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_11_evidence/`;
- optional temp files under `/private/tmp/agent11_ads_*`.

Forbidden writes:

- production `~/Docs/Autonomous_business/db/app.db`;
- repo code or tests;
- `.claude/*`;
- Web_automation repo files or DBs;
- Facebook_ads repo files;
- Kaspi/Meta/merchant/ads external writes;
- changing campaigns, bids, budgets, enabled state, targeting, names, or products.

Do not print or store secret values. You may reference env var names only.

## Required Investigation

Use read-only DB/source inspection to answer:

1. Which date/store/sku combinations need `ads_source_refresh_runs` and `ads_campaign_product_daily` coverage?
2. Which local source can populate ACMEWEAR coverage: AB DB, Web_automation `data/kaspi_marketing.sqlite`, external marketing DB, child-bundle registry, direct API handoff, or fresh read-only source call?
3. Which source can populate STOREB coverage, and is Universal-switcher access enough to fetch STOREB read-only data?
4. What rows can be `COVERED`, what rows can be `NO_SPEND_VERIFIED`, and what rows must remain blocked?
5. What exact importer/materializer should Agent 12 implement or run?

## Suggested Commands

Run from `~/Docs/Autonomous_business`.

```bash
python3 scripts/validate_ads_sidecar_readiness.py --db-path db/app.db --as-of 2026-05-03 --strict
python3 scripts/validate_ads_offer_universe_coverage.py --db db/app.db --as-of 2026-05-03 --json
python3 scripts/validate_ads_spend_reality.py --db db/app.db --as-of 2026-05-03 --json
```

```bash
python3 - <<'PY'
import json
from collections import Counter
p='exports/validation/release_agents4_7_20260504/post_operational_stock_integration_gates.json'
data=json.load(open(p))
for code in ['ADS_REFRESH_MISSING','ADS_COVERAGE_MISSING']:
    rows=[x for x in data.get('findings', []) if x.get('code')==code]
    print(code, len(rows))
    print(Counter((x.get('evidence') or {}).get('store_code') for x in rows))
    print(rows[:10])
PY
```

Inspect source DBs read-only only:

```bash
sqlite3 -readonly ~/Docs/Web_automation/data/kaspi_marketing.sqlite ".tables"
sqlite3 -readonly "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db" ".tables"
```

## Closeout Requirements

Your closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- ads blocker counts by store/date range/source;
- exact source freshness and coverage availability;
- exact mapping strategy to AB `sku_key`;
- exact Agent 12 implementation instructions;
- any required live read command, marked read-only, with no secrets;
- explicit stopline for any ads rows that cannot be covered honestly.

Gate meaning:

- GREEN: source-backed ads repair path is clear and testable.
- YELLOW: path is clear but live/current source evidence remains required.
- RED: ads cannot be repaired safely from available evidence.
