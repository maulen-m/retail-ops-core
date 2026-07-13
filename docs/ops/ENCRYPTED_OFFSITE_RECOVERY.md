# Encrypted Offsite Recovery

## Current Recovery Route

- Backend transport: the existing `gdrive2:` rclone remote.
- Encryption and repository format: restic.
- Repository: `rclone:gdrive2:Autonomous_business_backups/restic_critical_shipping_m1`.
- Password source: macOS Keychain generic-password service `Autonomous_business_restic_gdrive2`, account `adil`.
- Credential values must never appear in Git, LaunchAgents, shell history, reports, or evidence bundles.

Restic encrypts file contents, paths, and metadata before rclone sends repository objects. Google Drive never receives plaintext DB, workbook, order evidence, or credential files from this route.

## Operator Environment

```bash
export RESTIC_PASSWORD_COMMAND='/usr/bin/security find-generic-password -a adil -s Autonomous_business_restic_gdrive2 -w'
export RESTIC_REPOSITORY='rclone:gdrive2:Autonomous_business_backups/restic_critical_shipping_m1'
```

Do not export the password itself.

## Backup

Back up only a verified, owner-only checkpoint. Do not point restic directly at a live SQLite file or an unredacted scheduler/credential snapshot.

```bash
restic backup /absolute/path/to/verified-checkpoint \
  --host M1 \
  --tag daily-shipping
```

## Verification

```bash
restic snapshots --host M1 --tag daily-shipping
restic check
```

Repository success is not recovery proof. Restore the DB into a new owner-only directory, compare SHA-256 with the checkpoint manifest, and run SQLite integrity:

```bash
restic restore <snapshot-id> \
  --target /absolute/path/to/restore-drill \
  --include '/absolute/checkpoint/path/data/app.db.sqlite'

openssl dgst -sha256 /absolute/checkpoint/path/data/app.db.sqlite
openssl dgst -sha256 /absolute/restored/path/data/app.db.sqlite
sqlite3 /absolute/restored/path/data/app.db.sqlite 'PRAGMA quick_check;'
```

## Proven Baseline

The 2026-07-13 rescue produced encrypted snapshot `8587bb24` from the verified M1 shipping checkpoint. A cloud restore onto the external drive produced an exact matching DB SHA-256 and `PRAGMA quick_check = ok`. The run closeout contains the full local evidence paths.

## Provider Strategy

This Google Drive lane is immediate off-machine recovery, not the final compute host. Benchmark Hetzner Helsinki and UpCloud Helsinki separately after local reproducibility is stable. Paid resource creation and any live compute cutover require their own owner-approved GREEN packet; M1/M5 one-writer rules still apply.
