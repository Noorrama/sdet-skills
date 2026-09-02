# Step & fixture reuse — shared helpers

Companion to `GENERATION.md` §5 and `SKILL.md` §G.B.4 / §1.5. Avoid copying the same
`TapMind.runStep(...)` lines into every `@Test`. Applies to **both intake paths** after TDP
is resolved, and to **any** repeated step — TDP fixtures, auth preambles, create/fetch flows,
gRPC invokes — not only TDP.

## Problem (observed in gofood `tests/tapmind_backend/`)

**Fixture / TDP (same string everywhere):**

```java
TapMind.runStep("Get a customer from TDP and save accessToken as customerToken and save customerId as customerId");
TapMind.runStep("Get CUSTOMER_WITH_GO_PAY and save accessToken as hostNoGroupBearerToken …");
TapMind.runStep("Get me a merchant enabled for GoFood group order and save restaurantId as restaurantId", "TDP");
```

**Non-TDP patterns (same shape, different verify):**

```java
// Auth preamble repeated on every markdown test
TapMind.runStep("Call redemption API with header Authorization: saved customerToken and header User-ID: saved customerId for scenario … | verify: …");

// Group-order flow prefix shared across lifecycle tests
TapMind.runStep("Create a group order session with billing_type EVERYONE_PAYS_EQUALLY, restaurant_id saved restaurantId, header Authorization: saved hostNoGroupBearerToken and save $.id as sessionId | verify: …");
TapMind.runStep("Get group order session details for saved sessionId with header Authorization: saved hostNoGroupBearerToken | verify: …");
```

`GoFoodTapMindTestBase` centralises `setUp` / `tearDown` — **repeated step sequences belong
in named helpers**, not inlined per method.

---

## Step-pattern types (what to dedupe)

| Type | Example | Extract when |
|---|---|---|
| **Fixture / TDP** | `Get a customer from TDP…` | Identical in 2+ tests |
| **Auth bundle** | Same `header Authorization: saved X and header User-ID: saved Y` on same service | Same keys + service in 2+ prompts — helper runs fixed prefix or documents keys |
| **Resource create** | Create session/booking + `save $.id as sessionId` | Same create intent + save key; **verify may differ** → helper without verify, or parameter |
| **Resource fetch** | `Get group order session details for saved sessionId…` | Identical fetch (no verify, or shared verify) in 2+ tests |
| **Multi-step prefix** | Steps 1–3 identical, step 4 differs | Extract steps 1–3 as one helper; tests add tail steps |
| **gRPC + auth setup** | Customer TDP then grpc.invoke with `saved customerId` | Shared invoke preamble only |

---

## When to extract (suite convert / hand-write)

| Signal | Action |
|---|---|
| **Identical** `runStep` string in 2+ `@Test` methods (same class or package) | `protected void …()` on `*TapMindTestBase` |
| **Same prefix** before `\| verify:` (or before scenario-specific tail) in 2+ prompts | Helper for prefix; test adds verify/tail inline |
| Same **step sequence** (2+ consecutive prompts) in 2+ scenarios in one `scenario_group` | `setupGroupOrderSession()` style multi-step helper |
| Same `test_data[].required_state.category` + save keys across approved scenarios | One fixture helper per fixture family |
| **Different** verify clause only | Shared helper **without** verify; each `@Test` adds its own verify step (§10) |
| Different memory keys, TDP category, or negative vs happy path | **Separate** helpers — do not merge |
| Scenario-specific `verify:` on a step other tests reuse differently | Do not use shared `@BeforeMethod` |

---

## Detecting common patterns (batch generation)

When converting multiple approved scenarios for one module:

1. **Collect** all `prompts[]` per scenario (post-verify).
2. **Fingerprint** each prompt:
   - normalise whitespace;
   - optional: strip `| verify: …` for prefix matching;
   - optional: replace scenario-specific phrases (`for scenario X`) with `{{SCENARIO_TAIL}}`.
3. **Count** fingerprints across the batch (group by `scenario_group`, endpoint, or target class).
4. **Extract** any fingerprint or **prefix chain** appearing **≥ 2** times:
   - exact duplicate → single-step helper;
   - shared first *N* steps → multi-step helper;
   - shared auth + service pin (`"gofood", "gofood-markdown"`) → document in helper name.
5. Emit **`sharedHelpers[]`** (see artifact below) + per-test **`helper-call`** lines.

Do **not** merge prompts that differ in save keys, PDG/service pin, or request body shape.

---

## Helper patterns (prefer in order)

### 1. Protected method on module base (recommended)

