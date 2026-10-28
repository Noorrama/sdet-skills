# NLP test codegen — release (`nlp-codegen-release`)

Human guide for QA. Agent instructions: [`SKILL.md`](SKILL.md).

This skill turns **assigned BrowserStack cases** (a CSV export, or case ids
via the BrowserStack MCP) into TapMind NLP `@Test` methods in
**`tapmind-mobile-tests`**, and opens a **GitLab MR**. Every new method is
tagged `Agentic_nlp_tests` so the pipeline can run **only those new tests**
on the MR branch.

It is **not** `nlp-codegen`. That skill reads an agentic enriched plan.
This one reads TMS cases. Do not mix the two.

---

## 1. One-paragraph summary

You drop a BrowserStack CSV (or ids, if MCP is connected) for **one PDG**
— GoFood **or** Cartography, not both. The skill groups cases into the
existing directories under that module (`gofood/.../groupOrder`,
`gofood/.../discovery`). You choose: knowledge base only, a pasted pioneer
that is **not already in the checkout**, or one device pioneer **per
bucket**. It writes one class per bucket, compiles, and opens the MR.

---

## 2. Which skill is which

| You say… | What runs |
|---|---|
| “Automate these BrowserStack / GoFood CSV cases / raise the release MR” | **`nlp-codegen-release`** |
| “Generate NLP tests from the enriched / SDET / APG plan” | `nlp-codegen` (agentic — leave it alone) |
| “These steps don’t work” on one list | `step-validation` |
| Open-ended explore | `goal-driven-exploration` |

Plugin: `aep-tapmind`. Path: `plugins/aep-tapmind/skills/nlp-codegen-release/`.

---

## 3. Why this exists

`nlp-codegen` expects `automation_steps` and `test_buddy_prompt` from the
agentic pipeline. Release work starts from TMS: title, preconditions,
step + expected. Those are weaker, but `tapmind-mobile-tests` already has
proven GoFood Group Order / Discovery tests — that is the knowledge base.

Running step-validation on all 30 cases is too expensive. Clustering by
**bucket** (the directory that already owns the flow) means:

- 3 Discovery + 3 Group Order → **2** classes, and in device mode **2**
  pioneers (not 1, not 6).
- Each class harvests only that directory, so Discovery copy does not leak
  into Group Order methods.

---

## 4. What you need

### 4.1 Input (one of)

1. **BrowserStack CSV export** — the usual TMS download (`Test Case ID`,
   `Title`, `Folder Path`, `Steps`, `Expected Result`, `Preconditions`).
   Multi-row steps are fine; `assets/parse-bs-csv.py` handles them.
2. **Case ids + BrowserStack MCP** — if you did not attach a CSV, the
   agent asks whether MCP is connected, then fetches **only the ids you
   list**.

**One PDG per run.** A CSV that mixes GoFood and Cartography is rejected.
Split it.

### 4.2 Checkout

A writable `tapmind-mobile-tests` clone (`TAPMIND_TESTS_REPO` or a
shallow clone). That checkout **is** the primary knowledge base. House style,
deeplinks, TDP prompts, and `if visible` guards come from the bucket
directory first, then the module login stem, then **`nav_index/tapmind/`**
(aep-mobile) for proven deeplink/workflow steps when the CSV is thin — see
`references/nav-index.md`.

Release team walkthrough: [docs/nlp-codegen-release-e2e-one-pager.md](../../../../docs/nlp-codegen-release-e2e-one-pager.md)
(relative from plugin install: same file in `sdet-skills/docs/`).

**Finalise:** user says “Finalise this MR” → `references/finalise-mr.md`
(strip `Agentic_nlp_tests`, append successful pipeline links to MR description).

**Owner:** emitted `@TestInfo` uses `owner = "AI-AGENT"`, not BrowserStack Owner.

### 4.3 Machine

| Need | Why |
|---|---|
| `aep-tapmind` installed | So this skill is visible |
| SSH or `GITLAB_TOKEN` | Clone / push |
| `GITLAB_TOKEN` or `glab auth` with `api` + `write_repository`, `GITLAB_HOST=source.golabs.io` | Open the MR |
| BrowserStack MCP | Only when there is no CSV |
| TapMind server + device | Only for **device-pioneer** |
| JDK / Gradle | `./gradlew :<module>:compileTestJava` |

Never paste a GitLab token, TDP credential, or phone into chat.

---

## 5. How to run it

> Automate these BrowserStack cases with nlp-codegen-release:
> `<path-to.csv>` (GoFood). Knowledge base only.

or

> nlp-codegen-release, no CSV. MCP is connected. Fetch TC-614398 TC-614401
> from GoFood. Run one pioneer per bucket.

