# Food workflow — Customer → Merchant → Driver (TDP-grounded)

A GoFood order needs three entities, in a fixed order: a **customer** places the order **from a
merchant**, and a **driver** is required to fulfil (pick up and deliver) it. This is a strictly
longer chain than Transport (`../transport/index.md`'s Customer → Driver) because the order cannot
exist without knowing which merchant it was placed against.

## Keywords

`ORDER`, `FOOD`, `GOFOOD`, `MERCHANT`, `GROUP_ORDER`, `BOOKING`, `DELIVERY`, `MERCHANT_ACCEPTED`,
`OTW_PICKUP`, order-number prefix `F-` — see [../index.md](../index.md#examples) for where each
token is grounded (TDP `BookingState`, TestBuddy's `handle_group_order_*`/`handle_gofood_*` tools,
GBT's `gofood/src/test/java/tests/GroupOrder/**` suite).

## Required entities, in order

| Step | Entity | Why it must come first |
|---|---|---|
| 1 | Customer (`../../customer/index.md`) | Same pool-fetch prerequisite as Transport — the order needs a `customerId` before anything else. |
| 2 | Merchant | The customer's order is placed against this merchant. Not a TDP-pooled entity; see the knowledge-gap note. |
| 3 | Merchant accepts the order | The order transitions to `MERCHANT_ACCEPTED` (`BookingState`) before any driver is involved. |
| 4 | Driver (`../../driver/index.md`) | Fetched from the pool only once the order has passed merchant acceptance — see `ensureDriverIfRequired` below. |

## Entry point

Same `POST /aep/test-data-generator/booking/createBooking` (`BookingController.java`) and
`GetBookingRequest` shape as Transport, dispatched to `GoFoodBookingService.java` when
`module: "gofood"` (`BookingModule.java`):

```
module: "gofood"
customerId, merchantId, merchantType, driverId, driverType,
serviceAreaId, paymentMode, bookingType, bookingStatus, targetState
```

`GoFoodBookingService` also exposes `createSDFBookingFood`, `createChainingBookingFood`,
`createStaticPoolingBooking`, and `updateBookingStatus` — treat these as Food-specific operation
variants the same way Consumer's `/get-add-segment`/`/get-subscription` are pool-fetch variants
(`../../sequence/sequence.md` § 8), not separate workflows.

## Merchant — not a TDP-managed entity

Unlike Customer and Driver, there is **no merchant test-data category, model, service, or pool** in
this codebase — confirmed by the absence of any `TestDataCategoryMerchant`-style enum, any
`MerchantController`, or a `/get` pool path for merchants. `merchantId`/`merchantType` are plain
pass-through `String` fields on `GetBookingRequest` and `BookingModel` (`merchantId` only;
`merchantType` is not persisted on the model). At order-creation time, merchant identity actually
comes back **from the live GoFood order response** (`FBONV1Response.getMerchant().getSaudagarID()`
in `GoFoodBookingService.java`), not from a TDP-seeded fixture.

Identification consequence, per the parent skill's decision table
(`../../../SKILL.md#status-decision-table`):

- **Never propose a `MERCHANT_WITH_*`-style category.** It does not exist in this codebase; a
  catalog matcher returning one for a Food fixture fails the validation gate the same way an
  uncorroborated driver category would (`../../driver/index.md`'s ~379-candidate warning).
- A fixture whose *only* unmet signal is merchant state (e.g. "an in-operation-hours merchant", "a
  merchant with pooling supported" — `../../test_data_domains.md` § MERCHANT) routes to
  `TDP_OPERATION_FALLBACK` if a live merchant-lookup operation exists, or `TDP_NOT_SUPPORTED` with
  `missing_operations` naming the gap, otherwise. Do not silently substitute a hardcoded/example
  `merchantId` — that is inventing an identifier, prohibited by the parent skill's guardrails.

## The driver auto-assignment guard

`GoFoodBookingService.ensureDriverIfRequired`: a driver is fetched from the pool only if `driverId`
is null **and** the requested `bookingStatus` is past `MERCHANT_ACCEPTED` in the (external,
dependency-owned) `BookingState` enum. In other words: **the merchant accepts the order first, and
only then is a driver assigned to fulfil it** — this is the Food equivalent of Transport's
`isInitialStatus` guard (`../transport/index.md`) and is why the entity order is Customer →
Merchant → Driver, not Customer → Driver → Merchant: the driver-fetch is conditioned on merchant
acceptance having already happened, never the reverse.

## Booking status vocabulary — a different enum from Transport

Food orders use `BookingState` (external enum, not owned by this repo — referenced in
`BookingService.java` and `GoFoodBookingService.java`), **not** `BookingConfig`
(`../transport/index.md`'s table). Known values include `MERCHANT_ACCEPTED` and `OTW_PICKUP`. Do
not carry a `BookingConfig` value (`scheduled`, `confirmed`, …) onto a Food fixture, and do not
assume the two enums share ordinals — the "past X" comparisons in each guard are evaluated against
their own enum only.

## Order-number vocabulary

`OrderType.java`: Food orders carry the `F-` prefix (Transport is `RB-` — see
`../transport/index.md`).

## Where the rest lives

As with Transport, wallet top-up for the customer is a separate prerequisite closed by the Consumer
bundle's recharge operation (`../../sequence/sequence.md`), not documented on this page — this page
only documents entity existence and ordering (Customer → Merchant → Driver).
