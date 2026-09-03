# Pioneer template (PAM catalogue)

This method is what step-validation (or a prior agent run) produced for one
PAM 8 Levels case. The two `if visible` lines are **not** in
`enriched_automation_plan.json` — they fired as transients after login. Clone
them onto every sibling in the cluster.

```java
@Test(description = "PAM 8 Levels catalogue presents monthly, yearly and special recognition (8 levels), not only monthly performance", groups = {"driverTest"})
@TestInfo(countryName = "INDONESIA", projectId = "MARKETPLACE_DRIVER_PLATFORM", suiteId = "DRIVER_APP_FRONTEND", testCaseIds = {"C5542965"}, owner = "ashish.sharma@gojek.com")
public void testPAM8LevelsCatalogueContent() {
    try {
        TapMind.setMockLocation(-5.141923, 119.432362);
        TapMind.performBackdoorLogin("Give me an active registered Gojek driver in Indonesia with a 2-wheeler vehicle type");
        TapMind.updateAppPermission(PermissionAction.GRANT, List.of("android.permission.ACCESS_FINE_LOCATION", "android.permission.ACTIVITY_RECOGNITION", "android.permission.POST_NOTIFICATIONS"));
        runStep("Tap 'Allow' on the phone call permission dialog if visible");
        runStep("Tap 'Lewati' on the walkthrough if visible");
        TapMind.openDeeplink("gojekdriver://loyalty/catalogue");
        TapMind.scroll(Direction.RIGHT);
        TapMind.scroll(Direction.RIGHT);
        assertStep("Verify text contain 'Bulanan' and 'Tahunan' and 'Penghargaan spesial' and 'Penghormatan tertinggi' is visible", "Test Case failed");
    } catch (Exception e) {
        Assert.fail(e.getMessage());
    }
}
```

When emitting into `driverApp`, wrap the **same lines** in `$SAMPLE_TEST` shape:
`extends BaseTest`, `groups = {"driverTest"}`, `@TestInfo` constants from
`DriverProjectConfig` (`INDONESIA`, `MARKETPLACE_DRIVER_PLATFORM`,
`DRIVER_APP_FRONTEND`) — not the stringly-typed copies above. Keep the TDP
prompt as a prompt; do not switch to `DriverLogin.loginToDriver(CONSTANT)`
unless that constant is this scenario's fixture.

## What to copy vs replace for a sibling

Shared (copy):

```java
TapMind.setMockLocation(...);
TapMind.performBackdoorLogin("<this sibling's test_buddy_prompt>");
TapMind.updateAppPermission(...);
runStep("Tap 'Allow' on the phone call permission dialog if visible");
runStep("Tap 'Lewati' on the walkthrough if visible");
```

Delta examples:

| Sibling | After the guards |
|---|---|
| Catalogue content (pioneer) | `openDeeplink("gojekdriver://loyalty/catalogue")` + scrolls + its asserts |
| Profile-banner entry (SC-001) | `runStep("Tap the profile icon");` then unquoted tap on the PAM banner; **no** catalogue deeplink unless the scenario is the deeplink case |
| Same screen, different assert | Same navigation as pioneer; replace only `assertStep` |
