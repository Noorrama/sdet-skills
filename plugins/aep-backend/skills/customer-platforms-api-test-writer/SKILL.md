---
name: customer-platforms-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests in
  the customer-platforms module of gojek-backend-tests (customer-platforms/src/test/java/**,
  covering vouchers, policy/consent, shortcuts, loyalty, help/chat adjacency, and the gobstarter
  gRPC surface). Trigger this any time the user gives a cURL, endpoint definition, or API doc
  targeting a customer-platforms host/path and asks for a new test case, test class,
  Endpoint/Client/Controller/DTO, or feature folder. Also use it when the user references TestRails,
  TestCountry, CustomerPlatformCommonTest, or com/utils/BaseClient in this module.
---

# customer-platforms API Automation Test Writer

**Prerequisite:** read `backend-automation/SKILL.md` and
`backend-automation/references/test-annotation-rules.md` first. This file covers only what is
specific to customer-platforms.

## Framework corrections worth knowing up front

- **customer-platforms FOLLOWS the shared external convention** — it does **not** declare its own
  `IServiceEndpoint` (0 declarations). It imports
  `restidioms.security.core.template.IServiceEndpoint` from the external
  `com.gojek.aep-backend-core:core` jar **249 times, with 246 implementors**, and fires requests
  through the jar's `RequestHandler` → `IAPIResponse`. So unlike `iris` or `payment-core`, you are on
  the mainstream path here — the jar's contract applies.
- **`com/utils/BaseClient.java` is only a host resolver**, not a base class to extend and not an
  iris-style local framework clone. Do not `extends` it expecting `GoFoodBaseClient` semantics.
  ⚠️ It also holds a `public static final` Basic-auth credential at line 8 with ~97 import sites —
  never copy that literal; load from the secrets path instead.
- `src/main/java` has **7 top-level packages**, not just `com` — don't assume a single root.
- There are **four dominant sub-conventions** in this module, not one. The two you will meet most:
  - **Convention A** — controller → typed DTO
  - **Convention B** — client → raw `IAPIResponse`, with a per-class `@BeforeMethod`
  Hybrids of A and B exist. **Match the sibling file in your feature area**; there is no single
  module-wide answer.
- `src/generated` holds 357 Java files from proto; the `gobstarter` sub-tree is **Kotlin gRPC**
  (247 `@TestInfo` sites).

## Test-method contract (mandatory — measured over all 2233 `@TestInfo` occurrences)

```
projectId     2233   100%  ALWAYS present
suiteId       2233   100%  ALWAYS present
owner         2233   100%  ALWAYS present
testCaseIds   2233   100%  ALWAYS present
countryName    607    27%  optional
```

`sectionId` and `automationType` are never used.

```java
@Test(groups = {…})
@TestInfo(projectId = TestRails.<PROJECT>_PROJECT_ID, suiteId = TestRails.<AREA>_BACKEND_SUITE_ID,
          testCaseIds = {"<real id>"}, owner = Owner.<NAME>,
          countryName = TestCountry.ID)          // optional, 27% of sites
public void someTest() {
```

- Constants live in **`src/test/java/com/constants/TestRails.java`** — projects:
  `CUSTOMER_PLATFORM_PROJECT_ID`, `HELP_PROJECT_ID`, `CHAT_PROJECT_ID`,
  `TICKET_ARBITRATION_PROJECT_ID`, `AGENT_EXP_PROJECT_ID`; suites: `X_BACKEND_SUITE_ID`,
  `PILOT_BACKEND_SUITE_ID`, `TARDIS_BACKEND_SUITE_ID`, `MERLION_BACKEND_SUITE_ID` (an alias of
  TARDIS — the Merlion suite was merged into it), `ORION_`, `SHIELD_`, `ROJAK_`, `ARGON_`,
  `LOYALTY_BACKEND_SUITE_ID`, plus `HELP_`, `CHAT_`, `AGENT_EXP_`, `TICKET_ARBITRATION_` suites.
- **`owner` comes from the `Owner` class** (2233 usages) — a dedicated class, unlike iris which mixes
  owners into its TestRail constants.
- **`countryName` uses the constant `TestCountry.ID`** — *not* a bare string. `go-logistics` uses the
  literal `"indonesia"` for the same attribute; do not cross the two conventions.

### Base class

`src/test/java/com/CustomerPlatformCommonTest.java` (42 lines) is the *root* base but **adds almost
nothing**: no `@BeforeMethod`, no client wiring — just static account helpers
(`generateCustomerAccount(Country, String)`, `isCountryCodeValid(...)`). Expect to do your own
wiring, or find a nearer feature-specific base.

### ⚠️ `RetryAnalyzer` in this module is a no-op

`customer-platforms/src/test/java/retry/RetryAnalyzer.java:10` declares `int retryLimit = 0`, and the
guard is `if (counter < retryLimit)`. **All 61 `retryAnalyzer = RetryAnalyzer.class` usages therefore
never retry.** Do not add it expecting retry behaviour, and do not "fix" the limit without checking
why it was zeroed — 61 tests currently depend on not retrying.

### Compile check

```
./gradlew :customer-platforms:compileTestJava
```
