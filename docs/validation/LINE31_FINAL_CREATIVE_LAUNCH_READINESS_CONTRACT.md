# LINE31 Final Creative Launch Readiness Contract

Created: 2026-06-01

This contract defines the final LINE31 countrywide Meta launch gate from the Autonomous_business side.

## Modes

`GREEN_EXCEPT_CREATIVE` mode is allowed before videos are ready only when the latest non-creative synthesis matrix also allows it:

```bash
python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative
```

This mode may pass only when the non-creative LINE31 evidence packet is green, the latest current synthesis matrix has `can_use_green_except_creative=true`, and the creative mapping template is structurally valid. It must still report that final creative mapping and owner publish approval are pending.

If the current matrix is stale or failing, refresh it before making a launch decision. After the 2026-06-01 current refresh, the LINE31 launch-blocking non-creative matrix is green; strict mode still fails because final creative mapping and exact owner approval are pending.

The current matrix deliberately separates LINE31 launch-blocking gates from broader repo-health advisory gates. `validate_params.py --strict` remains visible as `scope=repo_wide_advisory` and may appear as `YELLOW_ADVISORY` when current-day order-processing or derived-report facts are unsettled. That advisory state must be recorded in `advisory_repo_blockers`, but it does not block LINE31 `GREEN_EXCEPT_CREATIVE` when all `scope=line31_launch_blocking` validators pass and `retained_noncreative_blockers=[]`.

The current matrix used by default is:

`exports/validation/line31_current_noncreative_gate_refresh_current/CURRENT_NONCREATIVE_GATE_MATRIX.json`

Refresh it with:

```bash
python3 scripts/build_line31_current_noncreative_gate_matrix.py --json
```

If that current matrix is absent, validators may fall back to the latest Round 3 synthesis matrix:

`exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.json`

Strict publish-readiness mode is required before live Meta publish:

```bash
python3 scripts/validate_line31_launch_readiness.py
```

This mode must fail until the final creative mapping contains real asset URIs, thumbnail evidence, SHA-256 values, required UTM fields, current tracking/redirect QA evidence, and owner publish approval.

## Read-Only Requirements

The mapping helper and validators are read-only/local-only:

- `scripts/prepare_line31_final_creative_mapping.py`
- `scripts/prepare_line31_launch_readiness_from_assets.py`
- `scripts/validate_line31_final_creative_drop_intake.py`
- `scripts/validate_line31_current_final_creative_drop.py`
- `scripts/validate_line31_final_creative_mapping.py`
- `scripts/validate_line31_launch_readiness.py`

They may read the LINE31 evidence packet, compute local hashes, validate JSON, and print reports. They must not mutate `db/app.db`, `excel_ui/SALES_KSP_CRM_V3.xlsx`, source pointers, scheduler state, Web_automation state, Meta/Kaspi/WebUI/API state, prices, stock, cash, PO state, or owner publication surfaces.

The preparation helper is the preferred launch-day bridge from final local video/thumbnail files to the mapping JSON:

```bash
python3 scripts/prepare_line31_final_creative_mapping.py \
  --creative-id line31_countrywide_v1 \
  --asset-dir /absolute/path/to/final_creative_drop_folder \
  --final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 \
  --duration-seconds 18 \
  --utm-placement reels \
  --landing-url 'https://acmewear.pro/line31' \
  --kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' \
  --creative-ready-declared \
  --tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json \
  --output exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json \
  --overwrite
```

By default the helper prints JSON to stdout and does not write files. It can either use explicit `--video`/`--thumbnail` paths or auto-detect exactly one video plus exactly one thumbnail from `--asset-dir`. It computes local SHA-256 hashes, injects required LINE31 UTM fields, refuses to overwrite output without `--overwrite`, and does not mark owner publish approval unless `--owner-approved` is explicitly supplied after the exact owner phrase and current tracking/redirect QA evidence are present.

Preferred one-shot launch-day local bridge:

```bash
python3 scripts/validate_line31_final_creative_drop_intake.py \
  --asset-dir /absolute/path/to/final_creative_drop_folder \
  --final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 \
  --landing-url 'https://acmewear.pro/line31' \
  --kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' \
  --json

python3 scripts/prepare_line31_launch_readiness_from_assets.py \
  --creative-id line31_countrywide_v1 \
  --asset-dir /absolute/path/to/final_creative_drop_folder \
  --final-asset-uri https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4 \
  --duration-seconds 18 \
  --utm-placement reels \
  --landing-url 'https://acmewear.pro/line31' \
  --kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' \
  --creative-ready-declared \
  --approval-text-file /absolute/path/to/pasted_owner_approval.txt \
  --tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json \
  --overwrite \
  --json
```

