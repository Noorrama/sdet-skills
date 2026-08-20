# QA Knowledge Catalog

Central knowledge index for the Gojek QA platform. Each domain is organized as an OKF bundle — a
directory of markdown concept documents navigable by humans and AI agents alike.

More domains (MERCHANT, VOUCHER, PAYMENT_INSTRUMENT, BOOKING, LOCATION — see
`../test_data_domains.md`) will be added here as their own bundles over time. Only Consumer and
Driver are populated today.

## Domains

| Domain | Description |
|---|---|
| [Consumer](customer/index.md) | Consumer (customer) domain — identity, wallet, addresses, booking history, and test data lifecycle. **Identifying keys:** `customerId`, `phone` (`+62`/`+65`), `testDataCategoryName` (`VANILLA`, `CUSTOMER_WITH_CC`, `CUSTOMER_WITH_GO_PAY`, `CUSTOMER_WITH_GOCORP`, `CUSTOMER_WITH_SAVED_ADDRESS_POI`, `CUSTOMER_WITH_SAVED_ADDRESS_AOI`), `paymentMode` (`CASH`, `card`, `GOPAY_WALLET`, `GOCORP`, `GOPAY_COINS`), `countryCode` (`ID`/`SG`), `wallet_balance_idr` / GoPay balance amount, GoPay coins balance, `customerType` (loyalty tier, e.g. `CUSTOMER_WITH_30k_STATUS_STAR`), `tierXp`, `accountStatus`/`Active`/`Blocked`, `segmentName`, `isBlackListed`, `isPinSet`, `isSubscription`, saved-address POI/AOI, booking-history flags (`hasTransportCompletedBooking`, `hasFoodCanceledBooking`, …), `accessToken` freshness. |
| [Driver](driver/index.md) | Driver partner domain — vehicle/service type, wallet, tags, sanctions, and booking allocation readiness. **Identifying keys:** `driverId`, `phone` (`+62`/`+65`), `testDataCategoryName` (`DRIVER__<COUNTRY>__<TYPE>`, e.g. `DRIVER__ID__BIKE`, `DRIVER__ID__CAR_ECONOMY_SHIELD`, `DRIVER__SG__TAXI_PREMIUM`), `driverType` enum, `countryCode` (`ID`/`SG`), vehicle-type tokens (`BIKE`, `CAR`, `RUNNER`, `CYCLE`, `KILAT`, `TAXI`, `BLUEBIRD`), service-tier tokens (`ECONOMY`, `COMFORT`, `PREMIUM`, `AIRPORT`, `EXTERNAL`), feature tokens (`VACCINATED`, `SHIELD`, `PURIFIER`, `RAVEN`, `HYBRID`, `SUPERSUB`, `EV`), `serviceArea`, wallet balance amount, `tags` set, sanction/suspension state (`SUSPENDED`, `BLOCKED_ACTION`), active-booking presence, `accessToken` freshness. |

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
   signal that the statement continues into `BOOKING`, which is a separate domain per
   `../test_data_domains.md`.
5. **For the order in which operations must happen** — creation, linking, top-up, allocation,
   booking — don't infer it here; refer to the [sequence](sequence/sequence.md) folder, which
   catalogs every Consumer and Driver function as call sequences and lays out the composite
   booking-creation flow across both domains.

## Bundle contents

| File | Covers |
|---|---|
| [customer/index.md](customer/index.md) | Consumer identification: TDP customer categories, the account vs. wallet-amount split, `POST /get` pooling contract |
| [driver/index.md](driver/index.md) | Driver identification: TDP driver categories (`DRIVER__<COUNTRY>__<TYPE>`), vehicle/service-type signal vocabulary |
| [sequence/sequence.md](sequence/sequence.md) | Ordered operation chains for every Consumer and Driver function, plus the composite booking-creation flow requiring both wallets to be topped up first |
