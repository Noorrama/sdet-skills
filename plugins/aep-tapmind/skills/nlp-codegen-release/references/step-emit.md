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

| Step text | Emit |
|---|---|
| `Tap 'Edit'` / `Tap on 'Update' button` | `runStep("Tap 'Edit'")` — quote if case quoted |
| `Scroll until "Payment Summary" is visible` | `runStep` as written or `scrollToText` if pioneer/bucket used it |
| `Wait until … is visible` | `runStep` or `assertStep` on terminal wait |

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