If you did not pick a mode, the agent **asks once**. Option 2 (reuse a
pioneer) is only for a `@Test` / report **that is not already in the
checkout**. If Group Order already has the stem on disk, use option 1.

---

## 6. What happens

### Step 1 — Ingest

CSV → `parse-bs-csv.py` → `release_suite.json`. Or MCP sub-agent fetches
the ids and writes the same file. Parent sees counts and titles, not raw
MCP JSON.

### Step 1b — One PDG

`GoFood - Group Order` and `GoFood - Discovery` are the **same** module
(`gofood`). `Cartography` is a different run. `module-profile.sh` reads
that module’s package / base class / sample test.

### Step 2 — Buckets (echoed before any device work)

```
PDG: gofood
  Bucket groupOrder/: TC-614398, …
    class → …/groupOrder/GroupOrderReleaseNlpTests.java
    kb    → existing groupOrder/ tests
    pioneer → TC-614398
  Bucket discovery/: TC-590728, …
    class → …/discovery/DiscoveryReleaseNlpTests.java
    kb    → existing discovery/ tests
    pioneer → TC-590728
```

Override if the grouping is wrong.

### Step 3 — Mode

| Mode | Device? | What you get |
|---|---|---|
| kb-only | No | Best NLP from that bucket’s tests + unquoted CSV English |
| reuse-pioneer | No | Your pasted `@Test` is the template for that bucket |
| device-pioneer | **One case per bucket** | Proven labels + `if visible` guards, then clone |

Device-pioneer is the expensive option. Two buckets = two TapMind runs.
A stopped pioneer does not clone that bucket.

### Step 4–5 — Emit

Shared setup and guards from the bucket template. Each case keeps its own
assert / extra tap. CSV lines that never ran stay **unquoted**.

### Step 6 — Groups and compile

Every **new** method includes the sample’s groups **plus**:

```java
"Agentic_nlp_tests"
```

Example (Group Order):

```java
@Test(description = "Verify Deadline Nudge for member …",
      groups = {"GOFOOD_GO_IOS", "GOFOOD_GO_ANDROID", "Agentic_nlp_tests"})
@TestInfo(..., testCaseIds = {"614398"}, ...)
```

Discovery keeps `FoodProjectConfig.DISCOVERY*` and still adds
`Agentic_nlp_tests`. Pre-existing methods are not retagged.

Then `./gradlew :gofood:compileTestJava` (or `:cartography:…`).

### Step 7 — MR

Branch `feat/<pdg>-release-nlp` on `aep/tapmind-mobile-tests`. One MR for
the PDG (both classes). Pipeline job should run:

```
-Dgroups=Agentic_nlp_tests
```

against **this branch**, so only the new methods execute once.

This skill **stamps the group**. The GitLab job that points at the MR
branch lives in `tapmind-mobile-tests` CI — wire it there if it does not
exist yet.

---

## 7. How close kb-only can get

The knowledge base is real Java in that bucket, not the CSV walk
(“Open the Gojek app…”). Group Order tests already: mock location, TDP
host + member, `createAndJoinGroupOrder`, merchant / shared-cart
deeplink, cancel / tooltip guards.

kb-only **cannot** invent:

- APIs the controllers do not have (e.g. set deadline &lt; 10 minutes)
- Nudge copy that no test has quoted
- `Lewati` / `Allow` unless that bucket already has them

Those stay unquoted or a `// kb-only hole` comment. Device-pioneer on
**that bucket** is how they become real. The other bucket is unchanged.

---

## 8. Failure / fallback

| Situation | What happens |
|---|---|
| No CSV and MCP not connected | Stop and ask |
| CSV mixes two PDGs | Stop; split the list |
| Case already has `@TestInfo` in the module | SKIP |
| Bucket directory cannot be derived | Ask; do not invent a package |
| Identification / enriched plan | Not used. Wrong skill (`nlp-codegen`) |
| Pioneer STOPPED | Do not clone that bucket |
| No GitLab write token | Commit locally; print `git push` + `glab mr create` |

---

## 9. Files in this directory

| File | Audience |
|---|---|
| `README.md` | This guide |
| `SKILL.md` | Agent instructions |
| `references/ingest.md` | CSV parse + MCP fetch |
| `references/buckets.md` | PDG constraint, placement, KB scope, pioneer-per-bucket |
| `assets/parse-bs-csv.py` | BrowserStack CSV → `release_suite.json` |

Shared (not copied): `nlp-codegen` sibling-emit + pioneer pick,
`step-validation` `module-profile.sh` / emit §6 / `direct-api-map.md`.
