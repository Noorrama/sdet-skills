# Focus areas — conditions you inject, not elements you find

§3a.9 probes what is **on the screen**: tabs, banners, filter chips, "See all". That is breadth
across the UI surface, and it is not the same thing as this file.

A **focus area** is a condition that is not on the screen at all and never will be — backgrounding
the app mid-checkout, denying location at the exact moment it is asked for, opening a deep link
while a booking is in flight, double-tapping Order. Scripted regression structurally cannot cover
these, because nobody writes a test case for "and then a call came in." They are where the bugs
that reach production actually live.

A charter names **exactly one** focus area (see `charter-exploration/references/charter-grammar.md`).
This file is what that name resolves to at run time.

## The three fields that make one runnable

Each entry below has the same shape, and all three parts are load-bearing:

- **Fires at** — which screens. Focus areas cost steps; spending them on the splash screen finds
  nothing. Almost all of them fire only at **state-bearing screens**: a screen holding user state
  that would be expensive or annoying to lose (a filled cart, a selected address, a chosen payment
  method, an in-flight booking, a half-completed form). If the current screen holds no such state,
  skip the focus area and move on — that is not a skipped step, it is the applicability rule
  working.
- **How** — the exact call, per `capabilities` (§1). Where the capability is `none`, the focus
  area **cannot run on this target**; say so in `run.coverageGaps` rather than substituting
  something adjacent and reporting it as covered.
- **Oracle** — what must be true afterwards. Without this, a run injects the condition, observes
  *something*, and has no basis on which to call it a bug. The oracle is what turns "I backgrounded
  the app and it came back" into a pass or a finding. **A focus area with no oracle is not a test.**

Record every injection as an edge with `phase: "focus"` and `focusArea: "<id>"`, so the report can
show focus-area coverage as its own axis rather than burying it in the goal path.

## Availability at a glance

Availability is set by the **MCP tool**, not by the run mode, except where a row says otherwise.
Several TapMind tools are Android-only — that is a property of the tool, so it holds on
BrowserStack Android too, and fails on iOS everywhere.

