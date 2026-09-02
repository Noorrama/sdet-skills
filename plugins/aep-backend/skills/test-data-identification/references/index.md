# QA Knowledge Catalog

Central knowledge index for the Gojek QA platform. Each domain is organized as an OKF bundle — a
directory of markdown concept documents navigable by humans and AI agents alike.

All domains named in `../test_data_domains.md` now have a bundle here — Consumer, Driver, Workflow,
and Booking are fully grounded and populated; Merchant, Voucher, Payment Instrument, and Location
are grounded against the code as it exists today, including where that code turns out to model
**less** than the domain file's illustrative signals (or nothing at all) — see each bundle's own gap
notes.

## Domains

| Domain | Description |
|---|---|
| [Workflow](workflow/index.md) | A functional sequence of TestData Units that identifies the domain, and the chain of domains, required to fulfil a scenario. **Identifying keys:** `module` (`transport`, `gofood`), domain chain (Transport: Customer → Driver; Food: Customer → Merchant → Driver), `bookingStatus` (`BookingConfig` for Transport, external `BookingState` for Food), order-number prefix (`RB-` Transport, `F-` Food). |
| [Booking](booking/index.md) | The entity a workflow chain produces or acts on — `BookingModel`/`GetBookingRequest` shape, `BookingModule` discriminator, `OrderType` prefix table, and pooling/chaining variants (`chainedBooking`, `sdfBooking`, `staticPoolingBooking`). **Identifying keys:** `bookingId`, `module`, `orderNumber` prefix (`RB-`/`F-`/`MT-`/`GK-11-`/`GK-91-`), `poolingGroupId`, `poolingSequence`, active-booking lookup (`getActiveBookings`). |
| [Consumer](customer/index.md) | Consumer (customer) domain — identity, wallet, addresses, booking history, and test data lifecycle. **Identifying keys:** `customerId`, `phone` (`+62`/`+65`), `testDataCategoryName` (`VANILLA`, `CUSTOMER_WITH_CC`, `CUSTOMER_WITH_GO_PAY`, `CUSTOMER_WITH_GOCORP`, `CUSTOMER_WITH_SAVED_ADDRESS_POI`, `CUSTOMER_WITH_SAVED_ADDRESS_AOI`), `paymentMode` (`CASH`, `card`, `GOPAY_WALLET`, `GOCORP`, `GOPAY_COINS`), `countryCode` (`ID`/`SG`), `wallet_balance_idr` / GoPay balance amount, GoPay coins balance, `customerType` (loyalty tier, e.g. `CUSTOMER_WITH_30k_STATUS_STAR`), `tierXp`, `accountStatus`/`Active`/`Blocked`, `segmentName`, `isBlackListed`, `isPinSet`, `isSubscription`, saved-address POI/AOI, booking-history flags (`hasTransportCompletedBooking`, `hasFoodCanceledBooking`, …), `accessToken` freshness. |
| [Driver](driver/index.md) | Driver partner domain — vehicle/service type, wallet, tags, sanctions, and booking allocation readiness. **Identifying keys:** `driverId`, `phone` (`+62`/`+65`), `testDataCategoryName` (`DRIVER__<COUNTRY>__<TYPE>`, e.g. `DRIVER__ID__BIKE`, `DRIVER__ID__CAR_ECONOMY_SHIELD`, `DRIVER__SG__TAXI_PREMIUM`), `driverType` enum, `countryCode` (`ID`/`SG`), vehicle-type tokens (`BIKE`, `CAR`, `RUNNER`, `CYCLE`, `KILAT`, `TAXI`, `BLUEBIRD`), service-tier tokens (`ECONOMY`, `COMFORT`, `PREMIUM`, `AIRPORT`, `EXTERNAL`), feature tokens (`VACCINATED`, `SHIELD`, `PURIFIER`, `RAVEN`, `HYBRID`, `SUPERSUB`, `EV`), `serviceArea`, wallet balance amount, `tags` set, sanction/suspension state (`SUSPENDED`, `BLOCKED_ACTION`), active-booking presence, `accessToken` freshness. |
| [Merchant](merchant/index.md) | **No pooled entity exists.** `merchantId`/`merchantType` are pass-through booking fields; real merchant identity comes back from the live GoFood order response. Route merchant-only fixtures to `TESTBUDDY_OPERATION_FALLBACK`/`TDP_NOT_SUPPORTED`, never an invented category. |
| [Voucher](voucher/index.md) | Voucher-**batch** entity — `voucherBatchId`, `countryCode`, `serviceTypeIds`, `voucherBatchType`. No per-voucher redemption/eligibility/expiry state exists; a promo-code-shaped fixture is `TDP_PARTIAL` when the batch itself resolves and only the per-voucher state is unserved, `TDP_NOT_SUPPORTED` when not even the batch matches. **Identifying keys:** `testDataEntity: VOUCHER`, `voucherBatchType`, `serviceTypeId`, `countryCode`. |
| [Payment Instrument](payment_instrument/index.md) | **No pooled entity exists.** No card/bank-account model anywhere; `paymentMode: "card"` lives entirely on the Consumer category (`CUSTOMER_WITH_CC`). A fixture varying the instrument itself (not who holds it) is `TDP_PARTIAL` when the holder still comes from a Consumer category and only the instrument state is unserved, `TDP_NOT_SUPPORTED` when nothing is, absent a confirmed TestBuddy/Pertamax/GBT tool. |
| [Location](location/index.md) | Service-**area** entity only — `serviceAreaId`, `status` (`AVAILABLE`/`LOCKED`/`INVALID`), lock lifecycle. Polygon is a driver-fleet tag (`../driver/index.md`), not a location entity; route/stop/coordinate fixtures have no code path. **Identifying keys:** `serviceAreaId`, `countryCode`, `ServiceAreaStatus`, `isRestrictedSA`. |

