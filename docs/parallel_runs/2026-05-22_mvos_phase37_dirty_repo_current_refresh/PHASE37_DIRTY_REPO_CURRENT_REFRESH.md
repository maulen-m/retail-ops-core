# PHASE37_DIRTY_REPO_CURRENT_REFRESH

Gate: `YELLOW`

Completed: `2026-05-22`
Evidence root: `exports/validation/mvos_phase37_dirty_repo_current_refresh/20260522_055629`

This is a non-production readiness refresh for `B010_dirty_repo_state`. It does not commit, revert, stage, reset, clean, production-apply, mutate protected DB/workbook surfaces, change schedulers, write source pointers, write external systems, or authorize owner publication.

## Why This Lane Exists

Phase22 refreshed the dirty-state board to `342` full `git status --porcelain=v1 -uall` entries. Phases 34, 35, and 36 added additional review docs, evidence, and Oracle-pack drafts. Production-readiness decisions should use the current dirty-state boundary, not the older Phase22 count.

## Current Snapshot

Measured with `git status --porcelain=v1 -uall`:

- `374` total status entries.
- `48` modified tracked files.
- `326` untracked paths/files.
- `48` tracked files changed in `git diff --name-status`.
- `git diff --stat`: `48 files changed, 6805 insertions(+), 151 deletions(-)`.

`git status --short` without `-uall` reports `141` collapsed entries.

The `-uall` count remains the production-readiness count because untracked starter packs, phase docs, local imports, and evidence pointers must be visible before any cleanup, preflight, release, or production-write lane.

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
| `other` | `??` | `5` | `imports/webui_archive_manual/17.05.2026_09_54_42/...`; plus local pack-sidecar/evidence additions not yet categorized |
| `phase_run_docs` | `??` | `154` | `docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/AGENT851_LAUNCH_CLOSEOUT.md`; `docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/CODECAPTAIN_PACK_CLOSEOUT.md`; `docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/CODECAPTAIN_PROMPT_MVOS_REPAIR_ROUND2.md` |
| `scripts_validators_materializers` | `M` | `17` | `scripts/generate_po_dashboard_data.py`; `scripts/materialize_c3_policy_state.py`; `scripts/materialize_policy_source_freshness.py` |
| `scripts_validators_materializers` | `??` | `4` | `scripts/materialize_copied_temp_source_freshness_bridge.py`; `scripts/materialize_merchant_cabinet_offer_availability.py`; `scripts/validate_mvos_source_contract_registry.py` |
| `starter_packs` | `??` | `135` | `docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`; `docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/01_AGENT_COGS__CHILDSUM_BUNDLE_COGS_CONTRACT__ROOT.md`; `docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md` |
| `tests` | `M` | `14` | `tests/test_ads_active_scope.py`; `tests/test_cogs_integrity_validator.py`; `tests/test_day_complete_validator.py` |
| `tests` | `??` | `3` | `tests/test_generate_po_dashboard_data_help_no_write.py`; `tests/test_materialize_merchant_cabinet_offer_availability.py`; `tests/test_mvos_source_contract_registry_validator.py` |
| `validation_docs` | `M` | `3` | `docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`; `docs/validation/DAY_COMPLETE_CONTRACT.md`; `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md` |

Machine-readable group counts:

`exports/validation/mvos_phase37_dirty_repo_current_refresh/20260522_055629/dirty_state_group_counts.csv`

## Delta From Phase22

Phase22 measured:

- `342` total `git status --porcelain=v1 -uall` entries.
- `46` modified tracked files.
- `296` untracked paths/files.
- `46` tracked files changed in `git diff --name-status`.
- `6724` insertions and `148` deletions across tracked files.

Current Phase37 boundary:

- `374` total entries, up by `32`.
- `48` modified tracked files, up by `2`.
- `326` untracked paths/files, up by `30`.
- `48` tracked files changed in `git diff --name-status`, up by `2`.
- `6805` insertions and `151` deletions across tracked files, up by `81` insertions and `3` deletions.

This growth is expected from Phase34/35/36 local review docs, evidence references, and current source-map refresh. It is still a production stopline, not a cleanup failure.

## Cleanup Split Recommendation

Do not execute this split from Phase37. It is the current cleanup map for a later explicit commit/park lane.

1. Keep current CodeCaptain review boundary first; do not clean/commit in a way that hides retained blockers.
2. Commit or review canonical current docs and contracts together after the current boundary is accepted.
3. Commit source-contract/C3/write-side gate code and tests as one serialized code lane after focused tests pass.
4. Commit WebUI/status/day-complete route code and tests as one serialized code lane after focused tests pass.
5. Commit PO/single-truth/order-entry/COGS/offer-linkage route code and tests as one or two serialized code lanes after focused tests pass.
6. Commit ads active-scope truth separately.
7. Park or archive starter packs and phase run docs separately so code review is not buried under evidence volume.
8. Park or commit mutable `.claude/*` state last.
9. Review local imports/manual evidence before committing; keep them out of code commits unless repo policy requires tracked evidence.

## Board Decision

`B010_dirty_repo_state` remains `STOP for production`.

Progress made: the dirty-state board now reflects the current state after Phase36. No cleanup, commit, revert, production-preflight, or production-readiness claim was made.

## Verification Inputs

- `git_status_porcelain_uall.txt`
- `git_status_short_collapsed.txt`
- `git_diff_name_status.txt`
- `git_diff_stat.txt`
- `dirty_state_summary.json`
- `dirty_state_group_counts.csv`
- `protected_surface_git_status_start.txt`
- `protected_surface_sha256_start.tsv`
