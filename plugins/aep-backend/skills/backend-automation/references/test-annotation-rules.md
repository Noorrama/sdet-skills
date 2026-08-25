# Mandatory test-method annotation contract

Evidence: full static scan of `gojek-backend-tests` (all `*.java`/`*.kt`, `build/` excluded) plus
`javap` on the `com.gojek:common-integrations` JAR. Counts are annotation-SITE counts unless the
column says FILES.

Read this **before writing any `@Test` method**. Everything here is compiler- or
listener-enforced — getting it wrong produces either a build failure or a test that silently
never runs.

---

## 1. `@TestInfo` — the contract, from the bytecode

`com.gojek.TestInfo` ships in the external `com.gojek:common-integrations` JAR. It is **not**
in-repo source, so you cannot read its definition from the tree. Decompiled:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)          // METHOD ONLY
public @interface TestInfo {
    String   projectId();            // no default -> MANDATORY
    String   suiteId();              // no default -> MANDATORY
    String[] testCaseIds();          // no default -> MANDATORY
    String   owner();                // no default -> MANDATORY
    String   countryName() default ""; // the ONLY optional attribute
}
```

Consequences you cannot argue with:

1. **All four of `projectId`, `suiteId`, `testCaseIds`, `owner` must be present.** They have no
   `AnnotationDefault`; omitting any one is a **compile error**. This is why a full-repo scan of
   29,363 usages found exactly **two** attribute-set combinations and zero structural deviation:

   | count | attribute set |
   |---|---|
   | 28,531 | `(owner, projectId, suiteId, testCaseIds)` |
   | 832 | `(countryName, owner, projectId, suiteId, testCaseIds)` |

2. **`@Target(METHOD)` — it is impossible to put `@TestInfo` on a class.** Do not try.
3. `testCaseIds` is `String[]`, so both `testCaseIds = {"123"}` (26,965 uses, preferred) and
   `testCaseIds = "123"` (2,011 uses) compile.
4. Attribute **order is free** and does vary by module (`transport` writes testCaseIds/owner
   first). Match the neighbouring file.
5. `RUNTIME` retention — it is read reflectively by the TestRail listeners in the `core` JAR
   (`testRail/GBTTestRailListener`, `testRail/UpdateTestRailTestCase`). A wrong id reports
   against the wrong TestRail case; it does not fail the build.

### Ordering convention

`@Test` first, then `@TestInfo`, then the method signature. Canonical
(`gopay/.../bnibanktopup/BniTopupTests.java:46-48`):

```java
@Test(groups = {Categories.REGRESSION_PAYMENTS_TRANSFER, Categories.TOPUP_SERVICE, Countries.ID})
@TestInfo(projectId = SuiteConstants.GOPAY_PROJECT_ID, suiteId = SuiteConstants.US_PAYMENTS_TRANSFER_PROJECT_ID,
          testCaseIds = {"4376145"}, owner = UserSpendOwnerEmail.DANIEL)
