# Booking domain — the entity every workflow produces

The [Workflow](../workflow/index.md) bundle documents which domain chain (Customer → Merchant →
Driver, etc.) a scenario needs. **Booking is the entity that chain ultimately produces or acts on**
— this bundle documents the Booking entity itself: its shape in TDP, the module/status vocabulary
that discriminates it, and the pooling/chaining variants confirmed against GBT's regression suite.

## Identifying keys

`bookingId`, `module` (`transport`, `gofood`, `gosend`, `gomart`, `multimodal`), `customerId`,
`driverId`, `serviceTypeId`, `serviceAreaId`, `paymentMode`, `bookingType`, `bookingStatus`,
`orderNumber` (prefix discriminates the module — `RB-` Transport, `F-` Food, `MT-` Gomart,
`GK-11-` Gokilat, `GK-91-`/`GK-` Gosend), `merchantId` (Food-only), `poolingGroupId` +
`poolingSequence` (chained/pooled bookings), `chainedBooking` / `sdfBooking` /
`sdfChainingBooking` / `staticPoolingBooking` flags.

## TDP shape

### `BookingModel` (`BookingModel.java`, MongoDB collection `bookings`)

The persisted entity behind every pooled booking:

| Field | Notes |
|---|---|
| `bookingId` | Indexed. |
| `customerId`, `customerPhone` | Owning customer — see `../customer/index.md`. |
| `driverId`, `driverType`, `driverPhone` | Fulfilling driver — see `../driver/index.md`; absent while the booking is in its initial status (per-workflow guard). |
| `module` | `BookingModule` value — the vertical discriminator. |
| `bookingStatus`, `status` | `bookingStatus` is the module-specific status string (`BookingConfig` for Transport, external `BookingState` for Food); `status` is the generic TDP record status. |
| `serviceTypeId`, `serviceAreaId`, `paymentMode`, `bookingType` | Booking-request pass-through fields. |
| `merchantId` | Food-only; see `../workflow/food/index.md#merchant--not-a-tdp-managed-entity` — never persisted as `merchantType`. |
| `origin`, `destination`, `journeyId`, `journeyType` | Trip-shape fields (Transport-oriented). |
| `tollFee`, `tip`, `parkingFee` | Optional fare add-ons. |
| `chainedBooking`, `sdfChainingBooking`, `sdfBooking`, `staticPoolingBooking` | Pooling/chaining variant flags — see below. |
| `poolingGroupId`, `poolingSequence` | Compound-unique index (`uniq_pool_seq`); groups multiple `BookingModel` rows into one chained/pooled sequence. |
| `appliedVoucher` | Present when a voucher batch (`../voucher/index.md`) was applied to the booking. |
| `bookingHistoryCountedAs`, `driverHistoryCounted` | Booking-history counters consumed by the Consumer/Driver bundles' history flags (`hasTransportCompletedBooking`, etc. — `../customer/index.md`). |

### `GetBookingRequest` (`GetBookingRequest.java`) — the pooling request shape

Same request POJO backs every module via `POST /aep/test-data-generator/booking/createBooking`
(`BookingController.java`) dispatched by `BookingService.java`:

```
module, countryCode, customerCountryCode, paymentMode, serviceAreaId, serviceTypeId,
customerId, driverId, driverType, voucher, isWithVoucher, voucherBatchId,
origin, destination, bookingType, bookingStatus, targetState, orderNumber, poolOrderNumber,
merchantId, merchantType, journeyType, journeyId, desiredLegSequenceCompleted,
isChainedBooking, isSdfBooking, isSdfChainingBooking, isStaticPoolingBooking,
applyParkingFee, applyTollFee, applyTip, parkingFeeAmount, tollFee, tip
```

