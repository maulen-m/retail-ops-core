# WEBUI_CRM_CHRONOLOGY_AUTHORITY_CONTRACT

## Purpose
Define the fail-closed fallback when a deterministic WebUI-to-CRM shipped-day rule is not authority-backed.

## Decision
- WebUI remains historical status truth.
- CRM/workbook remains the chronology authority for shipped-day publication.
- Do not bypass DB-backed validation/publication with raw WebUI chronology.

## Scope
This contract applies when `exports/validation/webui_shipped_authority_recon/<as_of>/shipped_day_authority_decision.json`
ends with:
- `CRM_REMAINS_CHRONOLOGY_AUTHORITY`

## Required Behavior
- WebUI archive packs and ledgers may still provide historical status lineage and delivery/return evidence.
- Exact shipped-day publication must stay anchored to the CRM/workbook chronology path until a rule is later proven.
- Owner-facing publication on `truth_source=webui_archive` must still require the workbook chronology gate.
- WebUI chronology comparison artifacts remain diagnostic evidence, not the publication authority, while this contract is active.

## Fail-Closed Rules
- If the authority decision is `CRM_REMAINS_CHRONOLOGY_AUTHORITY`, publication cannot treat WebUI-projected dates as the final shipped-day chronology.
- Missing workbook anchor evidence is a hard stop for publication.
- Any future attempt to promote a WebUI-only chronology rule must update this contract and the shipped-event projection contract first.

## Rationale
The current authority decision shows that CRM dates align strongly with API `planned_shipment_date`, but no single WebUI-only transformation closes the full Jan-Feb mismatch population. WebUI is therefore preserved as status-history truth, while CRM/workbook remains the chronology anchor for shipped-day publication.
