# Plan step → TapMind emit (agentic)

Apply when translating **`scenario_list[].automation_steps[]`** (or enriched-plan
`automation_scenarios[].automation_steps[]`) into Java lines. Read with
`step-validation/references/direct-api-map.md` and
[sibling-emit.md](sibling-emit.md).

UI actions become `runStep` / `assertStep` unless a direct API rung applies.

## Setup (never as generic runStep login/location)

| Source | Emit once per `@Test` before feature steps |
|---|---|
| `test_buddy_prompt` on fixture (enriched plan) | `TapMind.performBackdoorLogin("<verbatim>")` or module helper if `$SAMPLE_TEST` uses one |
| `preconditions_metadata` mock location / plan step `mock_location` | `TapMind.setMockLocation(lat, lng)` |
| `change_context` screen deeplink for entry | `TapMind.openDeeplink(...)` when plan uses deeplink Given |
| Harvested module / subdirectory stem | Post-login guards (`if visible`) in same order as sample tests |

Never `runStep("Do a backdoor login")` or `runStep("Mock location to latitude…")`.

## Open / deeplink

| Plan line | Emit |
|---|---|
| `openDeeplink("…")` in automation_steps | Verbatim direct API per plan |
| Plain English “Open gojek://…” | `TapMind.openDeeplink("<uri>")` |
| Vague navigate with no URI | Prefer deeplink from `change_context.screens[]`; else `runStep` walk from nav_index / module tests |

## Tap / scroll / wait

Use **`scroll`**, not `swipe`, to reveal off-screen content.

| automation_steps line (examples) | Emit |
|---|---|
| `Tap 'Edit'` / tap with quotes | `runStep("Tap 'Edit'")` — quote when plan or pioneer quoted |
| `Wait until … is visible` | `runStep` or terminal `assertStep` |

### Scroll (direct API — do not vague runStep scroll)

When the plan line names a **target label** (scroll down/until/to …):

| Plan wrote | Emit |
|---|---|
| Scroll until `"Payment Summary"` visible | `TapMind.scrollToText(Direction.DOWN, "Payment Summary", MatchType.CONTAINS);` |
| Scroll down with no target text | `TapMind.scroll(Direction.DOWN);` |
| Scroll to top / bottom | `TapMind.scrollToTop();` / `TapMind.scrollToBottom();` |

**Never** `runStep("Scroll down to …")` when a stable target string exists — use
`scrollToText`. Mirror imports from `$SAMPLE_TEST` or bucket/module tests.

If verify is only “X visible” on the same scroll row, do not duplicate `assertStep`
unless the plan has a separate verify line.

## Update / Edit / Input / Type

Do not emit one vague line when the plan names a field and value.

| Plan pattern | Emit |
|---|---|
| `Update the <Field> to <value>` | Split: tap field if needed → `runStep("Type <value> in the <Field> field")` when module tests type that way |
| `Edit` as button | `Tap 'Edit'` (quoted per plan/pioneer) |
| Missing field label | Type value + `// verify field label once` |

## Verify lines

Plan verify / `assertStep` lines → `assertStep("…", "<failure message>")` with
quoted strings when pioneer or module tests quoted them.
