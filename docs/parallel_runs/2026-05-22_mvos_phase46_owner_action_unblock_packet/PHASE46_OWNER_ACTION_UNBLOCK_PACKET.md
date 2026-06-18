# PHASE46_OWNER_ACTION_UNBLOCK_PACKET

Status: `YELLOW_OWNER_ACTION_REQUIRED`
Created: `2026-05-22`

This packet is a tiny owner-action surface for unblocking the next non-production copied-temp MVOS proof wave. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, production apply, copied DB creation, or evidence deletion by itself.

## Current Stopline

The next copied-temp DB proof wave is blocked by local disk runway.

Latest observed state, refreshed `2026-05-22 07:17:02 +05`:

- repo free space: approximately `128 MiB`
- copied DB source size: `256561152` bytes
- required free before copy with `3 GiB` runway: `3477786624` bytes
- Phase43 cleanup dry-run: `16` eligible non-production copied DB artifacts, `0` blocked, approximately `3920.0 MiB` recoverable

## Fastest Safe Owner Choice

Choose exactly one route.

### Route A: Approve Local Evidence Cleanup

Paste this exact phrase if you approve deleting only the first-batch non-production copied DB artifacts listed in the Phase43 cleanup manifest:

```text
I approve local evidence-disk cleanup in Autonomous_business for non-production copied DB files and copied DB backup files under exports/validation only, where SHA/evidence/closeout summaries are preserved. This authorizes deleting copied-temp validation .db artifacts to recover disk runway, with a deletion manifest recorded before removal and protected-surface SHA checks after cleanup. This does not authorize deleting production db/app.db, workbooks, source downloads, CSV/JSON/TXT evidence, closeouts, Oracle packs, source pointers, scheduler files, external data, or any business/production surface.
```

After that approval is pasted, the safe execution sequence is:

```bash
ENABLE_VALIDATION_DB_CLEANUP_DELETE=1 \
python3 scripts/cleanup_validation_db_artifacts.py \
  --manifest docs/parallel_runs/2026-05-22_mvos_phase43_disk_runway_cleanup_route/manifests/FIRST_DB_CLEANUP_BATCH_PROPOSAL.tsv \
  --deletion-manifest-out exports/validation/cleanup_manifests/phase43_first_batch_deleted.tsv \
  --apply \
  --json
```

Then:

```bash
mkdir -p exports/validation/mvos_next_copied_temp_wave/<timestamp>
python3 scripts/preflight_copied_temp_wave.py \
  --run-root exports/validation/mvos_next_copied_temp_wave/<timestamp> \
  --min-free-gib 3 \
  --cleanup-manifest docs/parallel_runs/2026-05-22_mvos_phase43_disk_runway_cleanup_route/manifests/FIRST_DB_CLEANUP_BATCH_PROPOSAL.tsv \
  --json
```

Then, only if preflight passes:

```bash
python3 scripts/create_copied_temp_db.py \
  --source-db db/app.db \
  --run-root exports/validation/mvos_next_copied_temp_wave/<timestamp> \
  --db-name app_copied_temp.db \
  --min-free-gib 3 \
  --manifest-out exports/validation/mvos_next_copied_temp_wave/<timestamp>/copied_temp_db_manifest.json \
  --copy \
  --json
```

### Route B: Provide An Existing Larger Run Root

If you prefer no local evidence cleanup, provide an existing mounted path with enough free space, preferably `8-10 GiB`, and state:

```text
Use this existing path as the copied-temp run root for the next non-production MVOS proof wave: <ABSOLUTE_PATH>. This authorizes local copied-temp DB artifacts and evidence under that path only, with no production DB writes, workbook writes, source-pointer writes, scheduler changes, external writes, WebUI/API/Kaspi mutations, ad-platform writes, cash/PO/stock/price changes, owner publication, production preflight, or production apply.
```

Then the safe sequence is the same preflight and copied DB helper, with `--run-root <ABSOLUTE_PATH>`.

## Gate

`YELLOW_OWNER_ACTION_REQUIRED`

Reason: no copied-temp DB can be created safely on the current repo volume, and no deletion/alternate-run-root authority has been provided yet.
