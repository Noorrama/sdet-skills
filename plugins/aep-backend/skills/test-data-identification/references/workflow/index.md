# Workflow bundle — the domain chain behind a scenario

## Workflow definition

A **workflow** is a functional sequence of TestData Units (Consumer,
Driver, Merchant, Booking, …) that correlates to a domain/vertical (Transport, Food, …). A workflow
is not itself a pooled entity, and it is not defined by `createBooking` — a workflow's job is to
**identify the domain, and the chain of domains required to fulfil that workflow**, for whatever
natural-language scenario is being described. Booking happens to be the mechanism Transport and
Food currently use to realize that chain in this codebase (`BookingController.java`,
`/aep/test-data-generator/booking/createBooking`), but the workflow concept itself is the ordered
domain sequence, not the booking call. The Consumer (`../customer/index.md`) and Driver
(`../driver/index.md`) bundles each answer *what is this entity, and which category is it*. This
bundle answers the question one level up: **given a scenario, which domains does it touch, and in
what order must each domain's test data exist relative to the others.**

**The customer step is usually already satisfied.** When TDP or TestBuddy performs the booking
creation itself (`createBooking` and the Transport/Food chains below), the customer most of the
time is already created — fetched from the pool (`fetchAndEngageCustomer`-style auto-fetch), not
freshly provisioned. Only create a customer when the fixture's signals show none is available to
fetch; don't add a customer-creation step by default just because a booking scenario names one.

### Examples

- **FoodWorkflow**
  - **Description** — Create a food order / booking.
  - **Keywords** — `ORDER`, `FOOD`, `GOFOOD`, `MERCHANT`, `GROUP_ORDER`, `BOOKING`, `DELIVERY`,
    `MERCHANT_ACCEPTED`, `OTW_PICKUP`, order-number prefix `F-`. Sourced from the fixture-description
    vocabulary in TDP (`GoFoodBookingService.java`'s `BookingState` values and `module: "gofood"`),
    TestBuddy's `BookingAgent`/group-order tool surface (`handle_group_order_create`,
    `handle_group_order_create_cart`, `handle_group_order_join`, `handle_group_order_leave`,
    `handle_group_order_mark_ready`, `handle_group_order_set_payment_method`,
    `handle_group_order_make_booking`, `handle_group_order_e2e_flow`, `handle_gofood_delivery_e2e_flow`),
    and GBT's `gofood/src/test/java/tests/GroupOrder/**` regression suite (`CreateGroupOrderTests`,
    `JoinGroupOrderTests`, `LeaveGroupOrderTests`, `GetGroupOrderDetailTests`) — a statement naming any
    of these tokens is a Food-workflow signal, not a generic `BOOKING` domain fixture.
  - **Domains involved** — Customer, Merchant, Driver, Booking.
  - **Sequence** — Create Customer → Get Merchant → Create Booking → Driver Assign → booking-status
    updates from the driver side.
    - **Note** — When only the booking itself is required, no driver assignment is needed. When a
      specific *post*-driver-assignment booking status is asked for, assign the driver first and
      then move the booking to the requested status (see the driver auto-assignment guard in
      [food/index.md](food/index.md#the-driver-auto-assignment-guard)).

- **TransportWorkflow**
  - **Description** — Create a transport (ride) booking.
  - **Keywords** — `RIDE`, `TRANSPORT`, `BOOKING`, `DRIVER_ASSIGN`, `SCHEDULE`, `INSTANT`,
    order-number prefix `RB-`. Sourced from TDP's `BookingConfig` status vocabulary
    (`scheduled`, `booked`, `confirmed`, `driver_arrived`, `started`, `completed`, `cancelled`,
    `driver_cancelled`) and `serviceTypeId` mapping in `BookingService.java`, TestBuddy's transport
    tool surface (`handle_create_transport_booking`, `transport_schedule_booking`,
    `transport_driver_found`, `transport_driver_arrived`, `transport_driver_pickup`,
    `transport_driver_complete`, `transport_driver_cancel`, `transport_customer_cancel`,
    `transport_quick_complete`, `transport_move_driver`, `handle_quick_instant_bike`,
    `handle_quick_instant_car`, `handle_quick_instant_hemat`, `handle_quick_sameday`,
    `handle_quick_complete_booking`), and GBT's transport regression suites — a statement naming any
    of these tokens is a Transport-workflow signal.
  - **Domains involved** — Customer, Driver, Booking.
  - **Sequence** — Create Customer → Create Booking → Driver Assign → booking-status updates from
    the driver side.
    - **Note** — Same rule as Food: a booking in its initial status (`scheduled`/`booked`) needs no
      driver. A driver is only fetched/assigned once the requested `bookingStatus` moves past that
      initial status (see [transport/index.md](transport/index.md#the-driver-auto-assignment-guard)).

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
