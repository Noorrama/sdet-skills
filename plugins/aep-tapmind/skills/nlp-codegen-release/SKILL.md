---
name: nlp-codegen-release
description: >-
  Generate TapMind NLP @Test methods into tapmind-mobile-tests from assigned
  BrowserStack cases (CSV export or case ids via BrowserStack MCP). One PDG
  per run (GoFood or Cartography, not both). One class per bucket directory
  (groupOrder vs discovery). Adds groups Agentic_nlp_tests so the MR pipeline
  can run only the new methods. Asks kb-only vs reuse-pioneer (only if the
  stem is not already in the tapmind-mobile-tests checkout) vs one device
  pioneer per bucket. Use when asked to automate BrowserStack / TMS cases,
  nlp-codegen-release, release NLP, or a GoFood/Cartography CSV. Not for
  agentic enriched plans (that's nlp-codegen) and not for diagnosing one
  broken step list (that's step-validation).
---

# NLP test codegen — release (BrowserStack cases)

Human guide: [README.md](README.md). Do **not** edit `nlp-codegen` (agentic
plan path). This skill is the sibling.

Plugin root:

```
ROOT="$(bash "${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-${TAPMIND_PLUGIN_ROOT:?}}}/scripts/plugin-root.sh")"
```

Turn assigned BrowserStack cases into Java in `tapmind-mobile-tests` and an
MR. **Orchestrates; does not re-implement the device loop.**

Constraint: **one PDG per run.** GoFood cases or Cartography cases — not a
mixed list. Inside that PDG, cases may span buckets (Group Order +
Discovery). That is **two classes, two knowledge bases, and (in device
mode) two pioneers.**

## 0. Mode — ask once, before any device work

Do **not** start step-validation autonomously.

If the user already chose, obey:

| They said… | Mode |
|---|---|
| “skip pioneer”, “no device”, “knowledge base only”, “just raise the MR” | **`kb-only`** |
| Pasted a `@Test` / `trace.json` that is **not** in the checkout | **`reuse-pioneer`** |
| “run pioneer”, “validate first”, “step-validation on one case per bucket” | **`device-pioneer`** |

If they said nothing, **ask once**:

```
How should I generate the NLP tests?

1. Knowledge base only (faster) — CSV/BS cases + existing tapmind-mobile-tests
   in this PDG, harvested per bucket (groupOrder/, discovery/, …). No device.
   MR still happens. Transients like Allow/Lewati are copied only if they
   already exist in that bucket's tests.

2. Reuse a pioneer — paste a proven @Test or step-validation report that is
   NOT already in the tapmind-mobile-tests checkout. Only use this when the
   knowledge base is missing that stem.

3. Device pioneer — step-validate ONE representative case PER BUCKET, then
   clone the rest in that bucket. 3 Discovery + 3 Group Order = 2 device runs
   (not 1). Expensive. Needs TapMind MCP + a device.
```

Record `validation.mode`: `generated` | `cloned_from_pioneer` | `validated_on_device`.

## Token discipline

- CSV parse and bucket listing are scripts. Don't hand-count 30 rows.
- Pioneer runs in a **sub-agent**, one bucket at a time. Parent keeps
  `tapmindTest`, `correctedSteps`, interruption guards — not hierarchies.
- BrowserStack MCP payloads stay in a sub-agent ([references/ingest.md](references/ingest.md)).
- Never paste credentials, phones, or tokens.

## Process

```
- [ ] 0. Mode: kb-only | reuse-pioneer | device-pioneer
- [ ] 1. Ingest CSV or MCP ids → release_suite.json
- [ ] 1b. One PDG; locate tapmind-mobile-tests; module-profile
- [ ] 2. Bucket by folder/directory; echo classes + pioneers; wait if mixed PDG
- [ ] 3. Pioneer only if reuse-pioneer or device-pioneer (once per bucket)
- [ ] 4. Harvest template per bucket (that directory first)
- [ ] 5. Emit siblings; every new @Test includes Agentic_nlp_tests
- [ ] 6. Write one class per bucket; compile
- [ ] 7. One MR on that module's branch
```

### 1. Ingest

Read [references/ingest.md](references/ingest.md).

- User named / attached a `.csv` → parse it. Do not also fetch MCP.
- No CSV → ask if BrowserStack MCP is connected. If yes, fetch **the ids
  they gave**. If no, stop.

Do **not** call `test-data-identification`. There is no enriched plan.

Read [references/case-authoring.md](references/case-authoring.md). After
`parse-bs-csv.py`, each case has `preconditions_parsed`:

- `test_data_prompt` — from `Test Data:` / `User:` / `TDP:` → emit
  `TapMind.performBackdoorLogin("<verbatim>")`. Never put backdoor in steps.
- `location_lat` / `location_lng` — from `Location:` →
  `TapMind.setMockLocation(...)`. If missing, harvest bucket default.
- `not_for_tapmind` — do not emit automation for that setup.

If `test_data_prompt` is empty, copy a login sentence from the bucket sample;
if still empty, ask once. Do not invent an account.

### 1b. Module + checkout

Same resolve order as `nlp-codegen` §1 (`TAPMIND_TESTS_REPO` → walk →
shallow clone). Never write Java into `aep/skills`.

```
bash "$ROOT/skills/step-validation/assets/module-profile.sh" \
  "$MODULE" "$TAPMIND_TESTS_REPO"
```

`$MODULE` is the PDG directory (`gofood`, `cartography`). If
`module-profile.sh` cannot derive it, ask.

### 2. Buckets

Read [references/buckets.md](references/buckets.md). Echo PDG, buckets,
target class paths, and the pioneer / reference per bucket **before** any
device work. If they disagree, use their grouping.

### 3. Pioneer / kb emit

**`reuse-pioneer`:** the pasted method is the template for **that** bucket
only. Other buckets still use kb-only unless they also got a paste.

**`device-pioneer`:** invoke `aep-tapmind:step-validation` per bucket, input
mode **A** (the case's written `steps[]`), one scenario per run. Pre-answer
location, TDP prompt, backdoor login, theme. Return only run-dir,
`run.result`, `run.tapmindTest`, `run.correctedSteps`, interruption rows.

Echo the device-run count first (`N buckets = N pioneers`). A STOPPED
pioneer does not clone that bucket.

**`kb-only`:** no device. Emit from [references/buckets.md](references/buckets.md)
+ `$ROOT/skills/nlp-codegen/references/sibling-emit.md` §offline. Mark
`generated`. Tell QA these are unverified on device.

### 4–5. Harvest and clone

Read [references/step-emit.md](references/step-emit.md),
`$ROOT/skills/nlp-codegen/references/sibling-emit.md`, and
`$ROOT/skills/step-validation/references/direct-api-map.md`.

Map each `steps[].action` with **step-emit** (Update/Edit/Input → Type in
field; Open `gojek://` in steps → `openDeeplink`). Score readiness per
case-authoring §auto-readiness; echo before emit.

Harvest guards from **that bucket's directory** first, then the module
login stem. Do not copy Discovery labels into Group Order methods.

Phrasing / quoting: step-validation §6. Quote only labels the pioneer
resolved at hierarchy, or labels already quoted in that bucket. CSV
English that never ran stays **unquoted**. Vision on a pioneer is the
existing ladder — never emit coordinates onto siblings.

### 6. Write classes

One class per bucket, in that directory, house style from **that
directory's** sample test (`extends`, imports, `suiteId`, try/catch).

- Class name from the folder / feature (`Group Order` →
  `GroupOrderReleaseNlpTests`).
- One `@Test` per selected case. Method from case id + short camelCase of
  title (`validateDeadlineNudgeForMemberOnLandingPageWhenLessThan10Mins`).
- `@Test(description)` = case `title`.
- **`groups`:** copy the sample test's groups for that directory **and
  always append `"Agentic_nlp_tests"`**. Example:

  ```java
  groups = {"GOFOOD_GO_IOS", "GOFOOD_GO_ANDROID", "Agentic_nlp_tests"}
  ```

  Discovery sample uses `FoodProjectConfig.DISCOVERY*` — keep those
  constants and still add `"Agentic_nlp_tests"`. This group is how the
  pipeline runs **only the new methods** on the MR branch. Do not add it
  to pre-existing methods you did not emit.
- `@TestInfo.testCaseIds` from the case `id` (`TC-614398` or `614398` as
  the sample writes ids — gofood samples use the bare number). Never
  invent an id. `countryName` / `projectId` / `suiteId` from the sample
  in **that directory**.
- Login: `TapMind.performBackdoorLogin` with `preconditions_parsed.test_data_prompt`
  (direct API — not `runStep`). No raw phones or tokens.

Dedup `@TestInfo.testCaseIds` and method names in the module. CREATE /
UPDATE / SKIP.

Compile: `./gradlew :<MODULE>:compileTestJava`. Fix compiler errors
before the MR.

### 7. MR

Same GitLab recipe as `nlp-codegen` §7 (`source.golabs.io`,
`aep/tapmind-mobile-tests`). Branch `feat/<pdg>-release-nlp`. Commit only
the new/updated classes in this PDG.

```
GITLAB_HOST=source.golabs.io glab mr create \
  --repo aep/tapmind-mobile-tests \
  --target-branch <default> \
  --title "<PDG>: release NLP tests (Agentic_nlp_tests)" \
  --description "$(cat <<'EOF'
Buckets: <list>. Pioneer per bucket: <ids or kb-only>.
Pipeline: run group Agentic_nlp_tests on this branch.
EOF
)"
```

No write token → stop after local commit and print the commands.

## What this is not

| Need | Skill |
|---|---|
| Enriched / APG / SDET plan from agentic | `nlp-codegen` |
| One broken step list on a device | `step-validation` |
| Open-ended explore | `goal-driven-exploration` |
| GMT coded tests | `aep-mobile:test-code-generator` |

## Model

**Composer** (`composer-2.5` or the session default Composer model) for ingest,
scoring, kb-only emit, and MR. Pioneer sub-agent: same model unless the user
asks for a higher model for device step-validation; do not switch mid-run.
