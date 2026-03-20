# PLAN_OWNER_COCKPIT_MAIN_PROMOTION_2026-03-20

## Scope
Promote the monitoring-grade owner cockpit into `main` without widening deferred semantics.

## Promotion path
- Chosen path: `B`.
- Reason: `git diff origin/main...HEAD` contains broad unrelated scope well beyond the owner-cockpit commit set, so a direct PR from the current branch tip would make review and rollback noisy.
- Promotion branch source: `origin/main`.
- Exact commit set to cherry-pick in order:
  - `66ed98c`
  - `41361a2`
  - `17ddec4`
  - `4585fcb`
  - `10682d1`
  - `1d3ee2c`

## Deferred items that remain deferred
- owner profit publication unlock
- PO planning freshness closure
- historical autonomy reprove on `2026-03-08`

## Gates
- replay the full promotion gate chain on the exact promotion head
- do not reuse earlier green evidence unless the delta is proven docs/evidence-only

## Stop conditions
- cherry-pick conflict that changes business meaning
- any required gate failure
- any hidden write path or semantic widening


## 2026-03-20 scope correction
- Initial path-B cherry-pick attempt onto `origin/main` failed the exact-head replay immediately: `validate_params.py --strict --as-of 2026-03-09` raised `ModuleNotFoundError: core.sales.ocean_drop_anchor`.
- This proved that `origin/main` does not contain the canonical owner-runtime green-center dependency chain needed by the owner cockpit.
- Revised promotion path: PR the current branch tip instead of continuing a misleading minimal cherry-pick lane.
- Reason: the six-commit set is not self-sufficient on top of current `origin/main`; direct promotion from the working branch is the only honest path unless a much larger dependency-chain cherry-pick is assembled and reproven.
