# Event sequences — Consumer, Driver, and Booking creation

Every function TDP exposes for the Consumer and Driver domains, grouped by what it operates on and
shown as a simple call sequence, plus the composite sequence that ties both together into a
booking. Use this to match a signal found in a request statement to the group (and exact
operation) that produces or reads that state. Sources: `CustomerController.java`,
`DriverController.java`, `TestDataPoolingController.java`, `BookingController.java`.

---

## Consumer sequences

### 1. Identity & lookup

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Customer Pool (Mongo)
    participant External as External Customer API

    Caller->>TDP: GET /customer/id?customerId=
    TDP->>Pool: find by customerId
    alt found in pool
        Pool-->>TDP: customer record
    else not in pool
        TDP->>External: fetch by customerId
        External-->>TDP: customer record
    end
    TDP-->>Caller: customer record

    Caller->>TDP: GET /customer/phone?phoneNumber=
    TDP->>Pool: find by normalized phone (+62/+65)
    Pool-->>TDP: customer record
    TDP-->>Caller: customer record

    Caller->>TDP: POST /customer/refresh-token?customerId=
    TDP->>External: request new access token
    External-->>TDP: accessToken, expiresOn
    TDP->>Pool: persist refreshed token
    TDP-->>Caller: customerId, phone, accessToken, expiresOn, customerType

    Caller->>TDP: POST /customer/refresh-token/bulk?customerType=&statuses=
    TDP->>Pool: find all matching customerType + statuses
    TDP->>External: refresh each token (async)
    TDP-->>Caller: job-started acknowledgement
```

Signals: `customerId`, `phone`, `accessToken` freshness/expiry, `customerType`, pool status
(`AVAILABLE`, `ENGAGED`, `INVALID`, …).

### 2. Wallet — GoPay balance, coins, wallet ID

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant GoPay as GoPay platform

    Caller->>TDP: GET /customer/gopay-balance?customerId=&countryCode=
    TDP->>GoPay: fetch wallet balance
    GoPay-->>TDP: balance, currency
    TDP-->>Caller: balance, currency, countryCode

    Caller->>TDP: POST /customer/gopay/recharge?customerId=&amount=&countryCode=
    TDP->>GoPay: fetch balance before
    TDP->>GoPay: top up by amount
    GoPay-->>TDP: balance after (or "maximum limit" no-op)
    TDP-->>Caller: balance before, balance after

    Caller->>TDP: GET /customer/gopay-coins-balance?customerId=&countryCode=
    TDP->>GoPay: fetch coins balance
    GoPay-->>TDP: coins balance
    TDP-->>Caller: coins balance

    Caller->>TDP: POST /customer/gopay-coins/recharge?customerId=&amount=&countryCode=
    TDP->>GoPay: top up coins by amount
    GoPay-->>TDP: coins balance after
    TDP-->>Caller: coins balance before/after

    Caller->>TDP: POST /customer/wallet/update/{customerId}
    TDP->>GoPay: re-fetch and persist wallet ID
    TDP-->>Caller: SUCCESS/FAILED

    Caller->>TDP: POST /customer/wallet/update-all?customerType=
    TDP->>Pool: iterate matching customers
    TDP->>GoPay: re-fetch wallet ID per customer
    TDP-->>Caller: process-completed acknowledgement
```

Signals: `wallet_balance_idr`/GoPay balance amount, GoPay coins balance, `countryCode`
(`ID`→IDR, `SG`→SGD), wallet ID staleness.

### 3. Loyalty

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Loyalty as Loyalty API

    Caller->>TDP: GET /customer/loyalty/membership?customerId=
    TDP->>Loyalty: get membership by customerId + countryCode + accessToken
    Loyalty-->>TDP: tierXp, redeemableXp
    TDP-->>Caller: customerType, tierXp, redeemableXp, countryCode

    Caller->>TDP: POST /customer/loyalty/restore-xp?customerId=
    TDP->>Loyalty: read current tierXp
    TDP->>Loyalty: restore XP to level implied by customerType
    Loyalty-->>TDP: tierXp after
    TDP-->>Caller: xpBefore, xpAfter, xpRestored
