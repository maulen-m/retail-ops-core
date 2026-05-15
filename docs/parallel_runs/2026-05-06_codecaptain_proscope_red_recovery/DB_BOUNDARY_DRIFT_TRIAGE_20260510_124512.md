# DB And Workbook Boundary Drift Triage - Agent750 - 2026-05-10 12:45 +05

Status: `READ_ONLY_TRIAGE_COMPLETE_REVIEW_STILL_REQUIRED`

## Purpose

This artifact records the fresh read-only evidence for the current production DB and protected workbook SHA drift that blocks the Agent750 -> Agent751/752/753 validate-only launch path after the CodeCaptain GREEN answer was received.

It does not authorize re-anchoring, production apply, answer replacement, Agent751/752/753 launch, scheduler mutation, workbook write, external write, or owner approval request.

## Current Gate Summary

CodeCaptain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer/Code_Captain_10.05.2026_12_35_59.md`

Answer SHA256:

`154e179a59a19f35605c154efcb1c7aea95717868e791b762291665b9eb4a0e4`

Answer mtime:

`2026-05-10T12:36:07+0500`

Answer decision token:

`GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`

Current readiness errors:

- `production_db_sha_mismatch`
- `protected_workbook_sha_mismatch`

The missing-answer gate is clear. The launch gate is still blocked by the current DB/workbook boundary.

## Boundary Summary

| Surface | Reviewed Agent750 pack SHA | Current SHA | Current mtime | Status |
|---|---|---|---|---|
| `db/app.db` | `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64` | `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156` | `2026-05-10T11:12:22+0500` | `BLOCKED` |
| `excel_ui/SALES_KSP_CRM_V3.xlsx` | `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c` | `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75` | `2026-05-10T11:07:20+0500` | `BLOCKED` |

`lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx` returned no rows at collection time; no active holder was observed.

Proof-window lock expected state: absent.

## DB Integrity And Shape

Read-only DB checks:

- `pragma integrity_check`: `ok`
- table count: `112`
- `fact_orders_kaspi` count: `34205`
- `dim_kaspi_article_map` count: `3757`
- `page_count`: `62251`
- `freelist_count`: `0`
- `schema_version`: `43286`

## Workbook Read-Only Open

The protected workbook opened read-only with `openpyxl`.

Observed workbook facts:

- sheets include `M02_SKU_CATALOG_NC`, `pivot`, `Price Brackets`, and `SALES_KSP_CRM_1`
- `M02_SKU_CATALOG_NC`: `913x36`
- `pivot`: `1375x62`
- `Price Brackets`: `229x16`
- ZIP entries: `88`
- `xl/workbook.xml` SHA256: `f09090d7b22ff5ac65fbdab38873d791997574686a65192c22c5077e256a33e3`
- `xl/worksheets/sheet1.xml` SHA256: `126306c8e9658af9ed4b1fa80515cef79ecb110e483ccfd3484bde2c00500523`
- `docProps/core.xml` SHA256: `82ac412218acef918da4574667f35de6dda4176b22a2ac524c4170f05df49c38`
- `docProps/app.xml` SHA256: `0b8d6a6300e5e8e760a2df0f608d0e0c3d26189b513773505929fcef50e19cc5`
- ZIP content SHA256: `97dfa4ede3c83c8784d167a964a4c49d301f71600a7838f08c4fb47b64d8a11e`

## Backup Chain

| Snapshot | SHA256 | Size bytes | Mtime |
|---|---:|---:|---|
| `runtime/backups/app_db_before_activeorders_enrich_20260510_110212.sqlite` | `660baaee643f4ccd3890bee94049ef93398c73c8c777e1100a48d3bb0d15e011` | `254980096` | `2026-05-10T11:02:13+0500` |
| `runtime/backups/app_db_before_workbook_catalog_map_sync_20260510_111219.sqlite` | `b5b2663511de45ece6b084b0a95bce0f358a18cf3b138ddb8c460791b7d7964d` | `254980096` | `2026-05-10T11:12:20+0500` |
| `runtime/backups/app_db_before_crm_identity_rebuild_20260510_111221.sqlite` | `c92ad89d66d43aaa43cc4a5ab00f96fed5e07979df9d154746e494ea5b86490c` | `254980096` | `2026-05-10T11:12:22+0500` |
| `db/app.db` | `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156` | `254980096` | `2026-05-10T11:12:22+0500` |

## Scheduled Refresh Evidence

Read-only report/log files indicate the current DB drift came from the 11:00 Kaspi import / ActiveOrders / workbook catalog / CRM identity chain:

- `~/Docs/Autonomous_business/exports/google_ops_board/2026-05-10/enrich_kaspi_orders_from_activeorders_20260510_110213.json`
- `~/Docs/Autonomous_business/exports/google_ops_board/health/identity_sync/2026-05-10/workbook_catalog_offer_map_sync.json`
- `~/Docs/Autonomous_business/exports/google_ops_board/health/identity_sync/2026-05-10/crm_identity_rebuild.json`
- `~/Docs/Autonomous_business/runtime_logs/kaspi_import_stdout.log`

Report-level changes:

- ActiveOrders enrichment: `candidate_rows=49`, `orders=47`, `updates_applied=49`, `inserts_applied=0`.
- ActiveOrders rows by store: `STOREB=17`, `ACMEWEAR=10`, `UNIVERSAL=22`.
- Workbook catalog offer-map sync: `status=APPLIED`, `candidate_count=4410`, `updated=140`, `inserted=0`, `unchanged=4270`, `skipped=30`.
- CRM identity rebuild: `status=APPLIED`, `grouped_keys=771`, `updated=20`, `inserted=0`, `skipped=550`, `skipped_fk=201`.
- Kaspi import log around 11:01 reported ActiveOrders rows `49`, stores synced `5`, total orders inserted `5`, total orders updated `604`, workbook backup `CRM_backup_20260510_110355.xlsx`, and saved `SALES_KSP_CRM_V3.xlsx`.

Evidence gap: a fresh repository-local search did not locate `CRM_backup_20260510_110355.xlsx` under `~/Docs/Autonomous_business`. Treat that as an evidence gap to preserve, not as proof the backup never existed.

## Read-Only Content Diff

Full table-content hashing across the 11:02/11:12 DB chain found content drift in only:

- `fact_orders_kaspi`
- `dim_kaspi_article_map`

Table hashes:

| Table | before ActiveOrders | before workbook map | before CRM rebuild | current |
|---|---|---|---|---|
| `fact_orders_kaspi` | `34205:9a2952fea0631f23b1daaa6c17c6d26e1538a3dacdf14b76c64e3e07f471a893` | `34205:99a4f656332cecccf65279da1525da58298f63ea046156cb450f08fc0a0f0340` | `34205:99a4f656332cecccf65279da1525da58298f63ea046156cb450f08fc0a0f0340` | `34205:99a4f656332cecccf65279da1525da58298f63ea046156cb450f08fc0a0f0340` |
| `dim_kaspi_article_map` | `3757:6c9c99c2fcb6dd0d679479db2d497fde63adb0c3b948b1f8333aa5309249c300` | `3757:6c9c99c2fcb6dd0d679479db2d497fde63adb0c3b948b1f8333aa5309249c300` | `3757:177a98a19eda19d58492a9943a059247fa1bae235eac6590884838963c0d3fe3` | `3757:25c423b0a68440c9b580b61afb5695105d77fad86f3abc6bcf6f180fbb0f28d5` |

Row-level digest comparison by primary key:

| Step | Table | Inserted | Deleted | Updated |
|---|---|---:|---:|---:|
| ActiveOrders enrichment | `fact_orders_kaspi` | `0` | `0` | `49` |
| Workbook catalog map sync | `dim_kaspi_article_map` | `0` | `0` | `74` |
| CRM identity rebuild | `dim_kaspi_article_map` | `0` | `0` | `20` |

No other table content drift was found in the 11:02/11:12 chain.

## Commands Run

```bash
python3 scripts/check_agent750_launch_readiness.py
python3 scripts/report_agent750_next_action.py --json-only
python3 scripts/build_agent750_stopline_checkpoint.py --refresh-current-surfaces
shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx ~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer/Code_Captain_10.05.2026_12_35_59.md
stat -f '%Sm %z %N' -t '%Y-%m-%dT%H:%M:%S%z' db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
sqlite3 'file:db/app.db?mode=ro' 'pragma integrity_check;'
```

Additional read-only Python probes inspected the workbook as ZIP/openpyxl, computed DB table hashes, and compared row digests across backup snapshots.

## Review Requirement

This triage supports the conclusion that the DB drift is narrow and appears tied to scheduled/import activity, while the protected workbook also changed and must be reviewed on its own terms.

Before Agent751/752/753 launch, a reviewer must explicitly decide whether to:

- re-anchor Agent750 readiness to current DB SHA `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156` and workbook SHA `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`;
- rebuild/re-send a refreshed Agent750/CodeCaptain pack for the current DB/workbook boundary; or
- stop and investigate further.

Until that decision is recorded and `scripts/check_agent750_launch_readiness.py` returns `ok=true`, the launch remains blocked.
