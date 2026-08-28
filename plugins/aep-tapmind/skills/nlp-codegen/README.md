# NLP test codegen (`nlp-codegen`)

Human guide for QA and engineers. The agent instructions are in [`SKILL.md`](SKILL.md).

This skill turns an **enriched automation plan** (plus post-build **change context**) into real TapMind NLP `@Test` methods in **`tapmind-mobile-tests`**, and opens a **GitLab MR**. It does **not** run step-validation on every scenario. It runs it **once per similar-flow cluster**, then clones the rest from that proven template.

---

## 1. One-paragraph summary

After the SDET / enriched plan and `change_context.json` exist, you ask the agent to generate TapMind NLP tests. It groups similar flows (for example 10 Driver BAM cases), **step-validates one representative case** (the pioneer), copies login setup and `if visible` transients (`Allow`, `Lewati`) onto the siblings, writes **one Java class** into the right Gradle module of `tapmind-mobile-tests` (PAM → `driverApp`), compiles it, and opens an MR on `source.golabs.io/aep/tapmind-mobile-tests` if GitLab write auth is available.

You do **not** have to open or run this skill *inside* `tapmind-mobile-tests`. That repo is only the **write target**. If it is not on disk, the skill shallow-clones it.

---

## 2. Which skill is which

| You say… | What actually runs |
|---|---|
| “Generate TapMind NLP tests / raise the MR” | **`nlp-codegen`** (this skill) |
| “Run test-code-generator” on `TAPMIND_NLP` scenarios | `aep-mobile:test-code-generator` **hands off** to `nlp-codegen` and stops |
| GMT Appium+TestNG coded tests (`GMT_JAVA`) | Stays in `test-code-generator` — not this path |
| “These steps don’t work” / debug one list | `step-validation` alone |
| Open-ended explore a flow | `goal-driven-exploration` |

`test-code-generator` is the **pipeline stage name** (Code Generation). For TapMind NLP, **`nlp-codegen` is the implementation** that writes Java and opens the MR.

Plugin: `aep-tapmind`. Path: `plugins/aep-tapmind/skills/nlp-codegen/`.

**Cursor vs Claude:** the skill body is the same `SKILL.md`. Cursor did not discover this plugin
until `.cursor-plugin/plugin.json` (v1.1.4). Install from the AEP marketplace as a Cursor
plugin, or symlink all of `plugins/aep-tapmind/skills/*` into `.cursor/skills/` **and** set
`TAPMIND_PLUGIN_ROOT` at the plugin root so sibling scripts still resolve. Full install:
[plugin README](../../README.md).

---

## 3. Why this exists

`step-validation` on every scenario is expensive: real device, hierarchy dumps, screenshots, one MCP turn per action, **one scenario per run**.

The plan JSON also never lists transients that appear after login:

```java
runStep("Tap 'Allow' on the phone call permission dialog if visible");
runStep("Tap 'Lewati' on the walkthrough if visible");
```

Those only show up on a device. Running **one** case that still logs in is enough to harvest them for every sibling that shares that stem.

---

## 4. Where it sits in the pipeline

```
PRD / design / RFC / tasks
        ↓
SDET plan  →  automation plan  →  enriched_automation_plan.json
        ↓
Dev build  →  code-change-extractor  →  change_context.json
        ↓
[optional] impact_shortlist.json
        ↓
Code generation
   TAPMIND_NLP  →  nlp-codegen  →  Java in tapmind-mobile-tests + GitLab MR
   GMT_JAVA     →  test-code-generator (coded tests)
```

Earlier stages already decided app, screens, deeplinks, TDP prompts, and BrowserStack ids. This skill does not invent those.

---

## 5. What you need **before** you run

### 5.1 Required artifacts

At least one of these (first match wins unless you name a file):

1. **`enriched_automation_plan.json`** — preferred. Has `automation_steps`, `test_buddy_prompt`, `browserstack_case_id`.
2. `*_automation_plan_generator.json`
3. `*_sdet_plan.json` / `*_SDET_plan.json`

Plus, strongly preferred:

- **`change_context.json`** — screens, deeplinks, flags, locators (from code-change-extractor / `dev_manifest`).

A typical folder looks like `PAM_08_FINAL/`: plan + `change_context.json` + optional shortlist.

### 5.2 Optional artifacts

| File | If missing |
|---|---|
| `design_context.json` | **Continue.** Figma copy/flow only. The SDET plan is **not** a substitute (it does not embed `screens[]` / `elements[].label`). PAM’s SDET plan even records design as DEGRADED/empty. |
| `impact_shortlist.json` | Generate all eligible NLP scenarios instead of a narrowed set. |
| Pasted proven `@Test` or `trace.json` | Skill will try a pioneer **device** run instead. |

### 5.3 Machine / access

