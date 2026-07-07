# Stopgap: CRM import timeout 600s -> 1500s (2026-07-07)

Incident: employee reported the Google ops board was stale / short of orders on
2026-07-07. Diagnosis: the 11:00 and 15:02 `com.example.kaspi-import-v2` runs were
killed by the Step-2 CRM/Excel import timeout (`CRM_IMPORT_TIMEOUT_SEC` default
600s via `scripts/run_with_timeout.py`); on a non-retryable Step-2 failure
`run_full_import.command` sets `STEP2_SKIP_DOWNSTREAM=1`, which SKIPS Step 3
(Google Ops Board publish) — so the board kept yesterday's rows until the 17:02
run succeeded (board current 17:03, `SUCCESS_GATE_OK`, 14/14/14 API/CRM/board
parity). The low order count itself is real demand (07-01..04: 37-39/day,
07-05/06: 27, 07-07: 14), not data loss.

Fix applied (config-only, zero source edits): added
`CRM_IMPORT_TIMEOUT_SEC=1500` to `~/Library/LaunchAgents/com.example.kaspi-import-v2.plist`
EnvironmentVariables and reloaded via launchctl bootout/bootstrap. Verified live
in `launchctl print gui/501/com.example.kaspi-import-v2`.

Rollback: restore `backups/com.example.kaspi-import-v2.plist.bak_20260707_1720`
and reload, or delete the key with PlistBuddy.

Lifetime: interim only. The CRM Excel lane is being retired per the owner-signed
decommission program (see OWNER_SIGNED_DECISIONS_CRM_DECOMMISSION_2026-07-06.md);
at Phase-2 cutover Step 2 disappears and this knob becomes irrelevant. The
board-publish-depends-on-CRM coupling is a known map risk and is resolved by the
same cutover — do not build further on the CRM lane.