public void verifyCustomerShouldBeAbleToDoTopUpUsingBni() {
```

---

## 2. The 10 modules where `@TestInfo` must NOT be added

`@TestInfo` is mandatory **in the 32 modules that use it**, not repo-wide. These modules have
**zero** usages, and adding it would be wrong:

`core`, `data-generator`, `gojek-commons`, `helper`, `payment-core`, `data-platform`,
`vehicle-financing`, `fleet-portal-backend`, `agent-experience`, `goagent`

**`payment-core` is the one that matters** — it has a skill and 311 `@Test` methods across 48
test files, all TestNG, none annotated. Its `build.gradle` declares neither `gojek-commons` nor
`common-integrations`, so `com.gojek.TestInfo` **is not on its classpath**: adding the import is
a compile error, not a style deviation.

---

## 3. Per-module values — the table you actually need

`projectId`/`suiteId` holder classes are **per-module and not uniform**. There is no repo-wide
`SuiteConstants`; only 8 classes with that name exist, and `scp`'s is singular (`SuiteConstant`).
Pick the row for your module and use those exact constants.

| Module | FILES | `projectId` (dominant) | `suiteId` (dominant) | `owner` style |
|---|---|---|---|---|
| `gopay` | 1354 | `SuiteConstants.GOPAY_PROJECT_ID` | `SuiteConstants.US_*` / `CXSuiteConstants.*` | `UserSpendOwnerEmail.*`, `MoneyManagementOwnerEmail.*`, `PXOwnerEmails.*` |
| `marketplace` | 578 | `TestRailConfig.MARKETPLACE_PROJECT_ID` (1009) | `TestRailConfig.MATCHMAKING_SUITE_ID`, `SUPPLY_TRACKERS_SUITE_ID` | quoted email literal (1278) |
| `driver-platform` | 479 | `TestRailConfig.DRIVER_PLATFORM_PROJECT_ID` (1343) | `TestRailConfig.DRIVER_ONBOARDING_TEST_SUITE_ID`, `DRIVER_PAYOUT_TEST_SUITE_ID` | `TestRailConfig.OWNER_*` (1344) |
| `gofood` | 363 | `TestRailConfig.GO_FOOD_PROJECT_ID` (1541), `GOFOOD_MERCHANT_PROJECT_ID` (468) | `TestRailConfig.GOFOOD_GROWTH`, `OPEN_API`, `DISCOVERY`, `MERCHANT_EXCELLENCE_MODERATOR` | quoted email literal (2021) |
| `midtrans-core-api` | 348 | `PAYMENT_PROJECT` (1853, **static import**) | `CNP_DRAGON_SUITE` etc (static import) | `KEVIN_GICA_ERWANDHA` etc (static import) |
| `customer-platforms` | 322 | `TestRails.*` (2233) | `TestRails.*` | `Owner.*` (2233) |
| `transport` | 319 | **`""` empty literal (2221)** | **`""` empty literal (2220)** | `GojekEngineer.*_EMAIL` (2301) |
| `iris` | 181 | `IrisTestrailConstants.*` (1138) | `IrisTestrailConstants.*` | `IrisTestrailConstants.*` (owners live in the same class) |
| `icp` | 139 | `IcpTestRailConfig.*` (565) | `IcpTestRailConfig.*` | `IcpTestRailConfig.*` |
| `driver-incentives` | 126 | `TestRailConfig.*` (184) | `TestRailConfig.*` | quoted email literal (179) |
| `app-platform` | 105 | `CM_PLATFORM_PROJECT_ID` (409, static import), `TestRailConfig.*` (127) | mixed | `OWNER_RAVI_N`, `PromoTechConstants.*` |
| `merchant-platform` | 83 | `MERCHANT_PLATFORM_PROJECT_ID` (476), `SALESFORCE_PROJECT_ID` (11) | mixed | quoted email literal (487) |
| `gopaylater` | 77 | `"161"` raw literal (208) | raw literal | quoted email literal (209) |
| `midtrans-enterprise` | 73 | `SuiteConstants.*` (620) | `SuiteConstants.*` | `OwnerEmails.*` (620) |
| `go-sure` | 73 | `"163"` raw literal (961), `SuiteConstants.*` (267) | mixed | `GoSureEmailOwner.*` (720) |
| `go-logistics` | 67 | `SuiteConstants.{CEG,TMS,PEG,GTL_LPS}_PROJECT_ID` | `SuiteConstants.CEG_GOSEND_BACKEND_MAIN_SUITE_ID`, `TMS_BACKEND`, `PEG_BACKEND` | quoted literal (306), `GojekEngineer.*` (33) |
| `care-platform` | 58 | `""` empty (132), `CareTestManagementConstants.*` (9) | mixed | `TestOwner.*` (80), literal (61) |
| `gtl` | 43 | `SuiteConstants.*` (129) | `SuiteConstants.*` | quoted email literal (129) |
| `gojek-e2e` | 40 | `E2ETestRailConstants.*` (52) | `E2ETestRailConstants.*` | `E2ETestRailConstants.*` |
| `pricing` | 32 | `PricingTestRail.*` (43) | `PricingTestRail.*` | `PricingTestRail.*` |
| `ticket-arbitration` | 28 | `TestRailConstants.PROJECT_ID` (263) | `TestRailConstants.SUITE_ID` | `TestRailConstants.PROJECT_OWNER` |
| `helpcenter` | 27 | `HelpTestRailConfig.*` — **semantically swapped, see §5** | `HelpTestRailConfig.*` | `HelpTestRailConfig.*` |
| `crypto` | 19 | `CryptoSuiteConstants.*` (38) | `CryptoSuiteConstants.*` | `CryptoOwnerEmailConstant.*` (38) |
| `scp` | 18 | `SuiteConstant.SCP_PROJECT` (87) — **singular** | `SuiteConstant.SCP_BACKEND` (87) | quoted email literal (89) |
| `gomart` | 17 | `GOMART_PROJECT_ID` (347, static import) | static import | `OWNER_GOPAL_SHARMA` etc |
| `gomodal` | 8 | `"162"` raw literal (49) | raw literal | quoted email literal (49) |
| `courier` | 4 | `config.TestRailConfig.*` (25) | `TestRailConfig.*` | quoted email literal (28) |
| `clloanplatform` | 4 | `"165"` (12), `"165_1"` (1) — **non-numeric ids exist** | raw literal | quoted email literal (14) |
| `merchantlending` | 3 | `"165"` raw literal (25) | raw literal | quoted email literal (25) |
| `cartography` | 2 | `CartoTestRail.*` | `CartoTestRail.*` | `CartoTestRail.*` |
| `gopay-merchant` | 1 | `SuiteConstants.*` | `SuiteConstants.*` | quoted email literal |
| `ep-web-platform` | 1 | `TestRailConfig.*` (19) | `TestRailConfig.*` | `TestRailConfig.*` |

**How to use this table:** find your module's row, then open the named holder class and pick the
constant whose name matches your feature area. Do not invent a constant; if none fits, ask.
`gofood`/`marketplace`/`driver-platform` holder is `<module>/src/main/java/config/TestRailConfig.java`.

---

## 4. `testCaseIds` — never invent one

| form | count | note |
|---|---|---|
| `{"4376145"}` | 26,965 | preferred |
| `"3847098"` | 2,011 | single-element shorthand |
| `{""}` empty placeholder | 1,410 | **precedent for "I don't have one yet"** |
| `{"TC-704845"}` | 1,764 | `iris` convention |
| `{"C4852207"}` | 165 | TestRail "C" prefix |

If the user gave you no TestRail id, use `testCaseIds = {""}` — that is an established,
checked-in placeholder (650 in gopay, 197 midtrans-core-api, 138 marketplace) — and tell the user
it needs filling. **Never fabricate a plausible-looking numeric id**; it silently reports results
against a real, unrelated TestRail case.

---

## 5. Module-specific anomalies — follow them, do not "fix" them

1. **`transport` passes empty ids.** 2,221 usages of `projectId=""`/`suiteId=""`, with the real
   information carried only by `owner` + `testCaseIds`, attributes reordered:
   ```java
   @TestInfo(testCaseIds = "3081592", owner = GojekEngineer.DICKY_EDGARDO_EMAIL, projectId="", suiteId = "")
   ```
   Writing a populated `projectId` in transport is the deviation, not the norm.
2. **`gopay` puts `*_PROJECT_ID`-named constants in the `suiteId` slot** (thousands of usages,
   e.g. `suiteId = SuiteConstants.US_PAYMENTS_TRANSFER_PROJECT_ID`). The constant *names* lie; the
   *values* are TestRail suite ids. Copy the neighbouring package's usage verbatim.
3. **`helpcenter` has project/suite swapped at the source.** `HelpTestRailConfig.HelpCenterSuiteId`
   is really a project id, so tests read `projectId = ...ChatBotSuiteId, suiteId = ...ChatBotProjectId`.
4. **`countryName` has two incompatible conventions** in the 2.8% of sites that use it:
   `customer-platforms` uses the constant `TestCountry.ID`; `go-logistics` uses the bare string
   literal `"indonesia"`.

---

## 6. `@Test` groups — the silent-skip trap

In **`gopay`**, groups are not decorative. `gopay/src/main/java/com/gopay/backendtests/listeners/TestFilterListener.java:29`:

```java
if (groups.contains(tag) && groups.contains(System.getProperty("country"))) {
```

A gopay `@Test` must carry **both** a `Categories.*` value **and** a `Countries.*` value. Miss
either and the test silently never executes under `-Dtag=...  -Dcountry=...` — it does not fail,
it just does not run. Check whether your target module has an equivalent filtering listener
before assuming groups are optional.

## 6b. `@Test(groups = …)` is the second compiler-adjacent invariant

`groups` is present on **40,055 of 40,606** `@Test` annotations repo-wide. It is not decorative:
**every Gradle test task selects by group** via `includeGroups System.getProperty('tag','NONE')`, and
`run-configurations.json` labels the TAG variable `REQUIRED_TESTNG_GROUP_TAG`.

**A test whose group is not selected by the CI tag never runs — silently.** Always reference a
constant from the module's own group class, never a raw string:

| module | group constant class |
|---|---|
| `gofood` | `utils.GoFoodCategories` |
| `marketplace` | `constants.MarketplaceCategories` |
| `driver-platform` | `utils.<Service>TestCategories` (38 separate files) |
| `transport` | `utils.TransportCategories` (one global class) |
| `gopay` | `Categories` **+ `Countries`** (both required — see §6) |
| `payment-core` | `constants.Groups` |
| `scp` | `testutils.TestGroup` |
| `midtrans-core-api` | `TestCategories` |

Known dead groups — do not copy them from a sibling: `groups = ""` (12 sites) and
`SANDBOX_SANDBOX_SANDBOX_SANDBOX_SANDBOX_REGRESSION` (16 sites). `enabled = false` is set on 2,804
tests, so a "similar sibling test" you are copying may itself be parked.

**Live proof this fails silently:** several of `iris`'s newest test classes (Aug 2026) omit `groups`
entirely and therefore can never be selected by the runner — e.g.
`iris/src/test/java/serviceTest/bcaAutoCollectAdapter/AuthTest.java`. They compile, they pass review,
they never execute. Copying one as a template propagates a dead test.

Note `midtrans-core-api` uses **raw string literals** in `groups` at ~5,350 sites alongside
`TestCategories` constants — so "always a constant" is the goal, not a universal description. Match
the sibling.

## 6c. Test-class registration — two modules do not auto-discover

~35 of 41 modules auto-discover new test classes. Two do not, and in both a new **package** is
invisible until registered:

- **`marketplace`** — add the package to `src/test/resources/{indo,sg,viet}Testng.xml`.
- **`pricing`** — add it to `entrypoint/Entrypoint.java` via `JARUtils.getClassesInPackage("<pkg>")`.

Six modules also bypass Gradle entirely through a shadow-jar `entrypoint/Entrypoint.java` `main()`,
which registers a **different listener set** than `runTests` — so behaviour can differ between the
two entry points.

## 6d. Assertion conventions worth matching

- `org.testng.Assert` with **actual-first** argument order dominates: 4,735 files, ~108k calls.
- The canonical response check is
  `Assert.assertEquals(response.getHttpStatusCode(), 200, "message")` — 13,300 sites, roughly 17x
  more common than the `assertHttpStatusToBe(...)` helper on `BaseResponse`.
- `@DataProvider` returns **`Object[][]`** in ~97% of cases. `Stream` is never used.
- **Anti-pattern present in 173 files: `new SoftAssert()` with no `assertAll()` call.** Those
  assertions never report. If you use `SoftAssert`, you must call `assertAll()`, and do not treat a
  sibling that omits it as the convention.

## 7. `@Test` label attribute — inverted between sibling modules

Do not generalise this one; it flips even between two modules that otherwise look alike:

| module | `description=` | `testName=` | use |
|---|---|---|---|
| `gofood` | 592 | 52 | `description=` |
| `marketplace` | 292 | 1264 | `testName=` |

---

## 8. Pre-flight checklist

- [ ] Does the target module use `@TestInfo` at all? (§2 — if it's one of the 10, stop here.)
- [ ] All four mandatory attributes present, or it will not compile.
- [ ] `projectId`/`suiteId` constants taken from **this module's** holder class (§3).
- [ ] `owner` in this module's style — constant vs quoted literal (§3).
- [ ] `testCaseIds` real, or `{""}` with a note to the user. Never invented.
- [ ] `@Test(groups = …)` present, from this module's group constant class, never a raw string (§6b).
- [ ] `@Test` groups satisfy the module's filtering listener (§6 — gopay needs a country group too).
- [ ] If the module is `marketplace` or `pricing` and this is a NEW package, register it (§6c).
- [ ] `@Test` label attribute is the one this module uses (§7).
- [ ] If you used `SoftAssert`, you called `assertAll()` (§6d).
- [ ] `@Test` then `@TestInfo` then signature (transport and driver-platform vary — match siblings).

---

## 9. Maintaining this file

Every count here was measured from `gojek-backend-tests` source, not asserted. Two claims in the
previous version of these skills rotted undetected ("1,100+ test files" — really 142; the Kotlin
scaffold called "modern" — abandoned since 2021), so re-run these before trusting a number you are
about to act on.

**Load-bearing vs illustrative.** Exact counts are illustrative — 592 drifting to 650 changes
nothing. What is load-bearing is the *direction* of a dominance claim. If one of these flips, the
guidance built on it becomes actively wrong:

```bash
# per-module naming + @Test label dominance (§7)
for m in gofood marketplace gopay; do
  printf "%-12s Endpoint=%-5s EndPoint=%-5s desc=%-5s testName=%s\n" "$m" \
    "$(find $m/src/main -name '*Endpoint.java' | wc -l | tr -d ' ')" \
    "$(find $m/src/main -name '*EndPoint.java' | wc -l | tr -d ' ')" \
    "$(grep -rho 'description *=' $m/src/test --include='*.java' | wc -l | tr -d ' ')" \
    "$(grep -rho 'testName *=' $m/src/test --include='*.java' | wc -l | tr -d ' ')"
done
# expected today: gofood 328/173 desc-dominant | marketplace 108/173 testName-dominant | gopay 1030/279 desc-dominant
```

**The §3 table is incomplete by construction.** It covers the 32 modules that used `@TestInfo` when
measured; the repo has 41 and grows. A module with no row means "not yet measured", **not** "no
`@TestInfo` needed" — §2 lists the 10 genuine exclusions. Check for drift:

```bash
grep -rl '@TestInfo' --include='*.java' --include='*.kt' . \
  | sed 's|^\./||' | cut -d/ -f1 | sort -u | wc -l    # was 32
```

**Before calling any code path "modern", "legacy" or "in-progress", check recency** — that is the
mistake that produced the Kotlin-scaffold error. Compare the path against its live sibling:

```bash
git log -1 --format='%ad %s' --date=short -- <suspect-path>
git log -1 --format='%ad'    --date=short -- <live-sibling-path>
```

The full evidence trail behind these skills (11 modules, ~25k lines, 369 `file:line` citations) was
session-scratch and is **not** checked in — these scans regenerate the parts that matter.
