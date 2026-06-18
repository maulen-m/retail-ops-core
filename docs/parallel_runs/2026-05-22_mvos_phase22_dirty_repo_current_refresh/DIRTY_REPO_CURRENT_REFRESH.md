# Phase 22 Dirty Repo Current Refresh

Gate: `YELLOW`

Completed: `2026-05-22T03:41:54+0500`

This is a non-production readiness refresh for `B010_dirty_repo_state`. It does
not commit, revert, stage, reset, production-apply, mutate protected
DB/workbook surfaces, change schedulers, write source pointers, write external
systems, or authorize owner publication.

## Why This Lane Exists

Phase 9 made the dirty state reviewable, but later Phase 20 and Phase 21 local
docs changed the current count. A stale dirty-state number is not dangerous by
itself, but it slows cleanup because every later agent has to rediscover what
changed. This refresh updates the current blocker board and keeps production
preflight blocked.

## Current Snapshot

Measured with `git status --porcelain=v1 -uall`:

- `342` total status entries.
- `46` modified tracked files.
- `296` untracked paths/files.
- `46` tracked files changed in `git diff --name-status`.
- `git diff --stat`: `6724` insertions, `148` deletions across tracked files.

`git status --short` without `-uall` reports `124` collapsed entries:

- `46` modified tracked paths.
- `78` collapsed untracked paths.

The `-uall` count is the production-readiness count because untracked starter
packs and evidence folders must be visible before any cleanup, preflight, or
release action.

## Current Dirty-State Group Counts

| group | status | count | examples |
| --- | --- | ---: | --- |
| `canonical_current_docs` | `??` | `9` | `docs/current/CURRENT_AGENT_OPERATING_CONTRACT.md`; `docs/current/CURRENT_ARCHITECTURE_MAP.md`; `docs/current/CURRENT_AUTHORITY_INDEX.md` |
| `config_boundaries` | `M` | `3` | `config/ads_active_scope.yaml`; `config/anchors/kaspi_webui_archive_downloads.json`; `config/write_side_gating_manifest.yaml` |
| `contracts` | `??` | `14` | `docs/contracts/MVOS_10_OUT_OF_10_CODECAPTAIN_REVIEW_PROMPT.md`; `docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`; `docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT_DRAFT.md` |
| `core_policy_validation` | `M` | `4` | `core/excel/dim_sku_light_parser.py`; `core/ops/policy_materialization_c3.py`; `core/ops/policy_registry_c3.py` |
| `inventory_docs` | `M` | `2` | `docs/inventory/INBOUND_CALENDAR_V10_002_PO_PART_TRANSITION_2026-02-07.md`; `docs/inventory/Sales_Data_Model_V16.md` |
| `local_imports` | `??` | `1` | `imports/webui_archive_manual/17.05.2026_18_26_58/Acmewear/ArchiveOrders.xlsx` |
| `marketing_docs` | `??` | `1` | `docs/marketing/STOREB_ADS_CAMPAIGN_MANUAL_STOP_20260520_094641.md` |
| `mutable_state` | `M` | `5` | `.claude/DECISIONS.md`; `.claude/ISSUES.md`; `.claude/PROGRESS.md` |
| `other` | `??` | `5` | `imports/webui_archive_manual/17.05.2026_09_54_42/Acmewear/ArchiveOrders (1).xlsx`; `imports/webui_archive_manual/17.05.2026_09_54_42/storeb/ArchiveOrders (2).xlsx`; `imports/webui_archive_manual/17.05.2026_09_54_42/universal/ArchiveOrders (2).xlsx` |
| `phase_run_docs` | `??` | `129` | `docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/AGENT851_LAUNCH_CLOSEOUT.md`; `docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/CODECAPTAIN_PACK_CLOSEOUT.md`; `docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/CODECAPTAIN_PROMPT_MVOS_REPAIR_ROUND2.md` |
| `scripts_validators_materializers` | `M` | `15` | `scripts/generate_po_dashboard_data.py`; `scripts/playwright/download_kaspi_archive_webui.py`; `scripts/recover_order_entries_from_evidence.py` |
| `scripts_validators_materializers` | `??` | `4` | `scripts/materialize_copied_temp_source_freshness_bridge.py`; `scripts/materialize_merchant_cabinet_offer_availability.py`; `scripts/validate_mvos_source_contract_registry.py` |
| `starter_packs` | `??` | `130` | `docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`; `docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/01_AGENT_COGS__CHILDSUM_BUNDLE_COGS_CONTRACT__ROOT.md`; `docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md` |
| `tests` | `M` | `14` | `tests/test_ads_active_scope.py`; `tests/test_cogs_integrity_validator.py`; `tests/test_day_complete_validator.py` |
| `tests` | `??` | `3` | `tests/test_generate_po_dashboard_data_help_no_write.py`; `tests/test_materialize_merchant_cabinet_offer_availability.py`; `tests/test_mvos_source_contract_registry_validator.py` |
| `validation_docs` | `M` | `3` | `docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`; `docs/validation/DAY_COMPLETE_CONTRACT.md`; `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md` |

