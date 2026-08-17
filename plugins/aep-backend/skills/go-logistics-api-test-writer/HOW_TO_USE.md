# How to use the go-logistics-api-test-writer skill

This skill lives at `.claude/skills/go-logistics-api-test-writer/` and teaches Claude the
layered test convention actually proven across `go-logistics/src/test/java/**` — TMS, GoKilat/
consignor/store, GoSend consumer, GoBox, and GoShop. You don't need to invoke it by name — Claude
picks it up automatically once it recognizes you're asking for a new API test, Endpoint, Client,
Controller, or DTO in this module.

## The three things to give Claude

**1. Which vertical / which existing feature folder.** Either point at a folder directly
(`src/test/java/tms/shipments/`) or just give the cURL — the URL path/host tells Claude which
vertical it is (e.g. `.../gokilat/v10/...` is GoKilat/store, `.../tms/...` is TMS). This
determines which base test class chain, which Assertion class, and which sibling
Endpoint/Client/Controller files it needs to match.

**2. The cURL (or Swagger/API doc) + a sample response.** Paste it exactly as you'd run it —
headers and all — plus a sample JSON response body:

```
curl --location 'https://integration-kilat-api.gojekapi.com/gokilat/v11/driverTip' \
--header 'Authorization: Bearer <token>' \
--header 'Content-Type: application/json' \
--data '{ "order_id": "GK-123", "tip_amount": 5000 }'
```
```json
{ "order_id": "GK-123", "status": "accepted", "tip_amount": 5000 }
```

Claude reads the URL, method, headers, and request/response shape directly off this. If a field
in the sample response doesn't exist yet in the repo's response DTO, Claude adds it rather than
dropping it silently.

**3. Scenarios** — positive and negative cases, and which countries matter (`id`/`vn`/`th`,
occasionally `sg`). Two accepted forms:

- **A test case list** (pasted as-is from TestRail/BrowserStack/Zephyr) — one ID/title/type block
  per case. Claude turns each into one `@Test` method; the ID becomes the real
  `testCaseIds = {...}` in `@TestInfo`.
- **PRD acceptance criteria** (no IDs needed) — a plain paste of "given/should/must" bullets.
  Claude derives one scenario per distinct statement, restates the breakdown back to you if it's
  ambiguous, and leaves an obviously-marked placeholder (never a fake-looking number) in
  `testCaseIds` since PRD bullets don't carry a real TestRail ID.

If you only give one scenario, Claude will ask whether adjacent ones are worth covering in the
same class (unauthorized, not-found, invalid input) — this repo's convention is a positive test
paired with at least one negative test per feature.

## What Claude checks before writing anything

- `go-logistics/{KILAT,GOSEND,TMS,GOBOX}_API_TEST_MAPPING.md` — is this endpoint already covered
  by an existing test class? If so, Claude extends that class/Controller/Client instead of
  duplicating it.
- Whether the vertical already has an Endpoint/Client/Controller for this feature — if it does,
  only the DTOs get extended (for new fields) and a new `@Test` method gets added.
- Which of the two live patterns applies: the proven Java `IServiceEndpoint`/Client/Controller
  chain (the default for everything), or — only if you ask for it, or it's already the
  convention in the exact file being extended — the Kotlin `goShop` scaffold, which Claude will
  explicitly flag as unexercised by any real test today.

## What happens if a scenario needs a business number or fixture Claude can't guess

Test titles/criteria sometimes imply a concrete value that isn't in the cURL or sample response —
"exceeds max distance", "for a blacklisted consumer", "non-integer tip amount". Claude won't
invent a plausible-looking number or a made-up error string; it'll ask you directly. Same for
anything environment-specific (a phone number that must actually exist in a test pool, a
TestRail case ID) — Claude will use the repo's real pools/annotations where it can
(`LoginHelper`/`GologisticBaseHelper.provideConsumer()`, `@TestInfo`) and ask or leave a clearly
marked placeholder for anything it can't source itself.

## Example, start to finish

> New test for `POST /gokilat/v11/driverTip` under `gokilat/consignor/store/driverTipping`.
> Curl: `curl ... /gokilat/v11/driverTip ...`. Response: `{ "order_id": "...", "status":
> "accepted", "tip_amount": ... }`.
>
> TC-88213 — Verify driver tip succeeds for a valid order and amount — smoke
> TC-88214 — Verify driver tip fails with 404 for a non-existent order — regression

Claude will: check `KILAT_API_TEST_MAPPING.md` for `/gokilat/v11/driverTip` (already mapped to
`DriverTippingTest`/`DriverTippingBaseTest` in the real repo, so this would be Case 1 — extend
the existing class rather than build new layers); add one `@Test` per pasted case with the real
TestRail IDs; reuse the existing `DriverTippingBaseTest` fixtures and `DriverTippingTest`'s
existing Controller/Client call; and ask you for anything it can't responsibly guess (e.g. the
exact tip-amount validation bounds, if the criteria don't spell them out).

## After the code is written

Ask Claude to compile-check the changed files, or run the relevant Gradle task yourself:

```
./gradlew :go-logistics:runTests -Dtag=<TestGroups constant> -Denv=integration -Dcountry=id
```

If something looks off (wrong host/path pair for TMS, wrong error shape, wrong base class),
just tell Claude what to change — it will check `references/architecture.md`'s notes on that
exact subsystem (e.g. the TMS gateway-prefix quirk) and the sibling files in the same package
before guessing again.
