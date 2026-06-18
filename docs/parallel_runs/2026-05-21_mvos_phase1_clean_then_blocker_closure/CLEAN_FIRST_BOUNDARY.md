# CLEAN_FIRST_BOUNDARY

Status: CLEAN_FIRST_RECORDED_NOT_PRODUCTION_CLEAN
Created: 2026-05-21 22:21 +05
Repo: `~/Docs/Autonomous_business`
Branch: `codex/TASK-webui-archive-single-truth-v1`
HEAD: `118c5fae2f14fc4b7998af39a393d075792aa5b7`

This is the clean-first boundary before Phase 1 bounded blocker-closure agents. It records and groups the dirty repo state so agents do not confuse uncommitted work with production readiness.

## Clean-First Decision

The repo was not blindly committed, stashed, reverted, or reset.

Reason: the dirty tree spans mutable logs, authority docs, configs, validators, source materializers, imports, current docs, and run/handoff history. A blind commit or stash would be faster on paper but unsafe because it could hide protected-adjacent changes or bundle unrelated owner/operator work.

Clean-first here means:

1. Dirty state is recorded and grouped.
2. Protected DB tracking and write-side gating are verified.
3. Phase 1 agents are launched with a strict read-only/copied-temp boundary.
4. Production work remains blocked until a later logical commit/park/cleanup lane resolves the dirty tree.

## Current Dirty State

- `git status --short` row count: `94`
- Modified tracked files: `41`
- `git diff --stat`: `5946 insertions`, `119 deletions`
- Current docs layer is present under `docs/current/`
- Active Phase 0 closeout: `docs/parallel_runs/2026-05-21_mvos_phase0_canonical_route/PHASE0_CLOSEOUT.md`

## Protected-Surface Checks

| check | result |
| --- | --- |
| `./scripts/check_no_db_tracked.sh` | PASS, `DB guard OK (no tracked/staged .db files).` |
| `python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml` | PASS, `WRITE_SIDE_GATING PASS`, `checked_count=35` |

## Phase 1 Boundary

Allowed for Phase 1 agents:

- read repo files and local evidence;
- read `~/Docs/Web_automation` only when needed for ads/source context;
- create copied DBs under their assigned out-of-repo evidence folders;
- run read-only and copied-temp validators;
- write assigned closeouts and local evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/`;
- run completion helper for tmux orchestration markers.

Forbidden for Phase 1 agents:

- production DB writes;
- workbook writes;
- scheduler/LaunchAgent/cron changes;
- source-pointer writes;
- WebUI/API/Kaspi/external mutations;
- Web_automation writes;
- ad-platform writes or spend changes;
- bank/cash movement;
- supplier payment;
- PO commitment;
- stock or price changes;
- owner publication;
- production preflight;
- production apply;
- editing repo implementation files or `.claude/*`.

## Phase 1 Launch Rule

Agents may call a blocker `GREEN` only when the relevant copied-temp/local validator proof actually passes and protected surfaces remain unchanged.

If source evidence is missing, stale, ambiguous, or owner-dependent, the correct gate is `YELLOW`, with the exact missing source or owner request.

If protected surfaces drift or authority conflicts appear, the correct gate is `RED`.