Run `scripts/validate_line31_final_creative_drop_intake.py` first. It checks exactly one video plus exactly one thumbnail, rejects placeholder launch URLs, and can require exact owner approval with `--require-approval`. The one-shot wrapper then records exact owner approval evidence when provided, writes the mapping, rebuilds the launch preflight packet, and returns the current gate in one local-only run. It does not publish and does not mutate protected DB/workbook, scheduler, source-pointer, Web_automation, Kaspi/API/WebUI/Meta, campaign, price, stock, cash, PO, supplier, or owner-publication surfaces.

Before running either bridge, refresh the stable status pointer:

```bash
python3 scripts/write_line31_current_launch_status.py --json
python3 -m json.tool docs/current/LINE31_LAUNCH_CURRENT_STATUS.json
python3 scripts/validate_line31_current_final_creative_drop.py --json
```

Then read `latest_drop_intake.checklist_path` from `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json` and follow the current `FINAL_CREATIVE_DROP_CHECKLIST.json`. The checklist is the machine-readable launch-day contract for exact-one video/thumbnail intake, required mapping fields, placeholder replacement, current tracking/redirect QA evidence, owner-approval policy, safety boundaries, final check commands, advisory repo-health commands, and the internal Kaspi keep-on policy. Operators and agents must not hard-code an older timestamped drop-intake folder when the stable pointer identifies a newer one; do not hard-code an older timestamped drop folder for launch-day execution.

Use `scripts/validate_line31_current_final_creative_drop.py --json` after refreshing `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json` when the agent should validate the latest drop folder selected by the stable pointer. Use the explicit `scripts/validate_line31_final_creative_drop_intake.py --asset-dir ...` route only when intentionally validating a non-current or explicitly supplied folder.

If `--asset-dir` contains multiple candidate videos or thumbnails, the wrapper must fail closed. The operator should either clean the drop folder or pass explicit `--video` and `--thumbnail` paths.

When `--owner-approved` is used, `--approval-evidence-file` and `--tracking-qa-evidence-file` are required. The approval evidence file must be separate from the approval-template file, must contain the exact owner approval phrase, and its SHA-256 is stored in the mapping. The tracking/redirect QA evidence file must be current JSON with `gate=GREEN`, stored browser events, `/go/:color` redirect proof, fallback-route proof, and fake-ecommerce fail-closed checks; its SHA-256 is stored at `tracking_redirect_qa.evidence_sha256`. This prevents strict readiness from being satisfied by naked booleans or stale assumptions.

Before any final publish handoff, build a read-only preflight packet:

```bash
python3 scripts/build_line31_launch_preflight_packet.py --json
```

The packet captures pending and strict readiness results, creative validation results, protected `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx` hashes, the next-action report, and the exact command list. It is evidence-only and must not mutate protected surfaces or external systems.

Before marking the active goal complete, run the completion audit:

```bash
python3 scripts/audit_line31_active_goal_completion.py --json
```

This audit refreshes the current non-creative validator matrix by default, then must exit non-zero while final creative mapping, current tracking/redirect QA evidence, or exact owner approval evidence is missing. It may pass only when pending readiness, strict readiness, final creative hashes, exact approval evidence, tracking/redirect QA evidence, the current non-creative matrix, owner objective facts, and the internal Kaspi keep-on policy are all proven.

Owner objective facts covered by the audit:

- option-2 unrelated failure repair is green or explicitly quarantined;
- latest `Cash_Balances`/SHR timing is accepted, including SHR #18 `7000 CNY` as paid with final exchanger receipt pending;
- protected reserve is exactly `800000 KZT`;
- LINE31 stock uses the owner-approved April leftovers plus PO1-A arrival rebuild.

The audit must call `scripts/validate_line31_owner_objective_source_freshness.py` before treating those owner objective facts as achieved. That verifier reads the current cash workbook in read-only mode, confirms the latest `Cash_Balances` timestamp, required SHR sheets, SHR #18 payment row, protected reserve proof `expected_min_kzt=800000`, LINE31 source packet `GREEN` gates, and LINE31 stock totals. Cached owner-fact JSON alone is not enough for completion.

Do not use `--ignore-current-noncreative-matrix` for the real launch state. That flag is only for fixtures or historical packet inspection.

Do not use `--skip-noncreative-refresh` for the real launch state. That flag is only for fixtures or historical inspection where refreshing current validators would hide the older evidence being inspected.

After the owner provides the exact final approval phrase, record it as local evidence before regenerating the mapping:

```bash
python3 scripts/record_line31_owner_publish_approval.py \
  --mapping exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json \
  --require-mapping-ready \
  --approval-text-file /absolute/path/to/pasted_owner_approval.txt \
  --json
```