| id | Android local | Android BrowserStack | iOS sim | iOS device | iOS BrowserStack |
|---|---|---|---|---|---|
| `lifecycle-background` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `lifecycle-kill` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `deeplink-midflow` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `rapid-input` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nav-back` | ✅ `BACK` | ✅ `BACK` | ⚠ gesture | ⚠ gesture | ⚠ gesture |
| `permission-denial` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `network-loss` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `orientation` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `locale-switch` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `interrupt-call` | emulator only | ❌ | ❌ | ❌ | ❌ |
| `token-expiry` | ⚠ unverified | ⚠ | ⚠ | ⚠ | ⚠ |

**Build charters from the top four first.** They run on every target, need no extra tooling, and
between them cover most of what the PRD's §9 was actually asking for.

`appium_update_app_permission` is documented "Supported only on Android" — so `permission-denial`
is an Android-only focus area, including on BrowserStack. Don't write it into an iOS charter.

**All TapMind tools below take `reasoning` (not `reason`)** — a mandatory step-by-step
justification string. Signatures here were read off the live tool schemas; don't paraphrase them
from memory.

---

## `lifecycle-background` — backgrounding and resuming mid-flow

**Fires at** state-bearing screens. Highest value mid-cart, mid-checkout, mid-payment, and while
an order is in flight.

**How** `appium_background_app(conversationId, durationInSeconds, reasoning)` — 5s for a quick
round trip, and once at ~30s on the single most state-heavy screen of the run (a short background
is often served from memory; a longer one is more likely to hit real restoration code).

**Oracle** — on resume, all of:
- the same screen is showing, at the same scroll position and step of a multi-step flow
- cart contents, quantities, item notes and variants are unchanged
- selected address and selected payment method are unchanged
- no re-authentication prompt, and no return to home or login
- no duplicate submission of anything already submitted

Any of those failing is a finding. A re-auth prompt after a 5-second background is a high-severity
one — it is the single most common real defect this focus area finds.

## `lifecycle-kill` — force-kill and relaunch

**Fires at** state-bearing screens, and immediately **after** a submit/confirm action (that is
where "did the order actually go through" gets interesting).

**How** `appium_kill_app(conversationId, …)` then `appium_launch_app(conversationId, …)`. Do not
use `appium_restart_app` here — it conflates the two halves, and the interesting part is what the
app reconstructs on a cold start.

**Oracle** — the app relaunches without crashing, **and** the post-kill state is *correct*, which
is not the same as *preserved*:
- an order that was confirmed before the kill still exists, exactly once
- an order that was *not* yet confirmed has not been silently created
- a cart is either restored or cleanly empty — never partially restored (three of five items back,
  wrong quantities, a stale total)
- no crash-on-restore, and no infinite splash

"Partially restored" is the failure mode worth hunting: it looks like it worked.

## `permission-denial` — deny at the moment of asking, then retry

**Android only.** `appium_update_app_permission` is documented "Supported only on Android"; there
is no iOS equivalent through TapMind. On an iOS target this is a coverage gap, not a substitution.

**Fires at** the first screen that requests a permission — location on the address picker, camera
on QR scan, notification on first launch, storage on upload.

**How** `appium_update_app_permission(conversationId, appId, permissions[], action, target,
reasoning)` with `action` revoking, before navigating to the screen that needs it. `appId` is
`device-info.json`'s `appPackage`; `permissions` is an array of Android permission strings
(`android.permission.ACCESS_FINE_LOCATION`, `android.permission.CAMERA`, …). Then attempt the
flow, then grant it and retry the same flow in the same session.

**Oracle**
- the app explains what it needs and why — not a bare system toast, and never a dead screen
- there is a way forward without the permission, or an explicit statement that there isn't
- **granting it afterwards recovers without an app restart** — this is the part that most often
  breaks, and the part scripted cases almost never cover
- no crash, and no silent no-op where a button simply stops responding

## `nav-back` — back button and back gesture at every transition

**Fires at** every screen of a multi-step flow, and with particular attention mid-payment.

**How** Android: `appium_press_physical_device_button(conversationId, buttonName="BACK",
reasoning)` — `buttonName` is an enum and `BACK` is in the Android-only half of it. iOS has no
back button: use a left-to-right edge swipe
(`appium_ios_drag_gesture_from_element_to_direction`), which exercises the gesture but **not**
the hardware-button path — note that difference rather than reporting the two as equivalent.

**Oracle**
- back goes exactly one step up the flow — not to home, not out of the app, not two steps
- **mid-payment, back must not leave a charge in flight or a half-created order.** Whatever it
  does, going forward again must not double it
- state entered on the abandoned screen is either kept or cleanly discarded, and the user can tell
  which
- back from the first screen of a flow exits the flow, not the app (unless the app is at root)

## `deeplink-midflow` — enter by deep link while something else is in progress

**Fires at** any state-bearing screen. This is the focus area most likely to find a real defect,
because the back stack is rarely designed for it.

**How** `appium_open_deeplink(conversationId, deeplink, reasoning)`. **The URI must come from the
charter's `probes`** — `source-cases.json` carries real ones. Never invent a plausible-looking
deep link: an invented URI fails silently and the failure looks like a bug in the app.

**Oracle**
- the deep link lands on the right screen, from a warm start as well as a cold one
- the interrupted flow is either preserved underneath or cleanly abandoned — not both, and not a
  duplicate of itself
- **back from the deep-linked screen goes somewhere sensible** — the most common defect here is a
  back stack that drops the user out of the app entirely, or into a screen they never visited
- no duplicate of the in-flight entity (two carts, two draft bookings)

## `rapid-input` — double taps and rapid successive taps

**Fires at** every submit, confirm, order, and pay control. Also on any control that triggers a
network call.

**How** `appium_double_tap_element(conversationId, rawElementId, reasoning)`, or
`appium_multi_tap_element(conversationId, rawElementId, numberOfTaps, numberOfFingers,
reasoning)` for more than two. `rawElementId` is the hierarchy id from the *current*
`get_view_hierarchy` — ids regenerate on every dump and cannot be reused from an earlier one. Do
this on the real submit control, not a proxy: the whole question is what the *submit* does.

**Oracle**
- **exactly one** of whatever the button creates: one order, one payment, one voucher redemption,
  one support ticket
- the control disables or shows progress after the first tap
- no duplicated toast, no stacked navigation (the same screen pushed twice)

Verify the "exactly one" against a back-end-visible surface — order history, TDP — not just
against what the screen says. A UI that shows one order while the back end has two is precisely
the bug worth catching.

## `network-loss` — go offline mid-transaction

**Fires at** the moment between submitting and confirming — the riskiest window in any flow.

**How** `capabilities.networkToggle == "adb"` only:
`adb shell svc wifi disable && adb shell svc data disable`, act, then re-enable both.
Where the capability is `none` this focus area **cannot run** — record it as a coverage gap. (On
BrowserStack, a session-level `networkProfile` is set at session start and cannot be toggled
mid-run, so it does not satisfy this.)

**Oracle**
- a clear offline message — not an infinite spinner, and not a generic "something went wrong"
- **on reconnect the transaction resolves to exactly one outcome**: it completed, or it didn't.
  Never both, never an order stuck in a limbo state
- retry is offered and actually works
- no crash on the transition in either direction

## `orientation` — rotate mid-flow

**Fires at** form screens, map/address pickers, and payment screens.

**How** `capabilities.rotation == "adb"` only:
`adb shell settings put system accelerometer_rotation 0` then
`adb shell settings put system user_rotation 1` (landscape) / `0` (portrait).
No MCP tool exists for this, and there is no iOS or BrowserStack equivalent here — record a
coverage gap on those targets.

**Oracle** — entered form data survives the rotation, no layout truncation or overlap in the new
orientation, no re-fetch that discards state, no crash.

## `locale-switch` — change language or locale mid-session

**Fires at** any screen for a multi-market app (ID/VN/SG/TH), ideally with a filled cart.

**How** `capabilities.locale == "adb"` only, via device settings. Note this typically restarts the
app, so run it as a deliberate before/after comparison rather than expecting live state to
survive.

**Oracle** — no raw resource keys leaking into visible text (`gofood_cart_title`), no untranslated
strings on a translated screen, no layout break from longer translations, prices and dates in the
right format for the locale.

## `interrupt-call` — an incoming call mid-flow

**Fires at** payment and confirmation screens.

**How** `capabilities.phoneCall == "adb-emu"` (Android emulator only):
`adb emu gsm call +6281234567890`, then `adb emu gsm cancel +6281234567890`.
No lever on physical devices, iOS, or BrowserStack — coverage gap there.

**Oracle** — same as `lifecycle-background`, plus: the flow does not double-submit when the call
ends, and audio/permission state doesn't leave the app wedged.

## `token-expiry` — auth token expires mid-flow ⚠ unverified

**Fires at** a multi-step checkout or booking, between steps.

**How** ⚠ **No confirmed lever.** In principle: force an expired/invalid token via
`appium_backdoor_login` with a stale credential, or ask TDP for a short-lived token. Neither has
been verified against TDP's actual catalogue.

**Oracle** — a silent refresh with the flow continuing, or a clear re-auth that **returns the user
to where they were** with state intact. Being dropped to home with a lost cart is a finding.

**Until the lever is confirmed, do not write charters against this focus area.** A charter that
cannot actually induce its own condition will run, find nothing, and report as covered — the worst
possible outcome. Confirm with TDP first, then mark this entry verified.

---

## Deliberately out of scope

- **Resource constraints** (low storage, low RAM, low battery). No reliable lever through TapMind
  or adb that doesn't destabilise the device itself. The PRD asks for it; we are not pretending to
  cover it.
- **Concurrent cross-app actions** (Driver cancels while Consumer is mid-checkout). Blocked by
  architecture, not effort: one TapMind server pins one Appium session, so a single run cannot
  drive two apps. This is the PRD's §7.4 and it needs multi-server orchestration that does not
  exist yet. Say this plainly when asked rather than approximating it with sequential single-app
  runs, which prove nothing about concurrency.
