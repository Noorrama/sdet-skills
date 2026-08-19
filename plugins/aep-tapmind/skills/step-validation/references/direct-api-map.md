# Direct TapMind API map

Which steps must **not** become `runStep(...)`.

`runStep("...")` sends the sentence to the TapMind server, which spends an LLM turn resolving it
against the view hierarchy. For anything that doesn't touch the UI — mocking a location, a
backdoor login, a deeplink, killing the app — that turn buys nothing and can drift. The client
exposes a direct call for all of it.

**Emit ladder, per step. Stop at the first rung that holds:**

| Rung | Emit |
|---|---|
| 1 | a **direct API call** from the table below |
| 2 | `assertStep("Verify …", "<failure message>")` — a check |
| 3 | `runStep("…")` — genuine UI interaction |

The repo is inconsistent here and rung 1 is often missed: `FCTGoFoodBooking` opens with
`runStep("Mock location to latitude: -6.2438469 and longitude: 106.8005818")` when
`TapMind.setMockLocation(-6.2438469, 106.8005818)` exists. Don't copy that habit — it burns a
server LLM turn on a pure device command.

## When in doubt, emit the base API

Some modules wrap these in helpers — `DriverMockLocation.mockLocation(BLOK_M)` in `driverApp`,
`returnDeeplinkByPlatform(...)` in `gofood`. **Every one of those wrappers calls the same client
method underneath.** `DriverMockLocation` is a switch over `LocationConstants` that ends in
`TapMind.setMockLocation(latitude, longitude)`.

So: use a module helper only when `module-profile.sh`'s `$SAMPLE_TEST` shows that module actually
using it and the named constant exists. **Otherwise emit the base call with literal values** —

```java
TapMind.setMockLocation(-6.200000, 106.816666);
```

A base call with real coordinates compiles and runs in every module. A guessed
`SomeModule.mockLocation(PLACE_NAME)` compiles nowhere if either the helper or the constant is
imaginary. Never invent a helper name or a constant name to look idiomatic.

## The map

Signatures from `javap` on `tapmind-client-1.2.5`; usage examples are real lines from the repo.

| Step intent | Emit |
|---|---|
| mock location | `TapMind.setMockLocation(-6.200000, 106.816666);` |
| driver login | `TapMind.performBackdoorLogin("get bike driver from TDP");` |
| customer login | `TapMind.performBackdoorLogin("get a new customer from TDP");` |
| login with known tokens | `TapMind.performBackdoorLogin(bearerToken, refreshToken);` |
| login, profile default | `TapMind.performBackdoorLogin();` |
| TDP data / state setup | `TapMind.getDataFromTDP("Update order status to driver arrived");` |
| deeplink | `TapMind.openDeeplink("gojek://gofood");` |
| launch / kill / restart | `TapMind.launchApp();` · `killApp();` · `restartApp();` |
| background N seconds | `TapMind.backgroundApp(5);` |
| permission | `TapMind.updateAppPermission(PermissionAction.GRANT, List.of("android.permission.ACCESS_FINE_LOCATION"));` |
| hide keyboard | `TapMind.hideKeyboard();` · `hideKeyboardByButton("Done");` |
| keyboard visible? | `TapMind.isKeyboardVisible()` |
| physical button | `TapMind.pressPhysicalButton(DeviceButton.BACK);` |
| scroll to either end | `TapMind.scrollToTop();` · `scrollToBottom();` |
| scroll a fixed amount | `TapMind.scroll(Direction.DOWN);` |
| scroll until text | `TapMind.scrollToText(Direction.DOWN, "GoRide");` |
| scroll until exact text | `TapMind.scrollToText(Direction.DOWN, "GoRide", MatchType.EXACT);` |
| network condition | `TapMind.controlNetwork(NetworkCondition.OFFLINE);` |
| GPS state | `TapMind.changeGPSState(GPSState.OFF);` |
| notification drawer | `TapMind.openNotificationDrawer();` · `getAllNotifications()` |
| webview / native context | `TapMind.switchToInAppWebviewContext();` · `switchToNativeAppContext();` |
| platform at runtime | `TapMind.getPlatformName()` |
| store / read a value | `TapMind.storeVariable(k, v);` · `retrieveVariable(k)` |
| camera image injection | `TapMind.injectCameraImage(url);` |
| **anything touching UI** | `runStep(...)` / `assertStep(...)` |

Imports live under `io.gojek.tapmind.client.model.constants.*` (`Direction`, `MatchType`,
`ScrollSpeed`, `DeviceButton`, `NetworkCondition`, `GPSState`, `PermissionAction`). Copy the exact
import block from `$SAMPLE_TEST` rather than reconstructing it.

## Two traps

**1. `performBackdoorLogin(String)` and `getDataFromTDP(String)` take an NLP prompt, not an id.**
The single-argument overload is a sentence handed to TDP:

```java
TapMind.performBackdoorLogin("get bike driver from TDP");                        // DriverLoginTest:73
TapMind.performBackdoorLogin("Get a transport bike booking with driver assigned from TDP");
TapMind.getDataFromTDP("Update order status to driver arrived");                 // PushNotificationTests:43
```

Only the **two**-argument overload is credentials — `(bearerToken, refreshToken)`, and those come
from config at runtime. **Never emit a literal token, phone number, or account id.** If the run
used a specific account, emit the TDP prompt that fetched it, not the value it returned.

**2. `verifyTransientText` is not a transient-screen guard.** It is backed by
`appium_start_android_page_dump` — a poller for text that appears *and vanishes* before a normal
dump can catch it (toasts, snackbars), and it is Android page-dump based. It is the wrong tool for
a walkthrough, coachmark, permission dialog, or promo interstitial. Those get an `if visible`
guard on a normal `runStep` — see SKILL.md §6d.

## Regenerating this map

It is pinned to a client version and will drift when `tapmindClientVersion` in the repo's
`build.gradle` moves. To re-derive:

```bash
javap -cp "$(find ~/.gradle/caches -name 'tapmind-client-*.jar' | sort -V | tail -1)" \
  io.gojek.tapmind.client.TapMind
```
