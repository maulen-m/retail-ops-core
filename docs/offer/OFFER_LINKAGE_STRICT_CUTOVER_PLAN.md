# Offer Linkage Strict Cutover Plan

## Purpose
Cut over from informational offer-linkage checks to strict fail-closed enforcement without breaking promotion flow.

## Baseline
- Validator: `scripts/validate_offer_linkage.py`
- Current strict toggle: `AB_REQUIRE_OFFER_LINKAGE_STRICT=1`
- Strict chain entrypoint: `scripts/validate_params.py --strict`

## Cutover stages
1. **Observe**
   - Run strict chain with default non-blocking linkage and capture error inventory.
2. **Remediate**
   - Reduce unresolved/ambiguous linkage rows and fix bidirectional map gaps.
3. **Enforce**
   - Set `AB_REQUIRE_OFFER_LINKAGE_STRICT=1` for scheduler/production paths.
4. **Lock**
   - Keep strict mode as default and remove temporary bypass.

## Required evidence before enforce
- `validate_offer_linkage.py` returns `ok=true`.
- `validate_params.py --strict` green with strict linkage enabled.
- Regression tests confirm no silent non-strict path in scheduler flows.

## Stop-line criteria
- Any unresolved or ambiguous linkage in strict mode.
- Any production path running without explicit strict linkage intent.

## Rollback
1. Temporarily disable strict linkage env toggle.
2. Keep validator output visible in strict logs as non-blocking detail.
3. Re-enable strict linkage only after map cleanup evidence is green.