## Delta From Phase 9

Phase 9 measured:

- `320` total `git status --porcelain=v1 -uall` entries.
- `44` modified tracked files.
- `276` untracked paths/files.
- `44` tracked files changed in `git diff --name-status`.
- `6633` insertions and `141` deletions across tracked files.

Current boundary:

- `342` total entries, up by `22`.
- `46` modified tracked files, up by `2`.
- `296` untracked paths/files, up by `20`.
- `46` tracked files changed in `git diff --name-status`, up by `2`.
- `6724` insertions and `148` deletions across tracked files.

This growth is expected from Phase 20/21 owner-fact and board-alignment docs
plus this Phase 22 refresh and review prompt. It is still a production
stopline, not a cleanup failure.

## Recommended Next Cleanup Split

Do not execute this split from Phase 22. It is the current cleanup map for a
later explicit commit/park lane.

1. Commit/review canonical docs and contracts together after CodeCaptain accepts
   the current boundary.
2. Commit source-contract/C3/write-side gate code and tests as one serialized
   code lane after focused tests pass.
3. Commit WebUI/status/day-complete route code and tests as one serialized code
   lane after focused tests pass.
4. Commit PO/single-truth/order-entry/COGS/offer-linkage route code and tests
   as one or two serialized code lanes after focused tests pass.
5. Commit ads active-scope truth separately.
6. Park or archive starter packs and phase run docs separately so code review
   is not buried under evidence volume.
7. Park or commit mutable `.claude/*` state last.
8. Review local imports/manual evidence before committing; keep them out of
   code commits unless repo policy requires tracked evidence.

## Board Decision

`B010_dirty_repo_state` remains `STOP for production`.

Progress made: the dirty-state board now reflects the current state. No cleanup
or production-readiness claim was made.

## Oracle Pack

Created for CodeCaptain review:

- `~/Docs/Oracle/Autonomous_business/2026-05-22/034625_TASK-000_mvos-phase22-current-boundary-yellow-review`
- Root file count is `4`.
- Markdown file count is `1`.
- `Answer/` is present and empty.
- Bundle markdown size is `189363` bytes, under the 2 MiB bundle cap.
- Mandatory full-range `ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv` is present.
- Mandatory CSV SHA-256 matches the full-range source
  `~/Docs/Autonomous_business/exports/webui_archive_full_parse_runs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211/final_merged/ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`:
  `e5f4ba4e5cdcf152bf01d7364fbca4d5f213ca83275cbe344cf04052e162db99`.
- Bundle includes Phase22 B010 wording with `342` status entries and `296`
  untracked paths/files.
- Bundle stale-stopline scan found no matches for the three checked stale
  Universal-conflict and premature-production-preflight patterns.

## Verification

Commands run:

```text
git status --porcelain=v1 -uall
git status --short
git diff --name-status
git diff --stat
```

Focused checks after edits:

- `bash scripts/lint_docs.sh` passed.
- `python3` TSV column sanity check passed with `header_cols=8` and
  `tsv_ok=20`.
- `git diff --check -- docs/current/CURRENT_BLOCKER_BOARD.tsv docs/parallel_runs/2026-05-22_mvos_phase22_dirty_repo_current_refresh/DIRTY_REPO_CURRENT_REFRESH.md`
  passed.
- Phase22 final Oracle pack audit passed.
- `python3 scripts/validate_mvos_source_contract_registry.py --strict` passed
  with `contract_count=19`, `active_contract_count=17`, and
  `warning_count=43`.
- Explicit trailing-whitespace scan of touched Phase22 docs and external
  closeout passed.
- `bash scripts/check_no_db_tracked.sh` passed.
