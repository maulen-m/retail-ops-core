# ORDER_ENTRY_NON_API_LOCAL_EVIDENCE_COPIED_TEMP_V1

Status: active copied-temp contract.

Accepted at: `2026-05-18T21:23:26+05:00`

Accepted by: CodeCaptain `2026-05-18 21:23:26` review, under the existing owner-approved copied-temp/read-only MVOS envelope.

## Purpose

This contract allows the next copied-temp MVOS proof wave to materialize non-API order-entry rows only when local evidence contains product identity. It is intended to resolve the Agent905/Agent908 order-entry blocker without creating production truth.

## Scope

Allowed scope:

- copied validation DB only;
- `MVOS_SCOPE_ACTIVE_BUSINESS_THREE_STORE`;
- stores `STOREB`, `ACMEWEAR`, and `UNIVERSAL`;
- as-of date `2026-05-18`;
- `162` identity-bearing missing order/store pairs classified by Agent905.

Forbidden scope:

- production `db/app.db`;
- workbook mutation;
- scheduler, LaunchAgent, or cron mutation;
- source-pointer writes;
- external writes;
- owner publication;
- synthetic or fuzzy product identity;
- header-only row insertion.

## Accepted Source Priority

The materializer must evaluate sources in this order:

1. API raw order entries.
2. Saved WebUI archive pack `~/Docs/Autonomous_business/imports/webui_archive_manual/17.05.2026_18_26_58`.
3. Saved WebUI archive pack `~/Docs/Autonomous_business/imports/webui_archive_manual/17.05.2026_09_54_42`.
4. Accepted current CRM workbook `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx` at SHA-256 `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`.

If a higher-priority source provides complete identity, lower-priority sources must not override it.

## Allowed Materialization

Allowed copied-temp insertion cohort:

- total identity-bearing rows: `162`;
- STOREB: `47`;
- ACMEWEAR: `26`;
- UNIVERSAL: `89`.

Every inserted copied-temp row must have row-level provenance with:

- order id;
- store code;
- selected source priority;
- source path;
- source file or directory hash;
- source row identifier where available;
- materializer command;
- copied DB path;
- contract id `ORDER_ENTRY_NON_API_LOCAL_EVIDENCE_COPIED_TEMP_V1`;
- `proof_scope=copied_temp`;
- `production_authority=false`;
- controlled `updated_at=2026-05-18T12:00:00+05:00`.

## Retained Quarantine

The following `15` STOREB rows are header-only source-gap quarantines unless a later identity-bearing source packet proves otherwise:

```text
919726875
920305856
920417956
921817321
922014323
922556382
922880013
923474762
923497390
923672781
923721827
925297090
925568908
925671939
925988478
```

These rows must remain visible as `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED`. They must not be inserted into `fact_order_entries_kaspi` as product truth.

## Required Validation

The next proof wave must run:

```bash
python3 scripts/validate_order_entries_freshness.py --db <copied-db> --as-of 2026-05-18 --lookback-days 14 --stores STOREB,ACMEWEAR,UNIVERSAL --strict
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
```

Expected proof behavior:

- identity-bearing missing rows decrease by the materialized copied-temp cohort;
- the `15` STOREB header-only rows remain visible and are not inserted;
- provenance sidecar proves the source selected for every inserted row.

## Stoplines

- Do not insert header-only rows.
- Do not infer SKU, size, product id, cost, or offer identity from names alone.
- Do not use this copied-temp contract for production apply.
- Do not hide the retained quarantine count.
- Do not claim copied-temp green unless validators genuinely pass and retained blockers are disclosed.
