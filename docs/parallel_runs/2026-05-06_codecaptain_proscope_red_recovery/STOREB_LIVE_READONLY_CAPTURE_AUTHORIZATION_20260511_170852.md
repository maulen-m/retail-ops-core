# STOREB Live-Readonly Capture Authorization

Generated at: `2026-05-11T17:08:52+0500`

Gate: `AUTHORIZED_FOR_BOUNDED_LIVE_READONLY_CAPTURE_ONLY`

## Owner Decision

The human owner approved Option 1 in this chat on `2026-05-11`:

- `We agree with the approach, let's do option one.`
- `Assign some execution agents or one execution agent to do it.`

## Authorized Lane

Launch one focused execution agent:

`Agent772 - STOREB Live-Readonly Capture, Packet Build, And Copied-Temp Replay`

This authorization is limited to resolving the STOREB ads source gap by bounded live-readonly capture and immutable packet proof.

## In Scope

- Refresh STOREB ads source evidence for `2026-05-05..2026-05-11`.
- Preserve business identity as `STOREB`.
- Record Universal switcher/shared login only as access identity: `UNIVERSAL_SWITCHER_FOR_STOREB`.
- Use campaign `2609342` / `Line52_storeb_26.2.2026` and STOREB merchant/API id `1065684` when freshly confirmed.
- Build an immutable `ads_web_source_packet.v1` under the assigned Autonomous_business evidence root.
- Strict-validate the packet with `scripts/validate_ads_source_packet_contract.py`.
- If and only if the packet validates, run copied/temp DB adapter replay and contained validators against the copied DB only.

## Still Forbidden

This does not authorize:

- production `db/app.db` mutation;
- protected workbook mutation;
- writes inside `~/Docs/Web_automation`;
- browser-login automation;
- credential, cookie, token, storage-state, browser-profile, `.env`, or session export/copy/reveal/packaging;
- scheduler, LaunchAgent, plist, launchctl, installer, or automation mutation;
- owner publication, owner send, or owner approval request;
- Kaspi merchant writes, external writes, ad spend, bid/budget/campaign/product mutation;
- cash movement, supplier payment, PO commitment, price changes, or stock changes.

## Stopline

If the only path to capture fresh STOREB evidence requires a forbidden action, Agent772 must stop `YELLOW` or `RED` and preserve the current blocker instead of improvising.
