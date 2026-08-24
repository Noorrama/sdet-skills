# Test-data recipes

A recipe is a **named bundle of data + environment defaults** so a charter can say
`data_needs.recipe: "transport-default"` instead of respelling the same facts in every charter, and
so the user can change one recipe at the gate and have it apply everywhere it's used.

Recipes resolve at **execution time** (phase D), not at synthesis. Phase B only names one and adds
`notes`. Resolution happens inside the charter's `goal-driven-exploration` sub-run, which already
owns `tdp_test_data_tool`, `appium_mock_location` and `appium_backdoor_login` — this file does not
re-specify those tools, only what to ask them for. Signatures and ordering live in
`goal-driven-exploration/references/tapmind-recipes.md`; that is the source of truth.

## ⚠ These recipes are UNVERIFIED against TDP

The table below was written from the shape of the test corpus, **not** from TDP's actual catalogue.
Nobody has confirmed TDP can supply "a customer whose GoPay balance is below IDR 20,000" on demand.
Treat every row as a *proposal* until it has been run once and the `verified` column says otherwise.

This matters because the failure is silent and expensive: an unverified ask returns *some*
customer, the charter runs green against the wrong data, and its findings look real. Two rules
follow from that, and they are not optional:

1. **At the gate, tell the user which recipes are unverified** so they can correct the ask before a
   device is touched. One sentence: "`transport-lowbalance` is unverified — TDP may not be able to
   guarantee a sub-fare balance."
2. **At execution, if TDP's response doesn't match what the recipe asked for, abort that charter**
   with the reason recorded. Do not substitute. See "When a recipe can't be satisfied" below.

Mark a row `yes` in `verified` only after a real run confirmed TDP returned matching data, and note
the date. A recipe nobody has exercised stays `no` no matter how reasonable it reads.

## Shared defaults

Unless a recipe overrides them:

- **Location** — South Jakarta, `-6.2615, 106.8106`. Same default as `goal-driven-exploration`;
  keep them in sync.
- **Customer** — from TDP. Never invented, never hardcoded.
- **Login** — backdoor, always, after the TDP fetch. Never drive the real login UI.
- **Theme** — whatever the gate settled for the suite.

## Recipes

| Recipe | TDP ask (verbatim `message`) | Verified | Notes |
|---|---|---|---|
| `transport-default` | *any active customer with a valid payment method* | no | Pickup at the default location; drop-off in the same city so allocation is realistic. |
| `transport-lowbalance` | *an active customer whose GoPay balance is below IDR 20,000* | no | For payment-fallback charters — the point is to make the insufficient-balance branch fire. Most likely row to fail; confirm early. |
| `transport-newuser` | *a customer with no completed bookings* | no | First-run coachmarks, empty states, onboarding interstitials. |
| `transport-firsttimecanceller` | *an active customer who has never cancelled a booking* | no | Needed for cancellation-fee waiver branches. |
| `gofood-default` | *any active customer with a GoPay balance* | no | Merchant search per `goal-driven-exploration/references/tapmind-recipes.md`. |
| `gofood-grouporder` | one call for the **host**, then one per **participant** | no | TDP is per-entity — a group order needs N+1 calls, not one. Default host + 2 participants unless the charter says otherwise. |
| `none` | — | n/a | Charter needs no provisioned customer (pre-login, app-launch, deep-link-only). Still mock the location. |

## Data states a recipe can't provide

Plenty of what charters need isn't a *customer* at all — an expired card on file, a blocked wallet,
a merchant in manual-accept mode, a config key at its limit. TDP has no lever for most of these.

Put them in `data_needs.notes` and, critically, in the charter's `preconditions` — so the gate shows
them and the user can say "we don't have that, drop the charter" **before** a device is provisioned
rather than after. A charter whose data state is unobtainable is a charter to drop at the gate, not
one to run hopefully.

## Adding a recipe

Add a row with `verified: no`. Keep the TDP ask column as the **literal string** to pass —
`tdp_test_data_tool` documents that the message must not be reworded, because TDP's own agent does
the interpretation. A recipe whose message has been "improved" in transit returns the wrong
customer.

## At the gate

Show which recipe each charter uses, grouped, so the user sees `transport-lowbalance` is needed by
two charters and can override once. Flag unverified rows. Record any override in the charter's
`data_needs.notes`; it passes through to the sub-run verbatim.

## When a recipe can't be satisfied

If TDP errors, or returns data that plainly doesn't match the ask, that charter is **`aborted`**
with the reason recorded — do not substitute a different customer to keep the run moving. A charter
run against the wrong data produces findings that look real and aren't, which is worse than a gap
the report reports honestly. The "Not covered" section exists precisely so this is cheap to admit.
