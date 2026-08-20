---
name: marketplace-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the marketplace module of gojek-backend-tests (marketplace/src/test/java/**, covering
  matchmaking/alice/bids/pooling, supply trackers and the unified supply interface (USI/SoW),
  driver incentives/schemes/shifts/points, constraint-enricher v2, MCS configs, manifest registry,
  self-onboarding, driver loyalty tiers, DLS/ADS and route store). Trigger this any time the user
  gives a cURL, endpoint definition, or API doc targeting a marketplace host/path and asks for a
  new test case, test class, Endpoint/Client/Controller/DTO, or feature folder. Also use it when
  the user references MarketplaceTestBase, SupplyIncentivesTestBase, MatchMakingTestBase,
  SowUSIBaseTest, Cev2BaseTest, MarketplaceCategories, ConfigManager, TestDataPoolHandler, or asks
  to follow the matchmaking / supply-trackers / supply-incentives test pattern.
---

# marketplace API Automation Test Writer

**Prerequisite:** read `backend-automation/SKILL.md` first if you haven't already this task — it
defines the common module-identification, local-framework-discovery, search-before-create,
never-invent-data, and compile-check workflow. Also read
`backend-automation/references/test-annotation-rules.md` before writing any `@Test` method.
This file only covers what's specific to marketplace.

> **marketplace looks like gofood and is different in almost every detail.** If you have the gofood
> conventions loaded, actively discard them: the endpoint suffix, the `@Test` label attribute, the
> DataProvider location, the nested-DTO layout and the assertion library all differ. The
> divergences are listed in the last section — read them.

## Architecture

```
TestNG @Test  →  Assertion class (assertions/<domain>/*, static methods) — optional
                     →  Controller (controllers.*, adds @Step + a `boolean expectSuccess` flag,
                                     asserts status, deserializes, Failsafe retry)
                         →  Client (clients.*, NO base client — 315x plain `new RequestHandler()`)
                             →  Endpoint (serviceEndpoints.*, 277 of 313 are flat
                                          `implements IServiceEndpoint`; no base endpoint)
                                 →  RequestHandler.processAPIRequest(endpoint)  →  IAPIResponse
```

**Negative tests bypass the controller** and assert directly on the client's `IAPIResponse` —
because the controller asserts success internally. This is the module's idiom for error paths.

## URLs — pre-joined constants, real path parameters

marketplace does **not** build URLs by concatenation in `url()`. Each `properties/*Properties`
class exposes `public static final String <Name>Url` already joined with `{placeholder}` tokens,
and the endpoint resolves them through a real `pathParameters()` implementation. Add your URL
constant to the module's properties class; never hardcode a host.

Hosts come from `marketplace-*.properties` under `src/main/resources`, selected by `PropertyLoader`
from `-Denv`, `INFRA`, `-Dmock` and `-Dsubenv`. Tests are additionally parameterised by
`-Dlocale=Indonesia|Singapore|Vietnam|Thailand` and `-DserviceAreaID`.

Secrets: Fortknox bucket `marketplace_platform`, property `api_secrets_json`. Never inline a secret.

## DTOs

Live in `entities/marketplace/<domain>/` (174 request + 141 response files).

- Annotation set: `@Data @Jacksonized @Builder` (the modern, dominant shape).
- Field naming: **camelCase with heavy `@JsonProperty`** mapping — not raw snake_case fields.
- **Nested objects go in separate sibling files**, one class per file. (gofood nests
  `public static class` inline — do not copy that here.)

## ⚠️ Registration — marketplace does NOT auto-discover new packages

Most modules in this repo auto-discover test classes. **marketplace is one of only two exceptions.**
Its suites enumerate packages explicitly in:

```
marketplace/src/test/resources/indoTestng.xml
marketplace/src/test/resources/sgTestng.xml
marketplace/src/test/resources/vietTestng.xml
```

**If your new test lives in a package not listed in those `<package>` entries, it silently never
runs** — no failure, no warning. When you add a test in a *new* package, add that package to all
three XMLs (or to whichever locales it applies to). Adding a method to an already-registered
package needs no XML change.

(The other exception is `pricing`, which enumerates packages in
`pricing/.../entrypoint/Entrypoint.java` via `JARUtils.getClassesInPackage("<pkg>")`.)

## Test-method contract (mandatory — verified counts over `marketplace/src/test/java`)

### Base class — pick by feature area, there are 21 of them

All under `src/test/java/testbases/`. Do **not** default to `MarketplaceTestBase`; route by area:

| Feature area | Base | uses |
|---|---|---|
| driver incentives / schemes / shifts / points | `SupplyIncentivesTestBase` | 269 |
| matchmaking / alice / bids / pooling | `MatchMakingTestBase` (or `MatchMakingTestBaseMinimal`, 37) | 193 |
| USI / SoW / plangen | `tests/supplytrackers/unifiedsupplyinterface/grpc/SowUSIBaseTest` | 186 |
| supply trackers / DLS / ADS / route store / anything else | `MarketplaceTestBase` | 95 |
| constraint-enricher v2 | `Cev2BaseTest` | 18 |
| prefman | `PrefmanTestBase` | 11 |
| supply incentives LTI | `SupplyIncentivesLTITestBase` | 10 |
| self-onboarding | `SelfOnboardingTestBase` | 10 |
| MCS configs | `McsBaseTest` | 8 |
| loyalty tiers | `loyalty/DriverLoyaltyTestBase`, `loyalty/ManualTierAdjustmentTestBase` | 1 each |

Two traps:
- **`SupplyIncentivesTestBase` does NOT extend `MarketplaceTestBase`** — it `implements ITest`
  directly (`testbases/SupplyIncentivesTestBase.java:66`) and holds ~25 controllers + ~10 builders
  as Lombok `@Getter @Setter` fields. Inheriting the wrong one silently loses the country/config
  machinery.
- `Cev2BaseTest extends MarketplaceTestBase` and adds an `@AfterMethod` that deletes rule trees
  recorded via `iTestResult.getAttribute("treeId")` — the marketplace way of per-test cleanup.

`MarketplaceTestBase` (360 lines) provides `scenarioContext`, `MongoDBUtils`,
`TestDataPoolHandler`, and — importantly — `setupConfig`/`rollbackConfig` `@BeforeMethod`/
`@AfterMethod` pair that reads `ConfigInfo` + `FeatureName` **out of the DataProvider row** and
mutates real service configs before each test (`:194-349`). That is why marketplace DataProviders
are so structured.

### The annotation block

```java
@Test(groups = {MarketplaceCategories.<GROUP>}, testName = "<human-readable intent>",
      dataProvider = "<dpName>", dataProviderClass = <Domain>DataProvider.class)
@TestInfo(projectId = TestRailConfig.<PROJECT>, suiteId = TestRailConfig.<SUITE>,
          testCaseIds = {"<real id>"}, owner = "first.last@gojek.com")
public void verifySomething(...) {
```

- `groups` mandatory (1826 uses), always from `src/main/java/constants/MarketplaceCategories.java`
  (342 lines). **Multiple groups per test is normal.** Common: `MP_CLOUD_MIGRATION_REGRESSION_TESTS`
  (455), `TRIPS_SMOKE` (137), `PLATFORM_CLOUD_MIGRATION_REGRESSION` (122),
  `MATCHMAKING_TEST_FIFO` (88), `MARKETPLACE_REGRESSION` (82), `POOLING_SMOKE` (81).
- Use **`testName =`** (1205) — **not** `description =` (291). `MarketplaceTestBase.setTestCaseName`
  prefers `testName()` and falls back to `description()` (`:66-71`).
- **`dataProviderClass` is the norm** (1297) — external DP classes, not inline methods.
- `priority =` is used here (219), unlike gofood.
- **`retryAnalyzer` is never used (0)**, and `dependsOnMethods` never (0). Retry goes through
  Failsafe in the controller or inline in the test body:
  ```java
  RetryPolicy<Object> p = new RetryUtil().getRetryPolicyForAssertionError(5, 3);
  Failsafe.with(p).run(() -> { /* asserts */ });
  ```

### `@TestInfo` values — from `src/main/java/config/TestRailConfig.java`

marketplace has **no `SuiteConstants`**. All three project ids happen to hold the same value, so
pick the one that names your area:

| Feature area | `projectId` | `suiteId` |
|---|---|---|
| matchmaking | `MARKETPLACE_PROJECT_ID` (1009) | `MATCHMAKING_SUITE_ID` (519) |
| supply trackers | `MARKETPLACE_PROJECT_ID` | `SUPPLY_TRACKERS_SUITE_ID` (486) |
| supply incentives | `USG_PROJECT_ID` (160) | `USG_SUPPLY_INCENTIVES_SUITE_ID` (95) or `USG_SUPPLY_DP_SUITE_ID` (43) |
| platform / CEV2 / MCS | `MARKETPLACE_DRIVER_PLATFORM_PROJECT_ID` (124) | `MP_PLATFORM_SUITE_ID` (124) |

`owner` is usually a quoted `"first.last@gojek.com"` literal (1278), but `TestRailConfig.OWNER_*`
constants also exist and are used (29) — prefer the constant when one exists for that person.

`testCaseIds` sometimes packs alternatives into a single string with `||`
(`{"5008641||4667784"}`) — follow the sibling file rather than splitting them.

### Naming — note the inversion vs gofood

| | marketplace | gofood |
|---|---|---|
| endpoint suffix | **`*EndPoint`** (173 vs 108) | `*Endpoint` (328 vs 173) |
| `@Test` label | **`testName =`** (1264 vs 292) | `description =` (592 vs 52) |

Method names are `lowerCamelCase`, usually mirroring `testName`.

### Assertions

| style | files | note |
|---|---|---|
| hard `org.testng.Assert` | 600 | **dominant** |
| `SoftAssert` | 112 | materially used — far more than gofood's 20 |
| AssertJ | 23 | minority |
| Google Truth | **0** | **not used in marketplace** (it is in gofood's `content/**`) |

Reusable assertion classes live in `src/main/java/assertions/<domain>/` and are called statically,
e.g. `Cev2Assertions.verifyCreateRuleTreeResponse(response)`.

### Controllers are fields, not inherited

564 of 924 test files declare `new <X>Controller()` as a test-class field. (gofood inherits ~60
pre-wired controllers from its base — marketplace generally does not.) Check your chosen base
first: `SupplyIncentivesTestBase` *does* hold ~25 controllers.

## Do-not-carry-over list (gofood → marketplace)

| Thing | gofood | marketplace |
|---|---|---|
| endpoint suffix | `Endpoint` | `EndPoint` |
| `@Test` label | `description=` | `testName=` |
| DataProviders | mostly inline | external `dataProviderClass` (1297) |
| nested DTOs | inner `public static class` | separate sibling files |
| DTO annotations | `@Getter @Setter @Builder` | `@Data @Jacksonized @Builder` |
| Truth assertions | 71 files | 0 — never |
| base client | `GoFoodBaseClient` | none — plain `new RequestHandler()` |
| builders | `requestbodybuilders/<Domain>RequestBodyBuilder` (static) | `builders/<Thing>Builder` (instance) |
| Fortknox | `gofood_secrets` / prop `key` | `marketplace_platform` / prop `api_secrets_json` |
| host resolution | hardcoded `HashMap` in `commons/PropertiesReader` keyed on `INFRA` | `marketplace-*.properties` via `PropertyLoader` |

## Compile check

```
./gradlew :marketplace:compileTestJava
```
