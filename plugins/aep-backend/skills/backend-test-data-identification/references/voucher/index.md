# Voucher identification (TDP-grounded)

TDP models a voucher as a **batch-level pooled entity**, selected by service type and country —
narrower than the Consumer/Driver bundles' per-account categories, and narrower than the
per-voucher redemption/eligibility state `../test_data_domains.md` describes. Ground identification
in what the code actually models, not the domain file's illustrative signal list.

## What TDP actually models: voucher batches, not individual vouchers

`VoucherModel.java` (`@Document(collection = "vouchers")`) fields:

| Field | Mongo key | Type |
|---|---|---|
| `voucherBatchId` | `voucher_batch_id` (`@Id`) | — |
| `countryCode` | `country_code` | — |
| `serviceTypeIds` | `service_type_ids` | `List<Integer>` |
| `voucherBatchType` | `voucher_batch_type` | — |

There is **no per-voucher field** for redemption state, usage caps, expiry, or eligibility —
`test_data_domains.md`'s VOUCHER signals (`Expired voucher`, `Redeemed`, `Usage limit`, `Eligible`,
a named promo like `SAVE20`) describe a *promo-code* concept that this codebase does not implement.
What exists is closer to "a batch of vouchers applicable to these service types in this country."

## Fetching voucher data

`VoucherService.java` methods, each backed by `VoucherRepository.java` derived queries:

| Method | Selects by |
|---|---|
| `getVoucherBatchIds` / `getAllVoucherBatches` | all batches |
| `getVoucherDataByVoucherBatch` / `getVoucherDataByVoucherBatchId` | `voucherBatchId` |
| `getVoucherDataByVoucherBatchType` | `voucherBatchType` |
| `getVoucherDataByServiceTypeAndCountryCode` | `serviceTypeIds` + `countryCode` |

Response shape: `GetAllVouchersResponse.java` — `List<VoucherModel> data`.

Pool-entity enum: `TestDataCategory.java` — `VOUCHER("voucher")` is a recognized
`testDataEntity`, alongside `CUSTOMER` and `driver`. Request filters
(`GetTestDataRequest.java`): `countryCode`, `voucherBatchType`, `serviceTypeId`.

## Identification consequence

- A fixture naming a **service type + country** ("a voucher for Bike bookings in ID") maps
  directly to `getVoucherDataByServiceTypeAndCountryCode` — `TDP_SUPPORTED`.
- A fixture naming a **specific promo code, redemption status, or usage-limit boundary** ("an
  expired SAVE20 voucher already redeemed once") has no corresponding field anywhere in
  `VoucherModel` — this is `TDP_PARTIAL` when the voucher **batch** still resolves and only the
  per-voucher state is unserved, `TDP_NOT_SUPPORTED` when nothing resolves (or
  `TESTBUDDY_OPERATION_FALLBACK` if a TestBuddy/Pertamax/GBT
  tool separately exposes promo-lifecycle operations), not a gap to paper over with an invented
  field. Record the specific missing concept (e.g. `redemption_state`) in `missing_operations`.
- `voucherBatchType` is a token to corroborate against, the same way `isEnabled` corroborates a
  customer/driver category — don't accept a batch type the matcher returns without a signal in the
  fixture naming it.

## Where the rest lives

Vouchers are not chained into the booking workflows in this codebase — no `voucherBatchId` field
appears on `GetBookingRequest.java` or `BookingModel.java`. Treat a fixture combining a voucher with
a Transport/Food booking as two identification concerns (`VOUCHER` here, plus
[../workflow/index.md](../workflow/index.md) for the booking), not one composite record, until code
shows otherwise.
