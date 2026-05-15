# STOREB Mapping Repair Proof Plan

Generated at: `2026-05-11T19:52:24+0500`

Decision: `LAUNCH_AGENT773_STOREB_PRODUCT_CODE_MAPPING_REPAIR_PROOF`

## Why This Is The Next Efficient Move

Agent772 solved the live-source blocker. The fresh STOREB packet covers `2026-05-05..2026-05-11` and strict-validates. The remaining high-leverage blocker is not capture; it is product-code mapping.

Repairing or explicitly preserving the seven blocked mappings in copied/temp proof is the shortest path toward usable STOREB ads truth without production risk.

## Authority Boundary

This plan is proof-only. It does not authorize owner publication, owner send, owner approval request, production DB write, protected workbook write, scheduler install/enablement/execution, LaunchAgent/plist mutation, Web_automation write, browser-login automation, credential/session/cookie/storage-state export, external-system write, cash movement, supplier payment, PO commitment, ad spend, bid/budget/campaign mutation, price change, or stock change.

Agent773 may write only under its assigned Autonomous_business evidence root and assigned closeout path. If focused repo code changes become absolutely necessary to enable copied/temp-only mapping proof, Agent773 must first stop and classify the missing implementation requirement unless the change can be limited to dry-run/copy-temp behavior with focused tests and no production apply path changes.

## Current Blocker

Current label:

`STOREB_ADS_MAPPING_BLOCKER_VISIBLE`

Blocked product codes from Agent772:

| Product code | Product name | Source rows | Source cost KZT |
|---|---:|---:|---:|
| `11391140b` | Комплект ALPIKA черный | `7` | `0` |
| `11391205b` | Комплект Antec черный | `7` | `5351.33` |
| `11391711b` | Комплект S SPORT серый | `7` | `3565.47` |
| `11869884b` | Спортивный костюм PRO COMBAT черный | `7` | `0` |
| `11956144b` | Спортивный костюм черный | `7` | `1290.00` |
| `12071269b` | Спортивный костюм Fashion черный | `7` | `0` |
| `12236047b` | Спортивный костюм IMPERIAL черный | `7` | `0` |

Already mapped product codes from Agent772:

- `11120372b` -> `CL_OC_MEN_LINE52_BLACK`
- `11122298b` -> `CL_OC_MEN_LINE52_BLACK`
- `11942309b` -> `CL_OC_MEN_LINE52_BLACK`

## Agent773 Assignment

Assigned evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_mapping_repair_proof/20260511_195224`

Assigned copied DB:

`~/Docs/Autonomous_business/exports/validation/storeb_mapping_repair_proof/20260511_195224/agent773_replay/app_copy.sqlite`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_mapping_repair_proof_20260511_195224_agent773_closeout.md`

Minimum work:

- verify Agent772 closeout has standalone `Gate: GREEN`;
- read Agent772 final classification and adapter lineage sidecar;
- inspect mapping evidence surfaces, including current copied DB tables, source packet rows, order-entry/product/article/catalog truth, and current adapter behavior;
- produce an evidence-local mapping decision table for all ten STOREB product codes;
- map only when deterministic evidence supports the SKU key;
- preserve any remaining ambiguity as explicit `ADS_MAPPING_MISSING` or stricter blocker;
- replay the adapter against copied/temp DB only;
- rerun ads sidecar readiness and ads offer-universe coverage validators against copied/temp DB only with outputs under the evidence root;
- write final blocker classification JSON.

## Success Criteria

Agent773 may close `Gate: GREEN` only if:

- all writes stay inside Agent773 evidence root and assigned closeout, except explicitly safe focused tests/code if unavoidable and documented;
- production DB/workbook/Web_automation/external/scheduler surfaces are not mutated;
- every new mapping has deterministic evidence;
- copied/temp replay and validators are complete;
- warning cohorts `23`, `252`, validator-visible `249`, and combined `275` remain visible as warnings/blockers, not product truth;
- final state is one of:
  - `STOREB_ADS_MAPPING_REPAIRED_IN_COPIED_TEMP_REPLAY`
  - `STOREB_ADS_PARTIAL_MAPPING_REPAIR_WITH_RESIDUAL_BLOCKER_VISIBLE`
  - `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`.

Agent773 should close `Gate: YELLOW` if the mapping can likely be repaired but requires missing source truth, missing product identity evidence, owner SKU confirmation, or a reviewed implementation change.

Agent773 should close `Gate: RED` if the only path requires production mutation, workbook mutation, browser/session/credential export, Web_automation write, external write, ad/campaign mutation, or fuzzy-name-only mapping.

## Do Not Do Yet

Do not run production apply, scheduler enablement, owner publication, price/stock changes, ad spend/campaign actions, cash movement, supplier payment, PO commitment, or owner approval request after this proof. Even a green Agent773 result remains review/proof-only until separately accepted.