```

Signals: `tierXp`, `redeemableXp`, `customerType` loyalty tier (e.g. `CUSTOMER_WITH_30k_STATUS_STAR`).
`restore-xp` only accepts a `customerType` containing `STATUS_STAR`.

### 4. Segmentation

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Seg as Segmentation service

    Caller->>TDP: GET /customer/segments?customerId=
    TDP->>Seg: list segments for customerId
    Seg-->>TDP: segments[]
    TDP-->>Caller: segments[], totalSegments

    Caller->>TDP: POST /customer/update-segment {segment_name, unit_type, customer_ids[]}
    TDP->>Seg: add each customer_id to segment (async)
    TDP-->>Caller: processing-started acknowledgement

    Caller->>TDP: POST /customer/update-segment-by-category {segment_name, unit_type, customer_type}
    TDP->>Pool: find AVAILABLE + ENGAGED customers of customer_type
    TDP->>Seg: add all matched customers to segment (async)
    TDP-->>Caller: processing-started acknowledgement

    Caller->>TDP: POST /customer/update-segment-batch {segment_name, unit_type, batch_size}
    TDP->>Pool: find AVAILABLE/ENGAGED customers not yet segmented
    TDP->>Seg: batch-add to segment (async)
    TDP-->>Caller: processing-started acknowledgement

    Caller->>TDP: DELETE /customer/remove-from-segment {segment_name, unit_type, customer_ids[]}
    TDP->>Seg: remove each customer_id from segment (async)
    TDP-->>Caller: processing-started acknowledgement
```

Signals: `segmentName`, `unitType`, membership in a named segment, `gamificationSegmented` flag.

### 5. Blacklist

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Customer Pool

    Caller->>TDP: POST /customer/blacklisted/add?customerId=
    TDP->>Pool: mark customer as blacklisted
    TDP-->>Caller: updated customer record

    Caller->>TDP: POST /customer/blacklisted/remove?customerId=
    TDP->>Pool: clear blacklist state
    TDP-->>Caller: updated customer record

    Caller->>TDP: POST /customer/blacklisted/create/bulk {testDataEntity: CUSTOMER, testDataCategory}
    TDP->>Pool: create/select `count` customers of category
    TDP->>Pool: mark each as blacklisted
    TDP-->>Caller: blacklisted record IDs
```

Signals: `isBlackListed`.

### 6. Saved addresses

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Customer Pool
    participant AddressAPI as Saved-address platform

    Caller->>TDP: GET /customer/addresses?customerId=
    TDP->>Pool: find customer
    TDP-->>Caller: saved addresses[]

    Caller->>TDP: PUT /customer/addresses {customerId, savedAddressId, label, placeId, ...}
    TDP->>AddressAPI: update saved address
    AddressAPI-->>TDP: updated address
    TDP-->>Caller: updated saved address

    Caller->>TDP: DELETE /customer/addresses {customerId, savedAddressId}
    TDP->>AddressAPI: delete saved address
    AddressAPI-->>TDP: deletion confirmed
    TDP-->>Caller: deletion confirmed
```

Signals: saved-address presence, `label`, `placeId` — POI vs. AOI is a category distinction
(`CUSTOMER_WITH_SAVED_ADDRESS_POI` / `_AOI`), while add/edit/delete of an individual address is a
state mutation on top of that category.

### 7. PIN

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Customer Pool
    participant GoPay as GoPay platform

    Caller->>TDP: POST /customer/pin/set?customerId=
    TDP->>Pool: find customer, read phone
    TDP->>GoPay: look up GoPay user by phone
    alt is_pin_setup already true
        TDP->>Pool: persist pin value directly
    else not set
        TDP->>GoPay: POST /pins (set PIN)
        TDP->>GoPay: verify is_pin_setup via GET-by-phone
        TDP->>Pool: persist pin value on success
    end
    TDP-->>Caller: pin-set confirmation

    Caller->>TDP: DELETE /customer/pin?customerId=
    TDP->>Pool: delete the customer record
    TDP-->>Caller: deletion confirmation

    Caller->>TDP: DELETE /customer/pin/engaged/cleanup
    TDP->>Pool: find ENGAGED pin customers older than 10 hours
    TDP->>Pool: delete each
    TDP-->>Caller: deleted customerIds[]

    Caller->>TDP: POST /customer/pin/create/bulk {testDataEntity: CUSTOMER, testDataCategory}
    TDP->>Pool: create/select `count` customers of category
    TDP->>TDP: run pin/set for each
    TDP-->>Caller: pinned customer IDs
