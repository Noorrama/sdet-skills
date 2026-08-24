# Workflow bundle — how entities compose into a booking

The Consumer (`../customer/index.md`) and Driver (`../driver/index.md`) bundles each answer *what
is this entity, and which category is it*. This bundle answers the question one level up: **which
entities does a given vertical need, and in what order do they have to exist**, before
`BookingController` (`BookingController.java`, `/aep/test-data-generator/booking/createBooking`)
can be called at all.

`module` on `GetBookingRequest` (`GetBookingRequest.java`) is the vertical discriminator —
`BookingModule.java` enumerates `Transport("transport")`, `Food("gofood")`, `Gosend("gosend")`,
`Gomart("gomart")`, `MultiModal("multimodal")`. Only **Transport** and **Food** are populated as
bundles today; the other verticals (`Gosend`, `Gomart`, `MultiModal`) share the same
`createBooking` entry point but have no dedicated workflow bundle yet — treat a fixture naming one
of them as `match_confidence: medium` against `BookingService.java` directly, the same way an
unbundled domain in `../test_data_domains.md` is handled.

## Domains

| Workflow | Required entities, in order | Description |
|---|---|---|
| [Transport](transport/index.md) | Customer → Driver | A ride: a customer places the booking, a driver is required to fulfil it. **Identifying keys:** `module: "transport"`, `customerId`, `driverId`, `serviceTypeId` (`50`/`66`/`69`/`43`/`67`/`77`/`203`), `bookingStatus` (`BookingConfig` — `scheduled`, `booked`, `confirmed`, `driver_arrived`, `started`, `completed`, `cancelled`, `driver_cancelled`, …), order-number prefix `RB-`. |
| [Food](food/index.md) | Customer → Merchant → Driver | A GoFood order: a customer orders *from* a merchant, and a driver is required to fulfil (pick up and deliver) it. **Identifying keys:** `module: "gofood"`, `customerId`, `merchantId`/`merchantType` (required, no TDP-managed merchant pool — see the bundle's knowledge-gap note), `driverId`, `bookingStatus` (external `BookingState` enum — includes `MERCHANT_ACCEPTED`, `OTW_PICKUP`), order-number prefix `F-`. |

## How to read a workflow statement

1. **Identify the module first.** "Book a ride", "create a booking", "assign a driver to a
   customer" with no food/merchant wording → Transport. "Order food", "GoFood order", "order from a
   merchant/restaurant" → Food. A statement never silently spans both.
2. **Identify which entities the statement already names.** A statement naming only a customer and
   a driver together, with no merchant wording, is still Transport even if it says "order" loosely
   — Food is only signalled by an explicit merchant/restaurant/GoFood mention (`../test_data_domains.md`
   § BOOKING note: "a composite booking category is one fixture and one call").
3. **Never reorder the entity chain.** Transport is Customer → Driver; Food is Customer → Merchant
   → Driver. Each bundle's page shows exactly why the order is fixed (an auto-assignment guard in
   `BookingService.java` that only fires once a prerequisite entity/state exists) — treat that guard
   as the source of truth for sequencing, not the fixture's prose order (same rule as
   `../sequence/sequence.md`'s "sequentially meaningful" signal ordering).
4. **A merchant is never a TDP pool fetch.** Unlike Customer and Driver, there is no
   `TestDataCategoryMerchant`-style enum and no `/aep/test-data-generator/get` pool for merchants —
   see [food/index.md](food/index.md#merchant--not-a-tdp-managed-entity). Don't propose a merchant
   category; route merchant-only signals through `TDP_OPERATION_FALLBACK` or
   `TDP_NOT_SUPPORTED` per the parent skill's decision table.
5. **Wallet top-ups still apply per entity.** Both workflows inherit the account-vs-wallet-amount
   split from the Consumer/Driver bundles (`../customer/index.md`,
   `../driver/index.md`) — a customer/driver needed for a booking is identified by category first,
   and a wallet recharge is only emitted when the amount itself is under test.

## Bundle contents

| File | Covers |
|---|---|
| [transport/index.md](transport/index.md) | Transport booking workflow: Customer → Driver, `BookingConfig` status enum, `serviceTypeId` → driver-type mapping, the driver auto-assignment guard |
| [food/index.md](food/index.md) | Food order workflow: Customer → Merchant → Driver, the `validateFoodMerchant` mandatory-merchant guard, the `ensureDriverIfRequired` guard, and the merchant knowledge gap |
