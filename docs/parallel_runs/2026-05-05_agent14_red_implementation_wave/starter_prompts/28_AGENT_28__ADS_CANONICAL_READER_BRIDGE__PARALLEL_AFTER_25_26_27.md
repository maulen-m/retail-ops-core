# Agent 28 - Ads Canonical Reader Bridge Implementation

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_28_ads_canonical_reader_bridge_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_24.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_25_26_27.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_combined_temp_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_26_ads_source_refresh_mapping_triage_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_27_ads_sidecar_validator_bridge_triage_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_27_evidence/table_reader_matrix.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_27_evidence/db_ads_surface_snapshot.md`
11. this starter prompt

## Mission

Implement the smallest code/test bridge so strict ads validators and owner publication consume canonical ads truth from `ads_campaign_product_daily` plus `ads_source_refresh_runs`, not stale `ads_spend_sidecar_daily*` tables.

## Write Boundary

Allowed:

- code/tests/docs needed for the canonical ads read bridge;
- assigned closeout and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_28_evidence/`.

Forbidden:

- production `db/app.db` writes;
- external-system writes;
- ad-platform writes;
- Web_automation writes;
- non-ads residual repair code;
- broad refactors;
- changing business math outside ads read-source routing.

## Required Implementation

1. Write tests first for canonical reader, offer-universe, spend-reality, readiness, and publication consumers.
2. Add a shared canonical ads reader module, for example `core/ads/canonical_truth.py`, that projects:
   - daily SKU rows from `ads_campaign_product_daily`;
   - daily/monthly store totals from canonical rows;
   - readiness/range metadata from `ads_source_refresh_runs`.
3. Update these consumers to use the canonical reader:
   - `scripts/validate_ads_offer_universe_coverage.py`;
   - `scripts/validate_ads_spend_reality.py` if needed through delegated offer-universe logic;
   - `scripts/validate_ads_sidecar_readiness.py` or a compatibility wrapper;
   - `scripts/build_north_star_owner_review.py`;
   - `scripts/build_owner_pnl_report.py`;
   - `scripts/generate_business_insides.py` and inherited `scripts/build_profit_after_ads.py`.
4. Do not materialize into `ads_spend_sidecar_daily*` as the primary fix. Keep legacy fallback only behind an explicit flag if needed.
5. Update owner PnL and business-insides docs so canonical ads truth is named as the publication dependency.

## Required Gates

Run:

```bash
python3 -m py_compile <changed-python-files>
```

Run focused pytest for changed tests.

Run canonical validators against the Agent 24 temp DB:

```bash
python3 scripts/validate_ads_offer_universe_coverage.py --db-path ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_evidence/agent24_combined_temp_proof_20260504.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_28_evidence/ads_offer_canonical
python3 scripts/validate_ads_spend_reality.py --db-path ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_evidence/agent24_combined_temp_proof_20260504.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_28_evidence/ads_spend_canonical
python3 scripts/validate_ads_sidecar_readiness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_evidence/agent24_combined_temp_proof_20260504.db --as-of 2026-05-04 --output-root ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_28_evidence/ads_readiness_canonical
```

Expected temp DB outcome:

- The canonical validators may still be non-green because true residual ads gaps remain after `2026-04-15` and unresolved mapping gaps remain.
- Success means failures are sourced from canonical `ads_campaign_product_daily` and `ads_source_refresh_runs`, not stale `ads_spend_sidecar_daily*` data ending at `2026-03-03`.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run with pass/fail;
- strict validator before/after interpretation on the Agent 24 temp DB;
- explicit launch status: not green for production publication unless all strict gates pass.
