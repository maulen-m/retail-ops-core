# Daily Shipping Recovery Automation

Status: candidate, intentionally not installed before the 2026-07-14 employee shipping closeout.

## Purpose

`scripts/manage_daily_shipping_recovery.py` creates a SQLite-consistent snapshot of the minimum daily-shipping recovery state and sends it to the existing encrypted restic repository. The backup candidate runs every 900 seconds, giving the recovery lane a 15-minute target cadence without joining the live order-writing cluster. A separate daily candidate applies retention, so retention failure can never invalidate a successful backup receipt.

The snapshot includes:

- `db/app.db`, copied with SQLite's online backup API and checked with `PRAGMA quick_check`;
- the current CRM workbook, copied and ZIP-validated;
- the shipping-obligation and READY debounce state files when present;
- the current business-date closeout checkpoint when present;
- a SHA-256 and byte-size manifest for every copied artifact.

Snapshot staging and restore targets must be outside the Git repo and are owner-only (`0700`). Staging is removed after every remote attempt. The latest successful remote receipt is recorded at `~/Library/Application Support/Autonomous_business/shipping_recovery/latest_success.json` with mode `0600`.

## Credential Boundary

The tool never reads or prints a credential value. Restic receives a Keychain-backed `RESTIC_PASSWORD_COMMAND` internally and uses the existing repository:

`rclone:gdrive2:Autonomous_business_backups/restic_critical_shipping_m1`

No password, token, buyer data, or environment-file content is written to reports.

## Local Proof

This creates and verifies a local staging snapshot, then removes it when the command exits:

```bash
python3.12 scripts/manage_daily_shipping_recovery.py backup
```

## Activation Gate

Do not install either recovery candidate until all of these are true:

1. The 2026-07-14 employee workflow is ledger-confirmed.
2. The exact tagged release passes its clean-clone gate.
3. One manual encrypted backup and one restore drill pass from the candidate tool.
4. The installed credential scan remains green.
5. M1 remains the only live shipping writer.

The two generated candidates are:

- `config/com.example.daily-shipping-recovery.plist` for encrypted snapshots every 15 minutes;
- `config/com.example.daily-shipping-recovery-retention.plist` for the 03:35 retention pass.

Activation uses the canonical plists only; do not hand-author an installed copy. After installation, update `config/daily_shipping_runtime.json` from `candidate_not_installed` to `active_m1`, regenerate the runtime documentation, and run the installed-drift validator.

## Encrypted Backup

```bash
ENABLE_SHIPPING_RECOVERY_BACKUP=1 \
python3.12 scripts/manage_daily_shipping_recovery.py backup --apply
```

The command is non-concurrent. A second invocation fails while the first holds the owner-only lock.

## Freshness

```bash
python3.12 scripts/manage_daily_shipping_recovery.py status --max-age-minutes 15
```

Status is GREEN only while the latest successful encrypted receipt is at most 15 minutes old. A missing, invalid, or stale receipt is RED.

## Retention

Retention is tag-scoped to `daily-shipping-critical` and preserves all snapshots from the most recent 24 hours, then 14 daily, 8 weekly, and 12 monthly restore points. Previewing the contract performs no remote action:

```bash
python3.12 scripts/manage_daily_shipping_recovery.py retention
```

The daily candidate uses the explicit destructive-maintenance gate:

```bash
ENABLE_SHIPPING_RECOVERY_RETENTION=1 \
python3.12 scripts/manage_daily_shipping_recovery.py retention --apply
```

The retention command is independent from backup creation, uses its own non-concurrent lock, never emits provider output, and advances `latest_retention.json` only after a successful encrypted prune.

## Restore Drill

Use a new owner-only target outside the repo:

```bash
ENABLE_SHIPPING_RECOVERY_RESTORE=1 \
python3.12 scripts/manage_daily_shipping_recovery.py restore-drill \
  --target "/absolute/owner-only/restore-drill" \
  --apply
```

The drill requires exact manifest and artifact hashes, a green SQLite quick check, and completion within 30 minutes. It never replaces the live database.

## Rollback

If the candidates are later activated and must be rolled back, boot out only `com.example.daily-shipping-recovery` and `com.example.daily-shipping-recovery-retention`, preserve the recovery receipts and encrypted repository, and set the manifest activation state back to `candidate_not_installed`. These jobs do not own or mutate shipping, Telegram, Google Board, marketplace, or customer state.
