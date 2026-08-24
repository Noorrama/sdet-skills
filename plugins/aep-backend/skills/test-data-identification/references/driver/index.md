# Driver identification (TDP-grounded)

Same pooling philosophy as Consumer (`../customer/index.md`): TDP pre-provisions driver partners
by category, and the default path for most statements is **select from the pool by category**,
not create. `POST /driver/create` exists for the pool-miss / bulk-seeding case — see Driver § 2 in
[../sequence/sequence.md](../sequence/sequence.md).

## Category naming pattern

Every driver category follows:

```
DRIVER__<COUNTRY>__<VEHICLE/SERVICE TYPE>
```

e.g. `DRIVER__ID__BIKE`, `DRIVER__ID__CAR_ECONOMY_SHIELD`, `DRIVER__SG__TAXI_PREMIUM_LARGE`
(`TestDataCategoryToActions.java`). Signal tokens map onto segments of this name:

| Signal wording | Token in category name |
|---|---|
| Country (`ID`/`SG`) | `<COUNTRY>` segment |
| `Bike`, `2w` | `BIKE` |
| `Car`, `4w` | `CAR` |
| `Economy` | `ECONOMY` |
| `Comfort` | `COMFORT` |
| `Premium` | `PREMIUM` |
| `Taxi` (SG only) | `TAXI` |
| `Airport` service | `AIRPORT` |
| `Vaccinated` | `VACCINATED` |
| `SDF`/`SDF3`/`SDF4`, health features | `SHIELD`, `PURIFIER`, `RAVEN`, `HEALTH` |
| Hybrid / SuperSub tagging | `SUPERSUB`, `HYBRID` |
| Runner / on-foot / cycle delivery | `RUNNER`, `CYCLE`, `KILAT` |
| Taxi fleet brand (ID) | `BLUEBIRD` |
| Externally sourced fleet (SG) | `EXTERNAL` |

With ~379 candidates in this enum, a catalog matcher's nearest-match behavior is very likely to
return a plausible-looking but wrong category — corroborate every token in a returned name against
an explicit signal in the statement before accepting it (parent skill's validation gate).

## The account vs. wallet-amount split

Same split as Consumer: whether a driver holds a positive balance at all is a property of the
pool (a freshly provisioned driver of any category typically has a default balance), while an
*exact or minimum amount* is a separate `WALLET_BALANCE` concern closed by a recharge operation —
see Driver § 3 in [../sequence/sequence.md](../sequence/sequence.md). Don't emit a recharge
operation just because a statement says "positive balance" if the category's default already
satisfies that.

## Fetching a pooled driver

```json
POST /aep/test-data-generator/get
{
  "testDataEntity": "driver",
  "testDataCategory": {
    "count": 1,
    "testDataCategoryName": "DRIVER__ID__BIKE",
    "countryCode": "ID"
  }
}
```

## Where the rest lives

[../sequence/sequence.md](../sequence/sequence.md) is the full catalog of every driver function
TDP implements — identity/lookup, creation, wallet balance, tags, sanitisation & sanctions, pool
fetch, and active-booking cleanliness — each shown as a call sequence, with the wording that points
to it. It also covers the composite booking-creation sequence, where a driver's wallet is topped
up before a booking is created. Use it to find the exact operation once this file has told you
which category the driver belongs to.
