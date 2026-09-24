# Scenario Economy, Priority, Titles & Categories

Feature-agnostic rules for **meaningful** suite size without dropping coverage.
The Hard Coverage Rules still require every checklist item to be *covered*; they do
**not** require one physical row per checklist item.

## 1. Combine when the flow is the same

**Combine into one scenario** when all of these hold:

- Same entry path / setup / navigation (same deeplink or same tap chain)
- Same actor / persona / country / flag set
- Only the **assertions** differ (different UI elements, copy, or fields on the same screen after the same actions)

How to combine:

- Keep a single `steps[]` for the shared flow
- Put every distinct check as its own numbered line in `expected_result`
- Set `requirement_ref` to **all** covered checklist ids (comma-separated), e.g.
  `BR-1:ac[0], BR-1:ac[1]` or `BR-1, BR-2`
- One `csv_title_association` naming the shared behaviour (not each element)

**Keep separate rows** when any of these differs:

- Different expected **outcome class** (success vs error vs empty vs denied)
- Different setup that changes the path (persona, flag off, permission denied, offline)
- A boundary/negative whose `proposed_default` / error copy is itself under test
- A true alternate happy path (different entry point that reaches a different route)

### Do not invent volume

Skip unless inputs force them:

- Positive “nav away and back / pull-to-refresh” persistence rows — only if PRD/RFC states persistence
- One row per UI copy string on the same screen after the same taps — fold into Expected Result
- FE-baseline extras the QA did not select
- Platform-variance rows when Android and iOS share the same UX path

## 2. Platform — column only, never the title

| Rule | Detail |
|---|---|
| Default | `platform: "Cross-Platform"` when the flow and expected UI are the same on Android and iOS |
| Split | Emit **one** Android row **and** one iOS row only when design/RFC documents a **different path or outcome** (different gestures, permissions, system UI, or screens) |
| Title | `csv_title_association` must **not** contain `Android`, `iOS`, `(Android)`, `(iOS)`, or `Android vs iOS` |
| Where platform lives | CSV **Platform** column (+ Android/iOS Automation Status v2). Never encode OS in the Title |

Forbidden: two near-identical cases titled `"… (Android)"` / `"… (iOS)"` with the same steps.

## 3. Priority rubric (`priority_tier`)

Assign from business risk, not from category fashion. Default is **P1** when unsure.

| Tier | Assign when |
|---|---|
| **P0** | Core happy path / E2E that proves the feature’s primary business outcome; money / safety / PII loss; kill-switch or flag-off that hides or breaks the feature; unblocker for release |
| **P1** | Important alternate valid paths; primary PRD boundaries with a defined `proposed_default`; permission-denied that blocks the feature; main error/empty states called out in PRD/RFC |
| **P2** | Secondary copy/polish; interruptions / lifecycle / N-1 **without** an RFC mandate that they are release-critical; FE-baseline hygiene; nice-to-have regional/theme variants |

Constraints:

- At least one **P0** when the plan has any `functional` / E2E happy path
- `source: fe_baseline` → **P2** unless the QA explicitly elevates it
- Do not mark every boundary P0; only those that can corrupt state, money, or access

## 4. Test-case categorisation (`test_case_type` → CSV **Type of Test Case**)

Stamp **exactly one** of these on every scenario (BrowserStack Type of Test Case):

| `test_case_type` | Use for `coverage_category` / intent |
|---|---|
| `Happy Path` | `functional` / `positive`, E2E business flows, alternate valid paths |
| `Negative` | `negative_error`, invalid input, API error UX, permission denied |
| `Boundary` | `boundary` (edges, limits, once-only, null/empty defined in PRD) |
| `Interruption` | `interruption_*`, lifecycle, offline, process death |
| `Permission` | `permission` grant/deny matrix when that is the subject under test |
| `Feature Flag` | `feature_flag_killswitch` |
| `Navigation` | `deep_link_nav` as the primary subject |
| `Accessibility` | `accessibility` / a11y baseline |
| `Localization` | `localization_regional` / l10n baseline |
| `Performance` | `non_functional_perf` |
| `Platform Variance` | `platform_variance` (only when paths truly differ) |
| `Sanity` | Thin smoke / FE-baseline hygiene |
| `Regression` | `is_legacy_regression: true` documented existing cases |

Do **not** put `[Happy Path]` / `[Boundary]` prefixes in the Title when `test_case_type` already carries the category. Title stays a clear behaviour name.

## 5. Preconditions (human-readable in CSV)

- JSON `test_data` / `preconditions_metadata` stay structured for downstream agents
- CSV **Preconditions** is produced by `scripts/plan_to_csv.py` as **numbered plain-language lines**
- Never paste raw JSON objects/arrays into a scenario field that is meant for testers
- Prefer short phrases: `Logged-in GoFood customer with an active cart`, not `[{"entity":"CUSTOMER",...}]`
