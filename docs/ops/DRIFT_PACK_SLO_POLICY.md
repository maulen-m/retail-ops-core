# Drift Pack SLO Policy

## Scope
Operational SLO policy for daily drift artifacts generated at:
- `exports/validation/<YYYY-MM-DD>/single_truth_drift_pack.md`
- `exports/validation/<YYYY-MM-DD>/single_truth_drift_pack.json`

## Severity Model
- `Critical`:
  - any strict gate hard-failure represented in drift pack status
  - missing required anchor health or strict validation sections
  - unresolved publication blocker counters above `0`
- `Warning`:
  - non-blocking alignment drifts that are contract-declared as informational
  - optional coverage gaps with explicit fallback status
- `Info`:
  - all checks green or known non-blocking notes

## Stop-line Rules
Stop-line when any `Critical` drift is present.

Minimum operator action on stop-line:
1. Do not publish or automate dependent outputs.
2. Resolve source check failure and regenerate drift pack.
3. Re-run strict gate chain before resuming operations.

## Fail-Closed Contract
Drift-pack policy is fail-closed:
- unknown or unclassified drift status is treated as `Critical`
- missing contract sections are treated as `Critical`
- no warn-only downgrade for checks marked strict