| Need | Why |
|---|---|
| Agent with `aep-tapmind` installed (this skill visible) | So `nlp-codegen` can be invoked |
| SSH to `source.golabs.io` **or** `GITLAB_TOKEN` | Clone `tapmind-mobile-tests` if it is not local; push the branch |
| `GITLAB_TOKEN` or `glab auth` with **`api` + `write_repository`**, `GITLAB_HOST=source.golabs.io` | **Open the MR**. A read-only token (`GITLAB_READ_TOKEN_FOR_AGENT`) is not enough |
| TapMind server + a device (local or BrowserStack) | Pioneer step-validation — **unless** you paste a proven `@Test` / report |
| JDK / Gradle on the tests clone | `./gradlew :<module>:compileTestJava` before the MR |

**Never paste a GitLab token, TDP credential, or phone number into chat.** Tokens come from the environment. Login in generated tests is `performBackdoorLogin("<test_buddy_prompt>")`, never a raw account.

### 5.4 You do **not** need

- To `cd` into `tapmind-mobile-tests` and run the skill from there
- A numeric GitLab project id (the remote path `aep/tapmind-mobile-tests` is enough)
- `design_context.json`
- To run step-validation on every scenario
- GitHub (`gh`) — this is GitLab only

---

## 6. How to run it

From any workspace (plan folder, `aep/skills`, Cursor chat):

> Generate the TapMind NLP tests from `<path-to-folder-or-enriched_automation_plan.json>` and raise the MR.

Useful extras:

- “Use this `@Test` as the pioneer” (paste the method)
- “Pioneer is SC-005”
- `export TAPMIND_TESTS_REPO=/path/to/tapmind-mobile-tests` if you already have a clone

The agent should **echo the cluster and pioneer pick before** spending a device. Override if the pick is wrong.

---

## 7. What happens (7 steps)

### Step 1 — Resolve inputs and module

Reads the plan + `change_context`. Selects `TAPMIND_NLP` / automatable scenarios. Skips empty steps, manual, deferred. New → CREATE. Legacy with an existing `@TestInfo` id → UPDATE or SKIP (no third copy).

Finds `tapmind-mobile-tests`:

1. `TAPMIND_TESTS_REPO`
2. Checkout next to cwd / config path
3. Else **`git clone --depth 1 git@source.golabs.io:aep/tapmind-mobile-tests.git`** (full tree at HEAD, no history). HTTPS + `GITLAB_TOKEN` if SSH is missing. If clone fails → **stop** and ask you to clone. Never writes Java into `aep/skills`.

Maps app → Gradle module (`gojek-driver` → `driverApp`) via `module-profile.sh`, which reads **that module’s own tests** for package, `BaseTest`, groups, and a sample file. ~19 modules disagree on all of those; there is no hardcoded table.

### Step 2 — Cluster, then pick one pioneer

**Module first, then cluster.** Driver vs GoFood is **not** a cluster; that is two apps / two write targets.

A **cluster** is scenarios that share the same login → feature-screen stem (same `destination_screen`, similar `automation_steps`). Ten BAM cases that differ on one assert = **one cluster** = **one device run**.

A second destination in the same Driver plan (e.g. onboarding) = a second cluster = a second pioneer, still `driverApp`, still one MR.

Pioneer pick: longest shared stem, prefer P0, prefer a case that still logs in so home transients fire. Echoed before the device run.

### Step 3 — Pioneer (one step-validation, or reuse)

If you already have a proven method (pasted Java, `trace.json`, or a module test with the same stem + guards), **that is the pioneer** — no device.

Otherwise invokes **`step-validation` once** on that scenario (sub-agent). If it **STOPPED**, siblings are not cloned from a half-flow.

No device and no proven `@Test`: still emits Java, copies `if visible` only from tests **already in that module**, marks methods unverified (`generated`). Does not invent `Lewati`.

### Step 4–5 — Harvest and clone siblings

**Copied onto every sibling:** mock location, `performBackdoorLogin` (swap prompt per fixture), permissions, every `if visible` guard in the same place.

**Per sibling only:** extra tap (banner vs deeplink), unique asserts, flags if the sample test uses toggle helpers.

Plan = assertions. Pioneer = transients and real labels. Android `resource-id` is **not** put in `runStep` (GMT only). Plan English that never ran on device stays **unquoted** (fuzzy), so `id-ID` does not break on a quoted English title.

### Step 6 — Write class and compile

One class per epic next to the sample test, e.g.

`tapmind-mobile-tests/driverApp/src/test/java/io/gojek/driverapp/tests/Pam8LevelsRelaunchM1Test.java`

House style from `$SAMPLE_TEST` (`extends BaseTest`, `DriverProjectConfig` constants — not stringly-typed `AgenticTests`). Then `./gradlew :driverApp:compileTestJava`.

`@TestInfo.testCaseIds` from a real `browserstack_case_id`; placeholders like `TC-PENDING-SC-005` are omitted. BrowserStack `projectId` on `@TestInfo` is **not** the GitLab project.

### Step 7 — GitLab MR

