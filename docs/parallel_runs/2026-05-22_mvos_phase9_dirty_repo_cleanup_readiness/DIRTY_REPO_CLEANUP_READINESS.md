# Phase 9 Dirty Repo Cleanup Readiness

Status: `PHASE9_DIRTY_REPO_GROUPED_STOP_FOR_PRODUCTION`
Created: `2026-05-22`

This is a non-production readiness lane for `B010_dirty_repo_state`. It does not commit, revert, stage, reset, production-apply, mutate protected DB/workbook surfaces, change schedulers, write source pointers, write external systems, or authorize owner publication.

## Why This Lane Exists

The current MVOS boundary has useful copied-temp proof, but production preflight is still unsafe while the worktree is broadly dirty. The efficient next step is not to pretend the repo is clean. It is to convert the dirty state into a reviewable split plan so later cleanup can happen quickly and safely.

## Snapshot

Captured evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase9_dirty_repo_cleanup_readiness/agent18_dirty_repo_evidence`

Measured current status:

- `320` total `git status --porcelain=v1 -uall` entries.
- `44` modified tracked files.
- `276` untracked paths.
- `44` tracked files changed in `git diff --name-status`.
- `git diff --stat`: `6633` insertions, `141` deletions across tracked files.

## Dirty-State Group Counts

| group | status | count |
| --- | --- | ---: |
| `canonical_current_docs` | `??` | `9` |
| `config_boundaries` | `M` | `3` |
| `contracts` | `??` | `13` |
| `core_policy_validation` | `M` | `3` |
| `inventory_docs` | `M` | `2` |
| `local_imports` | `??` | `1` |
| `marketing_docs` | `??` | `1` |
| `mutable_state` | `M` | `5` |
| `other` | `??` | `5` |
| `phase_run_docs` | `??` | `110` |
| `scripts_validators_materializers` | `M` | `15` |
| `scripts_validators_materializers` | `??` | `4` |
| `starter_packs` | `??` | `130` |
| `tests` | `M` | `13` |
| `tests` | `??` | `3` |
| `validation_docs` | `M` | `3` |

## Recommended Split Order

This is a commit/park plan only. Do not execute commits from this lane without a later explicit cleanup action.

| order | group | action | rationale |
| ---: | --- | --- | --- |
| `1` | Current canonical docs and acceptance contracts | Commit or keep together after review | These define the active route: `docs/current/*`, `docs/contracts/*`, source-contract registry, and 10/10 contract surfaces. |
| `2` | Source contracts, C3 policy, and write-side gates | Commit as one code/test lane after validators pass | Includes C3 policy registry/materialization and write-gating changes; should not be mixed with PO/order-entry code. |
| `3` | WebUI archive, status-ledger, and day-complete route | Commit as one code/test lane after focused tests pass | Includes WebUI archive source refresh wrappers, status-ledger continuity, day-complete validator logic, and related contracts/tests. |
| `4` | PO, single-truth, COGS, order-entry, and offer-linkage route | Commit as one or two code/test lanes | Includes `generate_po_dashboard_data.py`, `sync_po_parts_from_inbound_calendar.py`, PO money gate, order-entry quarantine, COGS validators, offer-linkage evidence, and tests. Split if review burden is too high. |
| `5` | Ads active-scope truth | Commit separately | Ads scope changes have source-truth and business-risk semantics; keep separate from stock/PO/order-entry commits. |
| `6` | Starter packs and phase run docs | Park or commit as documentation archive | Large count (`130` starter files plus `110` phase-run docs). These are useful evidence, but they inflate review noise and should not be mixed with code. |
| `7` | Mutable `.claude/*` state | Usually park or commit last as operational state | Session/progress logs are large and mutable. Keep separate from functional commits. |
| `8` | Local imports and binary/manual evidence | Review before commit | Includes manual WebUI ArchiveOrders source file. Commit only if the repo policy wants local source evidence tracked; otherwise park outside commit. |

## Protected Stoplines

- Do not run production preflight from this state.
- Do not run `git reset`, destructive checkout, or broad cleanup.
- Do not revert unrelated changes.
- Do not stage all files blindly.
- Do not mix source-truth code changes with starter-pack archive docs in the same commit.
- Do not hide the fact that production still waits on CodeCaptain review and retained blockers.

## Exact Evidence Files

- Full status snapshot: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase9_dirty_repo_cleanup_readiness/agent18_dirty_repo_evidence/git_status_porcelain_uall.txt`
- Tracked diff status: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase9_dirty_repo_cleanup_readiness/agent18_dirty_repo_evidence/git_diff_name_status.txt`
- Tracked diff stat: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase9_dirty_repo_cleanup_readiness/agent18_dirty_repo_evidence/git_diff_stat.txt`
- Group counts: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase9_dirty_repo_cleanup_readiness/agent18_dirty_repo_evidence/dirty_group_counts.tsv`

## Board Decision

`B010_dirty_repo_state` remains `STOP for production`.

Progress made: the dirty state is now grouped and ready for a later explicit cleanup/commit/park lane. It is not clean yet.
