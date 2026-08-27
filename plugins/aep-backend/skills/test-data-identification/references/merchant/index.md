# Merchant identification (TDP-grounded) — no pooled entity exists

Unlike Consumer and Driver, TDP has **no merchant test-data category, model, service, or pool**.
This bundle exists to make that gap explicit and grounded, the same way the populated bundles
ground what *does* exist — so identification never invents one.

## What was checked, and found absent

- No `MerchantController`, no `MerchantModel`/`@Document(collection = "merchants")`, no
  `MerchantRepository`, no `TestDataCategoryMerchant`-style enum anywhere in
  `src/main/java/com/gojek/aep/`.
- No `/aep/test-data-generator/get` pool path accepts `testDataEntity: "merchant"`.
- No fields or endpoints for outlet, menu, operating hours, or "pooling supported" — the MERCHANT
  signals listed in `../test_data_domains.md` (`GoFood merchant`, `Pooling supported`, `In operation
  hours`, `Closed`, `Menu`, `Outlet`) have no corresponding code.

## Signal vocabulary

"Restaurant" is MERCHANT-domain wording — a fixture describing a restaurant (e.g. "Restaurant
enabled for GoFood group order, max_participants 8") is a merchant fixture, not a workflow/booking
or session-entity fixture, even though the same gap above still applies: it lands in
`TDP_OPERATION_FALLBACK`/`TDP_NOT_SUPPORTED`, never an invented `MERCHANT_WITH_*` category.

## What exists instead, and why it doesn't count

| Code | What it actually is | Why it isn't a merchant entity |
|---|---|---|
| `merchantId` / `merchantType` on `GetBookingRequest.java`, `merchantId` on `BookingModel.java` | Plain pass-through `String` fields on the **booking** request/model | Not a pooled/categorized entity of their own — see [../workflow/food/index.md](../workflow/food/index.md#merchant--not-a-tdp-managed-entity) |
| `FBONV1Response.getMerchant().getSaudagarID()` (`GoFoodBookingService.java`) | Merchant identity **returned by the live GoFood order-creation call** | Sourced externally at order time, not seeded/managed by TDP the way a customer or driver category is |
| `GoPayMerchantUserController` / `GoPayMerchantUserService` (`com.gojek.aep.controllers.gopaymerchant.user`) | GoPay's own **merchant-user auth** domain — fetches an auth token for a GoPay merchant user by phone (`GET /aep/test-data-generator/gopay-merchant/user/auth-token`) | Payment-merchant auth, unrelated to GoFood restaurant merchants — no outlet/menu/hours concept |

## Identification consequence

A fixture whose signal is merchant state (an in-operation-hours merchant, pooling support, a menu
item) has no category or pool to select from:

- **Never propose a `MERCHANT_WITH_*`-style category** — it does not exist; a catalog matcher
  returning one fails the parent skill's validation gate the same way an uncorroborated driver
  category would (`../driver/index.md`'s ~379-candidate warning).
- Route to `TDP_OPERATION_FALLBACK` if a live merchant-lookup operation exists (e.g. resolving a
  `merchantId` via a `<Domain>Agent_*` tool), or `TDP_NOT_SUPPORTED` with `missing_operations`
  naming the gap, per the parent skill's decision table.
- Never substitute a hardcoded or example `merchantId` — that is inventing an identifier,
  prohibited by the parent skill's guardrails.
- When the fixture's real need is "a customer orders from a merchant, fulfilled by a driver," that
  is the **Food workflow** ([../workflow/food/index.md](../workflow/food/index.md)), not a
  standalone MERCHANT fixture — merchant existence there is a precondition of the booking call,
  not a separately provisioned entity.

## Where the rest lives

[../workflow/food/index.md](../workflow/food/index.md) is the operational context this gap matters
in: it documents the mandatory merchant-acceptance step (`MERCHANT_ACCEPTED` in `BookingState`)
that gates driver assignment, using the same "not TDP-managed" facts as this page.