```

Signals: `isPinSet` / PIN presence — the `pin` field itself is the sole source of truth, there is
no separate boolean flag stored alongside it.

### 8. Pool fetch and its variants

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Customer Pool
    participant GoPay as GoPay platform (create path)

    Caller->>TDP: POST /aep/test-data-generator/get {testDataEntity: CUSTOMER, testDataCategory}
    TDP->>Pool: find AVAILABLE customer(s) of category
    alt pool has one
        Pool-->>TDP: existing customer(s)
    else pool empty
        TDP->>GoPay: create customer, link category's payment method
        GoPay-->>TDP: new customer
        TDP->>Pool: persist
    end
    TDP-->>Caller: customer(s)

    Caller->>TDP: POST /get-add-segment {..., segmentName, unitType}
    TDP->>TDP: run the /get pipeline above
    TDP->>Seg: add returned customer(s) to segmentName (async)
    TDP-->>Caller: customer(s)

    Caller->>TDP: POST /get-subscription {...}
    TDP->>TDP: run the /get pipeline above
    TDP->>Pool: set isSubscription=true on returned customer(s) (async)
    TDP-->>Caller: customer(s)

    Caller->>TDP: POST /get-subscription-and-segment {..., segmentName, unitType}
    TDP->>TDP: run the /get pipeline above
    TDP->>Pool: set isSubscription=true (async)
    TDP->>Seg: add to segmentName (async)
    TDP-->>Caller: customer(s)

    Caller->>TDP: POST /get-subscription-customers {...}
    TDP->>Pool: find customers already isSubscription=true, matching category filters
    TDP-->>Caller: customer(s)
```

Signals: `testDataCategoryName`, `count`, `countryCode`, booking-history filters
(`hasTransportCompletedBooking`, `hasFoodCanceledBooking`, …), `used`, `isBlackListed`,
`isPinSet` — all carried on `GetTestDataRequest.TestDataCategory`. `isSubscription` and
`segmentName` membership are outcomes of the `-subscription`/`-segment` variants, not inputs.

---

## Driver sequences

### 1. Identity & lookup

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Driver Pool (Mongo)
    participant DP as Driver Platform (external)

    Caller->>TDP: GET /driver/{driverId}
    TDP->>Pool: find by driverId
    Pool-->>TDP: driver record
    TDP-->>Caller: driver record

    Caller->>TDP: GET /driver/phone/{phoneNumber}
    TDP->>Pool: find by normalized phone (+62 then +65)
    Pool-->>TDP: driver record
    TDP-->>Caller: driver record

    Caller->>TDP: POST /driver/refresh-token?driverId=
    TDP->>DP: request new access token
    DP-->>TDP: accessToken, expirationTime
    TDP->>Pool: persist refreshed token
    TDP-->>Caller: driverId, phone, accessToken, expirationTime, testDataCategory

    Caller->>TDP: GET /driverById?driverId=
    TDP->>Pool: find by driverId (pooling-service path)
    TDP-->>Caller: driver test data
```

Signals: `driverId`, `phone`, `accessToken` freshness/expiry, `testDataCategory`.

### 2. Creation

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant DP as Driver Platform (external)
    participant Pool as Driver Pool (Mongo)

    Caller->>TDP: POST /driver/create?number=&type=&serviceArea=
    TDP->>DP: create `number` drivers of `type`, assign serviceArea (async)
    DP-->>TDP: new driverIds
    TDP->>Pool: persist new drivers
    TDP-->>Caller: "Driver creation job triggered!" (immediate; job runs in background)
```

Signals: `type` (the `DRIVER__<COUNTRY>__<TYPE>` category), `serviceArea`, `number` (count).
Fire-and-forget — there is no created-driver ID in the response, so a caller needing the resulting
driver right away should fetch from the pool instead of chaining off this call.

