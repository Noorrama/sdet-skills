# Test Data Domains — knowledge file

Step 1 of `backend-test-data-identification`. This file is the **maintained memory** for domain
classification: it decides which domain a fixture belongs to, before any catalog lookup happens.

**Vocabulary owner:** the TDP team. Adding a domain is an edit to this file — no skill change.
**Not in this file:** category names and operation names. Those come from the TestBuddy MCP catalog
(`get_supported_categories`, `get_supported_operations`) at runtime and go stale the moment they are
copied here. The category/operation columns below are *illustrative shapes only*.

## How to use this file

1. Read the fixture's `description` + `required_state`.
2. Lift atomic signals (one per concept) → `test_data_type_signals[]`.
3. Match the signals against **Owns** and **Signals** below → `test_data_domain`.
4. A fixture that needs two independent entities (a customer *and* a driver) is two fixtures in the
   automation plan, so two records — never one record with two domains.
5. No section matches → `unidentified_fixtures[]` with `reason: NO_DOMAIN_MATCH`. Do not invent a
   domain; propose it to the TDP team and add a section here once agreed.

## Domains

### CUSTOMER
- **Owns:** consumer accounts and their account-level state — verification/KYC level, activation status, linked wallet, segments, saved addresses, tokens.
- **Signals:** `Active`, `Verified`, `First-time user`, `Linked Wallet`, `GoPay`, `Segment`, `Saved address`, `Blocked`, `account_status`, `wallet_linked`.
- **Category shape:** `CUSTOMER_WITH_*`.
- **Operation shape:** add-to-segment, refresh token, edit saved address.

### DRIVER
- **Owns:** driver partners and their operational state — vehicle type, service type, contract, online/offline, polygon and service-area association, shifts.
- **Signals:** `Bike`, `2w`, `4w`, `Car`, `Economy`, `Comfort`, `SDF`/`SDF3`/`SDF4`, `core`, `Polygon`, `Service area`, `non jabo`, `Shift opted`, `Shift started`, `Online`.
- **Category shape:** `DRIVER__ID__*`.
- **Operation shape:** identify polygon, assign polygon, go online.
- **Note:** driver *wallet* balance is `WALLET_BALANCE` when the balance is the point of the fixture; a driver merely holding a positive balance stays `DRIVER`.

### MERCHANT
- **Owns:** merchant/outlet entities — vertical, pooling support, operating hours, catalogue/menu availability.
- **Signals:** `GoFood merchant`, `Pooling supported`, `In operation hours`, `Closed`, `Menu`, `Outlet`.

### PAYMENT_INSTRUMENT
- **Owns:** the instrument itself — cards, bank accounts, linked third-party payment methods; validity, expiry, tokenisation/saved state.
- **Signals:** `VISA`, `Mastercard`, `card_type`, `is_expired`, `already_saved`, `Tokenised`, `Bank account`, `Linked method`.
- **Operation shape:** create card, associate instrument with a user.
- **Never** put a real card number, CVV or token in signals, `operationInput` or the TestBuddy prompt. The fixture describes the state; TestBuddy produces the instrument.

### WALLET_BALANCE
- **Owns:** balance state on a wallet — exact amount, sufficiency/insufficiency, zero, boundary and blocked balances.
- **Signals:** `Positive balance`, `Zero balance`, `Insufficient balance`, `Recharge`, `wallet_balance_idr`, `Balance limit`.
- **Operation shape:** recharge wallet, set balance.
- **Disambiguation:** `CUSTOMER`/`DRIVER` owns *who*; `WALLET_BALANCE` owns *how much*. When the amount is the variable under test, this is the domain.

### VOUCHER
- **Owns:** vouchers, promos and their lifecycle — active, expired, redeemed, usage caps, eligibility rules.
- **Signals:** `Voucher`, `Promo code`, `Expired voucher`, `Redeemed`, `Usage limit`, `Eligible`, a named promo (e.g. `SAVE20`).

### BOOKING
- **Owns:** composite booking/order state — often provisions customer + driver + order together.
- **Signals:** `Booking`, `Order`, `In-transit`, `Completed`, `Cancelled`, `Allocated`, `Multi-stop`, `Orders`.
- **Note:** a composite booking category is **one** fixture and one call, even though it materialises several entities.

### LOCATION
- **Owns:** geographic test data — pickup/drop points, stops, route distance, service areas, polygons as data (not as a driver association).
- **Signals:** `Static pooling`, `Stop location`, `Route distance`, `Service area`, `Pickup`, `Drop`, `Coordinates`.
- **Note:** frequently `TDP_OPERATION_FALLBACK` — locations are fetched by operation rather than held as categories.

### DB_INFRA — not a TDP domain
Testcontainers, migration and schema fixtures (`required_state.entity: DB_INFRA` in the automation
plan). **Skip these**: no domain, no category, no record. Count them as `skipped_db_infra`.

## Disambiguation quick rules

| Ambiguity | Resolve to | Because |
|---|---|---|
| `CUSTOMER` vs `USER` | `CUSTOMER` | `USER` is legacy phrasing for the same consumer account. Keep one name so category lookups stay consistent. |
| `CUSTOMER` vs `WALLET_BALANCE` | whichever the fixture varies | Account state → `CUSTOMER`; balance amount → `WALLET_BALANCE`. |
| `CUSTOMER` vs `PAYMENT_INSTRUMENT` | the entity being provisioned | "user with a saved card" where the card state varies → `PAYMENT_INSTRUMENT`, associated to a customer via operation. |
| `DRIVER` vs `LOCATION` | the entity under test | Driver-to-polygon association → `DRIVER`. Standalone stops/routes → `LOCATION`. |
| `BOOKING` vs its parts | `BOOKING` | If a composite category provisions the whole booking, one fixture beats three. |

## Maintenance

- Keep entries short — **Owns** + **Signals** is the whole job. Prose here does not improve matching.
- Retire a domain only when TDP retires it; a stale record referencing a removed domain fails
  identification loudly at re-identification time, which is the intended behaviour.
- Self-updating from the TDP catalog is a future step (RFC: TBD). Until then this file is edited by hand.
