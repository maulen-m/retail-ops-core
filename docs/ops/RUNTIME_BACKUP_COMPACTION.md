# Runtime Backup Compaction

## Purpose

`scripts/compact_runtime_backups.py` creates lossless `.zst` replacements for old SQLite backup files. It is disk relief, not a retention policy: every source remains recoverable byte for byte, and no fresh or active database is eligible.

## Safety Contract

- Inventory is the default and writes nothing.
- Apply requires both `--apply` and `ENABLE_RUNTIME_BACKUP_COMPACTION=1`.
- Eligible sources are regular, non-symlink `.db`, `.sqlite`, or `.sqlite3` files older than the explicit age threshold.
- One root-level nonblocking lock prevents concurrent compaction.
- A source is removed only after `zstd -t`, decompressed SHA-256 equality, atomic archive placement, and an adjacent `.manifest.json` restore record.
- Existing archives or sidecars cause a visible skip; they never cause source deletion.
- Each completed replacement is also appended to `compaction_manifest.jsonl`.
- Run compaction outside the end-of-day and backup windows. The current protected window is `20:30-21:10 Asia/Almaty`.

## Dry Run

```bash
python3.12 scripts/compact_runtime_backups.py compact \
  --root ~/Docs/Autonomous_business/runtime/backups \
  --older-than-days 30 \
  --max-files 20 \
  --target-free-percent 20 \
  --json
```

## Bounded Apply

Start with one file, inspect the report and adjacent manifest, perform a restore drill, and only then raise `--max-files`.

```bash
ENABLE_RUNTIME_BACKUP_COMPACTION=1 \
python3.12 scripts/compact_runtime_backups.py compact \
  --root ~/Docs/Autonomous_business/runtime/backups \
  --older-than-days 30 \
  --max-files 1 \
  --target-free-percent 20 \
  --apply \
  --json
```

## Restore Drill

Use a new output path for drills. Do not overwrite an existing backup unless the operator has separately verified why that is required.

```bash
ENABLE_RUNTIME_BACKUP_RESTORE=1 \
python3.12 scripts/compact_runtime_backups.py restore \
  --archive /absolute/path/to/backup.sqlite.zst \
  --output /absolute/path/to/restore-drill/backup.sqlite \
  --apply \
  --json
```

The restored SHA-256 must equal `original_sha256` in the adjacent manifest.

## Stop Conditions

Stop if the lock is held, `zstd` verification fails, decompressed SHA differs, the destination already exists, a scheduled writer or backup is active, or disk free space falls instead of rising. Preserve both source and any generated archive for diagnosis.
