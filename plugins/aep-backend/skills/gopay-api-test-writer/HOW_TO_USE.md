# How to use the gopay-api-test-writer skill

This skill lives at `.claude/skills/gopay-api-test-writer/` in this repo and teaches Claude
the layered test convention used under `gopay/src/test/java/userJourneyTests/userspend/**`
(the pattern visible in `miniapp` and `parking`). You don't need to invoke it by name — Claude
picks it up automatically once it recognizes you're asking for a new API test in this repo.

This file documents the request format that works best in practice: folder first, then the
curl, then the scenarios — which can be either a plain paste of test case IDs/titles/types
copied straight out of BrowserStack (or TestRail, Zephyr, etc.), or a plain paste of acceptance
criteria from a PRD/spec doc (optional, no IDs required). No reformatting needed on your end
either way.

## The three things to paste

**1. Target folder** — where the test file should live, e.g.

```
userJourneyTests/userspend/miniapp/globalsearch/cgsa
```

Say if you want a specific file name (e.g. `ContactBasedSearchTest.java`); otherwise Claude
names it after the feature. This also tells Claude whether it's adding to an existing feature
(reusing the Endpoint/RequestBody/Response/Client/Helper already there) or scaffolding a new
one from scratch.

**2. The curl (+ sample response)** — paste the full curl exactly as you'd run it, headers and
all, plus a sample JSON response body. Claude reads the URL, method, headers, and request/response
shape directly off of this — it does not need you to translate it into any particular format.

```
curl --location 'http://.../v1/global/search' \
--header 'Content-Type: application/json' \
--header 'gojek-country-code: ID' \
--header 'go-user-id: 2744181' \
--data '{ "search_term": "+91", "search_id": "...", "contacts_count": 0 }'
```

```json
{ "success": true, "data": { "results": [ { "search_items": [ { "id": "...", "title": "...",
"category": { "category_name": "Contact" } } ] } ] } }
```

If a field in the sample response doesn't exist yet in the repo's Response POJO (e.g. a new
`sub_icon_url` field), Claude will add it rather than drop it silently.

**3. Scenarios — either a test case list, or PRD acceptance criteria (optional)**

You can hand this over in either form:

- **Test cases, pasted as-is from BrowserStack/TestRail** — just paste the block copy exactly
  as it comes out of the tool, one case after another. The three-line ID / title / type pattern
  is enough for Claude to parse without you reformatting it into a table or list:

  ```
  TC-713964
  Verify search, when contact count is set to zero
  smoke
  TC-713840
  Verify Search, when passing contact no in Search_term
  Regression
  ```

  Claude turns each block into one `@Test` method: the ID becomes `testCaseIds = {"713964"}` in
  `@TestInfo`, the title becomes the basis for the method name and the assertions, and
  smoke/regression sets the `Categories` tag (`Categories.DISCOVERY_3PD_SMOKE` /
  `Categories.DISCOVERY_3PD_REGRESSION` or the equivalent for the domain).

- **Acceptance criteria from a PRD (optional, no IDs needed)** — instead of a formatted case
  list, you can just paste the acceptance-criteria bullets (or a paragraph) straight out of the
  PRD/spec doc, e.g.:

  ```
  Acceptance Criteria:
  - Given contacts_count = 0, the response must not contain any item with category_name "Contact"
  - Given contacts_count > max cap, API returns 400
  - Given contacts_count is omitted, request should still succeed with 200
  ```

  Claude reads each distinct "given/should/must/when X then Y" statement as one scenario and
  generates one `@Test` method per scenario, same as it would for a pasted case list. Since
  there's no TestRail ID attached to a PRD bullet, Claude leaves a clearly marked placeholder in
  `testCaseIds` (never a fake-looking number) and tells you it needs a real ID before this can
  ship. If the acceptance criteria are ambiguous or could reasonably be split into more than one
  test, Claude will restate the scenario breakdown it's about to code, so you can correct it
  before any files get written.

## What happens if a test case needs a business number or fixture Claude can't guess

Some test titles imply a concrete value that isn't in the curl or the response — "for max
contact_count", "non integer value", "exceeds max cap". Claude will not invent numbers like
these; it'll ask you directly (e.g. "what's the actual max cap and min value?") rather than
picking something plausible-looking. Same for anything environment-specific, like a contact
name that has to actually exist in a test user's synced contacts — Claude will drop in a
clearly marked `TODO` placeholder and flag it instead of making one up.

For the pass/fail assertions on invalid-input scenarios (negative values, wrong types,
missing fields), if you don't hand over the exact expected error code/message, say so up front
("just check status code + success flag for now") — otherwise Claude will ask.

## Example, start to finish

> I need new API tests under `userJourneyTests/userspend/miniapp/globalsearch/cgsa`. Here's
> the curl: `curl ... /v1/global/search ...`. Response looks like `{...}`. File name:
> ContactBasedSearchTest.java.
>
> TC-713964
> Verify search, when contact count is set to zero
> smoke
> TC-713840
> Verify Search, when passing contact no in Search_term
> Regression
> [... more cases ...]

Claude will: check whether `cgsa` already has an Endpoint/RequestBody/Response/Client/Helper
for this API (it usually does, once one test class exists for a feature) and reuse it; extend
the RequestBody/Response POJOs only for fields the curl/response introduce that aren't there
yet; write one `@Test` per pasted case; and ask you for anything it can't responsibly guess
(numeric bounds, real fixture data, expected error contracts) before finishing.

## Example using PRD acceptance criteria instead of a case list

> New tests under `userJourneyTests/userspend/miniapp/globalsearch/cgsa`. Curl:
> `curl ... /v1/global/search ...`. Response looks like `{...}`.
>
> Acceptance Criteria:
> - Given contacts_count = 0, response must not contain any "Contact" category item
> - Given contacts_count = N (1-20), response must contain exactly N "Contact" category items
> - Given contacts_count exceeds the max cap, API returns 400

Claude will derive three scenarios from these bullets, restate them back
("count=0 -> zero Contact items, count=N -> N Contact items, count>max -> 400"), then write one
`@Test` per scenario with a placeholder `testCaseIds` (since PRDs don't carry TestRail IDs) and
flag that a real ID is still needed.

## What you still need to fill in afterward

- **New `CustomerGroup` enum values**, if a scenario needs a test user type that doesn't exist
  yet — provisioning that user pool happens outside this repo.
- **New `Categories.kt` constants**, if the domain/tag doesn't have one yet (Claude will add
  the constant, but check it doesn't collide with anything already in flight from a teammate).
- Anything marked `TODO` in the generated code — usually environment-specific fixture data.

## After the code is written

Ask Claude to compile-check the new/changed files, or run the relevant Gradle test task
yourself:

```
./gradlew :gopay:test --tests "userJourneyTests.userspend.<domain>.<feature>.*"
```

If something looks off (wrong header, wrong error shape, wrong package), just tell Claude what
to change — it'll check the sibling classes in the same package before guessing again.
