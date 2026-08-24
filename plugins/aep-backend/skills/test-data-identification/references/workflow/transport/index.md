# Transport workflow — Customer → Driver (TDP-grounded)

Every transport booking needs a **customer to place it** and a **driver to fulfil it** — a ride
cannot exist as data without both. This bundle documents the exact code path that enforces that
order, so identification never emits a booking-first / driver-first signal chain.

## Required entities, in order

| Step | Entity | Why it must come first |
|---|---|---|
| 1 | Customer (`../../customer/index.md`) | `BookingService.createBooking` auto-fetches a customer from the pool when `customerId` is absent (`fetchAndEngageCustomer`) — the booking cannot be constructed without one. |
| 2 | Driver (`../../driver/index.md`) | Auto-assigned **only if the booking has moved past its initial status** — see the guard below. A driver is the entity that closes ("fulfils") the booking, not a co-equal input alongside the customer. |

## Entry point

`POST /aep/test-data-generator/booking/createBooking` (`BookingController.java`), body
`GetBookingRequest` (`GetBookingRequest.java`), dispatched by `module` (`BookingModule.java`):

```
module: "transport"
customerId, driverId, driverType, serviceTypeId, serviceAreaId,
paymentMode, bookingType, bookingStatus, targetState
```

`merchantId`/`merchantType` exist on the same request object but are **Food-only fields** — a
Transport fixture must never populate them (see `food/index.md`'s merchant note for why they exist
on a shared request shape at all).

## The driver auto-assignment guard

This is the concrete rule behind "then a driver is required to complete or assign the order"
(`BookingService.java`, lines ~224–230):

```java
if (bookingRequest.getDriverId() == null && !isInitialStatus) {
    // ... assignDriverFromTdp(...)
}
```

`isInitialStatus` is `SCHEDULED`/`BOOKED` (`BookingConfig`) — i.e. a booking can legitimately exist
in TDP with **no driver yet** while it is still in its initial status. Only once the target status
moves past that point does the driver-fetch-from-pool path fire. Consequences for signal ordering:

- A fixture asking for "a scheduled booking" needs **customer only** — do not emit a driver-fetch
  operation the pool will never call.
- A fixture asking for "a confirmed / driver_arrived / started / completed booking" needs
  **customer, then driver** — the driver signal always follows the customer signal, never precedes
  or replaces it, per the emission order rule in `../../sequence/sequence.md`.

## Booking status vocabulary (`BookingConfig.java`)

| `bookingStatus` value | Meaning | Driver required? |
|---|---|---|
| `scheduled` | Booking placed, not yet matched | No |
| `booked` | Initial booked state | No |
| `driver_not_found` | Matching attempted, failed | No (explicitly no driver) |
| `confirmed` | Driver matched | Yes |
| `driver_arrived` | Driver at pickup | Yes |
| `started` | Trip in progress (`driver_pickup`) | Yes |
| `meter_amount_accepted` | Fare/meter confirmed | Yes |
| `cancelled` | Cancelled after driver involvement | Yes (was assigned) |
| `driver_cancelled` | Cancelled by the driver | Yes |
| `OTW_PICKUP` | En route to pickup | Yes |
| `completed` | Trip finished | Yes |

Don't emit `driver_not_found` for a fixture that describes a *successful* booking — it is a
distinct negative-path status, not a synonym for "before driver assignment".

## `serviceTypeId` → driver-type signal mapping

`BookingService.java` switches on `serviceTypeId` to resolve the driver type needed for matching:

| `serviceTypeId` | Driver type |
|---|---|
| `50` | `SG_CAR` |
| `66` | `SG_TAXI` |
| `69` | `BIKE_EV` |
| `43` | `CAR_XTRA` |
| `67` | `BIKE_REGULAR` |
| `77`, `203` | `CAR_REGULAR` |

Use this table, not the vehicle/service-type token vocabulary in `../../driver/index.md` alone, to
resolve a *booking-request* `serviceTypeId` — the driver bundle's `DRIVER__<COUNTRY>__<TYPE>`
categories describe the pooled driver, this table describes what the booking call itself expects.

## Order-number vocabulary

`OrderType.java`: Transport orders carry the `RB-` prefix. A fixture referencing an order number
literal beginning `RB-` is Transport; `F-` is Food (`food/index.md`), `MT-` Gomart, `GK-11-`
Gokilat, `GK-91-` Gosend — the latter three have no dedicated workflow bundle yet
(`../index.md`).

## Where the rest lives

Wallet top-up for the customer (and, if the booking's payment mode checks it, the driver) is a
prerequisite closed by the Consumer/Driver bundles' own recharge operations
(`../../sequence/sequence.md`'s composite booking-creation sequence), not by this bundle — this
page only documents entity *existence and ordering*, not balance state.
