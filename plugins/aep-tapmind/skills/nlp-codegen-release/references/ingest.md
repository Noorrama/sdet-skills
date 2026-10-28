# Ingest — CSV or BrowserStack MCP

Parent thread keeps `release_suite.json` (or a short digest). Never dump a
raw BrowserStack `listTestCases` payload into the parent.

## A. CSV (preferred when the user attached a file)

BrowserStack Test Management export. Run, do not hand-parse:

```
python3 "$ROOT/skills/nlp-codegen-release/assets/parse-bs-csv.py" "<csv>" \
  > release_suite.json
```

Write `release_suite.json` next to the CSV (or in the run folder). Do not
write it into `aep/skills`.

If `case_count` is 0 or the file has no `Test Case ID` column, stop and ask.

## B. No CSV — BrowserStack MCP

Ask once:

> No CSV attached. Is the BrowserStack MCP connected? If yes, send the test
> case ids (e.g. `TC-614398 TC-614401`) and the PDG (GoFood / Cartography).

| They said | Action |
|---|---|
| No / MCP not connected | Stop. Ask for a CSV export or the ids + a connected MCP. |
| Yes + ids | Fetch **those ids only** in a sub-agent. |

Sub-agent rules (same token discipline as charter-exploration scoping):

1. Resolve the PDG → BrowserStack project from
   `aep-mobile/config/browserstack_project_map.json` (e.g. GoFood consumer →
   `PR-176`). Do not search every project.
2. Use the MCP's case-by-id tool if it exists. Else `listTestCases` **with a
   `folder_id`** (never project-wide on PR-176) and keep matching ids.
3. Write `release_suite.json` on disk. Return only: case count, ids, titles,
   folder paths, whether any id was missing.

Missing ids → say so. Do not invent a title or step list.

`GITLAB_READ_TOKEN_FOR_AGENT` is unrelated. BrowserStack auth is the MCP
connection. Never paste a token.

## Normalize (both paths)

Each case in `release_suite.json` must have: `id`, `title`, `folder_path`,
`steps[]` (`action` + `expected`), `preconditions`, `priority`, `platform`.

CSV ingest also adds `preconditions_parsed` per case:

| Field | Source in Preconditions cell |
|---|---|
| `test_data_prompt` | Line starting with `Test Data:`, `User:`, or `TDP:` |
| `location_lat` / `location_lng` | `Location:` line with `(lat, lng)` |
| `location_label` | Full text after `Location:` |
| `not_for_tapmind` | Line starting with `Not for TapMind:` |

See [case-authoring.md](case-authoring.md). MCP fetch must populate the same
shape when writing `release_suite.json`.

Skip:

- empty `steps[]`
- `execution_mode: Manual` when that field is present
- `state` not Active (when present)

Keep Android-pending cases when the user said Android. Do not drop a case
because `TapMind Automated` is blank — that is why they are here.

Dedup later against `@TestInfo.testCaseIds` in `$MODULE` (bare number and
`TC-` form). Already present → SKIP, do not emit a third copy.