```java
// base/GoFoodTapMindTestBase.java
protected void provisionDefaultCustomer() throws Exception {
    TapMind.runStep(
        "Get a customer from TDP and save accessToken as customerToken and save customerId as customerId");
}

protected void provisionHostNoGroupAndGroupOrderMerchant() throws Exception {
    TapMind.runStep(
        "Get CUSTOMER_WITH_GO_PAY and save accessToken as hostNoGroupBearerToken and save customerId as hostNoGroupUserId");
    TapMind.runStep(
        "Get me a merchant enabled for GoFood group order and save restaurantId as restaurantId", "TDP");
}

/** Create session — no verify; caller asserts in following steps. */
protected void createGroupOrderSessionEveryonPaysEqually() throws Exception {
    TapMind.runStep(
        "Create a group order session with billing_type EVERYONE_PAYS_EQUALLY, restaurant_id saved restaurantId, "
            + "header Authorization: saved hostNoGroupBearerToken and save $.id as sessionId",
        "gofood", "gofood-meal-scheduler");
}

protected void fetchGroupOrderSessionDetails() throws Exception {
    TapMind.runStep(
        "Get group order session details for saved sessionId with header Authorization: saved hostNoGroupBearerToken",
        "gofood", "gofood-meal-scheduler");
}
```

```java
// @Test — compose helpers + scenario-specific verify
public void sc024_lifecycle_departed_participant() throws Exception {
    provisionHostNoGroupAndGroupOrderMerchant();
    createGroupOrderSessionEveryonPaysEqually();
    TapMind.runStep("Make booking for group order session saved sessionId … | verify: …", "gofood", "gofood-meal-scheduler");
    fetchGroupOrderSessionDetails();
    TapMind.runStep("Verify social_group is populated and members_count equals two");
    // …
}
```

### 2. Parameterised tail (verify differs)

When only the verify clause or scenario label differs:

```java
protected void callRedemptionApi(String scenarioTail, String verifyClause) throws Exception {
    TapMind.runStep(
        "Call redemption API with header Authorization: saved customerToken and header User-ID: saved customerId "
            + scenarioTail + " | verify: " + verifyClause,
        "gofood", "gofood-markdown");
}
```

Prefer **separate `@Test` methods** with one clear verify each over one overloaded helper —
unless the batch is large and tails are truly data-driven.

### 3. `@BeforeMethod` (narrow use)

Only when **every** test in the class needs the **same** steps with **no** per-test verify:

```java
@BeforeMethod(dependsOnMethods = "setUpTapMind", alwaysRun = true)
public void provisionFixtures() throws Exception {
    provisionDefaultCustomer();
}
```

Do **not** use for flows where tests diverge after step 2 (session create vs booking-only).

### 4. Java `saveMemory` when plan payload exists

When `test_data_payloads` / enriched `test_data_output` is present for approved scenarios
(`NLP_COVERAGE.md`), load tokens in the helper instead of re-fetching TDP.

---

## Batch artifact: `sharedHelpers[]`

```json
{
  "className": "LifecycleTapMindTests",
  "sharedHelpers": [
    {
      "method": "provisionHostNoGroupAndGroupOrderMerchant",
      "on": "GoFoodTapMindTestBase",
      "kind": "fixture",
      "prompts": ["Get CUSTOMER_WITH_GO_PAY …", "Get me a merchant …"],
      "usedBy": ["SC-GOFOODSGM5-002", "SC-GOFOODSGM5-024"]
    },
    {
      "method": "fetchGroupOrderSessionDetails",
      "on": "GoFoodTapMindTestBase",
      "kind": "fetch",
      "prompts": ["Get group order session details for saved sessionId …"],
      "usedBy": ["SC-GOFOODSGM5-002", "SC-GOFOODSGM5-024", "SC-GOFOODSGM5-040"]
    }
  ]
}
```

| Line `kind` | Java |
|---|---|
| `helper-call` | `provisionDefaultCustomer();` / `fetchGroupOrderSessionDetails();` |
| `step` | Scenario-specific `TapMind.runStep(...)` only |

(`fixture-call` is an alias for `helper-call` in older artifacts.)

---

## Readability checklist

- [ ] No identical `runStep` in 2+ `@Test` without a shared helper
- [ ] No repeated **multi-step prefix** without a multi-step helper
- [ ] Shared helpers omit scenario-specific `verify:` — asserts stay in the test
- [ ] Memory keys stable and documented on the helper
- [ ] Base: `setUp`/`tearDown` + helpers; test class: `@Test` + composition only
