# nav_index — deeplink & workflow fallback (release)

Use when the BrowserStack case is **thin**: missing checkout deeplink URI,
vague “navigate to …”, or steps that assume a path the CSV does not spell out.

## Ladder (authoritative order)

For each bucket, resolve setup and navigation **before** inventing steps:

1. **Bucket directory** in the `tapmind-mobile-tests` checkout  
   (`gofood/.../booking/`, `groupOrder/`, …) — real `@Test` bodies, `Deeplinks.*`,
   guards, `scrollToText`, TDP prompts.
2. **Module login stem** — shared backdoor / mock location / tooltip guards used
   across that Gradle module.
3. **`nav_index/tapmind/<module>.json`** (checked in under **aep-mobile**) —  
   proven `tapmind_steps` from indexed regression/TapMind tests (deeplink, login,
   nlp), keyed by BrowserStack **bare** case id (`705875`, not `TC-705875`).
4. **CSV / MCP `steps[]` + `preconditions_parsed`** — emit from case text; keep
   labels **unquoted** unless already proven in (1)–(3).

Never skip (1)–(2) because nav_index exists. nav_index **backs up** gaps; it does
not override a bucket sample that disagrees.

## Where the files live

Monorepo path (sdet-skills marketplace):

```
plugins/aep-mobile/config/nav_index/tapmind/<module>.json
plugins/aep-mobile/config/nav_index/tapmind/project_map.json
```

Installed **aep-mobile** plugin: `config/nav_index/tapmind/` next to
`browserstack_project_map.json`.

`_meta.warning`: `tapmind_steps` is best-effort from Java — not a guaranteed
complete script. Prefer the **same `source_file`** under the bucket when both
exist.

## Lookup (do not Read the whole JSON)

Files are large. Use **aep-mobile** `scripts/corpus_lookup.py` only:

```bash
AEP_MOBILE="$(dirname "$ROOT")/../aep-mobile"   # monorepo; adjust if plugins layout differs
PY="$AEP_MOBILE/scripts/corpus_lookup.py"

# Exact case (if indexed)
python3 "$PY" case tapmind gofood 705875

# Keyword search across indexed steps (checkout, saved address, …)
python3 "$PY" nav-step tapmind gofood "checkout" 8
python3 "$PY" nav-step tapmind gofood "saved address" 8
```

Echo in the pre-emit summary when nav_index contributed:

```
nav_index: case 705858 → no match; nav-step "checkout" → 3 hits (used deeplink stem from 556941)
```

## Mapping `tapmind_steps` → Java emit

| `kind` | Emit |
|---|---|
| `login` | `TapMind.performBackdoorLogin(...)` — strip wrapper text to the prompt inside |
| `deeplink` | `TapMind.openDeeplink(returnDeeplinkByPlatform(Deeplinks.<CONST>))` when the bucket’s `Deeplinks.java` has the same path; else literal URI from `text` after normalizing `platform://` |
| `nlp` | `runStep` / `assertStep` / `scrollToText` per **step-emit.md** (e.g. “Swipe up until” → `scrollToText(DOWN, …)`) |
| `toggle` / `network` | Direct APIs per `step-validation/references/direct-api-map.md` |

If nav_index and CSV disagree on **entry** (deeplink vs UI walk), prefer nav_index
**only when** the CSV precondition explicitly says deeplink or the bucket has no
other pattern — otherwise leave a `// kb-only: CSV vs nav_index entry` comment
and follow CSV + bucket.

## Regenerating nav_index

When `tapmind-mobile-tests` on the MR branch adds new release tests, regenerate
from **aep-mobile** (optional, not every release run):

```bash
python3 plugins/aep-mobile/scripts/regression_corpus/extract_tapmind_nav_index.py \
  <tapmind-mobile-tests> plugins/aep-mobile/config
```

New TC ids then appear under `cases.<id>` for future runs.

## When nav_index has no row

New BrowserStack ids (e.g. first-time release cases) often **will not** be indexed.
Then rely on (1)–(2) + CSV; run **device-pioneer** once per bucket to harden.
Document `// kb-only hole: no nav_index row for TC-…` when deeplink/workflow stays
open.
