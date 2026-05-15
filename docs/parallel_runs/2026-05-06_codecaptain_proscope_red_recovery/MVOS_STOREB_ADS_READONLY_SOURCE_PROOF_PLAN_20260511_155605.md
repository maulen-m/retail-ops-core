# MVOS STOREB Ads Read-Only Source Proof Plan

Generated at: `2026-05-11T15:56:05+0500`

Decision: `LAUNCH_AGENT771_STOREB_ADS_READONLY_SOURCE_PACKET_AND_COPIED_TEMP_REPLAY`

## Authority Boundary

This plan is review/proof only. It does not authorize owner publication, owner send, owner approval request, production DB write, protected workbook write, scheduler install/enablement, LaunchAgent/plist mutation, Web_automation write, browser-login automation, credential/session/cookie/storage-state export, external-system write, cash movement, supplier payment, PO commitment, ad spend, price change, or stock change.

The lane may write only under its assigned Autonomous_business evidence root and assigned closeout path. Any DB mutation must be limited to a copied/temp DB inside the evidence root.

## Inputs

Required upstream evidence:

- Agent770 synthesis: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_PHASE_C_PLUS_SYNTHESIS_20260511_154019.md`
- Agent770 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_phase_c_plus_20260511_154019_agent770_synthesis_closeout.md`
- Agent767 STOREB gap closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_phase_c_plus_20260511_154019_agent767_storeb_ads_gap_closeout.md`
- Ads source packet contract: `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
- CodeCaptain ads source packet acceptance: `~/Docs/Oracle/Autonomous_business/2026-05-10/231609_TASK-000_codecaptain-ads-source-packet-content-rereview/Answer/Code Captain_11.05.2026_11_27_43.md`

## Current Blocker

Preserve this label until evidence changes it:

`STOREB_ADS_SOURCE_GAP_VISIBLE_NOT_ZERO_SPEND`

STOREB absence is not zero spend. ACMEWEAR freshness is not STOREB freshness. Universal access identity is not STOREB business identity.

## Agent771 Assignment

Launch one execution agent:

`Agent771 - STOREB Ads Read-Only Source Packet And Copied-Temp Replay`

Assigned evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_storeb_ads_readonly_source_20260511_155605_agent771_closeout.md`

Minimum work:

- build or receive an immutable STOREB-specific `ads_web_source_packet.v1` under the evidence root;
- validate the packet with `scripts/validate_ads_source_packet_contract.py --require-existing-files --strict --json`;
- preserve `business_store_code=STOREB`;
- record any Universal switcher only as access identity;
- cover at least `2026-05-05..2026-05-11`, or stop with the exact missing-source reason;
- copy production `db/app.db` only into the evidence root if and only if the packet is valid enough to replay;
- replay only against the copied/temp DB;
- run ads sidecar readiness and ads offer-universe coverage validators against the copied/temp DB only;
- preserve `product_identity_quarantine=23`, `header_only_source_gap=252`, validator-visible `249`, and combined `275` warning semantics;
- classify the STOREB result without converting missing rows into zero spend.

## Acceptable Outcomes

Agent771 may close with:

- `Gate: GREEN` only if the STOREB packet validates, copied/temp replay completes, required validators run against the copied/temp DB, warning cohorts remain visible, and the final STOREB classification is evidence-backed.
- `Gate: YELLOW` if a safe path exists but current source evidence is stale, missing, no-auth, ambiguous, or incomplete.
- `Gate: RED` if the only available path requires browser-login automation, credential/session export, Web_automation mutation, production mutation, scheduler mutation, external writes, or any other forbidden authority.

Acceptable final labels:

- `STOREB_ADS_SOURCE_FRESH_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_SOURCE_BACKED_NO_SPEND_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`
- `STOREB_ADS_SOURCE_GAP_STILL_VISIBLE`

No label authorizes owner publication, production apply, scheduler execution, external writes, cash/PO/ad/price/stock actions, or owner approval requests.

## Stoplines

Stop immediately if any of these would be required:

- browser-login automation;
- credential, cookie, token, storage-state, or session export/copy/reveal;
- writing inside `~/Docs/Web_automation`;
- writing production `db/app.db`;
- writing protected workbook files;
- scheduler, LaunchAgent, plist, launchctl, installer, or automation mutation;
- external-system write;
- ad spend, bid, budget, or campaign mutation;
- owner publication/send/approval request;
- treating missing STOREB rows as zero spend;
- treating Universal as STOREB business identity;
- treating copied/temp proof as production truth;
- hiding, clearing, downgrading, productizing, or using `23` / `252` warning cohorts as SKU, stock, COGS, profit, or profit-after-ads truth.

## Next Step After Agent771

After Agent771 closes, the orchestrator should inspect the closeout and decide whether the next lane is:

- owner-publication readiness evidence pack;
- current-boundary source/policy gate rematerialization;
- manual copied-DB scheduler dry-run with exact approval;
- or continued manual Daily Survival Brief review while more source proof is gathered.
