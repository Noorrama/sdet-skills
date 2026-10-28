# nav_index — deeplink & workflow fallback (agentic)

Use when the enriched scenario is **thin**: empty or sparse `automation_steps[]`,
vague navigation in `steps[]`, or missing deeplink in the plan but the case id
exists in BrowserStack.

## Harvest ladder (mandatory order)

For each cluster (or each emitted class), resolve **before** inventing steps:

1. **Subdirectory / package stem** in `tapmind-mobile-tests` for this flow — tests
   near `$SAMPLE_TEST`, or under the directory `module-profile.sh` implies
   (`groupOrder/`, `driverApp/`, …). Copy `Deeplinks.*`, guards, `scrollToText`,
   login phrasing.
2. **Module login stem** — shared backdoor / mock location / tooltip guards across
   that Gradle module (same as kb-only in sibling-emit).
3. **`config/nav_index/tapmind/<module>.json`** on the **mobile QA plugin** —
   proven `tapmind_steps` keyed by BrowserStack **bare** case id (`705875`, not
   `TC-705875`). Use **`scripts/corpus_lookup.py`** — never Read the full JSON.
4. **Enriched plan** — `automation_steps[]`, `preconditions_metadata`, fixture
   `test_buddy_prompt`; **`change_context.json`** deeplinks/locators/flags.
5. Plain `steps[]` English only when (1)–(4) still leave gaps — keep labels
   **unquoted** unless proven in (1)–(3).

Never skip (1)–(2) because nav_index exists. nav_index **fills gaps**; it does
not override a disagreeing sample test in (1).

## Plugin paths (Prodigy / monorepo)

Mobile QA plugin root = same as `nlp-codegen` (`qa-mobile-toolkit` / `aep-mobile`):

```
config/nav_index/tapmind/<module>.json
config/nav_index/tapmind/project_map.json
scripts/corpus_lookup.py
```

Resolve module id (`gofood`, `driverApp`, …) from `change_context.app` / plan app
+ `module-profile.sh`.

## Lookup commands

```bash
ROOT="$(bash "${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-${TAPMIND_PLUGIN_ROOT:?}}}/scripts/plugin-root.sh")"
PY="$ROOT/scripts/corpus_lookup.py"
MOD=gofood   # example

# Scenario browserstack_case_id → bare id
python3 "$PY" case tapmind "$MOD" 705875

# Keyword when steps are thin
python3 "$PY" nav-step tapmind "$MOD" "checkout" 8
```

Echo in pre-emit summary when nav_index contributed:

```
nav_index: SC-003 case 705858 → deeplink stem from indexed TC-556941
```

## Map `tapmind_steps` → emit

Same as release: `login` → backdoor; `deeplink` → `openDeeplink`; `nlp` → per
[step-emit.md](step-emit.md); toggles/network → direct-api-map.

If nav_index and plan disagree on **entry**, prefer plan deeplink /
`change_context` when present; else nav_index when bucket has no pattern.

## No indexed row

New plan scenarios may have no nav_index row. Rely on (1)–(2) + plan +
`change_context`; use **device-pioneer** once per cluster to harden. Note
`// kb-only: no nav_index for <browserstack_case_id>` when workflow stays open.