A request never populates every field for every module — `merchantId`/`merchantType` are Food-only
(`../workflow/transport/index.md`'s note); the `is*Booking` flags are pooling-variant switches, not
per-module fields.

### `BookingModule` (`BookingModule.java`) — the vertical discriminator

| `module` value | Vertical | Workflow bundle |
|---|---|---|
| `transport` | Transport (ride) | [../workflow/transport/index.md](../workflow/transport/index.md) |
| `gofood` | Food (GoFood order) | [../workflow/food/index.md](../workflow/food/index.md) |
| `gosend` | Gosend | none yet — treat as `match_confidence: medium` against `BookingService.java` |
| `gomart` | Gomart | none yet — treat as `match_confidence: medium` against `BookingService.java` |
| `multimodal` | MultiModal | none yet — treat as `match_confidence: medium` against `BookingService.java` |

### `OrderType` (`OrderType.java`) — order-number prefix vocabulary

| Prefix | Module |
|---|---|
| `RB-` | Transport |
| `F-` | Food |
| `MT-` | Gomart |
| `GK-11-` | Gokilat |
| `GK-91-` | Gosend |
| `GK-` | Gosend (common) |

Confirmed against GBT: `driver-platform` generates Transport order numbers with the exact `"RB-" +
<random>` pattern (`RandomOrderNumberGenerator.java`, `BffTestHelper.java`, and every
`tests/passbook/componentTests/*` fixture), and `BffServiceDataProvider.java` seeds Gosend fixtures
literally prefixed `GK-91-` — the same prefix table `BookingService.java` encodes on the TDP side.

### Booking status vocabularies

Booking status is **module-scoped, not shared** — do not carry one module's enum onto another:

- Transport uses `BookingConfig` (`BookingConfig.java`) — full table in
  [../workflow/transport/index.md](../workflow/transport/index.md#booking-status-vocabulary-bookingconfigjava).
- Food uses the external `BookingState` enum (values include `MERCHANT_ACCEPTED`, `OTW_PICKUP`) —
  see [../workflow/food/index.md](../workflow/food/index.md#booking-status-vocabulary--a-different-enum-from-transport).

### Pooling and chaining variants

`BookingModel`'s `chainedBooking`, `sdfBooking`, `sdfChainingBooking`, and `staticPoolingBooking`
flags (mirrored on `GetBookingRequest` as `isChainedBooking`, `isSdfBooking`,
`isSdfChainingBooking`, `isStaticPoolingBooking`) mark a booking as belonging to a multi-leg or
pooled sequence rather than a single standalone booking — `poolingGroupId` ties the rows together
and `poolingSequence` orders them within the group. `GoFoodBookingService` exposes matching
operation variants (`createSDFBookingFood`, `createChainingBookingFood`,
`createStaticPoolingBooking`) — treat a fixture naming "chained", "SDF", or "static pooling"
booking as selecting one of these variants, not a plain `createBooking` call. Grounded against
GBT's `transport/src/test/java/tests/regression/bookingExperience/rideService/chainingbooking/ChainingBookingTest.java`
and `builders/state_builders/BookingStateBuilder.java`, which exercise the same chained-booking
shape end-to-end.

### Active bookings

`BookingController.getAllActiveBookingsOfDriver` (`GET /aep/test-data-generator/booking/getActiveBookings?driverId=`)
returns the set of active `bookingId`s for a driver — this is the TDP-side counterpart to GBT's
`driver-platform` active-booking suite (`entities/activeBooking`, `tests/activebooking`,
`responses/ActiveBooking`). A fixture describing "a driver with an active booking" resolves through
this endpoint, not a fresh `createBooking` call, once the driver already has one.

## How to read a booking statement

1. **Booking is downstream of the workflow chain**, never the starting point — resolve the
   `module`'s required domains first (`../workflow/index.md`), then treat the booking fields above
   as what gets set once those domains are identified.
2. **The order-number prefix is the fastest module signal** in a statement that quotes a literal
   order number (`RB-…`, `F-…`, `GK-91-…`) — map it via the `OrderType` table above before falling
   back to keyword matching.
3. **"Chained" / "SDF" / "pooled" / "static pooling" booking wording** selects a pooling-variant
   operation (above), not a plain booking category — do not drop these tokens when they appear
   alongside a module name.
4. **"Active booking" wording** for a driver routes to `getActiveBookings`, not a new booking
   creation — see Active bookings above.
