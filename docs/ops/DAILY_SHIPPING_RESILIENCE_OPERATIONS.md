# Daily Shipping Resilience Operations

## Current Operating Boundary

M1 remains the only daily-shipping writer through the employee workflow on
2026-07-14. The live path must be ready by `17:00 Asia/Almaty`; the employee
continues to fill sizes and set READY as usual, and no employee-facing process
changed.

The recovery, retention, log-maintenance, and health-monitor LaunchAgents in
this release are generated candidates. They are not installed, loaded, or
part of tomorrow's live writer cluster. Their activation state is canonical in
`config/daily_shipping_runtime.json` and premature installation is a validator
failure.

## Resilience Surfaces

- `scripts/manage_daily_shipping_recovery.py` creates SQLite-consistent,
  owner-only snapshots and sends them to the existing encrypted restic
  repository only with its explicit apply gate. After a successful daily
  apply closeout, the snapshot also preserves the exact Board run-control and
  SalesRaw snapshots plus their successful closeout report for offline replay.
- `scripts/run_m5_daily_shipping_shadow.py` is the receiver-side gate. It
  verifies the exact Git release ancestry, snapshot and restored-state hashes,
  SQLite and workbook integrity, credential file permissions, and that none of
  the canonical shipping labels are loaded. Its preserved-day closeout reads
  only the checksummed Board snapshots; it does not read the current Google
  Board. It consumes protected M5 credentials for read-only Kaspi API context,
  strips all write-enable gates after dotenv loading, exposes no credential
  value, and cannot invoke apply/send/launchctl mutation arguments.
- `scripts/rotate_daily_shipping_logs.py` discovers shipping logs from the
  runtime manifest and creates verified owner-only gzip archives only with its
  explicit apply gate.
- `scripts/archive_cold_evidence.py` accepts only an immediate
  `exports/validation/*` packet or an
  `.claude/orchestrator_runs/*/evidence` tree. It requires at least 14 cold
  days by default and retires the expanded tree only after zstd integrity,
  tar-entry, file-count, and SHA-256 checks pass.
- `scripts/run_google_ops_board_closeout.py` enforces bounded timeouts for each
  executable stage and records timeout failures as return code `124` in the
  stage report. The validator compares those values with the canonical
  manifest.
- `scripts/monitor_daily_shipping_health.py` evaluates all ten canonical
  schedulers using explicit per-scheduler evidence modes. It also checks the
  disk floor, recovery-receipt freshness after activation, and the redacted
  daily Kaspi API ledger. Reports are owner-only and live outside the repo.
  Alerting needs both `--send-alert` and
  `ENABLE_DAILY_SHIPPING_HEALTH_ALERTS=1`.

## Current Proof

- One encrypted candidate snapshot completed and returned snapshot ID
  `0e1bce83a924bec4f7af78313b11cc1fa1fda48fd27b12f4ab5197aa4b7d731a`.
- Its independent restore drill verified four artifacts, exact hashes, and
  SQLite `PRAGMA quick_check = ok` in `72.331` seconds, below the 30-minute RTO.
- Internal free space is above the canonical 20 percent floor. Cold evidence
  remains recoverable from adjacent `.tar.zst` and
  `.archive_manifest.json` pairs with exact restore commands.
- The Kaspi API daily budget is observe-only: warn at `1500` calls and raise a
  hard alert at `3000`. It must not block tomorrow's live shipping until a
  no-send shadow proves that enforcement cannot interrupt fulfillment.
- Log maintenance is dry-run only before activation. A large log is not a
  reason to rotate it while a writer still has an open handle.
- A manual no-alert health-monitor probe against the live M1 runtime was GREEN
  on 2026-07-13: ten schedulers passed, disk was `20.613%` free, the API ledger
  had `707` valid rows, and inactive recovery freshness was reported as
  `NOT_ACTIVE`. No alert was requested or sent.
- The 2026-07-14 `00:08` rollover probe correctly returned
  `YELLOW_NOT_DUE`: all ten labels were loaded, interval/resident checks passed,
  calendar jobs had not reached their due slots, disk was `20.494%` free, and
  alert requested/enabled/sent remained `false/false/false`.

## Post-Closeout Activation Sequence

Run this sequence only after the 2026-07-14 delivery ledger confirms the full
employee workflow:

1. Re-run the release gate and installed-runtime validator.
2. Rotate the previously exposed Telegram credential, update only the
   owner-only credential source, and re-run the installed credential scan.
3. Run one new encrypted backup and one empty-target restore drill from the
   exact release commit.
4. Install the generated recovery and retention plists together, change their
   manifest activation state to `active_m1`, regenerate the canonical
   surfaces, and prove installed-versus-canonical equality.
5. Leave log maintenance uninstalled for its first live review. Apply one
   manual rotation only when the target log has no open writer, then activate
   its generated plist in a separate change.
6. Run the health monitor manually without `--send-alert`. After one full
   post-closeout day is GREEN, activate its generated plist in a separate
   change and confirm the first alert-enabled run writes only owner-local state
   when healthy.
7. Keep M5 and cloud compute shadow-only until their own one-writer cutover
   packet is GREEN.

The exact M5 packet and command are canonical in
`docs/ops/M5_DAILY_SHIPPING_SHADOW_CUTOVER_HANDOFF_20260713.md`. A GREEN
receiver report proves only no-send reproducibility. It never authorizes a
scheduler load or live canary.

## Global Test Debt

The bounded shipping release gate is hermetic and GREEN. Broad GitHub run
`29276852849` retained the v2.2 baseline's `145` inherited failures while
passing tests increased from `4074` to `4097`. They depend mainly on ignored
LINE31 evidence, mutable economics fixtures, old absolute paths, and external
runtime state. Do not copy private databases or historical evidence into Git
to make those tests pass. Repair those suites by replacing hidden runtime
dependencies with declared fixtures, one domain at a time.

## Rollback

- Before activation, rollback is simply to keep the candidate jobs uninstalled.
- After activation, boot out only the generated candidate labels, preserve all
  receipts and archives, set the activation state back to
  `candidate_not_installed`, regenerate, and re-run the installed validator.
- Never enable M5 or cloud writers as a recovery shortcut while any M1
  shipping scheduler can advance state.
