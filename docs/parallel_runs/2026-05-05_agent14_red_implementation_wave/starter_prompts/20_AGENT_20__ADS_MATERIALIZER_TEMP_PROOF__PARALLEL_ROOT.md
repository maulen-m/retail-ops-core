# Agent 20 - Ads Materializer Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_20_ads_materializer_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_implementation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_17_ads_evidence_retry_import_plan_closeout.md`
7. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/WA1_ACMEWEAR_CLOSEOUT.md`
8. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/WA2_STOREB_CLOSEOUT.md`
9. this starter prompt

## Mission

Implement and prove ads materializer support for WA1 ACMEWEAR aggregate-window absence/no-spend evidence.

You are not alone in the codebase. Do not revert edits made by others. Touch only your owned files. If an owned file has unexpected concurrent edits, stop and close out YELLOW/RED with evidence.

## Owned Write Set

Primary:

- `~/Docs/Autonomous_business/scripts/materialize_ads_campaign_product_daily.py`
- `~/Docs/Autonomous_business/tests/test_materialize_ads_campaign_product_daily.py`

Optional only if strictly needed for test fixtures:

- fixture files under `~/Docs/Autonomous_business/tests/fixtures/`

Forbidden:

- production `db/app.db` writes;
- Web_automation repo writes;
- live Kaspi Marketing calls;
- ad-platform writes;
- derived-table replay files owned by Agent 18;
- C3 policy files owned by Agent 19.

## Evidence Rules

Safe:

- Use WA1 ACMEWEAR aggregate full-store product universe evidence to reduce ACMEWEAR refresh blockers.
- Generate daily `NO_SPEND_VERIFIED` rows only when the source window proves full-store product rows complete and the active delivered-sale date/SKU is absent from that full-store product universe or maps to aggregate-zero product rows.
- Ledger generated rows with source window id and source paths.

Unsafe:

- Do not fan out positive aggregate spend into daily SKU-level `COVERED` rows.
- Do not use partial daily absence as no-spend proof.
- Do not mark STOREB covered or no-spend verified from WA2 because product rows were blocked by `429`.
- Do not store STOREB evidence as `UNIVERSAL`; Universal is only the access path, business store remains `STOREB`.

## Required Implementation

Write tests first, then code.

Required behavior:

1. Materializer reads WA1 `window_completeness` and only uses windows with full-store product-row completeness.
2. Materializer creates/apply-plans appropriate `ads_source_refresh_runs` provenance for the exact evidenced window.
3. Materializer generates daily `NO_SPEND_VERIFIED` rows from aggregate absence/zero evidence only.
4. Materializer does not generate daily `COVERED` rows from positive aggregate spend.
5. STOREB evidence from WA2 remains blocked unless product/SKU rows exist.
6. Dry-run remains default; production apply remains env-gated with existing ads write gate.

## Required Temp Proof

Use a copied temp DB, not production:

`/private/tmp/agent20_ads_materializer_temp_proof_20260504.db`

Use current read-only WA DBs:

- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite`

Do not production-apply.

## Required Gates

Run focused tests for your changed files.

Run temp DB dry-run/apply proof against the temp DB only, then:

- `python3 scripts/validate_operational_stock_integration_gates.py --db <temp_db> --as-of 2026-05-04 --json`
- `python3 scripts/validate_ads_sidecar_readiness.py --db <temp_db> --as-of 2026-05-04 --output-root <evidence_dir>/sidecar --strict`
- `python3 scripts/validate_ads_offer_universe_coverage.py --db-path <temp_db> --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir <evidence_dir>/offer --strict`
- `python3 scripts/validate_ads_spend_reality.py --db-path <temp_db> --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir <evidence_dir>/spend --strict`
- `sqlite3 <temp_db> 'PRAGMA integrity_check;'`

If strict ads validators still fail because STOREB remains blocked, that can be YELLOW if ACMEWEAR reduction is correctly proven and no fake STOREB success is introduced.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run and key outputs;
- exact blocker counts before and after temp materialization;
- explicit confirmation that STOREB remains blocked unless fresh product evidence exists;
- production apply stoplines.
