# M5 Daily Shipping Shadow and Cutover Handoff

## Why This Exists

M1 currently owns the only proven live daily-shipping chain. M5 is newer and should become primary, but migration must never create two hosts capable of shipping orders or sending Telegram bundles. This handoff prepares M5 without authorizing cutover.

## Release Anchor

- Repository: the existing private Autonomous_business remote
- Release branch: `task/20260713-daily-shipping-rescue`
- Immutable employee-path base tag: `release/daily-shipping-20260713-v2.2`
- Base tag commit: `03b191ed8f5766c7557aa573e01d32f92d7f050a`
- Receiver checkout: the exact later commit recorded in the rescue closeout;
  the M5 gate proves the base tag is its ancestor
- Current receiver release tag:
  `release/daily-shipping-m5-shadow-20260714-v3`
- Current receiver release commit:
  `200c8c1ab8d1ce01a1a31bc12be6d2aa45ca6b39`
- Runtime root required on M5: `~/Docs/Autonomous_business`
- Canonical manifest: `config/daily_shipping_runtime.json`
- Release gate: `scripts/run_daily_shipping_release_gate.sh`
- Receiver gate: `scripts/run_m5_daily_shipping_shadow.py`
- Post-closeout M1 credential procedure:
  `docs/ops/DAILY_SHIPPING_CREDENTIAL_ROTATION.md`

Use the exact final commit and tag from the closeout. Do not use M1's dirty working tree as the transfer authority.

Remote CI authority: GitHub Actions daily-shipping run `29281950357` passed
against the current receiver release commit.

## Required M5 Inputs

- Clean release checkout at the identical path.
- Current `db/app.db` plus any live `-wal` and `-shm` files captured while all M1 writers are paused.
- Current canonical CRM workbook and the minimal runtime state named by the final cutover packet.
- The recovery snapshot's `workflow/replay/` directory, containing the
  successful apply `closeout_report.json`, `run_control_snapshot.json`, and
  `salesraw_snapshot.json` for the preserved business date.
- Fresh M5-local credentials installed outside Git with owner-only permissions.
- The fresh M5 credential source must use the post-rotation owner-selected bot
  token. Do not copy `before.env`, a fresh-token input file, or any rotation
  receipt backup into the receiver packet.
- No historical exports, PDFs, logs, broad backup tree, `.claude` runs, or stale worktrees unless the closeout explicitly names them as required runtime state.

## Shadow Phase: No External Writes

1. Verify the checkout is clean and at the release tag.
2. Run the release gate with the repo virtual environment.
3. Generate scheduler plists from the canonical runtime manifest, but do not load them.
4. Run DB integrity, Google layout, merchant-context, credential-presence, and artifact-schema checks in read-only/no-send mode.
5. Replay a preserved completed day from copied evidence and prove stage idempotency without API mutation, Google Board access, or Telegram send.
6. Record disk latency, restore duration, API-read error rate, and end-to-end shadow duration.
7. Write a standalone GREEN/YELLOW/RED shadow packet. Shadow GREEN does not authorize cutover.

The post-closeout M1 snapshot command is local-only:

```bash
~/Docs/Autonomous_business/.venv/bin/python \
  scripts/manage_daily_shipping_recovery.py snapshot \
  --project-root ~/Docs/Autonomous_business \
  --state-root "$HOME/Library/Application Support/Autonomous_business/m5_shipping_transfer" \
  --json-out "$HOME/Library/Application Support/Autonomous_business/m5_shipping_transfer/snapshot_receipt.json"
```

After the checksummed snapshot folder and exact Git commit reach M5, run:

```bash
~/Docs/Autonomous_business/.venv/bin/python \
  scripts/run_m5_daily_shipping_shadow.py \
  --project-root ~/Docs/Autonomous_business \
  --manifest ~/Docs/Autonomous_business/config/daily_shipping_runtime.json \
  --snapshot-manifest /ABSOLUTE/PATH/TO/SNAPSHOT/snapshot_manifest.json \
  --output-root "$HOME/Library/Application Support/Autonomous_business/m5_shadow/20260714" \
  --expected-commit FULL_40_CHARACTER_COMMIT_SHA \
  --json
```

The receiver refuses a dirty or wrong checkout, a same-host run, a hash
mismatch, loose credential permissions, any loaded shipping label, an output
inside the repo, or missing preserved replay evidence. Its subprocess
environment starts without inherited write gates or secret-like variables. The
closeout child then loads the protected M5 credential source for read-only
Kaspi API context, strips every `ENABLE_*` write gate again, and never copies a
credential value into evidence. The final report records
`external_writes_performed: 0`, `credential_values_read: true`,
`credential_values_read_by_wrapper: false`,
`credential_values_exposed: false`, and `cutover_authorized: false`.

## Atomic Cutover: Separate Owner-Approved Window

1. Freeze a final checksummed M1 state packet.
2. Stop the complete ten-label M1 cluster.
3. Prove no closeout process, lock, debounce, delivery attempt, or pending READY identity remains.
4. Transfer the final DB/workbook/runtime-state delta and verify hashes on M5.
5. Load the complete M5 cluster once.
6. Prove exactly one host can advance state.
7. Run one no-send readiness check, then a separately approved live canary.
8. If any gate fails, disable the complete M5 cluster before re-enabling M1.

## Stop Points

Stop before loading any M5 scheduler until the cutover packet is approved. Stop if a state file cannot be identified, a hash differs, M1 has an active writer, M5 paths differ, credentials appear in an artifact, or rollback cannot be executed in under 30 minutes.

## Tomorrow's Constraint

The live M1 employee path must be ready by **2026-07-14 17:00
Asia/Almaty**. No cutover occurs before that employee workflow. M1 remains
authoritative through the ledger-confirmed closeout unless the owner explicitly
approves a separate emergency cutover packet after all checks above are GREEN.
Credential apply is also after closeout; pre-deadline readiness is metadata-only.
