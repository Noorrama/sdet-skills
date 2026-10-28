# One PDG, many buckets, one class per bucket

## PDG (hard constraint)

One run = **one** product / Gradle module. GoFood **or** Cartography, never
both.

Derive the PDG from `folder_path` prefixes (and the user's word):

| Folder path / user said | Module (`tapmind-mobile-tests` dir) |
|---|---|
| `GoFood - …` / GoFood | `gofood` |
| Cartography | `cartography` |
| Transport / GoRide / … | `transport` (or the matching module) |

If `folder_paths` map to **two modules**, **stop**. Ask them to split the CSV
/ id list. Mixed PDGs poison the knowledge base (wrong package, groups,
deeplinks, TDP prompts).

`module-profile.sh` still derives `PACKAGE`, `BASE_CLASS`, `SAMPLE_TEST` from
that module. Do not hardcode a table of packages.

## Bucket (where the Java file goes)

Inside the PDG, a **bucket** is the existing test directory that owns that
flow — not "the whole gofood module."

Resolve in this order:

1. `folder_path` last segment → directory name (`GoFood - Group Order` →
   `groupOrder`, `GoFood - Discovery` → `discovery`).
2. A directory under `$MODULE/src/test/java/**/tests/` whose name or existing
   class titles match the folder / case titles.
3. If nothing matches: ask. Do not invent a third top-level package.

Echo before any emit:

```
PDG: gofood
  Bucket B1 groupOrder/  (folder GoFood - Group Order): TC-614398, TC-614401
    class → io.gojek.gofood.tests.groupOrder.GroupOrderDeadlineNudgeTests
    kb    → groupOrder/ → module login stem → nav_index (if thin) → CSV
    pioneer (if device): TC-614398
  Bucket B2 discovery/  (folder GoFood - Discovery): TC-590728, TC-590926
    class → io.gojek.gofood.tests.discovery.DiscoveryReleaseNlpTests
    kb    → discovery/ → module login stem → nav_index (if thin) → CSV
    pioneer (if device): TC-590728
```

**One class per bucket**, in that directory, next to its sample test.
Discovery cases never land in `groupOrder/`.

Split a bucket further only when two cases share **fewer than half** of their
non-setup steps (same rule as `nlp-codegen/references/pioneer.md`). A second
stem in Group Order (landing vs checkout) = a second class in `groupOrder/`,
and a second pioneer if device mode is on.

## Knowledge base (keep it narrow)

For each bucket, harvest **in this order**:

1. Existing tests in **that directory** (quoted labels, deeplinks, TDP
   prompts, `if visible` guards, API helpers like `GroupOrderControllers`).
2. Module-level login stem only (backdoor login, `setMockLocation`, shared
   cancel / tooltip guards already used across the module).
3. **`nav_index/tapmind/<module>.json`** (aep-mobile) when (1)–(2) do not
   answer deeplink URI, checkout entry, or navigation — see
   [nav-index.md](nav-index.md). Lookup by bare case id or `nav-step` keyword;
   never read the whole file.
4. CSV `steps` / `expected` — **unquoted** if never seen in (1)–(3).

Do not copy Group Order shared-cart helpers into a Discovery method. Do not
invent `Lewati` / `Allow`. Do not invent a deadline API that
`GroupOrderControllers` does not have — leave a `// kb-only hole` comment.

`suiteId` / `projectId` / `countryName` come from the **sample test in that
directory** (Discovery uses `DISCOVERY_SUITE_ID`; Group Order uses
`GO_SUITE_ID`). Do not mix them.

## Pioneer pick (inside one bucket)

Same as `nlp-codegen/references/pioneer.md`: longest shared stem, P0 over P1,
prefer a case that still logs in.

**One pioneer per bucket.** Three Discovery + three Group Order = **two**
device runs, not one. Device-pioneer is expensive; echo the count before
starting:

```
Device pioneer will run 2 cases (one per bucket). Continue?
```

A STOPPED pioneer does not clone that bucket. Other buckets are independent.

## reuse-pioneer

Only when the user pastes a `@Test` / `trace.json` that is **not already**
in the `tapmind-mobile-tests` checkout. If the stem is already in that
bucket's directory, `kb-only` is the right mode — do not ask them to paste
a file that is sitting on disk.