In the tests clone only, scoped to that module:

1. Branch `feat/<epic_id>-nlp`
2. Commit the test class only
3. `git push -u origin HEAD`
4. `GITLAB_HOST=source.golabs.io glab mr create --repo aep/tapmind-mobile-tests …`

If there is no write token / `glab` login: **stop after the local commit** and print those commands. No `gitlab.com`, no invented token, no force-push.

---

## 8. Knowledge bases (what the agent is allowed to learn from)

| Source | Required? | Used for |
|---|---|---|
| Enriched / APG / SDET plan | **Yes** (one of them) | Scenarios, `automation_steps`, TDP prompts, BS ids, locale, flags, `mapped_user_flow` |
| `change_context.json` | Strongly preferred | Screen ids, deeplinks, flags, locators |
| `design_context.json` | Optional | Figma `elements[].label` / `ui_flow` if present |
| SDET plan as “hidden design” | **No** | Cannot reconstruct Figma screens or copy |
| `step-validation` files (reuse, not a fork) | Yes | Direct API vs `runStep`, verb-first phrasing, quote vs fuzzy, `module-profile.sh` |
| Pioneer device run or pasted `@Test` | Preferred | Transients (`Allow` / `Lewati`) and rendered labels |
| `tapmind-mobile-tests` clone | Yes (or auto-clone) | File path, package, base class, groups, dedup |
| `nav_index/tapmind/<module>.json` | If present | Proven phrasing already in that module |

Visible strings for NLP, in order: pioneer / pasted test → plan steps / `expected_result` → existing module tests → optional design labels. Missing design is normal.

---

## 9. How it knows **where** to write the file

| Question | Answer |
|---|---|
| Which git repo? | Clone of `aep/tapmind-mobile-tests` (`TAPMIND_TESTS_REPO` or shallow clone) |
| Which Gradle module? | `change_context.app` / plan app → directory (`gojek-driver` → `driverApp`). Confirmed by `module-profile.sh` |
| Which package / base class / groups? | Grep of that module’s existing tests |
| Which file? | One new class named from `epic_id` / `feature_key`, next to `$SAMPLE_TEST` |
| Which GitLab project for the MR? | `origin`: `aep/tapmind-mobile-tests` on `source.golabs.io`. No numeric id stored in the skill |

---

## 10. Worked example (PAM 8 Levels)

Inputs: `enriched_automation_plan.json` + `change_context.json` (`app: gojek-driver`, screens `PROFILE_PAGE` / `PAM_8_LEVELS_CATALOGUE`, deeplink `gojekdriver://loyalty/catalogue`).

- Module: `driverApp`
- Cluster: catalogue / intro flows (banner entry and deeplink stay together)
- Pioneer: e.g. catalogue deeplink case, **or** a pasted method that already has Allow / Lewati
- Siblings get those two `if visible` lines even though they are not in the plan JSON
- SC-001 still walks profile → banner; it does not replace an entry-point test with a deeplink shortcut
- Output class under `driverApp/.../tests/`
- MR on `aep/tapmind-mobile-tests`

Proven pioneer shape (guards are the point): see [`examples.md`](examples.md).

---

## 11. Failure / fallback behaviour

| Situation | What the skill does |
|---|---|
| No plan file | Stop and ask |
| No `change_context` | Continue if screens/deeplinks are on the plan; ask if module/deeplink cannot be derived |
| No `design_context` | Continue |
| No `tapmind-mobile-tests` on disk | Shallow clone; if that fails, stop and ask |
| No device and no proven `@Test` | Offline emit; no invented transients; mark `generated` |
| Pioneer STOPPED | Do not clone; fix or pick another pioneer |
| No GitLab write token | Commit locally; print `git push` + `glab mr create` |
| Pioneer `@Test` already in the module | Reuse; skip device for that cluster |

---

## 12. What this skill does **not** do

- Diagnose a single broken step list (use `step-validation`)
- Exploratory testing (use `goal-driven-exploration`)
- GMT coded Appium tests (use `test-code-generator` / GMT repo)
- Backend API TapMind grammar (use `backend-tapmind-nlp-prompts`)
- Store or print GitLab / TDP secrets
- Put Android resource-ids into `runStep` strings

If a **cloned sibling later flakes**, run `step-validation` on **that one method** as a repair. Do not regenerate the whole suite on device.

---

## 13. Files in this directory

| File | Audience |
|---|---|
| `README.md` | This guide (QA / engineers) |
| `SKILL.md` | Agent instructions when the skill is invoked |
| `references/pioneer.md` | Cluster + pioneer pick rules |
| `references/sibling-emit.md` | What to copy vs replace from the pioneer |
| `examples.md` | PAM catalogue `@Test` used as a pioneer template |

Shared with `step-validation` (same plugin, not copied): `assets/module-profile.sh`, `references/direct-api-map.md`, emit rules in `step-validation/SKILL.md` §6.
