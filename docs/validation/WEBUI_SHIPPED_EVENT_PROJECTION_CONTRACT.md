# WebUI Shipped Event Projection Contract

This contract defines the fail-closed shipped-event projection used when WebUI archive history is compared against CRM shipped-day style chronology.

If the authority decision is `CRM_REMAINS_CHRONOLOGY_AUTHORITY`, this projection remains diagnostic only and publication falls back to `docs/validation/WEBUI_CRM_CHRONOLOGY_AUTHORITY_CONTRACT.md`.

## Inputs

- frozen WebUI full-parse pack lineage
- frozen WebUI status ledger lineage
- no new scrape is permitted for this projection

## Event Basis

- primary event date: `planned_courier_at`
- fallback event date: `created_at`
- returned orders are excluded
- cancelled orders are excluded because the projection is built from delivered lineage only

## Hard Rules

- the shipped projection must not depend on DB-matched rows
- the projection is pack-native and ledger-scoped
- the projection is filtered by projected shipped date, not by delivered date
- missing `planned_courier_at` may fall back to `created_at`, but missing both is not promotable
- any future contract change must be documented before validator logic changes

## Fail-Closed

- if the ledger does not resolve pack lineage, hard-fail
- if the pack rows are empty, hard-fail
- if the delivered lineage is empty, hard-fail
- if a returned order would be included, hard-fail

## Rationale

`planned_courier_at` is the closest shipment-adjacent field available in the raw WebUI archive exports. The CRM comparison path therefore uses this event basis first, with `created_at` only as a deterministic fallback for rows where `planned_courier_at` is blank.

This contract is promotable only if `scripts/validate_webui_crm_shipped_day_authority.py` proves a deterministic WebUI rule against shipped-truth / waybill / API authority.
