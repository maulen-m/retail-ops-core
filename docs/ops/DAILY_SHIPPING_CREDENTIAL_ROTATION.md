# Daily Shipping Telegram Credential Rotation

## Boundary

This procedure rotates one allowlisted Telegram bot token in the owner-only
Autonomous_business environment file. It is deliberately unavailable until
the current Almaty business date has a successful apply closeout. For
2026-07-14, do not apply it before the employee workflow is ledger-confirmed.

The tool never accepts a token value on the command line, never writes one to
stdout, JSON, logs, Git, or evidence, and never sends a Telegram message. Its
only network action is a read-only Telegram `getMe` identity check before the
local credential file changes.

## Before Employee Closeout

The live M1 checkout intentionally does not receive rescue-branch files before
the employee closeout. Use the clean release worktree as the executable source
and point it explicitly at the live owner-only environment file. On a future
M5 checkout of the release tag, `RELEASE_ROOT` and `LIVE_ROOT` are the same
path.

```bash
RELEASE_ROOT=~/Docs/Autonomous_business__wt_shipping_rescue_20260713
LIVE_ROOT=~/Docs/Autonomous_business
PYTHON="$LIVE_ROOT/.venv/bin/python"
RELEASE_TAG=release/daily-shipping-m5-shadow-20260714-v4
test "$(git -C "$RELEASE_ROOT" rev-parse "$RELEASE_TAG^{}")" = \
  "075e8f9b9ecf2ea93bd34c5813125cb3028b7beb"
test "$(git -C "$RELEASE_ROOT" hash-object scripts/rotate_daily_shipping_credential.py)" = \
  "$(git -C "$RELEASE_ROOT" rev-parse "${RELEASE_TAG}^{}:scripts/rotate_daily_shipping_credential.py")"
```

Stop if either equality check fails. Readiness is metadata-only. Run it
separately for the credential key that will be replaced:

```bash
"$PYTHON" "$RELEASE_ROOT/scripts/rotate_daily_shipping_credential.py" \
  --env-file "$LIVE_ROOT/.env" \
  --key TELEGRAM_BOT_TOKEN \
  --json
```

For the dedicated waybill-bot key, substitute
`TELEGRAM_BOT_TOKEN_WAYBILL`. A readiness result does not read a credential
value and does not authorize apply.

## Owner Input

After the employee closeout, the owner generates or supplies the fresh token
for the exact bot being rotated. Put only that token in a temporary file
outside every repository and restrict the file before use:

```bash
TOKEN_FILE="$HOME/Library/Application Support/Autonomous_business/private/fresh-waybill-token.txt"
mkdir -p "$(dirname "$TOKEN_FILE")"
chmod 700 "$(dirname "$TOKEN_FILE")"
chmod 600 "$TOKEN_FILE"
```

Do not type the token into a shell command, tmux chat, report, or agent prompt.
The token file must contain exactly one Telegram token line and must not be a
symlink.

## Apply After Ledger-Confirmed Closeout

Set `CLOSEOUT` to the exact successful
`exports/google_ops_board/workflow_runs/2026-07-14/*/closeout_report.json`
selected from direct artifact readback. It must say `ok: true`, `mode: apply`,
`target_date: 2026-07-14`, and contain a `run_id`.

```bash
export ENABLE_DAILY_SHIPPING_CREDENTIAL_ROTATION=1
"$PYTHON" "$RELEASE_ROOT/scripts/rotate_daily_shipping_credential.py" \
  --env-file "$LIVE_ROOT/.env" \
  --key TELEGRAM_BOT_TOKEN \
  --token-file "$TOKEN_FILE" \
  --closeout-report "$CLOSEOUT" \
  --apply \
  --json
unset ENABLE_DAILY_SHIPPING_CREDENTIAL_ROTATION
```

Use `TELEGRAM_BOT_TOKEN_WAYBILL` instead only when that is the owner-selected
bot key. Never rotate both keys merely because both exist.

The apply path verifies the fresh token with `getMe`, then creates an
owner-only backup and secret-free receipt under
`~/Library/Application Support/Autonomous_business/credential_rotation/`.
It atomically changes only the selected dotenv key. If receipt persistence
fails after replacement, the tool restores the exact pre-rotation bytes.

## Required Readback

Immediately after a GREEN rotation receipt:

1. Re-run the live checkout's
   `scripts/validate_daily_shipping_runtime.py --check-installed
   --check-credentials --json`.
2. Re-run the release worktree's `scripts/run_daily_shipping_release_gate.sh`
   with `PYTHON_BIN="$PYTHON"`.
3. Run the prewindow health and shipment preflight without any send action.
4. Verify the ten canonical M1 labels are still the only loaded writer cluster.
5. Preserve the receipt and its `before.env` backup owner-only; do not add
   either to Git or a migration evidence bundle.
6. Delete the temporary fresh-token input file only after the owner confirms
   the replacement and readback. The backed-up old token remains sensitive.

If any check fails, stop. Do not load M5 or compensate by enabling another
scheduler cluster.

## Rollback

Rollback is local and one-key only: restore the exact owner-only `before.env`
from the rotation receipt, keep mode `0600`, and rerun the same installed and
shipping-readiness checks. Revoking or regenerating a token at Telegram is an
owner account action and is not performed by this repository tool.
