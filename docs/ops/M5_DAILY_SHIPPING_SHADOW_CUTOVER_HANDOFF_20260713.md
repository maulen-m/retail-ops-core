# M5 Daily Shipping Shadow and Cutover Handoff

## Why This Exists

M1 currently owns the only proven live daily-shipping chain. M5 is newer and should become primary, but migration must never create two hosts capable of shipping orders or sending Telegram bundles. This handoff prepares M5 without authorizing cutover.

## Release Anchor

- Repository: the existing private Autonomous_business remote
- Release branch: `task/20260713-daily-shipping-rescue`
- Release tag: recorded in the rescue closeout after final validation
- Runtime root required on M5: `~/Docs/Autonomous_business`
- Canonical manifest: `config/daily_shipping_runtime.json`
- Release gate: `scripts/run_daily_shipping_release_gate.sh`

Use the exact final commit and tag from the closeout. Do not use M1's dirty working tree as the transfer authority.

## Required M5 Inputs

- Clean release checkout at the identical path.
- Current `db/app.db` plus any live `-wal` and `-shm` files captured while all M1 writers are paused.
- Current canonical CRM workbook and the minimal runtime state named by the final cutover packet.
- Fresh M5-local credentials installed outside Git with owner-only permissions.
- No historical exports, PDFs, logs, broad backup tree, `.claude` runs, or stale worktrees unless the closeout explicitly names them as required runtime state.

## Shadow Phase: No External Writes

1. Verify the checkout is clean and at the release tag.
2. Run the release gate with the repo virtual environment.
3. Generate scheduler plists from the canonical runtime manifest, but do not load them.
4. Run DB integrity, Google layout, merchant-context, credential-presence, and artifact-schema checks in read-only/no-send mode.
5. Replay a preserved completed day from copied evidence and prove stage idempotency without API mutation or Telegram send.
6. Record disk latency, restore duration, API-read error rate, and end-to-end shadow duration.
7. Write a standalone GREEN/YELLOW/RED shadow packet. Shadow GREEN does not authorize cutover.

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

No cutover occurs before the 2026-07-14 employee workflow. M1 remains authoritative through that workflow unless the owner explicitly approves a separate emergency cutover packet after all checks above are GREEN.
