# STOREB Mapping Repair Proof Authorization

Generated at: `2026-05-11T19:52:24+0500`

Gate: `AUTHORIZED_FOR_AGENT773_COPIED_TEMP_MAPPING_REPAIR_PROOF_ONLY`

## Owner Decision

The human owner approved the recommended next move in chat on `2026-05-11`:

`Fully agree with the approach. Launch Agent 773.`

## Authorized Lane

Launch one focused execution agent:

`Agent773 - STOREB Product-Code Mapping Repair Proof`

This authorization is limited to copied/temp proof and evidence work for the Agent772 STOREB mapping blocker.

## Starting Point

Agent772 completed with `Gate: GREEN` and final label:

`STOREB_ADS_MAPPING_BLOCKER_VISIBLE`

The old source-date gap is no longer the active blocker in copied/temp proof. The active blocker is product-code mapping:

- `7` of `10` STOREB product-code mappings are blocked.
- `49` STOREB source rows remain unmapped.
- Blocked rows include `10206.80` KZT of source ad cost.
- Apply-mode readiness still sees `ADS_SOURCE_STALE` from the configured external ads source path, so production or scheduler movement remains blocked.

## In Scope

- Use Agent772 strict-valid packet and copied/temp replay evidence.
- Determine whether the seven blocked STOREB product codes can be mapped deterministically to existing AB SKU truth.
- Create an evidence-local candidate mapping file if and only if each mapping has deterministic proof.
- Replay the adapter only against a copied/temp DB inside Agent773 evidence.
- Rerun ads validators against the copied/temp DB only, with outputs under the Agent773 evidence root.
- Preserve any unresolved product codes as explicit mapping blockers.

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

If any mapping cannot be proven from deterministic product-code/order-entry/article-map/catalog evidence, keep it blocked. Do not map by fuzzy product name alone and do not convert unmapped rows into zero spend.
