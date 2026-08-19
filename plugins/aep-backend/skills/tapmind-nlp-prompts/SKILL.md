---
name: backend-tapmind-nlp-prompts
description: >-
  Reference for writing or fixing real TapMind NLP test-step prompts —
  `TapMind.runStep(...)` / `TapMind.assertStep(...)` calls against the
  com.tapmind.sdk.TapMind client SDK. Use only when the user is explicitly
  writing/debugging a TapMind prompt, or mentions TapMind, runStep,
  assertStep, bind_select, "entry where", verify-only steps, or a TapMind
  prompt that isn't parsing/asserting as expected. This is the actual
  TapMind SDK grammar — not the Allure `@Step("Given/When/Then ...")`
  descriptive-label convention used by backend-test-code-generator /
  backend-test-code-validator, which is a separate, unrelated convention
  despite the similar name. Not a general test-writing or API-scaffolding
  skill.
---

# TapMind NLP Prompt Writing

This is the **single canonical guide** for writing `TapMind.runStep(...)` prompts against the
real TapMind control-plane SDK. It assumes no prior knowledge of TapMind or its backend — if
you can write a plain English sentence, you can write a TapMind prompt.

> **Not the same thing as `backend-test-code-generator`'s "TapMind NLP conventions".** That
> skill's `@Step("Given/When/Then ...")` annotations are Allure reporting labels on
> traditionally-written Java (typed POJOs, `assertThat(...)`, `tdpClient.resolve(...)`) — they
> never call the real `TapMind.runStep(...)` SDK method. This skill documents the actual SDK
> grammar. If you're trying to make generated GBT test code actually invoke TapMind, that's a
> separate, not-yet-done integration — not covered here.

## 0. What TapMind actually does (30-second version)

TapMind is a test SDK + backend service. Instead of writing Java/RestAssured code for every
API call, you write **one plain-English sentence** describing the action (and optionally what
to check), and pass it to `TapMind.runStep("...")`. Under the hood, TapMind:

1. Reads your sentence and figures out which API it maps to.
2. Calls that API for you.
3. Runs any checks you described (`verify: ...`).
4. Fails the test (like a normal assertion) if a check doesn't match.

You never write the HTTP call yourself — you only describe what should happen, in the exact
phrasing patterns below. **The phrasing matters** — TapMind is a planner, not a general
chatbot, so it only reliably understands the sentence shapes documented here.

## 1. Minimal setup (once per test class)

```java
@BeforeMethod(alwaysRun = true)
public void beforeMethod(Method method) throws Exception {
    System.setProperty("tapmind.pdg", "transport"); // your PDG/squad
    TapMind.setUp(method);
}
```

Then, inside a `@Test` method, just call:

```java
TapMind.runStep("Get a customer from TDP");
```

---

## 2. Quick reference: types of `runStep` calls

| # | Purpose | Phrasing / SDK signature | Example |
|---|---|---|---|
| 1 | Standard action + optional check | `runStep("<action> \| verify: <check>")` | `runStep("Get a customer from TDP");` |
| 2 | Poll until a state changes | `runStep(prompt, maxAttempts, intervalMs)` | `runStep("fetch booking ... verify status is confirmed", 5, 3000);` |
| 3 | Search a list & save a value | `save <field> from the <list> entry where <field> equals <value> as <var>` | `runStep("save token from payment_options entry where type equals GOPAY_WALLET as token");` |
| 4 | Verify-only (reuse previous response) | Starts with `verify`/`assert`/`validate`/`check`/`expect` | `runStep("Verify booking status is CONFIRMED");` |
| 5 | Direct DB / Redis / Kafka call | `run query ...` / `run redis ...` / `produce to kafka ...` / `consume from kafka ...` | `runStep("Run redis GET 'driver:active_session:123'");` |
| 6 | Pin to a specific PDG / service | `runStep(prompt, pdg)` / `runStep(prompt, pdg, targetServiceId)` | `runStep("Get driver details", "transport-pdg", "driver-service");` |
| 7 | Assert with a custom failure message | `assertStep(prompt, failureMessage)` | `assertStep("Verify status is 200", "Order creation failed!");` |

