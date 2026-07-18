# OPEX Owner Input Contract - 2026-07-02

Purpose: define the Stage-B OPEX/loan source contract for cashflow commitments from
`2026-07-02` forward.

## Status

P1(a) owner approval released the Stage-B hold on `2026-07-03`: apply the normalized
2026-07-02 owner workbook truth, set `cash_floor_cons_mult` to `1.15`, and accept
`G-SCHED-02` remaining RED until cash improves. No preflight override is authorized.

Stage-B governed apply ran on `2026-07-03` under
`exports/validation/g_cashfloor_stageb_20260703/`: future OPEX rows at or after
`2026-07-02` were replaced from the owner-approved writer output, generated config
was refreshed, and `validate_cashflow_invariants.py` passed. The supervised EOD run
remains held because live post-apply preflight did not reproduce the owner packet's
expected `min_cash < floor` state; current preflight reports the conservative floor
passing from live cashflow history, so EOD behavior under the expected RED state is
not proven by this run.

## Authority

- Owner decision record: `config/owner_decisions/opex_loans_floor_refresh_2026_07_02.json`
- Intake authority: `docs/plan/green_path_2026-06/green_path_run/OWNER_APPROVALS_20260702_RESUME.md`
- Source workbook: `exports/opex_owner_input/2026-07-02/OPEX_and_Loans_OWNER_INPUT_MINIMAL_20260702.xlsx`
- Normalizer: `core/cashflow/opex_owner_input.py`
- CLI: `scripts/normalize_opex_owner_input.py`
- Stage-B writer: `scripts/apply_opex_owner_input_schedule.py`

The January protocol workbook is not the source for new OPEX commitments at or after
`2026-07-02`.

## Sheet Schema

`OPEX_INPUT` uses row 6 as the header row. Required operational columns are:
`owner_action`, `expense_name`, `account`, `expense_type`, `schedule`,
`payment_day_of_month`, `source_monthly_kzt`, `owner_monthly_kzt`,
`include_in_cashflow`, `months_left`, `principal_left_kzt`, `review_priority`,
`owner_notes`, and `source_ref`.

`LOANS_INPUT` uses row 6 as the header row. Required operational columns are:
`owner_action`, `loan_name`, `source_status`, `bank`, `account`, `opex_name`,
`source_payment_day`, `next_due_date_after_2026_07_02`,
`source_monthly_payment_kzt`, `owner_monthly_payment_kzt`, `principal_kzt`,
`balance_now_source_kzt`, `months_total`, `last_schedule_date`,
`include_in_cashflow`, `review_priority`, `owner_notes`, and `source_ref`.

`ADDITIONS` carries dated loan schedules and loan facts. It is authoritative for rows that the
owner explicitly confirmed as dated-schedule overrides.

## Inclusion Precedence

1. `owner_action` values `STOP`, `CLOSED`, or `CLOSE` exclude the row even when
   `include_in_cashflow=YES`.
2. `include_in_cashflow=NO` excludes the row.
3. `include_in_cashflow=REVIEW` is excluded until an owner decision resolves it.
4. A nonblank `owner_monthly_*` value overrides a source monthly value, except when the owner
   decision record explicitly restores the source value.
5. Blank owner-added rows are ignored.

The 2026-07-02 decision resolves these REVIEW items for Stage B:

- KaspiGOLD_KZ / GOLD_store-d: use V2 at `80,000` KZT per month.
- Gym_memberships: use the confirmed source value `30,000` KZT per month, not `90,000`.
- GOLD_Acmewear / KaspiGOLD_OF: use interim `126,693` KZT per month and tag commitment rows
  with `OWNER_INTERIM_REVISIT_20260703`.
- Internet: pay-day `27` is confirmed.
- LLM_6 and LLM_7: excluded because CLOSED wins over include=YES.
- employee_1 and MELVIS(tax): excluded.

## Dated Schedule Overrides

`ADDITIONS` dated schedules override flat OPEX rows for confirmed loan classes.

- KaspiGOLD_Uni / GOLD_universal uses the dated declining ADDITIONS schedule. The first unpaid
  cashflow date is `2026-07-21` for `166,000` KZT.
- BCC 5M / BCC_universal_5M uses account `Universal`, safe pay-day `9`, and keeps the
  `2026-04-11` screenshot evidence date distinct from the `2026-04-04` owner-stated context
  date.

Only unpaid or to-be-paid dates at or after the Stage-B boundary are inserted into future
commitments. Paid dates remain historical evidence and do not create new future commitments.

## July 2026 Owner-Stated Pay-Date Override

The owner decision
`config/owner_decisions/july_payment_commitments_2026_07_17.json` is the newer
authority for the four remaining July obligations named there. It overrides only
the exact July 2026 commitment preimages pinned in that file; later recurring
months remain governed by the 2026-07-02 workbook schedule.

For these rows, the owner-stated date is the planned cash outflow date. For loan
payments it must be at least one calendar day before the bank withdrawal date; a
contractual due date or withdrawal date must not replace it in the commitment
calendar. Applied rows carry the `owner_stated_pay_date` tag and the decision's
run ID in `notes` because `fact_cashflow_commitments` has no dedicated provenance
or run-ID columns.

The Stage-B writer applies this overlay fail-closed: every superseded row must
match its pinned date, ref ID, and amount exactly before any generated output or
DB replacement is accepted.

## DB Write Contract

The Stage-B writer is dry-run by default. Apply requires both:

- `ENABLE_CASHFLOW_WRITE=1`
- `--apply`

The writer must replace only future OPEX rows:

```sql
DELETE FROM fact_cashflow_commitments
WHERE commit_type = 'OPEX'
  AND commit_date >= '2026-07-02';
```

It then inserts the owner-approved 365-day commitment horizon. Rows before `2026-07-02` remain
unchanged so historical owner PnL stays stable.

The writer also regenerates:

- `config/opex/opex_commitments.csv`
- `config/opex/opex_schedule.yaml`

`config/opex/opex_schedule.yaml` must point `source_xlsx` to the 2026-07-02 owner workbook.

## Review Handling

REVIEW rows are not permission to guess. They either remain excluded or are resolved by a named
owner decision. Interim values are allowed only when the decision record says not to block; the
commitment row notes must retain the interim provenance flag and revisit date.