The standalone recorder rejects non-exact approval text, refuses to run with `--require-mapping-ready` until the mapping is populated and strict-valid except for the expected pending owner-approval boolean, writes a timestamped local evidence file, and returns the `approval_evidence_path` plus `approval_evidence_sha256` required by the strict mapping validator. The one-shot helper may record approval while generating the mapping because it validates the produced mapping immediately in the same local-only run.

Launch-day command surfaces must list the owner source-freshness verifier explicitly:

```bash
python3 scripts/validate_line31_owner_objective_source_freshness.py --json
```

This is intentionally redundant with the active-goal audit call. It makes the workbook/SHR/LINE31 stock proof visible in closeout logs before final creative publish authority is considered.

Broad repo-health commands such as `python3 scripts/validate_params.py --strict` and `python3 scripts/run_end_of_day.py --dry-run --skip-api-sync --verbose` are advisory for this LINE31 launch gate unless their failure is also represented by a LINE31 launch-blocking matrix row. They should be captured in review logs, but a current-day broad repo-health failure must not be re-labeled as a LINE31 launch blocker without evidence.

The read-only preflight packet must also embed that proof as `owner_objective_source_freshness.json` and include a human-readable owner source-freshness section in `line31_launch_preflight_summary.md`. This keeps the packet self-contained for review instead of forcing a reviewer to reconstruct source freshness from separate terminal output.

Strict readiness treats missing tracking/redirect QA evidence as a launch blocker. The evidence should normally come from the latest acmewear.pro LINE31 live-proof JSON, then be passed to the mapping helper with:

```bash
--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json
```

## Meta API Primary Route

The launch authority remains in Autonomous_business, but Meta execution/control must now use `~/Docs/Business_3/Facebook_ads` as the primary ad-platform repo.

Before any final Meta publish conversation, run the read-only API preflight from that repo:

```bash
PYTHONPATH=. python3 scripts/preflight_meta_api_primary.py --live-readonly --json
```

The resulting packet must be treated as evidence of API readiness only. `ENABLE_META_WRITE=1` is not owner approval. Any live campaign/ad/ad set/creative/audience/budget/status/URL mutation must require an exact owner approval phrase tied to that preflight packet's `preflight_evidence_lock.json` path and SHA.

Chrome/Ads Manager UI is a fallback route only when the Graph API is blocked or cannot expose a required field/action. If fallback is used, record why the API route was insufficient.

Regression coverage:

```bash
pytest -q tests/test_audit_line31_active_goal_completion.py tests/test_validate_line31_owner_objective_source_freshness.py tests/test_prepare_line31_launch_readiness_from_assets.py tests/test_record_line31_owner_publish_approval.py tests/test_build_line31_launch_preflight_packet.py tests/test_prepare_line31_final_creative_mapping.py tests/test_report_line31_next_launch_action.py tests/test_validate_line31_launch_readiness.py tests/test_validate_line31_final_creative_mapping.py tests/test_create_line31_final_creative_drop_intake.py tests/test_validate_line31_final_creative_drop_intake.py
```

The focused tests prove that current pending-creative mode fails when latest non-creative blockers remain, strict publish mode fails until creative is filled, tracking/redirect QA evidence is hashed, and non-creative gates clear, the completion audit refreshes current non-creative validators and still refuses the current incomplete state, owner objective facts are backed by current source freshness checks, publish-ready synthetic mappings pass when fixture non-creative evidence is clean, the approval recorder rejects non-exact text, the drop-intake validator rejects ambiguous folders and placeholder URLs, the one-shot helper records approval evidence and rebuilds the preflight packet without publishing, the mapping helper computes hashes without implicit approval, the preflight packet captures the current state without protected-surface mutation, and the validator commands do not mutate protected DB/workbook surfaces.

Operator next-action command:

```bash
python3 scripts/report_line31_next_launch_action.py
```

This command must stay read-only and should print the current gate, missing creative fields, approval path, and serialized final-publish starter prompt.

Stable current-status pointer:

```bash
python3 scripts/write_line31_current_launch_status.py --json
```

This command writes `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json` and `docs/current/LINE31_LAUNCH_CURRENT_STATUS.md`. Those files are operator pointers only: they expose the current report, latest preflight packet, latest drop-intake folder, latest drop-intake checklist path, current-pointer drop validator command, preferred one-shot command, and remaining blockers. They do not replace strict validators or the active-goal completion audit.

## Launch Policy

Internal Kaspi LINE31 campaigns stay ON until the owner separately declares final creative readiness and gives an explicit pause approval. The Meta launch readiness validator must not blend internal Kaspi directional activity into Meta conversion truth.

Final publish is blocked unless the exact owner approval phrase in:

`exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_publish_intake_and_approval.md`

is present in a separate approval-evidence file after final creative mapping is filled, current tracking/redirect QA evidence is SHA-verified, and strict validators pass.
