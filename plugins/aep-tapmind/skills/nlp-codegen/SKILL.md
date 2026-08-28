---
name: nlp-codegen
description: >-
  Generate TapMind NLP @Test methods into tapmind-mobile-tests from an
  enriched_automation_plan / automation plan / SDET plan plus change_context,
  by step-validating ONE representative scenario per similar-flow cluster and
  cloning the rest from that proven template (including transient-screen
  guards the plan never listed). Use when asked to generate NLP test cases,
  write tapmind-mobile-tests Java, raise an MR for Driver BAM / PAM / a
  feature's automatable scenarios, or skip running step-validation on every
  case. Not for diagnosing a single broken step list (that's step-validation)
  and not for open-ended exploration (that's goal-driven-exploration).
---

# NLP test codegen (TapMind)

Human guide (what to prepare, what runs, where files go): [README.md](README.md).

Turn a plan of similar scenarios into a real `tapmind-mobile-tests` class and an MR.

**This skill orchestrates; it does not re-implement the device loop.** Per cluster it
invokes `aep-tapmind:step-validation` **once**, on a representative (pioneer) scenario.
That run is what discovers walkthroughs, permission dialogs, and real labels — none of
which come from the PDG / automation JSON. Sibling tests are cloned from the proven
`@Test`, not independently guessed.

Do **not** run step-validation on every scenario. Ten Driver BAM cases with the same
login → home → feature stem cost **one** device run, not ten.

## Token discipline

- Pioneer run in a **sub-agent**. Parent keeps the emitted `tapmindTest`,
  `correctedSteps`, and interruption guards — not hierarchies or screenshots.
- Never paste a plan's full `identification_steps` into context; take
  `test_buddy_prompt` and `automation_steps` only.
- Clustering, module derivation, and compile are scripts / grep. Don't hand-count.

## Inputs (resolve before any device work)

Same ledger order as step-validation mode B — first match wins; if the user named a
file, use that file:

1. `enriched_automation_plan.json` / `*enriched_automation_plan.json`
2. `*_automation_plan_generator.json`
3. `*_sdet_plan.json` / `*_SDET_plan.json`

Also resolve, when present:

| Artifact | Used for |
|---|---|
| `change_context.json` | `screen_id`, deeplinks, flags, locators, `locator_fallback` |
| `design_context.json` | Figma `elements[].label` + `ui_flow` — **optional**. Do not require it. The SDET plan is **not** a substitute (see below). |
| `impact_shortlist.json` | which scenarios to generate (optional) |
| `tapmind-mobile-tests` checkout | house style + write target. Clone if missing (see §1). |

**Design copy:** `design_context.json` is a separate Figma extract (`design-extractor`).
The SDET plan *consumed* it when scenarios were generated; it does **not** embed
`screens[]` / `ui_flow[]` / per-element `label`. `unmapped_extractor_data.design`
is only leftover fields that did not map, not a recoverable design file. PAM's
SDET plan even records `design_context.screens` as DEGRADED/empty. Visible
strings for NLP come from, in order: pioneer device / pasted `@Test`, then
plan `automation_steps` / `expected_result` (unquoted if never resolved), then
existing module tests. Missing `design_context.json` is normal — continue.

Select scenarios with `target_framework` / `target_execution_framework` = `TAPMIND_NLP`
(or unset + `execution_mode: Automatable`). Skip `deferred` / `manual` / empty
`automation_steps`. New (`is_legacy_regression: false`) → CREATE. Legacy with
`existing_case_ref` matching an existing `@TestInfo` → UPDATE that method, else SKIP.

A pasted proven `@Test` (or a step-validation `trace.json` / report) **is** a pioneer —
do not re-run the device for that cluster.

## Process

Copy this checklist:

```
- [ ] 1. Resolve plan + change_context + module
- [ ] 2. Cluster scenarios; pick one pioneer per cluster; echo both
- [ ] 3. Pioneer: reuse proven @Test / trace, else invoke step-validation
- [ ] 4. Harvest shared template (setup + guards + rewritten labels)
- [ ] 5. Emit sibling methods from the template + each scenario's delta
- [ ] 6. Write one class into the module; compile
- [ ] 7. Open an MR in tapmind-mobile-tests scoped to that module
```

### 1. Module (and locating `tapmind-mobile-tests`)

**You do not run this skill inside `tapmind-mobile-tests`.** The skill lives in
`aep-tapmind`. The agent can run from the plan folder, `skills`, or anywhere.
It only needs a **writable clone** of the tests repo to put the Java file in.

Resolve the checkout in this order:

1. `TAPMIND_TESTS_REPO`
2. `module-profile.sh` walking up from a TapMind config / cwd / sibling
   `tapmind-mobile-tests/`
3. **If none exist — shallow clone** (full tree at HEAD, no history):

   ```
   git clone --depth 1 git@source.golabs.io:aep/tapmind-mobile-tests.git \
     "${TMPDIR:-/tmp}/tapmind-mobile-tests"
   export TAPMIND_TESTS_REPO="${TMPDIR:-/tmp}/tapmind-mobile-tests"
   ```

   HTTPS fallback when SSH is unavailable and `GITLAB_TOKEN` is set:
   `https://gitlab-ci-token:${GITLAB_TOKEN}@source.golabs.io/aep/tapmind-mobile-tests.git`
   Do not print the token. If clone fails, **stop** and ask QA to clone or
   export `TAPMIND_TESTS_REPO`. Do not write tests into `aep/skills`.

Then:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/step-validation/assets/module-profile.sh \
  "$(bash ${CLAUDE_PLUGIN_ROOT}/skills/step-validation/assets/resolve-config.sh --path)" \
  "$TAPMIND_TESTS_REPO"
```

`MODULE`, `PACKAGE`, `BASE_CLASS`, `TEST_GROUPS`, `SAMPLE_TEST` come from that
module's own tests — never a hardcoded table. Read `$SAMPLE_TEST` and copy its
annotations, imports, `extends`, groups, try/catch.

`change_context.app` / the plan's app maps to a TapMind **directory** name
(`gojek-driver` → `driverApp`). If `module-profile.sh` can't derive it, ask.

### 2. Cluster + pioneer

Read [references/pioneer.md](references/pioneer.md). Echo to the user **before**
the device run:

```
Cluster C1 (destination PAM_8_LEVELS_CATALOGUE): SC-001, SC-002, … SC-010
  pioneer: SC-005 — longest shared stem; login still runs so transients fire
  siblings: SC-001 … (delta = profile-banner entry vs deeplink)
```

One cluster ⇒ one step-validation. Disjoint destinations ⇒ one pioneer each.
Do not pick silently.

### 3. Pioneer run

**Reuse if the user already has a proven method** (pasted Java, `trace.json`
`run.tapmindTest`, or a report's TapMind-test tab). That method *is* the template.

Otherwise invoke `aep-tapmind:step-validation` in a sub-agent:

- Input mode B, **that one scenario only**.
- Pre-answer location, `test_buddy_prompt` (verbatim from the fixture whose
  `required_state` matches `driver_type` / `country` / `platform`), backdoor
  login, theme.
- Return **only**: run-dir, `run.result`, `run.tapmindTest`, `run.correctedSteps`,
  and the `origin: "interruption"` / `origin: "inserted"` rows. Not the trace body.

If the pioneer **STOPPED**, do not clone a half-flow. Fix that scenario (or pick
the next-best in the cluster) and re-run. A stopped pioneer poisons every sibling.

No device and no proven `@Test`: fall back to offline emit
([references/sibling-emit.md](references/sibling-emit.md) §offline). Harvest
`if visible` guards only from `$SAMPLE_TEST` / sibling tests **already in that
module**. Do not invent transients. Mark every method `validation.mode: generated`.

### 4–5. Harvest and clone

Read [references/sibling-emit.md](references/sibling-emit.md) and
`${CLAUDE_PLUGIN_ROOT}/skills/step-validation/references/direct-api-map.md`.

The pioneer's `kind: guard` lines (Allow / Lewati / walkthrough) go into **every**
sibling at the same relative position — after login, before the feature action —
whether or not the plan listed them. That is the whole point of the pioneer.

Each sibling keeps its own delta: extra tap, different assertion, different
deeplink / `test_buddy_prompt` / flags. Do not copy the pioneer's unique asserts.

Phrasing, quoting, and direct-API vs `runStep` follow step-validation §6. Quote
only labels the pioneer resolved at the hierarchy rung; plan English that never
ran stays **unquoted**.

### 6. Write the class

One class per epic, next to `$SAMPLE_TEST`:

- Class name from `epic_id` / `feature_key` (`pam_8_levels_relaunch_m1` →
  `Pam8LevelsRelaunchM1Test`).
- One `@Test` per selected scenario. Method name from `scenario_id` + a short
  camelCase of `description`.
- `@Test(description)` from the scenario `description`. `groups` from
  `$TEST_GROUPS`.
- `@TestInfo.testCaseIds` from `browserstack_case_id` if it looks like a real id
  (`TC-766717`, `5542965`); **omit / `{}`** for placeholders (`TC-PENDING-SC-005`).
  Else `existing_case_ref`. Never invent an id. Copy `countryName` / `projectId` /
  `suiteId` **as `$SAMPLE_TEST` writes them** (constants, not stringly-typed copies
  of AgenticTests).
- `extends $BASE_CLASS` when the sample does.
- Never emit a credential, token, phone, or account id. Login is
  `performBackdoorLogin("<test_buddy_prompt>")` unless `$SAMPLE_TEST` uses a
  module helper **and** the sibling's fixture is that same named constant.

Dedup against existing `@TestInfo.testCaseIds` and method names in the module
(including `AgenticTests`). CREATE vs UPDATE vs SKIP; don't add a third copy.

Then compile: `./gradlew :<MODULE>:compileTestJava` from the tests repo. Fix
what the compiler reports before the MR.

Worked example of a proven pioneer (guards are **not** in the plan JSON):
[examples.md](examples.md).

### 7. MR (GitLab — needs a write token; not magic)

This is **GitLab** (`source.golabs.io`), not GitHub. There is **no numeric
project id in this skill.** The project is the checkout's `origin`:

`git@source.golabs.io:aep/tapmind-mobile-tests.git` → `aep/tapmind-mobile-tests`

(`glab` and `POST /api/v4/projects/aep%2Ftapmind-mobile-tests/merge_requests`
both derive it from that path. Do not confuse this with `@TestInfo(projectId=…)`
— that is BrowserStack / TestRail, unrelated.)

**Auth is not bundled.** Creating an MR is a GitLab API write. You need:

| What | Enough for |
|---|---|
| SSH push to `origin` | `git push` the branch |
| `GITLAB_TOKEN` (or `glab auth`) with `api` + `write_repository`, `GITLAB_HOST=source.golabs.io` | `glab mr create` / MR API |

The read token some mobile skills use (`GITLAB_READ_TOKEN_FOR_AGENT`) is **not**
enough to open an MR. Never paste a token into chat. Never hardcode one. Read
it from the environment (or an already-authenticated `glab`). If neither is
present, **stop after the local commit** and print the commands for the user.

In `$TAPMIND_TESTS_REPO` only, scoped to `$MODULE`:

1. Branch `feat/<epic_id>-nlp` from the repo's default branch.
2. Commit the new/updated test class (nothing else).
3. `git push -u origin HEAD` (SSH).
4. If `GITLAB_TOKEN` is set **or** `glab auth status` succeeds against
   `source.golabs.io`:

   ```
   GITLAB_HOST=source.golabs.io glab mr create \
     --repo aep/tapmind-mobile-tests \
     --target-branch <default> \
     --title "<epic_id>: TapMind NLP tests (<MODULE>)" \
     --description "$(cat <<'EOF'
   Pioneer: <scenario_id> (step-validated once).
   Siblings cloned from that template, including if-visible transients.
   EOF
   )"
   ```

   Else print that command (and the MR URL once the user runs it). Do not
   invent a token or call `gitlab.com`.

Don't force-push. Don't touch other modules.

## What this is not

| Need | Skill |
|---|---|
| "These steps don't work" / one list on a device | `step-validation` |
| Open-ended explore a flow | `goal-driven-exploration` |
| GMT Appium+TestNG coded tests | `aep-mobile:mobile-test-code-generator` |
| Backend API `runStep` grammar | `aep-backend:backend-tapmind-nlp-prompts` |

## Model

Sonnet, default or higher reasoning. Pioneer sub-agent must not switch models
mid-run (invalidates that skill's prompt cache). Sibling emit can stay on the
parent model.
