# Kaspi Pricelist Safe Active Patch Contract

Scope: Autonomous_business planning and approval lanes that request Kaspi merchant price, stock-display, or sellability changes through `Web_automation`.

## Boundary

`Autonomous_business` does not upload Kaspi pricelists and must not mutate `Web_automation` runtime state directly. It may prepare owner approvals, evidence packets, target SKU tables, and review-only workbooks.

The execution owner for live merchant pricelist transport is:

`$HOME/Docs/Web_automation/Docs/offer_ops/PRICELIST_SAFE_ACTIVE_PATCH_CONTRACT.md`

## Required Rule

Any Autonomous_business lane that proposes a Kaspi pricelist price, stock-display, or activation change must request the Web_automation safe-active-patch path:

```bash
python3 -m web_auto.cli --json kaspi-pricelist safe-active-patch \
  --store <STORE> \
  --updates-csv <updates.csv> \
  --expected-active-before <N> \
  --expected-active-after <N> \
  --apply \
  --confirm FULL_ACTIVE_STATE \
  --verify-after-upload \
  --headless
```

The apply command is only valid after a fresh owner approval names the exact store, SKU rows, generated workbook, expected active-before count, expected active-after count, price/stock values, and allowed activation/deactivation set.

## Inventory Truth Separation

Kaspi pricelist stock values such as `PP1` are live marketplace availability-display inputs. They are not physical inventory truth in Autonomous_business.

Physical inventory truth still comes from:

- owner physical overrides;
- owner-approved stock anchors;
- accepted inbound events;
- shipment/status depletion rules;
- accepted return-QC rules.

## Stoplines For AB Agents

Stop before asking Web_automation to apply if any of these are true:

- the request is a target-only ACTIVE workbook or one-row patch;
- the request uploads ARCHIVE to turn rows on;
- the expected active-before or active-after count is missing;
- any baseline ACTIVE SKU would be dropped without explicit owner-approved deactivation;
- a pricelist PP value is being treated as physical inventory truth;
- owner approval does not name the exact live mutation and `FULL_ACTIVE_STATE` confirmation phrase.

## Required AB Evidence Fields

Closeouts and owner approval packets must include:

- target store;
- target merchant SKU rows;
- expected price and PP columns;
- whether each target row starts from ACTIVE or ARCHIVE;
- expected ACTIVE row count before and after;
- whether deactivation is intended;
- statement that PP/pricelist stock is display-state, not inventory truth;
- Web_automation safe-active-patch output folder after dry-run/preflight.
