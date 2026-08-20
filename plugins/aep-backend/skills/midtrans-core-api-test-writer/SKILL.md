---
name: midtrans-core-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests in
  the midtrans-core-api module of gojek-backend-tests (midtrans-core-api/src/test/java/**, covering
  credit-card/Dragon payment flows, MTI/MID router, card management (CMS), exbin, and core-api
  charge/capture journeys). Trigger this any time the user gives a cURL, endpoint definition, or API
  doc targeting a midtrans host/path and asks for a new test case, test class, endpoint enum
  constant, controller/request-helper, or Model DTO. Also use it when the user references ApiDetails,
  ApiHelper, RequestModelHelper, ApiHost, TestCategories, or the "enum constant per endpoint" idiom.
---

# midtrans-core-api API Automation Test Writer

**Prerequisite:** read `backend-automation/SKILL.md` and
`backend-automation/references/test-annotation-rules.md` first. This file covers only what is
specific to midtrans-core-api.

> ## ⚠️ Handling secrets in this module — read before writing any code
>
> `midtrans-core-api` is a **payments** module and currently contains **hardcoded live-looking
> credentials and raw card data committed to source control** (server keys, Basic-auth blobs, API
> keys, card numbers).
>
> **When you write or extend code here:**
> - **Never copy a credential or card-number literal** out of a neighbouring file, even though the
>   surrounding pattern is otherwise the one to follow. Load from `VaultUtils/` or an env var and
>   leave `// TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.`
> - **Never reproduce such a literal** in a summary, report, commit message, or MR description.
> - If you notice one while working, flag its **file:line to the user** without quoting the value, so
>   it can be rotated.
> - Raw PAN/card data in source is a PCI concern, not just hygiene. Treat it as a finding worth
>   escalating rather than a convention to imitate.

## The endpoint idiom — enums, not classes

This module is **100% Java** (1213 `.java`, 0 `.kt`) and looks like nothing else in the repo:

- **No `IServiceEndpoint`, no `BaseClient`, no client layer at all.**
- The endpoint contract is the local interface **`CommonUtils/Api/ApiDetails.java`**, and **all 20
  implementations are Java `enum`s, not classes** — one enum per backend service, **one enum constant
  per endpoint**, ~335 endpoint constants in total.
- Request firing lives in **`CommonUtils/Api/ApiHelper.java`** and its near-duplicate
  **`Controller/RequestModelHelper.java`**, which `<Service>Controller` / `<Service>RequestHelper`
  classes extend.
- Supporting enums on `ApiDetails`: **85 `ApiHost` constants**, **68 `Headers` constants**, 6
  `ApiRequestType` (GET/POST/PUT/PATCH/DELETE/OPTIONS). 6 files `implements JsonDetails`.
- There is a 5-file gRPC `endpoint/client/host` outlier sub-pattern — an exception, not the norm.

**To add a new endpoint you add an enum constant to the right `*ApiDetails` enum** — you do not
create an endpoint class. Copy the canonical enum-constant body from the nearest sibling constant in
the same enum.

## Non-standard package naming

Top-level packages under `src/main/java` are **capitalized and non-reverse-domain**:
`Clients/`, `CommonUtils/`, `Controller/`, `Model/`, `Payment/`, `TestData/`, `TestRailUtils/`,
`VaultUtils/`, `Listeners/`. The productive layer is `Controller/<Product>/<Service>/`. Do not
"correct" this to `com.gojek.*` — match it.

## Test-method contract (mandatory)

`src/test/java` holds 893 files; **833 (93%) `extends TestBase`** (`CommonUtils/TestBase.java`).
2010 `@TestInfo` occurrences across 347 files; 7329 `@Test(` occurrences.

```java
@Test(timeOut = DEFAULT_TEST_TIMEOUT, dataProvider = "getTestConfig",
      description = "…", groups = {TestCategories.<GROUP>})
@TestInfo(projectId = PAYMENT_PROJECT, suiteId = CNP_DRAGON_SUITE,
          testCaseIds = {"5163751"}, owner = KEVIN_GICA_ERWANDHA)
public void someTest(TestConfig testConfig) {
```

Distinctive points:

- **All four `@TestInfo` values are referenced via `static import`** — bare identifiers like
  `PAYMENT_PROJECT`, `PAYMENT_CP_PROJECT`, and owner constants, not `Class.CONSTANT`. Match that
  style and add the static imports.
- `projectId` is `PAYMENT_PROJECT` (1853 sites) or `PAYMENT_CP_PROJECT` (157). The holder classes
  are `TestRailUtils/TestRailProjectAndSuitesIds.java` (projects + suites) and
  `TestRailUtils/TestRailOwnerEmails.java` (owners) — both consumed as bare static imports.
- **`timeOut = DEFAULT_TEST_TIMEOUT` is part of the standard `@Test` block here** — one of the very
  few modules that uses `timeOut` at all (iris and transport use it ~never).
- **`dataProvider = "getTestConfig"` is the module-wide provider.** Tests take a `TestConfig`
  parameter; you normally do not hand-write `Object[][]` rows.
- `groups`: **both styles coexist heavily** — `TestCategories.*` constants and **raw string
  literals** (`groups = {"..."}`, ~5,350 sites). Prefer the `TestCategories` constant, but match the
  sibling file rather than "correcting" a raw literal you find next to your test.

### Compile check

```
./gradlew :midtrans-core-api:compileTestJava
```