---

## 3. Detailed guide by call type

### 3.1 Standard action + optional inline check

```
<action description> | verify: <what to check>
```
```java
runStep("Get a customer from TDP");
runStep("Create a CASH booking | verify: status is 200 and $.order_number starts with 'RB-'");
```
> If there's no `verify` clause, the step still runs but asserts nothing — it will PASS even
> if the call errors. Only add `verify` when you actually want this step to fail on a bad
> response.

**Saving a plain top-level field (not inside a list):** just say `save $.path as <name>` — do
**not** use "entry where" here, that phrase is only for searching inside an array (§3.3).

```java
runStep("Get a customer from TDP and save $.data.customer_id as custId");
```

Match the phrasing to the actual data shape: scalar/top-level field → `save $.path as name`;
value inside a list → `entry where field equals value` (§3.3). Using the wrong one for the
shape you actually have is a common source of a prompt silently not parsing as intended.

### 3.2 Polling / retry (`runStep(prompt, maxAttempts, intervalMs)`)

Use for eventually-consistent state transitions (e.g. waiting for a booking to move from
`BOOKED` to `CONFIRMED`).

```java
runStep("fetch booking details for the saved order number using saved customer token and verify '$.body.booking.status' is confirmed", 5, 3000);
```
> **Must include the fetch action itself.** Do NOT poll a verify-only prompt like
> `"Verify status is X"` — verify-only prompts just re-judge the same frozen response from the
> previous step, so polling it repeats the same stale check instead of re-fetching.

### 3.3 Array search & save (`bind_select`)

Use this whenever the value you need lives *inside a list*, and you need to find the right
entry first — not a plain dotted path.

```
save <field to extract> from the <list name> entry where <filter field> equals <filter value> as <variable_name>
```
```java
runStep("Verify payment_options contains type GOPAY_WALLET; save token from the payment_options entry where type equals GOPAY_WALLET as gopay_token");

// Filtering by a value saved earlier
runStep("save driver_name from the drivers entry where driver_id equals ${memory.saved_driver_id} as matched_driver_name");
```

**Nested (two-level) array search** — e.g. pick an estimate by `service_type`, then a payment
method inside it by `payment_method_type`:
```
"save the pricing_token from the estimates entry where service_type equals 1, then from its payment_methods entry where payment_method_type equals CASH"
```

> **Always use the phrase "entry where [field] equals [value]".** Don't write
> `payment_options.type` — TapMind needs the word **"entry"** to know you're searching a list.
> When the filter value is itself a saved variable, wrap it as `${memory.variableName}` — never
> quote it as a literal string like `'paymentMethod'` (that searches for the literal text
> `paymentMethod`, not the value you saved, and silently returns nothing).

**Presence-only check** (confirm a match exists, without saving anything):
```java
runStep("verify payment_options contains an entry with type GOPAY_WALLET");
```

### 3.4 Verify-only steps (reuse the previous response, no re-fetch)

If a previous step already called an API and you only want to assert something on that same
response, start the prompt with one of these five words:

**`verify` / `assert` / `validate` / `check` / `expect`**

```java
runStep("Create a CASH booking");                                   // Step 1: makes the call
runStep("Verify the booking status is CONFIRMED and $.order_number is not null"); // Step 2: checks it, no new call
```
> The prompt **must start directly** with one of those 5 words. `"Please verify..."` or
> `"Can you check..."` will NOT be treated as verify-only — TapMind will plan it as a brand-new
> API call and may re-fetch (possibly getting different data).

### 3.5 Direct tool execution (DB / Redis / Kafka)

These skip the usual "which API is this" planning and go straight to the named tool. The
prompt must start with the exact prefix.

