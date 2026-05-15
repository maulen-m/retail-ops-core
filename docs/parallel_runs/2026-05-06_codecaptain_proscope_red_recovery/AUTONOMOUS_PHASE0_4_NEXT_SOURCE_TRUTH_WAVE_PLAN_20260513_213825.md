# Autonomous Phase 0.4 Next Source-Truth Wave Plan

Timestamp: `2026-05-13T21:38:25+0500`

## Purpose

Continue the owner-approved autonomous review-only/copied-temp path after Agent799 synthesis while preserving all stoplines.

Agent799 established the current score at `4/10`: the boundary and blocker map are clear, but owner-publication readiness remains RED because source freshness, stock/order, ads, PO, cashflow, and exception gates are still blocked.

## Current Accepted Boundary

- DB SHA: `40d21f643caefc38270427096ee615fe0667f7d90b628acf5da56d080ad783d1`
- Workbook SHA: `e7ff6fd8da8938b3247343a58e1257c102ac1d62077f68f33ad7a5b8a45ec870`
- Boundary use: review-only and copied-temp only.

## Parallel Launch Now

### Agent800 - Order Entry Copied-Temp Recovery Replay

Run now.

Goal:

- Use Agent794's immutable source packet from `2026-05-05..2026-05-13`.
- Copy the accepted `40d21...` production DB into an evidence-only SQLite file.
- Run order-entry recovery/materialization only against the copied DB.
- Preserve the product-identity `23` and header-only `252` warning cohorts.
- Produce before/after evidence, validator results, and a closeout.

Allowed writes:

- Agent800 evidence root only.
- Copied DB under that evidence root only.
- Agent800 closeout only.

### Agent801 - Ads Read-Only Current Packet Discovery

Run in parallel with Agent800.

Goal:

- Inspect AB and Web_automation local evidence for ACMEWEAR and STOREB ads truth through `2026-05-13`.
- Validate against `docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`.
- If a complete no-secret immutable packet can be assembled from already-existing local files, assemble it under the Agent801 evidence root and validate it.
- If current evidence is missing, stop with exact missing rows/files and exact next approval or command needed.

Allowed writes:

- Agent801 evidence root only.
- Agent801 closeout only.

Forbidden:

- Browser login.
- Credential/session/cookie/storage-state export.
- Web_automation writes.
- Live fetch unless later explicitly authorized.
- Ad-platform writes.

## Held Until Owner / Source Facts Exist

- Agent802 PO replacement bundle copied-temp proof.
- Agent803 cashflow compact SKU cost/bank proof.
- Agent804 stock exception resolution proof.
- Agent805 combined copied-temp readiness replay.
- Any serialized production apply lane.

## Stoplines

Stop if:

- current DB/workbook boundary drifts before copying or packet proof;
- any lane needs production DB apply, protected workbook mutation, scheduler mutation, source-pointer replacement, owner publication, browser/session/credential export, cash movement, PO commitment, supplier contact, ad-platform write, price change, stock change, or owner-decision application;
- any ads lane needs live login/fetch or Web_automation write without separate explicit approval;
- any validator writes outside the assigned evidence root again;
- warning cohorts `23` or `252` disappear or become productized.

## Success Criteria

Phase 0.4 succeeds when:

- Agent800 returns a copied-temp order-entry replay closeout with protected surfaces unchanged; and
- Agent801 returns either a current valid no-secret ads packet or a precise RED/YELLOW missing-source command/approval packet; and
- no forbidden action is performed.
