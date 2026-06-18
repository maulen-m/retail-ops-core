# LINE31 Next Inputs And Ready-To-Run Handoff

Generated: `2026-06-01T21:17:03+05:00`

Current gate: `GREEN_EXCEPT_CREATIVE`

Strict publish gate: `YELLOW`

Ready to publish: `false`

## Current Evidence

- Current status pointer: `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
- Current active-goal audit: `docs/current/LINE31_ACTIVE_GOAL_COMPLETION_AUDIT_CURRENT.md`
- Latest preflight packet: `exports/validation/line31_final_launch_preflight_20260601_211045`
- Latest Oracle Pack for external expert: `~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert`

## One-Command Input Status Check

Run this command first in any follow-up turn or agent handoff:

```bash
python3 scripts/report_line31_next_inputs_status.py --json
```

It reports whether the next move is expert-answer ingestion, final creative mapping, one-shot local bridge execution, or ambiguity cleanup. It is read-only and does not perform external writes.

## Input 1 - External Expert Answer

Paste or place the expert answer under:

`~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer`

Current check: the `Answer/` folder now contains the 2026-06-02 expert answer, and the answer is integrated into the post-expert strict publish addendum.

Expert answer file:

`~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer/Strategy_expert_02.06.2026_11_14_17.md`

Post-expert integration plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-06-02_line31_post_expert_strict_publish_integration/PLAN.md`

Post-expert strict publish addendum:

`~/Docs/Autonomous_business/docs/validation/LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md`

Post-expert orchestrator starter:

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_POST_EXPERT_STRICT_PUBLISH_20260602_STARTERS/01_AGENT_1__POST_EXPERT_STRICT_GATE_INTEGRATION__SERIAL.md`

The expert answer has been ingested against:

- `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
- `docs/current/LINE31_ACTIVE_GOAL_COMPLETION_AUDIT_CURRENT.md`
- `exports/validation/line31_final_launch_preflight_20260601_211045/line31_launch_preflight_manifest.json`
- `exports/validation/line31_current_noncreative_gate_refresh_current/CURRENT_NONCREATIVE_GATE_MATRIX.json`

Owner-facing publish status after expert review must be:

`YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA`

`GREEN_EXCEPT_CREATIVE` remains an internal non-creative planning label only. It is not publish authority.

The next action is final creative intake plus strict live QA proof, not a fake publish-ready state.

## Input 2 - Final Creative Assets

Drop exactly one final video and exactly one thumbnail into:

`~/Docs/Autonomous_business/exports/validation/line31_final_creative_drop_intake_20260601_204005/final_assets`

Current check: the final-assets folder is empty.

Required media rules:

- Video extensions: `.mp4`, `.mov`, `.m4v`, `.webm`
- Thumbnail extensions: `.png`, `.jpg`, `.jpeg`, `.webp`
- The validator fails closed if there are zero or multiple video/thumbnail candidates.

## Input 3 - Final URLs And Owner Approval

Before strict launch readiness can pass, provide:

- final asset URI, replacing `https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4`;
- final Kaspi marketplace CTA URL, replacing `https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/`;
- exact owner Meta publish approval phrase in a separate text file after final mapping is filled.
- current tracking/redirect QA JSON evidence with `gate=GREEN`, passed as `--tracking-qa-evidence-file` and SHA-256 recorded in `tracking_redirect_qa.evidence_sha256`.

Approval placeholder:

`~/Docs/Autonomous_business/exports/validation/line31_final_creative_drop_intake_20260601_204005/approval/PASTE_EXACT_OWNER_APPROVAL_HERE.txt`

## Ready-To-Run Commands After Assets Exist

First refresh the stable pointer:

```bash
python3 scripts/write_line31_current_launch_status.py --json
```

Then validate the latest drop from the stable pointer:

```bash
python3 scripts/validate_line31_current_final_creative_drop.py --json
```

When final URLs and approval evidence are ready, run the one-shot local bridge:

```bash
python3 scripts/prepare_line31_launch_readiness_from_assets.py --creative-id line31_countrywide_v1 --asset-dir ~/Docs/Autonomous_business/exports/validation/line31_final_creative_drop_intake_20260601_204005/final_assets --final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 --duration-seconds 18 --utm-placement reels --landing-url 'https://acmewear.pro/line31' --kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' --creative-ready-declared --approval-text-file ~/Docs/Autonomous_business/exports/validation/line31_final_creative_drop_intake_20260601_204005/approval/PASTE_EXACT_OWNER_APPROVAL_HERE.txt --overwrite --json
```

Replace the placeholder final asset URI and Kaspi slug, and add `--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json`, before using that command for real launch readiness.

## Safety Boundary

This handoff does not authorize production DB writes, workbook writes, scheduler/source-pointer changes, Web_automation writes, Kaspi/API/WebUI/Meta writes, campaign bid/budget/state changes, price changes, stock changes, cash movement, PO commitment, supplier payment, owner publication, or pausing internal Kaspi LINE31 campaigns.

Internal Kaspi LINE31 campaigns remain ON until a separate exact owner approval phrase authorizes a pause.
