# LINE31 Post-Expert Strict Publish Gate Addendum

Created: 2026-06-02

Source expert answer:

`~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer/Strategy_expert_02.06.2026_11_14_17.md`

This addendum extends `docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md`.

## Operational Status Language

`GREEN_EXCEPT_CREATIVE` is allowed only as an internal planning label for LINE31 non-creative readiness.

Owner-facing publish status must be:

`YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA`

until all strict publish requirements pass.

Do not say "ready to launch except upload the video" unless the statement also says:

- final creative mapping is not complete;
- exact owner publish approval evidence is missing;
- live tracking and redirect QA still must pass;
- protected hashes must be rechecked;
- final Meta publish is not authorized.

## Strict Publish Must Remain Yellow Until

Strict LINE31 countrywide Meta publish readiness may turn green only when all of these are true:

- exactly one final video exists in the current drop folder;
- exactly one final thumbnail exists in the current drop folder;
- final mapping has no placeholder values;
- final asset URI is real;
- landing URL is real;
- Kaspi marketplace CTA URL is real;
- local video SHA-256 is present;
- local thumbnail SHA-256 is present when the thumbnail path is local;
- `creative_ready_declaration_received=true`;
- `publish_authority.approved=true`;
- `publish_authority.approval_evidence_path` points to a separate owner approval evidence file;
- `publish_authority.approval_evidence_sha256` matches that file;
- current non-creative LINE31 launch-blocking matrix is green;
- owner objective source freshness is green;
- current tracking and redirect QA artifact is green;
- protected production DB/workbook hashes are stable or any drift is explicitly authorized and explained.

## False-Green Guards

Validators and handoffs must fail closed or stop `YELLOW` for these cases:

- any `REPLACE_WITH` value remains in final asset URI, landing URL, or Kaspi CTA URL;
- final thumbnail is local but no thumbnail SHA-256 is recorded;
- final creative folder has zero or multiple videos;
- final creative folder has zero or multiple thumbnails;
- owner approval is recorded before the final mapping is populated;
- owner approval is represented only as a boolean without a separate evidence file and SHA;
- tracking QA is stale, missing, or only theoretical;
- old candidate/noindex route maps are used as launch authority;
- internal Kaspi LINE31 campaigns are paused or mutated without a separate exact owner approval phrase;
- advisory repo-wide failures are misrepresented as LINE31 launch blockers without evidence.

## Tracking And Redirect QA Gate

Before live publish, the current tracking QA artifact must prove:

- final landing URL opens;
- `utm_source=meta` is preserved;
- `utm_medium=paid_social` is preserved;
- `utm_campaign=line31_countrywide` is preserved;
- `utm_content` is populated;
- `utm_placement` is populated;
- no raw `fbclid`, `gclid`, or raw click IDs appear in owner-facing exports;
- `PageView` fires;
- `ViewContent` fires;
- `ColorSelect` fires when a swatch is selected;
- `KaspiClick` fires on CTA;
- `HighIntentKaspiClick` fires only under valid high-intent rules;
- `/go/:color` validates color;
- selected color and destination route are preserved;
- server-side `KaspiRedirect` is recorded before 302;
- no fake ecommerce events are emitted.

Forbidden fake ecommerce events:

- `Purchase`;
- `AddToCart`;
- `InitiateCheckout`;
- `AddPaymentInfo`.

## Route Truth

Current LINE31 launch routing must use current live route evidence, not old candidate/noindex maps.

Old candidate route maps may remain in the repo as history/context only. They must not be used as launch authority unless a current validator explicitly marks them live and sellable.

## Internal Kaspi And Seller Bonus Boundary

Internal Kaspi LINE31 campaigns and seller bonus context remain ON by default.

They are attribution noise and business context, not Meta conversion proof.

They may not be paused, changed, or isolated unless the owner separately provides an exact approval phrase for that specific action.

## Pass Gates For Post-Expert Integration

The post-expert integration lane can be called green only if:

- this addendum exists and is referenced by the orchestrator handoff;
- `docs/current/LINE31_NEXT_INPUTS_AND_READY_TO_RUN.md` no longer states that the expert answer folder is empty;
- focused LINE31 docs/tests/scripts pass if changed;
- `python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative --json` remains `GREEN_EXCEPT_CREATIVE`;
- strict `python3 scripts/validate_line31_launch_readiness.py --json` remains `YELLOW` before final creative and owner approval;
- no protected DB/workbook drift is caused by the lane;
- final closeout clearly says no live Meta, Kaspi, WebUI, price, stock, cash, PO, scheduler, source-pointer, supplier, or owner-publication action was performed.

## Downstream Boundary

This addendum does not authorize final publish.

After final creative assets and exact owner approval evidence exist, the downstream serialized final-publish starter is:

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md`