## How to read a natural-language statement

1. **Identify the noun** — is the state being described about a *Consumer* (consumer-side account)
   or a *Driver* (partner-side account)? A statement never carries both; a request for "a customer
   and a driver" is two separate identifications.
2. **Identify the payment/wallet mention** — "gopay", "wallet", "balance", "recharge", "top up" are
   the biggest source of ambiguity in this codebase. See [Consumer](customer/index.md#the-account-vs-wallet-amount-split)
   for why "a user with gopay" means *"give me a `CUSTOMER_WITH_GO_PAY`-category customer"*, not
   *"create a wallet"* — the wallet already exists on that category; only the **amount** in it is
   ever a separate signal.
3. **Identify vehicle/service-type mentions** for drivers ("Bike", "4w", "Car", "Economy",
   "SDF3") — these select a `DRIVER__<COUNTRY>__<TYPE>` category, never an operation.
4. **Identify a downstream use** — "…then book a ride", "…so it can be used for a food order" is a
   signal that the statement continues into a booking. Go to [Workflow](workflow/index.md) to
   resolve which entities the named vertical needs and in what order (Transport: Customer → Driver;
   Food: Customer → Merchant → Driver) before falling back to the generic `BOOKING` domain notes in
   `../test_data_domains.md`.
5. **For the order in which operations must happen** — creation, linking, top-up, allocation,
   booking — don't infer it here; refer to the [sequence](sequence/sequence.md) folder, which
   catalogs every Consumer and Driver function as call sequences and lays out the composite
   booking-creation flow across both domains.

## Bundle contents

| File | Covers |
|---|---|
| [workflow/index.md](workflow/index.md) | Workflow bundle root: workflow definition, which vertical (`module`) needs which entities, in what order, before `createBooking` runs |
| [workflow/transport/index.md](workflow/transport/index.md) | Transport booking workflow: Customer → Driver, `BookingConfig` status enum, `serviceTypeId` → driver-type mapping, driver auto-assignment guard |
| [workflow/food/index.md](workflow/food/index.md) | Food order workflow: Customer → Merchant → Driver, merchant-accepts-then-driver-assigned guard, merchant knowledge gap |
| [booking/index.md](booking/index.md) | Booking entity identification: `BookingModel`/`GetBookingRequest` shape, `BookingModule`/`OrderType` vocabularies, pooling/chaining variants, active-booking lookup |
| [customer/index.md](customer/index.md) | Consumer identification: TDP customer categories, the account vs. wallet-amount split, `POST /get` pooling contract |
| [driver/index.md](driver/index.md) | Driver identification: TDP driver categories (`DRIVER__<COUNTRY>__<TYPE>`), vehicle/service-type signal vocabulary |
| [merchant/index.md](merchant/index.md) | Merchant identification: confirms no pooled merchant entity exists, and where merchant-shaped fixtures should route instead |
| [voucher/index.md](voucher/index.md) | Voucher identification: the real `VoucherModel` batch shape vs. the domain file's promo-code-shaped signals |
| [payment_instrument/index.md](payment_instrument/index.md) | Payment instrument identification: confirms no card/instrument entity exists, and why `paymentMode: "card"` belongs to Consumer instead |
| [location/index.md](location/index.md) | Location identification: the real `ServiceAreaModel` shape, why Polygon is a driver tag not a location entity, and what geo signals have no code path |
| [sequence/sequence.md](sequence/sequence.md) | Ordered operation chains for every Consumer and Driver function, plus the composite booking-creation flow requiring both wallets to be topped up first |
