# Ads Active Scope Contract

## Purpose
- Encode which stores are expected to have Kaspi ads coverage by effective date.
- Prevent validators from treating intentionally inactive stores as missing-ads failures.
- Keep the rule explicit, versioned, and auditable.

## Source Of Truth
- Config file: `config/ads_active_scope.yaml`

## Rules
- Resolution is store-by-store and date-by-date.
- If a store/date falls inside an active window, ads coverage and spend-reality gates apply.
- If a store/date falls inside an inactive window, ads coverage is not required for those sold rows.
- If a store has no matching window, `default_active` from the config applies.
- Inactive scope suppresses false missing-ads failures only. It does not fabricate ads spend or relax unrelated gates.

## Current Effective Policy
- `ACMEWEAR`: active for historical source-backed economics from `2025-01-01`
- `STOREB`: active from `2026-03-08` forward under current operator policy; Jan-Feb 2026 is not ads-required
- `UNIVERSAL`: explicitly inactive from `2026-02-22`; no historical Jan-Feb 2026 active window is encoded without source evidence
- Unlisted stores default to inactive until explicitly added

## Evidence Basis
- Active scope is not inferred from sales volume.
- Historical windows must be backed by marketing-source evidence or an explicit operator decision with a concrete effective date.
- Fresh Jan-Feb 2026 source refreshes for `STOREB` and `UNIVERSAL` returned zero campaigns/products, so those stores are not treated as ads-required for that historical window.

## Change Management
- Update this contract first.
- Then update `config/ads_active_scope.yaml`.
- Then update tests and validators.
- Broad or retrospective quarantine is not allowed without explicit documented rationale.
