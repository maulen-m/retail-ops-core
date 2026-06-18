# PHASE45_CODECAPTAIN_RUNWAY_ADDENDUM

Status: `YELLOW_REVIEW_ADDENDUM_DRAFT`
Created: `2026-05-22`

This phase creates a small CodeCaptain addendum to the existing Phase42 review pack. It does not create a new bulky Oracle pack because the local repo volume is critically low. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, production apply, copied DB creation, or evidence deletion.

## Current Review Surface

Base review packet:

`~/Docs/Oracle/Autonomous_business/2026-05-22/062954_TASK-000_mvos-phase42-codecaptain-review-pack-refresh`

Add this Phase45 addendum beside it when asking CodeCaptain to review the current route:

- `docs/parallel_runs/2026-05-22_mvos_phase43_disk_runway_cleanup_route/PHASE43_DISK_RUNWAY_CLEANUP_ROUTE.md`
- `docs/parallel_runs/2026-05-22_mvos_phase44_runroot_gated_continuation/PHASE44_RUNROOT_GATED_CONTINUATION.md`
- `docs/parallel_runs/2026-05-22_mvos_phase45_codecaptain_runway_addendum/CODECAPTAIN_PHASE45_RUNWAY_ADDENDUM_PROMPT.md`
- `docs/parallel_runs/2026-05-22_mvos_phase45_codecaptain_runway_addendum/PHASE45_CODECAPTAIN_RUNWAY_ADDENDUM.md`

## Live Stopline

Combined preflight on the current repo run root:

```bash
python3 scripts/preflight_copied_temp_wave.py \
  --run-root ~/Docs/Autonomous_business \
  --min-free-gib 3 \
  --cleanup-manifest docs/parallel_runs/2026-05-22_mvos_phase43_disk_runway_cleanup_route/manifests/FIRST_DB_CLEANUP_BATCH_PROPOSAL.tsv \
  --json
```

Current result:

```json
{
  "ok": false,
  "status": "FAIL_PRECHECK",
  "validation_disk_runway": "FAIL_LOW_DISK_RUNWAY",
  "free_gib": 0.175,
  "cleanup_manifest_dry_run": "PASS",
  "cleanup_eligible_count": 16,
  "cleanup_blocked_count": 0,
  "cleanup_eligible_mib": 3920.0,
  "db_guard": "PASS",
  "source_contract_registry": "PASS"
}
```

Copied DB helper dry-run:

```bash
python3 scripts/create_copied_temp_db.py \
  --source-db db/app.db \
  --run-root ~/Docs/Autonomous_business \
  --db-name app_copied_temp.db \
  --min-free-gib 3 \
  --json
```

Current result:

```json
{
  "ok": false,
  "status": "FAIL_PRECOPY_CHECK",
  "source_size_bytes": 256561152,
  "required_free_before_copy": 3477786624,
  "free_gib": 0.175,
  "errors": [
    "FAIL_LOW_DISK_RUNWAY",
    "insufficient_post_copy_runway"
  ],
  "mode": "DRY_RUN"
}
```

`df -h .` showed approximately `180 MiB` free after the latest checks.

## What Is Reviewable Now

- Phase42 remains the current business retained-blocker review packet.
- Phase43 adds an owner-approval-gated cleanup route for non-production copied DB artifacts under `exports/validation`.
- Phase44 adds run-root-aware preflight and a copied DB helper so future copied-temp waves can use either cleaned local evidence space or an existing larger external/alternate run root.
- The new helper refuses to copy when the chosen run root cannot preserve the required post-copy runway.

## Exact Decision Needed From CodeCaptain

Ask CodeCaptain to review:

1. Whether Phase43 local evidence cleanup is an acceptable next non-production unblocker before more copied-temp proof work.
2. Whether Phase44/45 run-root preflight plus `create_copied_temp_db.py` is sufficient as the required start gate for the next serialized copied-temp integrator.
3. Whether the next wave should require `3 GiB` minimum free space or a stricter `8-10 GiB` minimum because C3 materializers and backup-producing scripts can grow quickly.
4. Whether future agents should be required to use `scripts/create_copied_temp_db.py` instead of ad hoc `cp`/`shutil.copy` commands for copied DB setup.
5. Whether any production-preflight discussion must remain blocked until a fresh copied-temp proof wave passes under this new gate.

## Recommended Local Route Before CodeCaptain Answers

Do not start another copied DB proof wave on the current repo volume.

Safe next local actions are only:

- keep the Phase42 review pack as the base packet;
- send this Phase45 addendum with Phase43/44 docs as a small supplemental review surface;
- wait for owner cleanup approval or provide an existing larger run root;
- then rerun `preflight_copied_temp_wave.py` and `create_copied_temp_db.py` before any copied-temp materialization.

## Gate

`YELLOW_REVIEW_ADDENDUM_DRAFT`

Reason: this phase improves the review/launch contract, but no copied DB was created and no business retained blocker was cleared.
