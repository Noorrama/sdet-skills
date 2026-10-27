# Release NLP automation — one-pager (release team)

How we turn **raw BrowserStack cases** into **TapMind NLP tests** in
`tapmind-mobile-tests`, run them on **real devices** via a **dedicated CI
job**, and merge with fewer revision loops.

Skill: **`nlp-codegen-release`** (Cursor / AEP TapMind plugin).  
Example case: **TC-705875** (GoFood saved address).

---

## 1. What you give us

| Input | Purpose |
|--------|---------|
| BrowserStack **CSV export** (or case ids + MCP) | Steps, preconditions, folder → bucket |
| Optional: **updated** case text (clear Test Data, scroll targets, verify copy) | Less kb guessing |
| `tapmind-mobile-tests` checkout | Primary knowledge base (existing NLP in that flow) |

**Preconditions (not steps):**

- `Test Data:` → `TapMind.performBackdoorLogin("…")` verbatim  
- `Location:` → `TapMind.setMockLocation(lat, lng)`  
- Deeplinks stay in **Steps** as `Open gojek://…`

---

## 2. Example: TC-705875 (raw → runnable)

**Before (typical raw case):** vague profile navigation, “saved address” without
casing, login mixed into steps.

**After (authoring + kb):**

- Preconditions: `Test Data: Get me a customer with a saved address` (+ mock
  location when needed)
- Steps: profile → **scroll until** `Saved addresses` visible → edit flow →
  search/type → **Update** → assert on **Business1** / location copy
- Emit: `scrollToText(DOWN, "Saved addresses", CONTAINS)` (not generic
  `runStep("Scroll…")`) — aligned with booking bucket tests

**Output:** `SavedAddressReleaseNlpTests.java` under `gofood/.../booking/`,
`@TestInfo(testCaseIds = {"705875"})`, `owner = "AI-AGENT"`.

---

## 3. How the skill decides what to write (knowledge ladder)

Per bucket directory, **in order**:

1. **Bucket tests** — same folder in `tapmind-mobile-tests` (deeplinks, TDP
   prompts, `scrollToText`, guards)
2. **Module login stem** — shared backdoor / mock location for that Gradle module
3. **`nav_index/tapmind/<module>.json`** (aep-mobile) — when CSV lacks deeplink
   or path; lookup via `corpus_lookup.py` (`case`, `nav-step`), not by reading
   the whole JSON file
4. **CSV steps** — unquoted UI text unless proven in (1)–(3)

**Modes:**

| Mode | When | Device |
|------|------|--------|
| **kb-only** | Default / “just raise the MR” | No |
| **device-pioneer** | Thin case, one representative per bucket | Yes (step-validation) |
| **reuse-pioneer** | Pasted proven `@Test` not on disk | Uses paste |

Goal: **reuse proven stems** (e.g. booking scroll labels) so CI failures are
product issues, not invented wording.

---

## 4. MR branch workflow

1. Ingest CSV → bucket by folder (e.g. GoFood booking vs Comms chatrevamp).
2. Emit `*ReleaseNlpTests.java` — one class per bucket.
3. Tag methods with **`Agentic_nlp_tests`** (temporary) so CI runs **only** new
   methods.
4. Open MR on `feat/<area>-release-nlp-agentic` (or shared release branch).

**Do not** use embedded `"` inside `@Test(description)` — BrowserStack session
names break JSON (`setSessionName`).

---

## 5. CI: Android + iOS (generic jobs)

In `tapmind-mobile-tests` (root, not per-module YAML):

| Job | Platform |
|-----|----------|
| `agentic_nlp_release_android` | Consumer Android |
| `agentic_nlp_release_ios` | Consumer iOS |

**API / web trigger variables:**

| Variable | Example |
|----------|---------|
| `ref` | MR branch |
| `TAG` | `Agentic_nlp_tests` |
| `MODULE` | `gofood`, `communication-platform`, … |
| `TAPMIND_CONFIG` | `gofood_android.json`, `comms_remote_ios.json`, … |
| `APP_TYPE` | `gojek-android` / `gojek-ios` |
| `INFRA` | `qa` |

App binaries: same **download_gojek_android_app** / **download_gojek_ios_app**
as other consumer jobs. Reports: **Tapmind-release-reports** (Lark).

**705875 example:** `MODULE=gofood`, configs `gofood_android.json` /
`gofood_ios.json`, tag `Agentic_nlp_tests`.

---

## 6. Finalise before merge

When the author says **“Finalise this MR”**:

1. **Remove** `Agentic_nlp_tests` from all release NLP classes in that MR.
2. **Fetch** successful `agentic_nlp_release_*` pipelines on the branch (GitLab).
3. **Append** a **Agentic NLP verification** table (platform, module, pipeline
   URL, SHA) to the MR description.
4. Push cleanup commit.

After merge, tests run under normal regression groups (`BOOKING_*`, `COMMS_*`,
etc.), not the agentic tag.

---

## 7. What reduces revisions (checklist)

| Practice | Why |
|----------|-----|
| Strong **Test Data** + **Location** in preconditions | Correct TDP/mock without guessing |
| **Scroll-to-text** rows with real on-screen labels | `scrollToText` + `CONTAINS` vs flaky `runStep` scroll |
| **Quote** controls when known (`Tap 'Update'`) | Matches hierarchy / bucket |
| **Bucket-first** harvest (705875 ↔ `booking/`) | Same `suiteId`, deeplinks, scroll casing |
| **nav_index** when CSV is thin | Proven deeplink/chat entry from indexed Java |
| **Pioneer one case per bucket** when kb is weak | Labels/guards validated once, siblings cloned |
| Plain **`@Test(description)`** (no `"` in title) | BS session init succeeds |
| **`owner = "AI-AGENT"`** on emitted tests | Clear automation provenance vs TMS owner |

---

## 8. References

| Artifact | Location |
|----------|----------|
| Skill | `plugins/aep-tapmind/skills/nlp-codegen-release/` |
| Pipeline vars | `references/gitlab-pipeline.md` |
| Finalise MR | `references/finalise-mr.md` |
| nav_index ladder | `references/nav-index.md` |
| Example MR | `tapmind-mobile-tests` !960 (GoFood + Comms release NLP) |

**Questions:** SDET / TapMind — extend buckets, regenerate nav_index after new
release tests land (`extract_tapmind_nav_index.py`).
