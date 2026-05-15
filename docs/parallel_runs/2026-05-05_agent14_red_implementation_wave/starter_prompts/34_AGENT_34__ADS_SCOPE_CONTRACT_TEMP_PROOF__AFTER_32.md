# Agent 34 - Ads Scope Contract Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_34_ads_scope_contract_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/agent-scripts-main/skills/ads-scope-and-sidecar-refresh/SKILL.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_ads_fresh_evidence_temp_materialization_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_32.md`
8. this starter prompt

## Mission

Fix the remaining ads coverage semantics in temp-proof form. Agent 32 showed fresh Kaspi Marketing evidence clears ads freshness and spend-reality, but `validate_ads_offer_universe_coverage.py` still treats STOREB as if every sold SKU must have ads rows.

Owner/business truth says STOREB Kaspi internal ads are for specific generic advertised product offers, not the whole STOREB sold SKU universe. Your job is to encode that distinction safely and prove it with tests and a temp DB validation.

## Coordination

You are not alone in the codebase. Agent 33 is working on STOREB order-entry temp apply, and FB2 is working in Facebook_ads. Do not revert or overwrite their edits.

Your likely write set is:

- `docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`
- `config/ads_active_scope.yaml`
- `core/ads/active_scope.py`
- `scripts/validate_ads_offer_universe_coverage.py`
- `tests/test_validate_ads_offer_universe_coverage.py`
- evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_34_evidence/`
- assigned closeout

If you need files outside this set, explain why in closeout. Avoid ads materializer changes unless absolutely required.

## Write Boundary

Allowed:

- docs/config/code/tests for ads scope semantics;
- temp evidence under the assigned Agent 34 evidence folder;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- live API calls;
- Web_automation writes;
- Facebook_ads writes;
- non-ads order-entry/cashflow/stock code changes;
- broad quarantine of all STOREB missing sold SKUs;
- product-name or fuzzy SKU mapping;
- clearing unresolved STOREB product-code mapping conflicts.

## Required Policy Shape

Preserve this distinction:

- ACMEWEAR: full sold-SKU ads coverage semantics remain valid for the historical/current source-backed period.
- STOREB: current Kaspi internal ads scope is advertised-product scope, not all-sold-SKU scope.

For STOREB advertised-product scope:

- product codes with exact mapped spend/no-spend evidence should be valid coverage truth;
- sold SKUs that were never advertised should not create false `ADS_COVERAGE_MISSING`;
- positive-spend product codes that cannot be exactly mapped must remain blockers;
- conflicts such as `11391711b`, `11942309b`, and `11391205b` must remain fail-closed unless exact evidence resolves them.

Do not silently convert missing ads to zero. The point is to narrow scope, not hide missing source.

## Required Work

1. Write tests first for scope semantics:
   - a store in `all_sold_skus` mode still fails when a sold SKU lacks ads coverage;
   - a store in `advertised_products_only` mode does not fail for non-advertised sold SKUs;
   - a positive-spend advertised product/code with unresolved mapping still fails;
   - spend-reality checks still fail if store/month has neither spend nor verified no-spend rows.
2. Update the owning docs before or with code:
   - `docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`
3. Update `config/ads_active_scope.yaml` to encode STOREB current coverage mode explicitly.
4. Update the validator/core helpers to honor the effective-dated coverage mode.
5. Run focused tests.
6. Rerun ads validators against Agent 32's temp DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_evidence/agent32_ads_fresh_temp_20260504.db`

7. Produce before/after evidence showing:
   - `missing_sold_offers`;
   - `failing_month_store_pairs`;
   - unmapped/blocked positive-spend product-code blockers;
   - whether `ADS_COVERAGE_MISSING` drops and why.

## Required Validation Commands

Run the smallest relevant gates and record exact commands/results:

```bash
python3 -m py_compile core/ads/active_scope.py scripts/validate_ads_offer_universe_coverage.py tests/test_validate_ads_offer_universe_coverage.py
pytest -q tests/test_validate_ads_offer_universe_coverage.py
python3 scripts/validate_ads_offer_universe_coverage.py --db-path ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_evidence/agent32_ads_fresh_temp_20260504.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_34_evidence/ads_offer_universe_after_scope --strict
python3 scripts/validate_operational_stock_integration_gates.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_evidence/agent32_ads_fresh_temp_20260504.db --as-of 2026-05-04 --json
bash scripts/lint_docs.sh
```

If a strict validator still fails, preserve the failure and explain exact remaining blockers.

## Expected Gate

GREEN is allowed only if:

- tests pass;
- docs/config/code agree;
- ACMEWEAR full coverage remains enforced;
- STOREB non-advertised sold SKUs no longer create false coverage failures;
- unresolved positive-spend product-code mappings remain blockers;
- no production DB or external write occurred.

YELLOW is correct if:

- implementation is sound but strict publication still blocked by product-code mapping, Agent 33, FB2, or other C3 source/gate blockers.

RED is correct if:

- the only way to pass requires fuzzy mapping, broad quarantine, or hiding positive-spend unmapped product codes.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run with pass/fail;
- temp DB path used;
- before/after ads coverage residuals;
- unresolved positive-spend product-code blockers;
- explicit production apply status.
