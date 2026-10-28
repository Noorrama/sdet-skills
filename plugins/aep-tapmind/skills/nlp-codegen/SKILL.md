---
name: nlp-codegen
description: >-
  Generate TapMind NLP @Test methods into tapmind-mobile-tests from an
  enriched_automation_plan plus change_context. If only an automation plan or
  SDET plan is given, the mobile-test-code-gen orchestrator runs
  backend-test-data-identification (qa-backend-toolkit) first so
  enriched_automation_plan.json exists. Default is to ASK whether to skip the
  device (knowledge-base only, faster MR) or step-validate ONE pioneer scenario
  per similar-flow cluster (or reuse a pasted proven @Test). Use when asked to
  generate NLP test cases, write tapmind-mobile-tests Java, raise an MR, skip
  pioneer / skip step-validation, or knowledge-base-only codegen. Not for
  diagnosing a single broken step list (that's step-validation) and not for
  open-ended exploration (that's goal-driven-exploration).
---

# NLP test codegen (TapMind)

Human guide (what to prepare, what runs, where files go): [README.md](README.md).
Claude Code and Cursor both load these `SKILL.md` files — install notes:
[plugin README](../../README.md).

Plugin root for bash (Claude sets `CLAUDE_PLUGIN_ROOT`, Cursor sets `CURSOR_PLUGIN_ROOT`):

```
ROOT="$(bash "${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-${TAPMIND_PLUGIN_ROOT:?}}}/scripts/plugin-root.sh")"
```

Use `$ROOT` anywhere this skill used `${CLAUDE_PLUGIN_ROOT}`.

Turn a plan of similar scenarios into a real `tapmind-mobile-tests` class and an MR.

**This skill orchestrates; it does not re-implement the device loop.** A device
pioneer is **optional**. QA chooses the mode (see §0). Knowledge-base-only is
faster and still uses the plan, `change_context`, existing module tests, and
step-validation emit rules — it will not discover `Allow` / `Lewati` unless
those already exist in the knowledge base.

If they opt into a device pioneer: **one** `step-validation` per similar-flow
cluster, then clone siblings. Never validate every scenario.

## 0. Mode — ask once, before any device work

Do **not** start step-validation autonomously.

If the user already chose in the prompt, obey and do not re-ask:

| They said… | Mode |
|---|---|
| “skip pioneer”, “no device”, “knowledge base only”, “just raise the MR”, “I don’t have time” | **`kb-only`** |
| Pasted a `@Test` / `trace.json` / “use this as the pioneer” | **`reuse-pioneer`** |
| “run pioneer”, “validate first”, “step-validation on one case” | **`device-pioneer`** |

If they said nothing, **ask once** (recommend `kb-only` when they sound rushed):

```
How should I generate the NLP tests?

1. Knowledge base only (faster) — plan + change_context + existing tapmind-mobile-tests
   + step-validation phrasing rules. No device. MR still happens. Transients like
   Allow/Lewati are copied only if they already exist in that module's tests.
2. Reuse a pioneer — paste a proven @Test or point at a step-validation report.
3. Device pioneer — step-validate ONE representative case, then clone the rest
   (discovers Allow/Lewati). Needs TapMind MCP + a device.
```

Then proceed. Record the mode on the class/ledger (`validation.mode`:
`generated` | `cloned_from_pioneer` | `validated_on_device`).

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

**Codegen always reads an enriched plan.** If the match is an APG or SDET
file, the orchestrator should have run **`backend-test-data-identification`**
already (step 3 of **`mobile-test-code-gen`**). If enrichment is still missing,
**stop** and ask to run that step — do not emit from an unenriched ledger.

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
strings for NLP come from, in order: pioneer device / pasted `@Test` (when
those modes ran), then existing module tests (quoted labels already proven),
then plan `automation_steps` / `expected_result` (**unquoted** if never
resolved on device). Missing `design_context.json` is normal — continue.

Select scenarios with `target_framework` / `target_execution_framework` = `TAPMIND_NLP`
(or unset + `execution_mode: Automatable`). Skip `deferred` / `manual` / empty
`automation_steps`. New (`is_legacy_regression: false`) → CREATE. Legacy with
`existing_case_ref` matching an existing `@TestInfo` → UPDATE that method, else SKIP.

A pasted proven `@Test` (or a step-validation `trace.json` / report) **is** a pioneer —
do not re-run the device for that cluster.

## Process

Copy this checklist:

```
- [ ] 0. Mode: kb-only | reuse-pioneer | device-pioneer (ask unless already stated)
- [ ] 1. Resolve plan; if not enriched, stop (run backend-test-data-identification via orchestrator)
- [ ] 1b. change_context + module
- [ ] 2. Cluster scenarios; pick one pioneer / reference per cluster; echo both
- [ ] 3. Pioneer only if mode is reuse-pioneer or device-pioneer
- [ ] 4. Harvest shared template (setup + guards + rewritten labels)
- [ ] 5. Emit sibling methods from the template + each scenario's delta
- [ ] 6. Write one class into the module; compile
- [ ] 7. Open an MR in tapmind-mobile-tests scoped to that module
- [ ] 8. Pipeline (optional, ask once): trigger `Agentic_nlp_tests` on MR branch
- [ ] 9. Finalise MR (on request): strip `Agentic_nlp_tests`; append verification table
```

### 1a. Enrich when `enriched_automation_plan.json` is missing

| On disk | Action |
|---|---|
| `*enriched_automation_plan.json` present | Use it. Do **not** re-run identification. |
| Only APG or SDET | **Stop.** Run **`mobile-test-code-gen`** step 3, or skill **`backend-test-data-identification`** (qa-backend-toolkit), then re-run this agent. |
| No plan at all | Stop and ask. |

Identification is maintained by the TDI team in **qa-backend-toolkit** only
(**`backend-test-data-identification`**). This skill does not call it inline when
invoked from the orchestrator (step 3 already ran). Standalone invocations must
enrich first.

When identification **aborts**: **stop**. Do not emit Java from the unenriched APG / SDET.

When identification **succeeds**: use `enriched_automation_plan.json` and continue from clustering.

**`test-data-provisioner`** is **not** identification — runtime handles only.

### 1. Module (and locating `tapmind-mobile-tests`)

**You do not run this skill inside `tapmind-mobile-tests`.** The skill ships in
**qa-mobile-toolkit** (skills `nlp-codegen` + `step-validation`). The agent can run from the plan folder or anywhere.
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
ROOT="$(bash "${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-${TAPMIND_PLUGIN_ROOT:?}}}/scripts/plugin-root.sh")"
bash "$ROOT/skills/step-validation/assets/module-profile.sh" \
  "$(bash "$ROOT/skills/step-validation/assets/resolve-config.sh" --path)" \
  "$TAPMIND_TESTS_REPO"
```

`MODULE`, `PACKAGE`, `BASE_CLASS`, `TEST_GROUPS`, `SAMPLE_TEST` come from that
module's own tests — never a hardcoded table. Read `$SAMPLE_TEST` and copy its
annotations, imports, `extends`, groups, try/catch.

`change_context.app` / the plan's app maps to a TapMind **directory** name
(`gojek-driver` → `driverApp`). If `module-profile.sh` can't derive it, ask.

### 2. Cluster + pioneer

Read [references/pioneer.md](references/pioneer.md). Echo the cluster **before**
any device work (even in `kb-only`, so they see the grouping):

```
Cluster C1 (destination PAM_8_LEVELS_CATALOGUE): SC-001, SC-002, … SC-010
  pioneer: SC-005 — longest shared stem; login still runs so transients fire
  siblings: SC-001 … (delta = profile-banner entry vs deeplink)
```

`kb-only`: still pick a “reference” scenario (longest stem) as the **phrasing
template** from the plan + module tests — do not invoke step-validation.
Disjoint destinations ⇒ one reference / pioneer each. Do not pick silently.

### 3. Pioneer / knowledge-base emit

**`reuse-pioneer`:** the pasted `@Test` / `trace.json` `run.tapmindTest` / report
tab **is** the template. Do not re-run the device for that cluster.

**`device-pioneer`:** invoke **`step-validation`** in a sub-agent:

- Input mode B, **that one scenario only**.
- Pre-answer location, `test_buddy_prompt` (verbatim from the fixture whose
  `required_state` matches `driver_type` / `country` / `platform`), backdoor
  login, theme.
- Return **only**: run-dir, `run.result`, `run.tapmindTest`, `run.correctedSteps`,
  and the `origin: "interruption"` / `origin: "inserted"` rows. Not the trace body.

If the pioneer **STOPPED**, do not clone a half-flow. Fix that scenario (or pick
the next-best in the cluster) and re-run. A stopped pioneer poisons every sibling.

**`kb-only`:** skip the device. Emit from the knowledge base
([references/sibling-emit.md](references/sibling-emit.md) §offline): plan
`automation_steps`, `change_context` screens/deeplinks, `test_buddy_prompt`,
direct-api map, `$SAMPLE_TEST` house style, and `if visible` guards **only**
from tests already in `$MODULE`. Do not invent `Lewati` / `Allow`. Mark every
method `validation.mode: generated`. Still raise the MR. Tell QA this is
unverified on device; they can run `device-pioneer` later on one flaky method.

### 4–5. Harvest and clone

Read [references/nav-index.md](references/nav-index.md) and run the harvest
**ladder** for each cluster before emit (subdirectory tests → module login stem →
`corpus_lookup.py` on nav_index → plan + `change_context`).

Read [references/step-emit.md](references/step-emit.md),
[references/sibling-emit.md](references/sibling-emit.md), and
`$ROOT/skills/step-validation/references/direct-api-map.md`.

The pioneer's `kind: guard` lines (Allow / Lewati / walkthrough) go into **every**
sibling at the same relative position — after login, before the feature action —
whether or not the plan listed them. That is the whole point of a device /
reused pioneer.

In **`kb-only`**, copy guards only from `$MODULE` tests that share this login
stem. If none exist, emit none.

Each sibling keeps its own delta: extra tap, different assertion, different
deeplink / `test_buddy_prompt` / flags. Do not copy the pioneer's unique asserts.

Phrasing, quoting, and direct-API vs `runStep` follow step-validation §6. Quote
only labels a device/reused pioneer resolved at the hierarchy rung, or labels
already quoted in `$MODULE` tests. Plan English that never ran stays **unquoted**.

### 6. Write the class

One class per epic, next to `$SAMPLE_TEST`:

- Class name from `epic_id` / `feature_key` (`pam_8_levels_relaunch_m1` →
  `Pam8LevelsRelaunchM1Test`).
- One `@Test` per selected scenario. Method name from `scenario_id` + a short
  camelCase of `description`.
- `@Test(description)` from the scenario `description`. **`groups`:** copy
  `$TEST_GROUPS` from `$SAMPLE_TEST` **and always append**
  `"Agentic_nlp_tests"` on every **new or updated** method this skill emits
  (MR pipeline runs only that group on the branch). Do not add it to unrelated
  existing methods.
- **`@TestInfo(owner = "AI-AGENT")`** on every emitted method (org standard for
  agentic-generated NLP).
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

MR description should mention: pioneer/cluster summary and that pipeline can run
group **`Agentic_nlp_tests`** on this branch.

### 8. Pipeline (optional — ask once)

After the MR branch is pushed, ask **once** whether to trigger generic release NLP
jobs on that `ref`. If yes, read [references/gitlab-pipeline.md](references/gitlab-pipeline.md)
and use GitLab MCP on `aep/tapmind-mobile-tests` with `TAG=Agentic_nlp_tests` and
the correct `MODULE` / `TAPMIND_CONFIG` / `APP_TYPE`. Return pipeline URLs only;
record them for §9.

### 9. Finalise MR (on user request)

When the user asks to finalise, read [references/finalise-mr.md](references/finalise-mr.md):
strip `Agentic_nlp_tests`, append successful pipeline table to the MR description,
push the cleanup commit.

## What this is not

| Need | Skill |
|---|---|
| "These steps don't work" / one list on a device | `step-validation` |
| Open-ended explore a flow | `goal-driven-exploration` |
| GMT Appium+TestNG coded tests | `aep-mobile:mobile-test-code-generator` |
| Backend API `runStep` grammar | `aep-backend:backend-tapmind-nlp-prompts` |
| Enriched plan / `test_buddy_prompt` | **`backend-test-data-identification`** (qa-backend-toolkit); orchestrator step 3 of **`mobile-test-code-gen`** |

## Model

Sonnet, default or higher reasoning. Pioneer sub-agent must not switch models
mid-run (invalidates that skill's prompt cache). Sibling emit can stay on the
parent model.
