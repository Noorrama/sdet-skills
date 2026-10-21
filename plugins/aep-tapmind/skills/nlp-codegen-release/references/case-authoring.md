# BrowserStack case authoring (release / kb-only)

Same TMS columns. Authors do **not** write backdoor login or mock location in
**Steps** — the skill emits TapMind **direct APIs** from **Preconditions** and
harvested bucket Java.

## Preconditions cell

Use labeled lines (any order):

| Label | Required? | Skill emit |
|---|---|---|
| `Test Data:` | **Yes** for logged-in flows | `TapMind.performBackdoorLogin("<rest of line verbatim>")` — strip only the `Test Data:` prefix. Also accept `User:` or `TDP:` as aliases; same rule. |
| `Location:` | When wrong geo breaks the case | `TapMind.setMockLocation(lat, lng)` — parse `Jakarta (-6.255319, 106.810750)` or two numbers; else harvest bucket/module default. |
| `Not for TapMind:` | When manual-only setup remains | Skill does **not** emit steps for these lines (CMS, curl, Litmus, API mocks, query-param checks). |

Do **not** ask authors to write “Do a backdoor login” in steps. Do **not** call
`test-data-identification` (agentic path).

**Deeplinks:** authors put `Open gojek://…` or `Open deeplink "…"` as a **Step**
row only — not under Preconditions. Emit `TapMind.openDeeplink(...)` per
`step-validation/references/direct-api-map.md`.

## Steps template

- One action per row (Steps template, not Text).
- Quote exact on-screen control text when known (`Tap 'Edit'`).
- `Scroll until "…" is visible` when the control is below the fold.
- Last row should be an **Assert** / **Verify** with visible copy, not screenshot-only.

## Auto-readiness (skill decides kb-only vs pioneer)

After ingest, score each case **without** asking the author for A/B/C:

| Signal | Points |
|---|---|
| `Test Data:` / `User:` / `TDP:` present | +2 |
| `Location:` or bucket has default mock | +1 |
| ≥5 step rows, one verb each | +2 |
| Any step has `Scroll until` / `Open gojek` | +2 |
| Quoted tap targets or `Update … to <value>` with field name | +2 |
| `Not for TapMind:` only blocks non-UI setup | neutral |
| Compound step (“open app and navigate…”) | −2 |
| No test-data line and empty preconditions | −2 |
| Preconditions are curl/mock/Litmus-only with no UI path | mark **limit** — UI slice only |

**kb-only** when every case in the run scores ≥6 and bucket harvest has a login
stem. **device-pioneer** when any bucket scores low or harvest lacks the folder
stem. Echo scores in the pre-emit summary.

## Example (GoFood Saved Address)

```text
Preconditions
Test Data: Get me a customer with a saved address
Location: Jakarta (-6.255319, 106.810750)

Steps
1. Wait until Gojek home is visible
2. Tap on User Profile Image on Gojek Homepage
…
6. Update the Address name to HomeTest1
7. Tap on Personal Address Type label
8. Tap on the 'Update' button to save
9. Verify HomeTest1 is visible on Saved Address with label Personal Address Type
```