### 3. Wallet balance

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant DP as Driver Platform (external)

    Caller->>TDP: GET /driver/wallet-balance?driverId=&countryCode=
    TDP->>DP: fetch wallet balance
    DP-->>TDP: balance, currency
    TDP-->>Caller: balance, currency, countryCode

    Caller->>TDP: POST /driver/wallet-balance/recharge?driverId=&amount=&countryCode=
    TDP->>DP: fetch balance before
    TDP->>DP: top up by amount
    DP-->>TDP: balance after
    TDP-->>Caller: balance before, balance after
```

Signals: driver wallet balance amount, `countryCode` (`ID`→IDR, `SG`→SGD).

### 4. Tags

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Marketplace as Marketplace/Driver-tag service

    Caller->>TDP: GET /driver/tags?driverId=
    TDP->>Marketplace: fetch current tags (with retry)
    Marketplace-->>TDP: tags set
    TDP-->>Caller: tags set

    Caller->>TDP: POST /driver/refresh-tags?driverId=
    TDP->>Marketplace: recompute/refresh tags
    Marketplace-->>TDP: refreshed tags
    TDP-->>Caller: refresh confirmation

    Caller->>TDP: GET /driver/validate-tags?driverId=
    TDP->>Marketplace: fetch tags
    TDP->>TDP: compare against expected tag set for driver's category
    TDP-->>Caller: valid/invalid, missingTags[], extraTags[]
```

Signals: `tags` set, "correctly tagged" / "wrong tags" as a failure mode rather than a category.

### 5. Sanitisation & sanctions

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant DP as Driver Platform (external)

    Caller->>TDP: POST /driver/sanitise?driverId=
    TDP->>DP: check driver validity
    alt driver marked INVALID
        TDP-->>Caller: sanitisation skipped
    else driver usable
        TDP->>DP: reset driver to clean, reusable state (complete active orders, clear flags)
        TDP-->>Caller: sanitisation successful
    end

    Caller->>TDP: POST /driver/sanitise-driver?driverId=
    TDP->>DP: same full sanitisation path as /sanitise
    TDP-->>Caller: sanitisation successful / skipped

    Caller->>TDP: POST /driver/remove-sanctions?driverId=
    TDP->>DP: clear SUSPENDED / BLOCKED_ACTION flags
    DP-->>TDP: sanctions cleared (or some remain)
    TDP-->>Caller: cleared confirmation, or 409 if some sanctions remain

    Caller->>TDP: POST /invalid?driverId=
    TDP->>Pool: mark driver record as INVALID
    TDP-->>Caller: marked-invalid confirmation
```

Signals: `SUSPENDED`, `BLOCKED_ACTION`, driver validity state (`INVALID` vs. usable), "dirty" pooled
driver needing reset before reuse. Note the asymmetry: TDP can clear sanctions
(`remove-sanctions`) and mark a driver invalid (`/invalid`), but there is no endpoint to *impose* a
suspension.

### 6. Pool fetch

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Pool as Driver Pool (Mongo)
    participant DP as Driver Platform (external)

    Caller->>TDP: POST /aep/test-data-generator/get {testDataEntity: "driver", testDataCategory}
    TDP->>Pool: find AVAILABLE driver of category
    alt pool has one
        Pool-->>TDP: existing driver
    else pool empty
        TDP->>DP: create driver of category (same path as group 2)
        DP-->>TDP: new driver
        TDP->>Pool: persist
    end
    TDP-->>Caller: driver(s)
```

Signals: `testDataCategoryName` (`DRIVER__<COUNTRY>__<TYPE>`), `count`, `countryCode`.

### 7. Active-booking cleanliness

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant Booking as Booking platform (external)

    Caller->>TDP: GET /booking/getActiveBookings?driverId=
    TDP->>Booking: list active bookings for driverId
    Booking-->>TDP: activeBookings set
    TDP-->>Caller: activeBookings set, count

    Caller->>TDP: POST /booking/removeActiveBookings?driverId=
    TDP->>Booking: cancel/clear each active booking
    TDP->>Booking: poll until count reaches 0 (bounded wait)
    TDP-->>Caller: removedCount, success/fail status

    Caller->>TDP: POST /booking/bulk-remove-active-bookings
    TDP->>TDP: trigger scheduled cron job (async, fleet-wide)
    TDP-->>Caller: job-triggered acknowledgement
