# DB Boundary Drift Triage - Agent750 - 2026-05-10 07:29 +05

Status: `READ_ONLY_TRIAGE_COMPLETE_REVIEW_STILL_REQUIRED`

## Purpose

This artifact records the read-only evidence for the production DB SHA drift that now blocks the Agent750 -> Agent751/752/753 validate-only launch path.

It does not authorize re-anchoring, production apply, answer import, or Agent751/752/753 launch.

## Boundary Summary

Reviewed Agent750-pack DB SHA:

`dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`

Current production DB SHA:

`17de45128748e9db195c71f956d1a5713a6062f430a6eccaf42bc9084fc44828`

Current production DB mtime:

`2026-05-10T07:02:15+0500`

Current launch readiness errors:

- `missing_codecaptain_answer_file`
- `production_db_sha_mismatch`

## Backup Chain

| Snapshot | SHA256 | Size bytes | Mtime |
|---|---:|---:|---|
| `runtime/backups/app_db_before_activeorders_enrich_20260510_070211.sqlite` | `af8149a863a044e8395f53c9d405434b47842be9c23704e3978ea8deed9e23e2` | `254959616` | `2026-05-10 07:02:12 +0500` |
| `runtime/backups/app_db_before_workbook_catalog_map_sync_20260510_070212.sqlite` | `70a59800cbf7c9861cffdaf12fdb27cfc718762c6fae74c23d38f933cf66e8b8` | `254980096` | `2026-05-10 07:02:13 +0500` |
| `runtime/backups/app_db_before_crm_identity_rebuild_20260510_070214.sqlite` | `1a542e3162ceb65171e0295c178020df48f7f15ba10e0cee06e370d27fc5d4ba` | `254980096` | `2026-05-10 07:02:15 +0500` |
| `db/app.db` | `17de45128748e9db195c71f956d1a5713a6062f430a6eccaf42bc9084fc44828` | `254980096` | `2026-05-10 07:02:15 +0500` |

## Scheduled Refresh Reports

Read-only report files indicate the drift came from the scheduled 07:00 Google Ops Board / ActiveOrders / Kaspi refresh path:

- `~/Docs/Autonomous_business/exports/google_ops_board/2026-05-10/enrich_kaspi_orders_from_activeorders_20260510_070212.json`
- `~/Docs/Autonomous_business/exports/google_ops_board/health/identity_sync/2026-05-10/workbook_catalog_offer_map_sync.json`
- `~/Docs/Autonomous_business/exports/google_ops_board/health/identity_sync/2026-05-10/crm_identity_rebuild.json`
- `~/Docs/Autonomous_business/runtime_logs/google_ops_board_publish_stdout.log`
- `~/Docs/Autonomous_business/runtime_logs/google_ops_board_publish_stderr.log`

Report-level changes:

- ActiveOrders enrichment: `updates_applied=43`, `inserts_applied=2`.
- Workbook catalog offer-map sync: `status=APPLIED`, `updated=140`, `inserted=0`.
- CRM identity rebuild: `status=APPLIED`, `updated=20`, `inserted=0`.

## Read-Only Content Diff

All table row counts across the backup chain and current DB changed in only one table:

| Table | before ActiveOrders | before workbook map | before CRM rebuild | current |
|---|---:|---:|---:|---:|
| `fact_orders_kaspi` | `34198` | `34200` | `34200` | `34200` |

Full table-content hashing found only two tables with content drift:

| Table | before ActiveOrders | before workbook map | before CRM rebuild | current |
|---|---|---|---|---|
| `fact_orders_kaspi` | `34198:fd4796c1eec47c27acec2d51293111787e6a0abd5808375f16138165b87a6f61` | `34200:dd1913c1b074f71eccbd80a186edfcea79082afc701dd5be09337055b7b35aa8` | `34200:dd1913c1b074f71eccbd80a186edfcea79082afc701dd5be09337055b7b35aa8` | `34200:dd1913c1b074f71eccbd80a186edfcea79082afc701dd5be09337055b7b35aa8` |
| `dim_kaspi_article_map` | `3757:0c3b11467c001bf416f0dc9180c238840fd887348aebff7dbb6b9aa41a89abff` | `3757:0c3b11467c001bf416f0dc9180c238840fd887348aebff7dbb6b9aa41a89abff` | `3757:8da817987afebd61255896ab5d0bcaac7c3b10dae418119e4e7e8544cc32db6f` | `3757:6c9c99c2fcb6dd0d679479db2d497fde63adb0c3b948b1f8333aa5309249c300` |

Row-level digest comparison by table primary key:

| Step | Table | Inserted | Deleted | Updated |
|---|---|---:|---:|---:|
| ActiveOrders enrichment | `fact_orders_kaspi` | `2` | `0` | `43` |
| ActiveOrders enrichment | `dim_kaspi_article_map` | `0` | `0` | `0` |
| Workbook catalog map sync | `fact_orders_kaspi` | `0` | `0` | `0` |
| Workbook catalog map sync | `dim_kaspi_article_map` | `0` | `0` | `74` |
| CRM identity rebuild | `fact_orders_kaspi` | `0` | `0` | `0` |
| CRM identity rebuild | `dim_kaspi_article_map` | `0` | `0` | `20` |

The workbook catalog report counted `updated=140`; primary-key content hashing observed `74` rows with changed serialized content. Treat the report count as operator-script output and the digest count as row-content-diff evidence; a reviewer should decide which granularity matters for re-anchoring.

## Commands Run

```bash
shasum -a 256 db/app.db runtime/backups/app_db_before_activeorders_enrich_20260510_070211.sqlite runtime/backups/app_db_before_workbook_catalog_map_sync_20260510_070212.sqlite runtime/backups/app_db_before_crm_identity_rebuild_20260510_070214.sqlite
ls -lT db/app.db runtime/backups/app_db_before_activeorders_enrich_20260510_070211.sqlite runtime/backups/app_db_before_workbook_catalog_map_sync_20260510_070212.sqlite runtime/backups/app_db_before_crm_identity_rebuild_20260510_070214.sqlite
sqlite3 'file:db/app.db?mode=ro' "select count(*) from sqlite_master where type='table';"
python3 -m json.tool exports/google_ops_board/2026-05-10/enrich_kaspi_orders_from_activeorders_20260510_070212.json
python3 -m json.tool exports/google_ops_board/health/identity_sync/2026-05-10/workbook_catalog_offer_map_sync.json
python3 -m json.tool exports/google_ops_board/health/identity_sync/2026-05-10/crm_identity_rebuild.json
```

Additional read-only Python one-liners computed row counts, table-content hashes, and primary-key row digest deltas using `sqlite3.connect("file:<path>?mode=ro", uri=True)`.

## Review Requirement

This triage supports the conclusion that the DB drift is narrow and appears scheduled/expected, but it does not by itself clear `production_db_sha_mismatch`.

Before Agent751/752/753 launch, a reviewer must explicitly decide whether to:

- re-anchor Agent750 readiness to current DB SHA `17de45128748e9db195c71f956d1a5713a6062f430a6eccaf42bc9084fc44828`,
- rebuild/re-send a refreshed CodeCaptain pack for the current DB boundary, or
- stop and investigate further.

Until that decision is recorded and `scripts/check_agent750_launch_readiness.py` returns `ok=true`, the launch remains blocked.
