---
name: payment-core-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the standalone payment-core module of gojek-backend-tests (payment-core/src/test/java/settlement/**,
  covering merchant payout/settlement: Wallstreet rules/formulas/payouts, Plutus wallet balance
  and payout, Saudagar merchant onboarding, MPAdapter/MPAPI, CAA/PAA charge-refund, card, and
  Phoenix settlement). Trigger this any time the user gives a cURL targeting a payment-core host/
  path and asks for a new test case, test class, Endpoint/Client/Controller/DTO, or feature folder.
  Also use it when the user references WallstreetClient, PlutusClient, HttpServiceEndpoint,
  TestBase.step, or MerchantData. IMPORTANT — do not confuse this with "payment core" as used
  inside the separate gopay module (gopay/src/test/java/paymentTooling/**, a different domain
  folder documented in gopay/.gitlab/skills/qa-intern/playbooks/domain/payment-core.md) — these
  are two unrelated things with the same name; confirm which one the user means before proceeding.
---

# payment-core (standalone module) API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first if you haven't already
this task — it defines the common module-identification, local-framework-discovery,
search-before-create, never-invent-data, and compile-check workflow. This file only covers what's
specific to the standalone `payment-core/` module on top of that.

**This module does NOT depend on `gojek-commons`** (confirmed: no reference to it anywhere in
`payment-core/build.gradle` or source). It reimplements an equivalent stack locally under its own
package (`com.paymentcore.backendtests.*`) rather than using the shared `restidioms.security.*`
interfaces. Do not import anything from `restidioms.security.*` here — it will not resolve.

## Architecture

```
TestNG @Test (extends testBase.TestBase, uses the step(...) DSL — see below)
    →  Client (clients.<domain>.*Client, e.g. WallstreetClient, PlutusClient — plain classes,
                each holding one RequestHandler field)
        →  Endpoint (apis.<domain>.endpoint.*Endpoint, implements
                      com.paymentcore.backendtests.core.template.HttpServiceEndpoint — this
                      module's own local equivalent of IServiceEndpoint, NOT the shared interface)
            →  RequestHandler.processRequest(endpoint)  [raw RestAssured — see internal method
                                                          literally named processIServiceEndpoint(),
                                                          a naming leftover from the shared pattern]
                →  Response.as(ResponseClass)  [RestAssured/Jackson], then the Client manually
                                                 calls .setHttpStatusCode(response.getStatusCode())
```

A parallel `com.paymentcore.backendtests.core.template.GrpcServiceEndpoint<T extends AbstractStub<T>>`
interface and gRPC build tooling exist, but no confirmed live test consumer was found during
analysis — don't assume gRPC is the pattern for a new test here unless you find a real, currently
passing gRPC test to copy from first.

## Local Client/Endpoint/Controller pattern

- There is no shared `BaseClient` — each domain Client (`WallstreetClient`, `PlutusClient`,
  `AccountingFacetClient`, `ExchangeClient`, `MerchantPartnerAdapterClient`,
  `MerchantPartnerApiClient`, `RheaClient`) independently owns a `RequestHandler` field and
  hand-rolls each method: construct the `*Endpoint`, call `requestHandler.processRequest(endpoint)`,
  `response.as(ResponseClass)`, manually `.setHttpStatusCode(...)`, return.
- `RequestBody` here is `com.paymentcore.backendtests.core.entity.RequestBody` — a **local** class
  (constructed as `new RequestBody(SomeRequest.class, requestInstance)`), not the shared one.
- There is no separate Controller layer distinct from the Client in most domains — the Client
  method itself is the equivalent of what other modules call a "Client", and the test's private
  helper methods (e.g. `RuleCreationGopayTests.verifyRuleCreation(request)`) play the orchestration
  role a Controller would elsewhere.

## Request/response conventions

- Request/response POJOs live under `com.paymentcore.backendtests.apis.<domain>.model.{request,response}`,
  generally Lombok `@Builder`/`@Getter`.
- Response POJOs get their HTTP status **manually stamped post-hoc** by the Client
  (`.setHttpStatusCode(response.getStatusCode())`) — it is not part of the JSON body. Don't forget
  this line when adding a new Client method; every downstream assertion depends on it.
- Custom Jackson deserializers exist for loosely-typed fields (`AdditionalInfoDeserializer`,
  `StringOrListDeserializer`) — check whether the response field you're mapping needs one before
  assuming a plain type will deserialize cleanly.

## Authentication

**There is no single central auth mechanism — it's ad hoc per sub-domain.** Check the sibling
Endpoint in the exact sub-domain you're touching:

- **None** (default): most endpoints return no explicit auth override.
- **Basic auth via header literal**: e.g. `CreatePayAccountEndpoint` manually adds
  `new Param("Authorization", "Basic " + basicAuth)` — passed into the constructor, not computed
  via the interface's built-in `auth()`/`AuthType.BASIC` mechanism (even though that mechanism
  exists) — match this literal-header pattern for CAA/PAA-style endpoints, don't "fix" it to use
  the unused `auth()` path.
- **API key header**: e.g. `CreatePlutusPayoutEndpoint` adds `new Param("apiKey", HostProperties.plutusApiKey)`
  plus a generated `Idempotency-Key: UUID.randomUUID()`.
- **HMAC/RSA request signing**: `com.paymentcore.backendtests.utils.SignatureHelper` —
  `generateAsymmetricSignature` (RSA/SHA256withRSA, PAA/PayAccount-style) and
  `generateSymmetricSignature` (HMAC-SHA512 over `METHOD:PATH:AccessToken:SHA256(body):Timestamp`),
  used by `caa`/`card`/`paa`/`exchange`/`mpadapter`/`rhea` endpoints.
- **mTLS client cert**: applied automatically by `RequestHandler.formRequestSpecification()` via
  `httpServiceEndpoint.sslConfig()`, with a hardcoded fallback keystore for URLs containing
  `merchant1-gateway.staging.gopayapi.com`.

Credentials/hosts come from environment `.properties` files (`src/main/resources/{staging,qa}.properties`,
optionally overridden per-env under `overrides/`) — never hardcode a URL or key.

## Test-data conventions

- **Dominant pattern**: hardcoded enum constants mapping semantic names to real, pre-provisioned
  staging merchant IDs — e.g. `testData.saudagar.MerchantData` (64 entries,
  `MERCHANT_WS_RULE`, `MERCHANT_PLTS_PAYOUT_ONE_TIME`, etc., each wrapping a real merchant ID
  string). **This is the module's actual convention, not an anti-pattern to avoid here** — each
  test scenario gets its own dedicated pre-configured merchant fixture rather than dynamically
  creating one. If you need a new scenario, check whether an existing `MerchantData` entry already
  fits before asking for/inventing a new merchant ID.
- Similar per-domain enum/constant classes: `testData/wallstreet/*`, `testData/plutus/WalletSource`,
  `testData/caa/ChargeData` (a `@Builder` class, not an enum), `testData/card/MidtransCardData`.
- `@DataProvider`s are widely used for parameterization on top of these fixtures (e.g.
  `RuleCreationBankTransferTests` → `"bankTransferProviders"`).

## Validation patterns

- Status-code family assertions centralize in `assertions.commons.CommonsAssertions`
  (`assertStatusCode2xx`, `assertStatusCode400`, `assertStatusCode404`, etc.) — use the specific
  one if the API's behavior is precisely pinned down, the family one if it isn't.
- Domain-specific negative assertions encode business semantics too, e.g.
  `PlutusAssertions.assertPayoutLimitExceeded` checks `error_const == "PAYOUT_LIMIT_EXCEEDED"`
  **and** a locale-specific Indonesian error-message substring (matched via `.contains(...)`, not
  exact equality — tolerant of surrounding text changes). Don't invent new error strings; copy the
  exact substring from a sibling assertion or ask for a real sample response.
- **Async/eventual-consistency validation is HTTP-polling only — there is no DB or Kafka access in
  this module** (confirmed: no JDBC/Kafka usage found anywhere in `src/main`/`src/test`). Use
  `PlutusClient.getWalletBalanceWithRetry(...)` / `getLatestPayoutWithRetry(...)`-style methods, or
  `assertions.plutus.PlutusAssertions.assertBalanceIncreasedByWithRetry(Supplier<Double>, assertionFn)`
  (wraps `utils.Retry.assertWithRetry(...)`) — driven by `config.TestConfig.noOfRetries()`/
  `retrySleepSeconds()`, which explicitly replaced ~15 ad hoc call sites (per its own code comment)
  — reuse `TestConfig`, don't hand-roll a new sleep loop.
- Money comparisons use `BigDecimal`/`RoundingMode.HALF_UP`, not raw `double` equality — match this
  for any new balance/amount assertion.

## The `TestBase.step(...)` reporting DSL

`testBase.TestBase` (every test extends this) provides `step(String title, Callable<T> action)` /
`step(String title, Runnable action)` — wraps each logical test step with timing + cURL/response
capture, and implements "fail one step → skip remaining steps in this test, re-throw at the end"
semantics via a `ThreadLocal<Boolean> STEP_FAILED`. Structure multi-step tests (create → verify →
verify-again) as a sequence of `step(...)` calls, matching `RuleCreationGopayTests`/`PayoutPlutusTests`,
rather than a flat sequence of bare method calls with no step boundaries.

## Canonical tests (read these directly, don't guess)

- `src/test/java/settlement/wallstreet/rule/RuleCreationGopayTests.java`
  (`verifyRuleCreationGopay`) + `clients.wallstreet.WallstreetClient` — canonical
  create→search→get cross-verification chain using the `step(...)` DSL.
- `src/test/java/settlement/plutus/payout/PayoutPlutusTests.java`
  (`verifyPlutusPayoutSufficientAmount`, and its sibling negative-case methods) +
  `assertions.plutus.PlutusAssertions.assertBalanceIncreasedByWithRetry` — canonical
  async-polling-assertion example, plus several real negative cases driven by dedicated
  pre-provisioned `MerchantData` fixtures rather than mocked failures.

## Module-specific pitfalls

- Don't import `restidioms.security.*` — it doesn't exist as a dependency here.
- Don't forget the manual `.setHttpStatusCode(...)` stamp in a new Client method.
- Don't assume one central auth mechanism — check the specific sub-domain's sibling Endpoint.
- Don't invent a merchant ID — check `MerchantData` (and sibling per-domain enums) for an existing
  fixture that already matches the scenario you need.
- Don't hand-roll a new retry/sleep loop — reuse `PlutusClient`'s retry methods or `utils.Retry`/`TestConfig`.

## Legacy/dead patterns that must not be copied

- `GrpcServiceEndpoint<T>` and the gRPC build tooling — present but no confirmed live test
  consumer; don't treat it as the pattern for a new test without first finding a real, currently
  passing example.
- Nothing else was found to be clearly dead in this module during analysis — flag anything else
  you find as a new observation rather than assuming it's safe to imitate.

## Test-method contract (mandatory — verified)

Read `backend-automation/references/test-annotation-rules.md` first — then note that **the headline
rule there does not apply to this module.**

### ⚠️ payment-core does NOT use `@TestInfo` — do not add it

`payment-core` has **zero** `@TestInfo` usages across 48 test files and 311 `@Test` methods. Its
`build.gradle` declares **neither `gojek-commons` nor the `common-integrations` jar**, so
`com.gojek.TestInfo` **is not on the classpath**: adding the import is a **compile error**, not a
style deviation. Same for `@Ownership`.

This is the one module with a skill where "every test needs `@TestInfo`" is actively wrong.

### ⚠️ `@Test(groups = …)` is what actually matters here

CI selects tests **only** by group. A generated test with no wired group **never runs**. Groups come
from **`constants.Groups`** — this class was missing from earlier versions of this skill entirely.

```java
@Test(groups = {Groups.<GROUP>}, dataProvider = "…")
public void someTest(...) {
```

### Base class

`testBase.TestBase` (`payment-core/src/test/java/testBase/TestBase.java:17`) —
`@Listeners(BasicTestListener.class)` and **`implements IHookable`** (not a plain class; the
`IHookable` hook is how it wraps test invocation).

### Response DTOs — the compile-blocking correction

**56 of 65 response DTOs `extends com.paymentcore.backendtests.apis.commons.BaseHttpResponse`**
(`.../apis/commons/BaseHttpResponse.java:8`). Earlier versions of this skill never named this class
while still telling you not to forget the `.setHttpStatusCode(...)` stamp — following that literally
produces code that **does not compile**, because the stamp is inherited from `BaseHttpResponse`.

Annotation set: **`@Data` (122 files)** vs `@Getter` (22 files) across `payment-core/src`.
Earlier guidance said `@Builder`/`@Getter` was the convention; `@Data` dominates by ~5.5x.

### Local framework — payment-core clones the convention, shares nothing

| Concern | payment-core reality |
|---|---|
| Endpoint contract | **own** `com.paymentcore.backendtests.core.template.HttpServiceEndpoint` (75+ importers). **Zero** references to `IServiceEndpoint` or `restidioms.*` |
| Client base | **no `BaseClient` of any kind**. Each of the 7 domain clients owns a `RequestHandler` field; the de facto base is `.../utils/RequestHandler.java:25` |
| Response base | own `BaseHttpResponse` (above) |
| `gojek-commons` | **not a dependency** — no `project(...)` deps at all |

Use fully-qualified real package names from the table above. Earlier versions of this skill used
shorthand package names that do not exist and will not compile.

### Assertions

**`SoftAssert` appears in only 3 files here** (vs 103 in go-logistics). Hard asserts are the norm —
do not inject `SoftAssert` by default; match the sibling test.

### Corrections to earlier guidance

- **`SignatureHelper` is exchange-only** (2 files total) — *not* used by `caa`/`card`/`paa`/
  `mpadapter`/`rhea`. Earlier guidance sent authors down a signing path for five domains that do
  not sign.
- **`BigDecimal`/`HALF_UP` is not a module convention** — it exists in 2 files and is
  Plutus-balance-specific.
- There is a **`src/gatling/java` source set** in this module, previously undocumented.

### Compile check

```
./gradlew :payment-core:compileTestJava
```
