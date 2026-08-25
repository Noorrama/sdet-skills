# Consumer identification (TDP-grounded)

TDP models a consumer as a **pooled, pre-provisioned account** — most statements should be
answered by selecting an existing account of the right category from the pool, not by creating
one. `CREATE_CUSTOMER` exists for pool-miss cases, but the default path is **select by category**.

## The account vs. wallet-amount split

The most common source of mis-identification: TDP separates *whether a payment method is linked at
all* from *how much money is currently in it*.

| What varies | Owned by | Mechanism |
|---|---|---|
| Does this customer have GoPay/card/GoCorp linked | the **category** it was pooled under | `TestDataCategoryCustomer` enum |
| How much is in the wallet right now | the **balance**, a mutable number | wallet endpoints, Consumer § 2 in [../sequence/sequence.md](../sequence/sequence.md) |

So "a user with gopay" → category `CUSTOMER_WITH_GO_PAY` (the wallet is already linked — nothing to
operate on). "A gopay user with a positive balance" → category, plus a recharge operation, only
when the amount itself is the thing under test.

## TDP customer categories

From `TestDataCategoryCustomer.java` (`(value, isEnabled, paymentMode)`):

| `testDataCategoryName` | Enabled | `paymentMode` | Selected by wording like |
|---|---|---|---|
| `VANILLA` | ✅ | `CASH` | no payment-instrument mention; default/plain customer |
| `CUSTOMER_WITH_CC` | ✅ | `card` | "saved card", "credit card", "CC" |
| `CUSTOMER_WITH_GO_PAY` | ✅ | `GOPAY_WALLET` | "gopay", "linked wallet", "e-wallet" |
| `Customer_With_Go_Pay_coins` | ❌ disabled | `GOPAY_COINS` | "gopay coins" — not currently served; treat as `TDP_COMPLETE_FALLBACK` |
| `Customer_With_Partial_Go_Pay_coins` | ❌ disabled | `GOPAY_COINS` | "partial gopay coins" — same caveat |
| `CUSTOMER_WITH_GOCORP` | ✅ | `GOCORP` | "gocorp", "corporate account" |
| `CUSTOMER_WITH_SAVED_ADDRESS_POI` | ✅ | `CASH` | "saved address", "point of interest", "POI" |
| `CUSTOMER_WITH_SAVED_ADDRESS_AOI` | ✅ | `CASH` | "saved address", "area of interest", "AOI" |

`isEnabled: false` is a hard signal for the parent skill's validation gate: even if the matcher
returns a coins category, corroborate against `isEnabled` before accepting.

## Fixture-description vocabulary that isn't a real category name

Automation plans (e.g. `EPIC-1122/automation_plan.json`) sometimes author fixture-level category
names that describe intent but don't match a real `TestDataCategoryCustomer` value — don't propose
these literally, translate them to the enum above:

| Fixture-description wording | Real TDP category | Why |
|---|---|---|
| `CUSTOMER_WITH_WALLET`, `wallet_status: ACTIVE` | `CUSTOMER_WITH_GO_PAY` | "wallet" in fixture prose means the linked GoPay wallet, the same signal as "gopay"/"linked wallet" above — there is no separate `_WITH_WALLET` enum value. |
| `CUSTOMER_WITH_SAVED_CARD`, `saved_card_type`, `saved_card_number` | `CUSTOMER_WITH_CC` | "saved card" is the `CUSTOMER_WITH_CC` signal; the card-specific sub-fields (`saved_card_type`, `saved_card_number`, a SHA-256 fingerprint) describe state this domain does not track — see [../payment_instrument/index.md](../payment_instrument/index.md) for why those sub-fields fall outside TDP. |
| `card_already_saved: false` | N/A — not a Consumer signal | Describes payment-instrument state, not the account; route the instrument-state part to [../payment_instrument/index.md](../payment_instrument/index.md), keep only the customer-category part here. |

A fixture combining one of these left-column names with true `CUSTOMER_WITH_CC` (as this file uses
it) still resolves to that customer for the pool-fetch — the "not a Consumer signal" phrase above
applies only to the card-specific attributes layered on top.

## Fetching a pooled customer

```json
POST /aep/test-data-generator/get
{
  "testDataEntity": "CUSTOMER",
  "testDataCategory": {
    "count": 1,
    "testDataCategoryName": "CUSTOMER_WITH_GO_PAY",
    "countryCode": "ID"
  }
}
```

`TestDataCategory` also carries optional selection filters — booking-history flags
(`hasTransportCompletedBooking`, …), `isPinSet`, `isBlackListed`, `used` — these narrow which
pooled account comes back; they are pool attributes, not operations.

## Where the rest lives

[../sequence/sequence.md](../sequence/sequence.md) is the full catalog of every consumer function
TDP implements — identity/lookup, wallet, loyalty, segmentation, blacklist, saved addresses, PIN,
and the pool-fetch variants — each shown as a call sequence, with the wording that points to it. It
also covers the composite booking-creation sequence, where a customer's wallet is topped up before
a booking is created. Use it to find the exact operation once this file has told you which
category (if any) the account belongs to.
