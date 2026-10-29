---
name: iris-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests in
  the iris module of gojek-backend-tests (iris/src/test/java/**, covering money transfer, merchant
  snap/QR, BiFast, and provider-integration user journeys). Trigger this any time the user gives a
  cURL, endpoint definition, or API doc targeting an iris host/path and asks for a new test case,
  test class, Endpoint/Client/DTO, or feature folder. Also use it when the user references
  IrisTestrailConstants, IrisTestListener, IrisProperties, or the iris local endpoint contract.
---

# iris API Automation Test Writer

**Prerequisite:** read `backend-automation/SKILL.md` and
`backend-automation/references/test-annotation-rules.md` first. This file covers only what is
specific to iris.

### Fixture setup from enriched plan (`test_data_output`)

Load `reference/fixture-acquisition-from-tdi/SKILL.md` first. This module has **no** live
`TDP2Controller` / `TestDataPoolController` usage in `iris/` — grep before emitting either.

| Status | iris APIs |
|---|---|
| `TDP_SUPPORTED` | Existing helpers / fixtures in the feature package. Do not invent pool calls. |
| `TESTBUDDY_*` | `TODO(agent-pm)` unless a sibling already calls TDP2. |

## Framework — iris rolls its own, module-wide

iris does **not** use the `restidioms` / `gopay` `IServiceEndpoint` convention. It defines its own
local endpoint contract, applied consistently across all 51 endpoint classes (see
`analysis` note below). It is a **50/50 HTTP and gRPC module** — confirm which transport your
target API uses before picking a template.

Config is loaded lazily via **static initializers in `properties/IrisProperties`** — there is no
bootstrap hook to hang setup off.

## Layering — there is NO controller layer

iris is a **5-layer** module: `Endpoint → DTO → Client → Helper → Test`. There are **zero** files
with `Controller` in the name. The orchestration a controller would do lives in
`helpers/*Helper` (101 files). Do not create a controller here; extend or add a helper.

`iris` reimplements the framework locally: its `HttpServiceEndpoint` is a clone of the canonical jar
interface (same seven abstract methods, differing only in defaults — iris alone adds
`getFormattedBearerToken`), and it has local copies of `Param`, `RequestBody` and `RequestHandler`
too. Note `CommonEndpoint` / `BaseIrisLibreAdapterClient` are **irisLibreAdapter-only**, not
module-wide — don't generalise them.

## Assertions — hard asserts only

**`SoftAssert` appears in 0 files.** Use hard `org.testng.Assert`. Do not introduce `SoftAssert`.

## Test-method contract (mandatory — verified counts over `iris/src/test/java`)

### `@TestInfo` is the strongest convention in this module

```
files with @TestInfo   182 of 183   (the only exception is TestBase.java itself)
@TestInfo occurrences  1141
@Test( occurrences     1134
```

**Every single test method has one.** Never omit it here.

```java
@Test(groups = {<GROUP>})
@TestInfo(projectId = IrisTestrailConstants.<PROJECT>, suiteId = IrisTestrailConstants.<SUITE>,
          testCaseIds = {"TC-704845"}, owner = IrisTestrailConstants.<OWNER>)
public void someTest() {
```

- **All of `projectId`, `suiteId` AND `owner` come from the single class `IrisTestrailConstants`**
  (1138 usages each). This is unusual — most modules keep owner emails in a separate class. iris
  mixes them into the TestRail constants class.
- **`testCaseIds` uses the `TC-` prefix** in iris (`{"TC-704845"}`) — 1,764 such ids repo-wide are
  concentrated here. Do not strip the prefix.

### Base class — provides nothing but a listener

`iris/src/test/java/testBase/TestBase.java` is **9 lines**: `@Listeners(IrisTestListener.class)`
and an empty body. No `@BeforeSuite`, no shared fields, no helper factories, no config bootstrap.

147 test files `extends TestBase`. Extend it for the listener, but expect to construct everything
you need yourself in your own `@BeforeClass`.

### Class-level annotations: essentially none

Only 5 files add Lombok `@Slf4j`. The single `@Listeners` lives on `TestBase`. No Allure/`@Epic`/
`@Feature` annotations anywhere.

### `@Test` attributes — measured over 1134 parsed `@Test(...)`

```
groups           1114   (98.2%)  <- effectively mandatory
dataProvider       51   (4.5%)
description        48   (4.2%)
enabled            32   (2.8%)   <- ALL 32 are `enabled = false`
priority            0
retryAnalyzer       0
dependsOnMethods    0
invocationCount     0
timeOut             0
```

Plus 9 bare `@Test` with no parentheses.

- `groups` is effectively mandatory (98.2%) — the suite is assembled by group, so a missing group
  means the test does not run.
- `description` is rare here (4.2%) — unlike gofood, do not feel obliged to add it.
- **`priority`, `retryAnalyzer`, `dependsOnMethods`, `invocationCount`, `timeOut` are used exactly
  zero times.** Do not introduce them.
- `enabled` is only ever used as `enabled = false` to park a test.

### Compile check

```
./gradlew :iris:compileTestJava
```

## ⚠️ Known defect to not replicate

Several of the newest test classes (Aug 2026) **omit `groups` entirely**, which means the
`includeGroups`-driven runner can never select them — they are dead on arrival. Confirmed examples:

```
iris/src/test/java/serviceTest/irisRouter/CreatePayoutSeabankIntrabankOpenApi.java
iris/src/test/java/serviceTest/bcaAutoCollectAdapter/{OAuthTokenTest,AuthTest,AccountAuthorizationNotificationTest}.java
iris/src/test/java/serviceTest/irisOpenApiService/transferStatus/CreateTransferStatusInquiryCIMBBIFast.java
```

If you copy one of these as your template you inherit a test that never runs. Always add `groups`.

Also `BankSchedulerServiceClient.java:31` contains a `Thread.sleep(25000)` — do not copy that
polling approach.