```java
runStep("Run query 'SELECT status FROM drivers WHERE driver_id = ''957378666''' on DB 'driver_service'");
runStep("Run redis GET 'driver:active_session:957378666'");
runStep("Produce to kafka topic 'driver-location-events' with key '${memory.driverId}' and payload '{\"lat\": -6.2, \"long\": 106.8}'");
runStep("Consume from kafka topic 'order-status-events' where order_id equals ${memory.orderNumber}");
```

### 3.6 Pin a step to a specific PDG / service

If TapMind resolves the wrong API for your prompt, or you know exactly which service it should
hit, pin it explicitly:

```java
TapMind.runStep(prompt, pdg);
TapMind.runStep(prompt, pdg, targetServiceId);
TapMind.runStep(prompt, pdg, targetServiceId, maxAttempts, intervalMs);
```
```java
runStep("Get customer profile", "transport-pdg");
runStep("Fetch driver location", "transport-pdg", "driver-tracking-service");
```

### 3.7 Assert with a custom failure message

`assertStep` wraps `runStep` — if the step fails, you get a clean assertion message instead of
a generic error.

```java
TapMind.assertStep(prompt, failureMessage);
TapMind.assertStep(prompt, pdg, failureMessage);
```
```java
assertStep("Verify order created successfully with 200 code and $.order_number starts with 'RB-'",
           "Booking creation failed or returned an invalid order number!");
```

---

## 4. Memory: saving and reusing values

Every value you `save ... as <name>` in a prompt is stored in memory for later steps, or from
plain Java:

```java
saveMemory("bookingId", "BK-100234");
String bookingId = TapMind.getValueFromMemory("bookingId");
String bookingId = TapMind.getValueFromMemory("bookingId", "defaultIfMissing");
```

Reference a saved value inside a later prompt with `${memory.<variable_name>}` — always use
the **exact name** you saved it as. A guessed/hallucinated name won't match anything TapMind
actually stored. This isn't just a style rule: the planner only sees the keys actually bound
so far in that conversation (`available_memory_keys`) and will refuse to invent a name that
isn't in that list — so an unbound `${memory.x}` fails at plan time, not silently.

---

## 5. TDP fixture calls ("Get a customer/driver from TDP")

For TDP fixture steps, TapMind's response only actually contains `accessToken` and
`customerId`/`driverId`. **Only assert on those two fields.** Asserting anything else (e.g.
`vehicle_type`) fails with a vague `NEEDS_REVIEW` instead of a clean failure, because that
field was never in the response to begin with.

---

## 6. "One of" multiple allowed values

If a field can legitimately be one of several values, group them into a single check —
never write it as separate `verify` clauses for the same field (those get ANDed together and
will always fail, since a field can't equal two things at once).

```java
// Wrong — always fails
runStep("verify status is ACTIVE and verify status is PENDING");

// Right
runStep("verify status is one of ACTIVE, PENDING, or COMPLETED");
```

---

## 7. Handling secrets (auth tokens, client secrets, etc.)

API specs never store secrets. If an API needs one, fetch and save it in Java **first**, then
reference it in the prompt via `${memory.<key>}` — never paste the raw secret into the prompt
string itself.

```java
saveMemory("clientSecret", System.getenv("SOME_SECRET_ENV_VAR")); // TODO: load from your actual secrets source, don't hardcode
runStep("Hit login methods api with phone_number +628210274599, country_code 62 and header X-ClientSecret as ${memory.clientSecret}");
```

---

## 8. Editing request shape inline (headers / query params)

You can tweak the request for a single call directly in the prompt — no need to touch the API
spec:

```java
runStep("Hit get order api without any order_number param");                       // drop a query param
runStep("Hit estimate api with token as customer_token and header X-AppVersion:4.78.0"); // add/override a header
runStep("Hit estimate api with only header 'X-AppVersion'");                        // send ONLY this header (drops the rest)
```

### 8.1 Overriding nested / cross-referenced array fields in the body

Some endpoints need the same value written to several nested fields at once — e.g. an
array of objects, or fields that cross-reference each other by id/name across different
parts of the body. Describing the intent with one generic field name (e.g. "template_name")
only overrides a field with that *exact* key. It will NOT propagate into nested/array
fields that use a different key name, even if they logically hold "the same" value — those
fields silently fall back to the spec's example values instead of failing.

**How to spot it:** after running, check the executor log for a line like:
`references identifier(s) [...] that are not defined by any 'name'/'id' entry elsewhere
in the request body — likely a partially filled array`. That WARN means your override
landed on the wrong field, and the fields that actually needed the value are still using
spec examples.

**Fix:** don't rely on one generic field name — name the exact JSON key path for every
field that must carry the value:

```
Create <resource> with <arrayA>[<idx>].<key> = ${memory.value}, <arrayB>[<idx>].<key> = ${memory.value}, ...
```

(e.g. for a create-template endpoint where `templates[0].id/en/default` must all match a
`name` inside `whatsapp_templates[]`, you'd set each of those six paths individually to
`${memory.templateName}` rather than saying "template_name = ...".)

This indexed-path override isn't a formally documented grammar feature (unlike header/query
param edits above) — it works because the planner matches literal key names. Always verify
against the executor log after running; don't assume it took effect.

