# STOREB Offer 116515378_626543467 Owner Decision Request

Created: 2026-05-19 11:24 +05

## Resolution

Resolved by human owner answer at 2026-05-19 11:33 +05.

Canonical owner-confirmed mapping for the current Agent914 sales source packet:

```text
sku_key=CL_OC_MEN_LINE52_BLACK
sku_id=CL_OC_MEN_LINE52_BLACK_XL
my_size=XL
```

Recorded in:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/OWNER_CONFIRMED_STOREB_OFFER_116515378_626543467_MAPPING.md`

Future agents should not re-ask this same mapping question unless new contradictory source evidence appears.

## Decision Needed

Agent9144 is `YELLOW` because this offer is not source-identifiable to SKU/size:

- Store: `STOREB`
- Offer ID: `116515378_626543467`
- Product ID: `MTE2NTE1Mzgz`
- Offer name: `Спортивный костюм PRO COMBAT черный`
- Current source rows: `11`
- Terminal delivered sales candidates: `8`
- Open/non-terminal rows: `3`

The source row does not expose size. We cannot infer size from the name.

## Local Hints Only

These are hints, not proof:

- Historical ads/product mapping points the offer token to `sku_key=CL_OC_MEN_LINE52_BLACK`.
- Two older production `sales_fact_v2` rows used `sku_id=CL_OC_MEN_LINE52_BLACK_XL`, `my_size=XL`.
- Older quarantine rows exist for the same offer/product family.

These hints do not prove the current 8 terminal rows are `XL`, and they do not automatically authorize quarantining the new rows.

## Owner Reply Options

### Option A: Exact Mapping

Paste this only if true:

```text
I confirm STOREB offer 116515378_626543467 / product MTE2NTE1Mzgz / "Спортивный костюм PRO COMBAT черный" should be mapped for the current Agent914 sales source packet as:
sku_key=<FILL>
sku_id=<FILL>
my_size=<FILL>
This approval is for copied-temp proof planning only and does not authorize production DB writes, workbook writes, source-pointer writes, scheduler changes, external writes, owner publication, production preflight, or production apply.
```

Likely candidate from historical hints if owner can confirm:

```text
sku_key=CL_OC_MEN_LINE52_BLACK
sku_id=CL_OC_MEN_LINE52_BLACK_XL
my_size=XL
```

### Option B: Visible Quarantine / Exclusion

Paste this if the size cannot be source-proven and should not block stock/ads proof:

```text
I approve a copied-temp-only visible quarantine/exclusion contract for the 8 terminal delivered STOREB rows for offer 116515378_626543467 / product MTE2NTE1Mzgz / "Спортивный костюм PRO COMBAT черный" from sales_fact_v2 green proof, while retaining the 3 open/non-terminal rows visibly until terminal status and identity are resolved. This does not authorize production DB writes, workbook writes, source-pointer writes, scheduler changes, external writes, owner publication, production preflight, or production apply.
```

### Option C: CodeCaptain Review First

Paste this if the owner wants independent review first:

```text
Prepare a CodeCaptain Oracle pack for Agent9144 YELLOW, focused on STOREB offer 116515378_626543467 / product MTE2NTE1Mzgz identity mapping versus visible quarantine/exclusion before Agent915 copied-temp proof.
```

## Recommended Fast Path

If the owner is certain the likely historical mapping is correct, choose Option A.

If the owner is not certain, choose Option B or C. Do not guess.