```

Signals: "driver currently has an active booking" vs. "a driver free/ready for allocation",
`ACTIVE_BOOKING` state.

---

## Booking creation — customer and driver, both wallets topped up first

A booking always sits on top of a customer *and* a driver. When the booking's payment mode needs a
wallet (`GOPAY_WALLET` on the customer side; the driver's own wallet for driver-side balance
checks), both wallets must be topped up **before** `createBooking` is called — TDP does not top up
either wallet as a side effect of booking creation.

```mermaid
sequenceDiagram
    participant Caller
    participant TDP
    participant CPool as Customer Pool
    participant DPool as Driver Pool
    participant GoPay as GoPay platform
    participant DP as Driver Platform
    participant Booking as Booking platform

    Caller->>TDP: POST /get {testDataEntity: CUSTOMER, testDataCategory}
    TDP->>CPool: fetch/create customer of category
    CPool-->>TDP: customerId, paymentMode

    Caller->>TDP: POST /customer/gopay/recharge?customerId=&amount=
    TDP->>GoPay: top up customer wallet
    GoPay-->>TDP: customer balance after top-up

    Caller->>TDP: POST /get {testDataEntity: driver, testDataCategory}
    TDP->>DPool: fetch/create driver of category
    DPool-->>TDP: driverId, driverType

    Caller->>TDP: POST /driver/wallet-balance/recharge?driverId=&amount=
    TDP->>DP: top up driver wallet
    DP-->>TDP: driver balance after top-up

    opt driver must be free for allocation
        Caller->>TDP: POST /booking/removeActiveBookings?driverId=
        TDP->>Booking: clear existing active bookings
    end

    Caller->>TDP: POST /booking/createBooking<br/>{customerId, driverId, paymentMode, serviceTypeId, bookingStatus, ...}
    TDP->>Booking: create order, allocate driverId to customerId, drive to targetState
    Booking-->>TDP: booking created at requested status
    TDP-->>Caller: booking details
```

Ordering rules:
- **Customer and driver wallet top-ups happen before `createBooking`**, not after — both are
  independent prerequisites, not part of the booking call itself.
- `paymentMode` on the booking request should match the customer's category's `paymentMode`
  (`CUSTOMER_WITH_GO_PAY` → `GOPAY_WALLET`, `Vanilla` → `CASH`).
- `driverType` on the booking request should be the resolved driver category's `DriverType` (e.g.
  `ID_BIKE` for `DRIVER__ID__BIKE`), not the raw category string.
- `bookingStatus`/`targetState` values come from `BookingConfig` (`scheduled`, `confirmed`,
  `driver_arrived`, `started`, `completed`, `cancelled`, `driver_cancelled`, …).
- Skip a wallet top-up on either side when the statement's signal is about a *shortfall* (e.g.
  "insufficient balance") rather than a positive amount — recharging would erase the exact state
  being tested.

## Using this catalog for signal matching

| Wording mentions | Refer to |
|---|---|
| "gopay", "wallet", "balance", "coins", "recharge", "top up" (customer) | Consumer § 2 |
| "loyalty", "tier", "XP", "status star" | Consumer § 3 |
| "segment", "gamification" | Consumer § 4 |
| "blacklisted", "blocked" (customer) | Consumer § 5 |
| "saved address", "POI", "AOI" | Consumer § 6 |
| "PIN", "pin set" | Consumer § 7 |
| plain customer category only ("a vanilla customer", "a gopay customer") | Consumer § 8 |
| "bulk create", "seed N drivers", "in service area X" | Driver § 2 |
| "wallet", "balance", "recharge", "top up" (driver) | Driver § 3 |
| "tags", "correctly tagged", "wrong tags" | Driver § 4 |
| "reset", "clean", "sanitised", "sanctioned", "suspended", "invalid" (driver) | Driver § 5 |
| plain vehicle/service-type category only ("a bike driver") | Driver § 6 |
| "active booking", "free for allocation", "ready to be assigned" | Driver § 7 |
| "…then book a ride/order", "…used for a food order", any statement naming both a customer and a driver together | Booking creation, above |
