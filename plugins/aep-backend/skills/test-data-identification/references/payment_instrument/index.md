# Payment instrument identification (TDP-grounded) — no pooled entity exists

Like Merchant, TDP has **no card, bank-account, or generic payment-instrument entity** — no model,
service, controller, or category enum. This bundle records that gap explicitly rather than leaving
`../test_data_domains.md`'s illustrative PAYMENT_INSTRUMENT section unverified.

## What was checked, and found absent

Zero hits anywhere in `src/main/java/com/gojek/aep/` for: `card_type`, `is_expired`, `tokenised` /
`tokenized`, `bank_account`, `VISA`, `Mastercard`, or `payment_instrument`. No `CardModel`,
`CardService`, `CardController`, or `TestDataCategoryCard`-style enum exists.

## What exists instead, and why it doesn't count

| Code | What it actually is | Why it isn't a payment-instrument entity |
|---|---|---|
| `QRGenerationController` / `QRGenerationService` (`com.gojek.aep.controllers.gopay.qris`, `POST /aep/test-data-generator/qr/generate-dynamic-qr`) | Generates a **dynamic QR code** for a merchant via `OpenApiMerchantMpmAdapterClient.postQrMpmGenerate(merchantId, acquirer)` | `GenerateDynamicQRRequest.java` carries only `merchantId` and `acquirer` — no card/instrument state, validity, or tokenisation fields |
| `GoPayMerchantUserController` / `Service` | GoPay merchant-user auth token fetch by phone | Holds no card or instrument fields (same finding as `../merchant/index.md`) |
| `paymentMode` (String) on `GetBookingRequest.java`, elsewhere | A **booking** attribute (`CASH`, `card`, `GOPAY_WALLET`, `GOCORP`, `GOPAY_COINS` — see `../customer/index.md`) | Selects *how* a booking is paid; it is not itself an instrument record with its own validity/expiry/tokenisation state |

`paymentMode: "card"` on a Consumer category (`CUSTOMER_WITH_CC`) is the closest thing to a "has a
card" signal, and it is owned entirely by the **Consumer** bundle
(`../customer/index.md#tdp-customer-categories`) — there is no separate card object to look up
underneath it.

## Keywords seen in fixture descriptions (still no TDP entity behind them)

`EPIC-1122/automation_plan.json` (a `wallet-service` card-save automation plan) is a concrete
example of this gap in practice — its fixture `description`/`config` fields carry a full
card-shaped vocabulary that still has no TDP model behind it: `cardNumber`, `expiryMonth`,
`expiryYear`, `cvv`, `holderName`, `card_already_saved`, `saved_card_type`, `saved_card_number`,
card `fingerprint` (`SHA256('<customerId>:<cardNumber>')`), Luhn-check validity, `vault-service`
tokenisation (`POST /vault/v1/tokenise`), and the feature flag `payment.card_save.enabled`. None of
these are `../customer/index.md` signals — they describe the *instrument*, not the account — and
none of them resolve to a TDP category or operation; they document a `wallet-service`-owned
Postgres table (`payment_cards`) and its own validation/tokenisation logic, entirely outside TDP.

This is exactly the "fixture varies the instrument itself" case the Identification consequence
below already calls out — a plan referencing this vocabulary stays `TDP_NOT_SUPPORTED` for the
instrument-specific fields, with only the owning customer (`CUSTOMER_WITH_CC` via
`../customer/index.md`) resolved through TDP.

## Identification consequence

- **Never propose a `PAYMENT_INSTRUMENT_WITH_*`-style category or a `CardModel`-shaped record** —
  neither exists in this codebase.
- A fixture whose signal is purely payment-instrument state (a specific card type, an expired card,
  a not-yet-saved card) is `TDP_NOT_SUPPORTED` unless a live TestBuddy/Pertamax tool independently
  exposes card creation/association (per the parent skill's worked example: `CREATE_CREDIT_CARD` →
  `ADD_CREDIT_CARD_TO_USER`, `TDP_HYBRID_FALLBACK`) — verify that tool actually exists in the live
  MCP inventory before citing it; do not assume it from the SKILL.md example alone.
- A fixture whose signal is really "a customer who pays by card" (no card-specific state under
  test) is **not** this domain — it's `CUSTOMER_WITH_CC` via `../customer/index.md`. Route there
  first; only fall back here when the fixture varies the instrument itself, not who holds it.
- **Never** put a real card number, CVV, token, or account number into a signal, prompt, or record
  — this domain's absence in TDP is exactly why any such value appearing in a fixture is fabricated
  or a genuine secret, and both are prohibited (parent skill's guardrails; org data-protection rules
  redact live-looking credentials on sight).

## Where the rest lives

Nothing to route to yet — this is a pure knowledge gap, not a partially-covered domain. Flag any
fixture that lands here in `needs_human_review` so a recurring pattern becomes a TDP backlog item,
the same way `../driver/index.md` treats a repeatedly-requested-but-missing category.
