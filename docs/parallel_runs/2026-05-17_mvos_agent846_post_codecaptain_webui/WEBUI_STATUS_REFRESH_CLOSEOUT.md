# May 17 WebUI Status Refresh Closeout

Generated: `2026-05-17T10:12:48+05:00`

Gate: GREEN

## Scope

Imported the human-provided manual WebUI ArchiveOrders folder as read-only evidence and joined it against the `112` lifecycle/status residual pairs from the May 16 Agent850/Agent851 repair chain.

## Inputs

- Manual source root: `~/Docs/Autonomous_business/imports/webui_archive_manual/17.05.2026_09_54_42`
- Prior residual CSV: `~/Docs/Oracle/Autonomous_business/2026-05-16/182945_TASK-000_mvos-repair-round2-agent846-codecaptain/12_unresolved_pairs_after_fresh_webui.csv`
- CodeCaptain answer: `~/Docs/Oracle/Autonomous_business/2026-05-16/182945_TASK-000_mvos-repair-round2-agent846-codecaptain/Answer/Code Captain_17.05.2026_09_59_38.md`

## Refresh Command

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-05-05 \
  --until 2026-05-17 \
  --stores STOREB,ACMEWEAR,UNIVERSAL \
  --mode import-existing \
  --source-root imports/webui_archive_manual/17.05.2026_09_54_42 \
  --run-id mvos_20260517_webui_status_refresh \
  --strict
```

## Refresh Outputs

- Run summary: `~/Docs/Autonomous_business/exports/webui_archive_source_refresh_runs/mvos_20260517_webui_status_refresh/run_summary.md`
- Run manifest: `~/Docs/Autonomous_business/exports/webui_archive_source_refresh_runs/mvos_20260517_webui_status_refresh/run_manifest.json`
- Integrity report: `~/Docs/Autonomous_business/exports/webui_archive_source_refresh_runs/mvos_20260517_webui_status_refresh/pack_outputs/mvos_20260517_webui_status_refresh_pack/integrity_report.json`
- Final merged CSV: `~/Docs/Autonomous_business/exports/webui_archive_source_refresh_runs/mvos_20260517_webui_status_refresh/final_merged/ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`
- Raw-status profile: `~/Docs/Autonomous_business/exports/validation/mvos_20260517_webui_manual_profile/raw_status_change_profile.md`
- Residual join report: `~/Docs/Autonomous_business/exports/validation/mvos_20260517_webui_status_refresh_residual_join/RESIDUAL_112_JOIN_REPORT.md`
- Residual join CSV: `~/Docs/Autonomous_business/exports/validation/mvos_20260517_webui_status_refresh_residual_join/residual_112_joined_to_20260517_webui.csv`

## Refresh Result

The read-only wrapper passed:

| Check | Result |
|---|---|
| Wrapper status | `PASS` |
| Pack integrity | `PASS` |
| Source files checked | `3` |
| Stores present | `STOREB`, `ACMEWEAR`, `UNIVERSAL` |
| Final merged rows | `1163` |
| Delivered missing `status_change_at` | `0` |
| Duplicate rows | `0` |

## Residual Join Result

The fresh WebUI archive resolved `63` of the previous `112` residual pairs with non-empty WebUI `status_change_at`.

| Resolution | Pairs |
|---|---:|
| Fresh WebUI active status-change evidence | `18` |
| Fresh WebUI shipped status-change evidence | `41` |
| Fresh WebUI cancelled status-change evidence | `4` |
| Still no fresh WebUI hit | `49` |

The original `145` lifecycle/status population is now:

| Source route | Pairs | Agent846 treatment |
|---|---:|---|
| Prior Agent838 WebUI `status_change_at` | `33` | accepted copied-temp WebUI truth |
| Fresh May 17 WebUI `status_change_at` | `63` | accepted copied-temp WebUI truth |
| Remaining active API-backed route | `30` | accepted copied-temp non-WebUI active/current evidence per CodeCaptain |
| Remaining shipped API/courier route | `14` | accepted copied-temp non-WebUI shipped evidence per CodeCaptain |
| Remaining cancellation blocker | `5` | keep blocked unless separate cancellation contract or WebUI evidence appears |

Remaining lifecycle cancellation blockers:

| store_code | order_id | prior_status_detail |
|---|---|---|
| `STOREB` | `915465339` | `CANCELLING` |
| `STOREB` | `919478081` | `CANCELLING` |
| `STOREB` | `919976585` | `CANCELLING` |
| `UNIVERSAL` | `919005528` | `CANCELLING` |
| `UNIVERSAL` | `919681847` | `CANCELLING` |

## Agent846 Launch Decision

Agent846 may now launch under CodeCaptain's `GREEN_TO_LAUNCH_AGENT846_COPIED_TEMP_ONLY` decision, with the updated May 17 WebUI evidence incorporated and the five cancellation rows retained as explicit blockers.

This does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron mutation, external writes, Web_automation writes, Kaspi/API writes, ad-platform writes, bank writes, owner publication/send, cash movement, supplier payment, PO commitment, ad spend, stock changes, price changes, production repair, or treating copied-temp proof as production truth.