---

## 9. Response schema validation

Two independent mechanisms — know which one applies to your API:

1. **Automatic** — only for APIs ingested from an OpenAPI/Swagger spec. You don't write
   anything; schema validation runs on its own. Does **not** apply to curl-ingested APIs.
2. **Explicit (works for any API)** — bring your own JSON Schema file and call it directly:
   ```java
   TapMind.verifySchema("src/test/resources/schemas/booking-response.schema.json", TapMind.getLastResponseBody());
   ```
   Throws an `AssertionError` with the exact violations if the response doesn't match.

---

## 10. Common mistakes to avoid

| Don't write | Write instead | Why |
|---|---|---|
| `data.payment_options.type equals GOPAY` | `payment_options entry where type equals GOPAY` | TapMind needs the word **"entry"** to know it's searching a list. |
| `verify state is A and state is B` | `verify state is one of A, B` | Separate checks are ANDed — always fails for a single field. |
| Guessed variable name, e.g. `as customerToken` when you never saved it | The exact name used in the earlier `save ... as <name>` | Hallucinated names won't match what was actually stored. |
| `[?(@.type=='paymentMethod')]` (quoting a variable name as a literal) | `entry where type equals ${memory.paymentMethod}` | Quoting filters for that literal text, not the saved value — matches nothing, silently saves empty. |
| `"Please verify status is 200"` after an earlier fetch | `"Verify status is 200"` | Only prompts that **start with** verify/assert/validate/check/expect are verify-only; extra words in front cause a needless re-fetch. |
| `runStep("Verify status is 200", 5, 2000)` (polling a verify-only prompt) | `runStep("fetch order details ... and verify status is 200", 5, 2000)` | Verify-only prompts don't re-fetch, so polling just re-checks the same stale response. |
| Asserting `vehicle_type` on a "Get a customer/driver from TDP" step | Only assert `accessToken` / `customerId` / `driverId` | Other fields aren't in the TDP response — see §5. |
| Pasting a raw secret into the prompt string | `saveMemory(...)` first, then `${memory.<key>}` in the prompt | See §7. |
| Loading strict assertions onto a shared setup step (e.g. a "create booking" step other scenarios also reuse as a precondition) | Keep setup steps assertion-free (or a bare `status is 200`); put the detailed checks in the dedicated verify-only step for that specific scenario | Over-asserting a shared step breaks reuse by other scenarios (e.g. negative tests) that need that same step's evidence to look different. |
| `data.whatsapp_templates.provider is X` (dotted path into a list) | `whatsapp_templates contains an entry with provider X` | Same "entry" rule as above — a scalar dotted path can't reach into a list. |
| One generic field name (e.g. "template_name = X") when the schema actually needs the value on several nested/cross-referenced fields | Name each real field path explicitly: `arrayA[0].key = X, arrayB[1].key = X, ...` | A generic/wrapper field name only overrides an exact key match — nested or cross-referenced fields with different key names silently keep spec-example defaults instead of erroring. See §8.1. |
