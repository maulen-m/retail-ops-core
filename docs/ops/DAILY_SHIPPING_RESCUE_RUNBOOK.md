# Daily Shipping Rescue Runbook

## Operational Priority

The employee shipping chain is the business-critical lane. For 2026-07-14, M1 remains the only live writer and must be ready before `17:00 Asia/Almaty`. M5 and cloud work are shadow-only until a separate atomic-cutover packet is GREEN.

Canonical runtime truth is `config/daily_shipping_runtime.json`. Generated scheduler plists and `docs/ops/DAILY_SHIPPING_RUNTIME.generated.md` must match it exactly.

## Separate Verdicts

- `shipping_gate`: readiness of DB, Google Board, store context, employee READY watcher, shipment, waybill, bundling, Telegram ledger, and shipped-truth sync.
- `resilience_gate`: clean release, disk headroom, off-machine recovery, credential hygiene, restore proof, and standby readiness.

Unrelated COGS, finance, creative, or advertising gaps do not block `shipping_gate`. A critical disk floor, missing credential, unavailable DB, scheduler drift, unresolved READY identity, or failed delivery ledger does.

## Daily Timeline

1. `07:00`: first board publish opportunity.
2. `11:00-17:11`: source refresh and board publish cadence.
3. `13:45`: full prewindow health writes `exports/google_ops_board/health/<date>/prewindow_health.json`.
4. Before `17:00`: employee fills sizes and sets READY.
5. `09:00-24:00`: the 15-second watcher observes a stable READY for 60 seconds and resumes only incomplete stages.
6. `18:30`: deadline backstop exists, but it is not the normal employee trigger.
7. Completion requires the checkpoint, exact waybill manifest, and confirmed Telegram delivery ledger. A chat message alone is not completion proof.

## Release Gate

```bash
PYTHON_BIN=~/Docs/Autonomous_business/.venv/bin/python \
  scripts/run_daily_shipping_release_gate.sh
```

Installed runtime check on the active host:

```bash
~/Docs/Autonomous_business/.venv/bin/python \
  scripts/validate_daily_shipping_runtime.py --check-installed --json
```

The check reads credential presence and permissions only. It never emits credential values.

## One-Writer Rule

The following scheduler cluster moves as one unit: source refresh, board publish, prewindow health, size preview, READY watcher, keep-awake guard, deadline backstop, Telegram fallback control, shipped-truth sync, and daily report. Never enable part of the cluster on M5 while any part can advance state on M1.

Before a future cutover, prove all of the following in one packet: no active closeout process, no closeout or delivery lock, no unsettled debounce/READY identity, M1 cluster disabled, M5 installed-runtime check GREEN, M5 no-send shadow GREEN, and an exact rollback command that re-enables M1 only.

## Failure Handling

- Resume only the failed or incomplete stage from the checkpoint.
- Do not restart confirmed shipment, PDF, or Telegram stages merely because a later truth-sync stage failed.
- Duplicate READY events and restarts must resolve to the same request identity.
- If delivery status is `api_started` or uncertain, reconcile evidence before any retry.
- Keep M1 powered and preserved for at least four weeks after a future cutover, with its write schedulers disabled.

## Recovery Priorities

1. Preserve tomorrow's known-green M1 path.
2. Keep at least a critical working floor of local disk space; work toward the canonical 20 percent recovery target using verified lossless compaction.
3. Restore the attached-drive mirror and add an encrypted truly off-machine copy.
4. Promote M5 only after seven consecutive M1/release-green days or a separately approved accelerated cutover packet.
5. Benchmark cloud compute after local reproducibility is proven; cloud compute is not a prerequisite for tomorrow's shipping.

Encrypted off-machine recovery is documented in `docs/ops/ENCRYPTED_OFFSITE_RECOVERY.md`.
The candidate recovery, log maintenance, manifest-driven health monitor,
disk-preservation, and post-closeout activation sequence is documented in
`docs/ops/DAILY_SHIPPING_RESILIENCE_OPERATIONS.md`.
