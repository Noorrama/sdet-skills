# CSV step → TapMind emit (release)

Read with `direct-api-map.md`. UI steps become `runStep` / `assertStep` unless
rung 1 applies.

## Setup (never from steps[])

| Source | Emit once per `@Test` before step 1 |
|---|---|
| `Location:` in preconditions | `TapMind.setMockLocation(lat, lng)` |
| `Test Data:` / `User:` / `TDP:` | `TapMind.performBackdoorLogin("<verbatim prompt>")` |
| Harvested bucket stem | Post-login guards (`if visible` transients) in same order as sample tests |

Never `runStep("Mock location to latitude…")` or `runStep("Do a backdoor login")`.

## Open / deeplink (steps only)

| Step text | Emit |
|---|---|
| `Open gojek://…` / `Open deeplink "…"` | `TapMind.openDeeplink("<uri>")` |
| `Navigate to …` with no URI | `runStep` walk; prefer deeplink if case includes `Open` on that row |

## Tap / scroll / wait

Use **`scroll`**, not `swipe`, to reveal off-screen content (`nlp-codegen`
`sibling-emit.md`, `step-validation/references/direct-api-map.md`).

| Step text | Emit |
|---|---|
| `Tap 'Edit'` / `Tap on 'Update' button` | `runStep("Tap 'Edit'")` — quote if case quoted |
| `Wait until … is visible` | `runStep` or `assertStep` on terminal wait |

### Scroll (direct API — do not `runStep` generic scroll)

Parse the **target label** from the step (strip direction words and trailing
`is visible` / `are visible`). Match **bucket** tests for casing when the same
screen exists (e.g. booking → `"Saved Address"` / `"Saved Addresses"`).

| Author wrote (examples) | Emit |
|---|---|
| `Scroll down to saved Address` | `TapMind.scrollToText(Direction.DOWN, "Saved addresses", MatchType.CONTAINS);` when profile uses that label (Android + iOS) |
| `Scroll down until saved address is visible` | same — `scrollToText` stops when matching text is on screen |
| `Scroll until "Payment Summary" is visible` | `TapMind.scrollToText(Direction.DOWN, "Payment Summary");` |
| `Scroll up to …` / `Scroll left` / `Scroll right` | `scrollToText` with `Direction.UP` / `LEFT` / `RIGHT` |
| `Scroll down` (no target text) | `TapMind.scroll(Direction.DOWN);` — optional `ScrollSpeed` if bucket uses it |
| `Scroll to top` / `Scroll to bottom` | `TapMind.scrollToTop();` / `TapMind.scrollToBottom();` |
| Label casing may differ on device | `MatchType.CONTAINS` with the on-screen substring (e.g. `"Saved addresses"`) |
| Same step, different platform copy | Platform `if` only when bucket tests prove different strings; otherwise one `scrollToText` for both |
| Exact label match required | `TapMind.scrollToText(Direction.DOWN, "…", MatchType.EQUALS);` |

Imports (mirror the bucket class):

```java
import static io.gojek.tapmind.client.TapMind.scrollToText;
import static io.gojek.tapmind.client.model.constants.Direction.DOWN;
import static io.gojek.tapmind.client.model.constants.MatchType.CONTAINS;
```

`ScrollRequest` defaults `scrollToTextMatchType` to **CONTAINS** when omitted; still pass
`MatchType.CONTAINS` explicitly in release tests so casing/substring intent is clear.

If the expected result is only “X is visible” and the step is a scroll-to-X row,
**do not** duplicate with `assertStep` unless the case has a separate **Verify**
step.

**Never** emit `runStep("Scroll down to …")` when a target string is present —
use `scrollToText`. Reserve `runStep` for scroll wording the device agent must
interpret with no stable text target (rare).

## Update / Edit / Input / Type / Enter

Authors use **Update**, **Edit** (field), **Input**, **Type**, **Enter** for
text fields. **Do not** emit one vague `runStep("Update the address details…")`
when the step includes a concrete value.

Parse patterns:

| Author wrote | Emit (prefer split when bucket tests type into fields) |
|---|---|
| `Update the <Field> to <value>` | `runStep("Type <value> in the <Field> field")` or tap field → clear if bucket clears → type |
| `Update <field> to <value>` (no “the”) | same |
| `Enter <value> in <field>` | `runStep("Type <value> in the <field> field")` |
| `Edit …` as **button** | `Tap 'Edit'` (quoted per case) |
| Field name missing (“Update address details to X”) | `runStep("Type X in the address field")` + `// verify field label once` |

Values (`HomeTest1`, `blok m pasarayaTest2`) are **literal** in `runStep` text.

## Verify / Assert

| Step text | Emit |
|---|---|
| `Verify …` / `Assert:` | `assertStep("Verify …", "<short failure message>")` — include **quoted** strings from the case expected column when present |

## Limit lines

If preconditions contain `Not for TapMind:`, do not emit automation for that
setup. If the whole case is limit-only, SKIP or emit comments only.
