# Agent 36 - Combined Temp Proof After Agents 33, 34, 35

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_combined_temp_proof_after_33_34_35_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_32.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_33.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_34.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_35.md`
8. this starter prompt

## Mission

Build the first combined temp proof that uses all accepted lanes together:

- Agent 33: STOREB API order-entry temp apply, reducing `ORDER_ENTRY_MISSING` from `276` to `23`.
- Agent 34: ads scope semantics, reducing false STOREB `ADS_COVERAGE_MISSING` to `0`.
- Agent 35: FB2 Meta/Facebook source-freshness packet bridge, clearing `src_facebook_ads_external_ads`.

The goal is not to force a green result. The goal is to produce the most decision-grade combined residual matrix we have so far and identify the minimum next unblocker if anything remains.

## Coordination

You are not alone in the codebase. Do not revert or overwrite previous agents' edits.

Likely write set:

- evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/`
- assigned closeout
- only if tests prove a necessary source-freshness bug:
  - `core/ops/policy_materialization_c3.py`
  - `tests/test_policy_materialization_c3.py`

If you edit code, write tests first and explain exactly why existing code could not represent the combined proof safely.

## Write Boundary

Allowed:

- temp DB copies under Agent 36 evidence;
- rerunning repo-owned temp materializers and validators;
- narrow tests/code only if required to preserve fail-closed source-freshness semantics;
- assigned closeout and evidence files.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- live API calls;
- Web_automation writes;
- Facebook_ads writes;
- broad quarantine of remaining blockers;
- fuzzy/product-name SKU mapping;
- treating stale or missing data as zero.

## Required Starting DB

Start from Agent 33's temp DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_33_evidence/agent33_storeb_api_order_entry_temp_apply_20260505.db`

Copy it to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db`

Do not mutate Agent 33's DB directly.

## Required Source Inputs

Use the same fresh ads evidence accepted by Agent 32:

- `~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite`

Use the FB2 Meta packet accepted by Agent 35:

- `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260505_acmewear_meta_live_refresh/meta_live_refresh_summary.json`

## Required Work

1. Copy Agent 33 DB into the Agent 36 evidence folder and verify integrity.
2. Apply the fresh ads materializer to the Agent 36 temp DB.
3. Run ads validators after Agent 34 scope semantics:
   - sidecar readiness;
   - offer-universe coverage;
   - spend reality.
4. Materialize C3 source freshness using current code with Agent 35's Meta bridge.
5. Materialize C3 policy gate results.
6. Run operational integration, source freshness, policy gate, cashflow coverage, and cashflow invariant validators.
7. Produce a combined residual matrix comparing at least:
   - Agent 24/32 before shape if available;
   - Agent 33 after order-entry shape;
   - Agent 34 after ads-scope shape;
   - Agent 35 after Meta-source shape;
   - Agent 36 combined shape.
8. If `src_ab_db_operational_truth` blocks because of future-dated ingestion/update timestamps, investigate whether the correct source-freshness behavior should use latest eligible rows at or before the as-of cutoff. Add tests/code only if you can prove this is a source-observation bug and not a data-quality problem.
9. If `src_web_automation_kaspi_marketing_directapi` remains stale despite accepted fresh Web_automation evidence, investigate the narrowest fail-closed bridge for accepted `source_evidence_summary.json` packets. Add tests/code only if the packet schema is strict enough. Otherwise preserve the blocker and specify the next required agent.
10. Do not hide stale `fact_cashflow_daily`. If it remains stale, keep it as a blocker and state the exact rebuild/materializer needed next.

## Suggested Command Skeleton

Use exact paths and record final commands in the closeout.

```bash
mkdir -p ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence
cp ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_33_evidence/agent33_storeb_api_order_entry_temp_apply_20260505.db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db 'PRAGMA integrity_check;'
```

Fresh ads apply:

```bash
ENABLE_C3_ADS_SOURCE_WRITE=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/materialize_ads_campaign_product_daily.py \
  --app-db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db \
  --external-marketing-db "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db" \
  --external-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite \
  --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite \
  --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite \
  --webauto-marketing-db ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite \
  --stores ACMEWEAR,STOREB \
  --start 2025-01-01 \
  --end 2026-05-04 \
  --output-root ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/ads_materializer_fresh_source_apply \
  --apply \
  --json
```

C3 source and gate materialization:

```bash
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/materialize_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --run-id agent36_combined_after_33_34_35 --apply --backup-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/backups --json
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/materialize_policy_gate_results.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --run-id agent36_combined_after_33_34_35 --apply --backup-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/backups --json
```

## Required Validation Commands

Run the relevant focused gates and record exact pass/fail:

```bash
python3 -m py_compile scripts/materialize_ads_campaign_product_daily.py scripts/validate_ads_offer_universe_coverage.py scripts/validate_policy_source_freshness.py scripts/validate_policy_gate_results.py core/ads/active_scope.py core/ops/policy_materialization_c3.py
pytest -q tests/test_materialize_ads_campaign_product_daily.py tests/test_validate_ads_offer_universe_coverage.py tests/test_policy_materialization_c3.py tests/test_policy_registry_c3_contract.py tests/test_materialize_storeb_api_order_entries_from_agent31.py
python3 scripts/validate_ads_sidecar_readiness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --output-root ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/validators/ads_readiness --strict
python3 scripts/validate_ads_offer_universe_coverage.py --db-path ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/validators/ads_offer_universe --strict
python3 scripts/validate_ads_spend_reality.py --db-path ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/validators/ads_spend_reality --strict
python3 scripts/validate_operational_stock_integration_gates.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --json
python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --strict --json
python3 scripts/validate_policy_gate_results.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --strict --json
python3 scripts/validate_order_cashflow_coverage.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db 'PRAGMA integrity_check;'
git status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
bash scripts/lint_docs.sh
```

## Expected Gate

GREEN is allowed only if:

- all strict validators pass;
- production DB/workbook/external systems are untouched;
- remaining exception queues are either closed or explicitly non-blocking under owner-approved policy;
- no source freshness blockers remain.

YELLOW is correct if:

- combined temp proof is valid but strict publication still blocks on known residuals such as the `23` STOREB quarantine rows, `16` negative-ledger review rows, stale `fact_cashflow_daily`, or a still-unresolved source-freshness contract.

RED is correct if:

- combining the accepted lanes introduces regression, double counting, fuzzy mapping, hidden ads spend, stale source treated as fresh, or production/external writes.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- temp DB path;
- commands run with pass/fail;
- combined residual matrix;
- exact remaining blockers with owning next lane;
- production apply status.
