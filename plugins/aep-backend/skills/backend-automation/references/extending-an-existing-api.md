# Extending an already-automated API, and where a new API's tests go

Two decisions that look small, are made early, and are expensive to unpick in review:

1. The cURL targets an endpoint **already automated**, and adds a field → *extend every layer that
   builds the request.*
2. The cURL targets a **genuinely new endpoint** → *it gets its own test class, even when a sibling
   test class for a related endpoint sits right there.*

Getting either wrong produces code that compiles and reviews as "fine" until someone tries to run
it.

---

## Part 1 — A new field on an existing API

> **Adding a field to a request means walking the whole chain that builds that request. Stopping
> at the DTO is the failure mode.**

### The chain, and what "done" means for each link

Walk it in this order, and state in your summary what you did to each — including the ones you
deliberately left alone. Layer names vary per module; map them to the module's actual layout
first.

| Link | What "extend" means | Skipping it costs you |
|---|---|---|
| Request model / DTO | Add the field, keeping the class's existing Lombok/Jackson shape (see the trap below) | The field never serialises |
| Body builder / test-data builder | Add an overload that sets the new field; leave existing signatures untouched so current callers are unaffected | Tests hand-roll the DTO and drift from the module's idiom |
| Endpoint | Usually **nothing** — it passes the body through. Touch it only if the field changes a header, query param, or the path | — |
| Client | Usually **nothing** — same reason | — |
| Controller | **Check the asserted status.** Controllers pin an expected status per method. A new field with a new failure mode usually needs a different one | The test asserts the wrong status and can never pass |
| Response model | Add any new response field the scenario asserts on | The assertion has nothing to read |
| Shared assertion helper | See "Don't mutate a shared assert" below | You silently change every existing caller |
| Data provider | Add a row only if the scenario is a new input to an existing method's shape | — |

### The controller pinned-status trap

Failure-path controller methods in this repo pin exactly one status:

```java
public <X>FailureResponse create<X>Failure(...) {
    IAPIResponse resp = client.create<X>(...);
    Assert.assertEquals(resp.getStatusCode(), HttpStatuses.UNPROCESSABLE_ENTITY,  // <-- pinned
                        "Creation should have failed");
    return resp.deserialize(<X>FailureResponse.class);
}
```

If your new field introduces a **different** failure status — a 400 validation path where the
existing method pins 422 — calling this method fails before your own assertion ever runs. Add an
overload that takes the expected status; leave the existing signature alone, because its callers
depend on the pinned value:

```java
public <X>FailureResponse create<X>Failure(<X>RequestBody body, String userId, String token,
                                           HttpStatuses expectedStatus) { … }
```

**Do not** loosen the existing assertion to `assertTrue(status == A || status == B)`. That lets a
scenario expecting 400 pass on a 404 — exactly the confusion negative tests exist to catch. Some
existing controller methods do this; it's a wart to avoid copying, not a convention.

### The Lombok `@Builder` trap

Many request DTOs here carry class-level `@Getter @Setter @Builder` **plus** a hand-written
constructor:

```java
@Getter @Setter @Builder
public class <X>RequestBody {
    private String field_one;
    private String field_two;

    public <X>RequestBody(String field_one, String field_two) { … }
}
```

This compiles today only because the hand-written constructor *happens to be* the all-args
constructor. Lombok's class-level `@Builder` generates an all-args constructor **only when no
constructor is declared**; here it binds to the declared one instead.

Add a third field and the coincidence breaks. The tempting repair — demote `@Builder` onto a new
hand-written all-args constructor and keep the old one — is wrong twice over: it contorts the class
away from every sibling DTO, and it preserves a constructor that (check this) usually has zero
callers.

```java
// WRONG — contorts the class to preserve a constructor nothing calls
@Getter @Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class <X>RequestBody {
    private String field_one;
    private String field_two;
    private String field_three;

    public <X>RequestBody(String field_one, String field_two) { … }

    @Builder
    public <X>RequestBody(String field_one, String field_two, String field_three) { … }
}
```

```java
// RIGHT — the shape every sibling DTO already uses
@Getter @Setter @Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
public class <X>RequestBody {
    private String field_one;
    private String field_two;
    private String field_three;
}
```

Before deleting the hand-written constructor, confirm it's unused:

```bash
rg 'new <X>RequestBody\(' <module>/src
```

If it *is* called, keep it and add `@AllArgsConstructor` alongside `@Builder` rather than moving
`@Builder` onto a constructor.

**`@JsonInclude(NON_NULL)` is required, not optional,** when adding an optional field to a DTO
existing tests already use: without it the new field serialises as `"field": null` on every
existing call, changing requests those tests were passing with.

### Don't mutate a shared assert

Adding an assertion inside a shared `static assert<X>(response)` helper changes behaviour for
**every** existing caller. If you do it:

```bash
rg 'assert<X>' <module>/src/test    # find ALL callers, not the ones you remember
```

and confirm the new assertion holds for each. If it holds only for your scenario, assert it in your
own test method, or add a separate `assert<X>With<Y>(...)` helper. A shared assert is a contract
with callers you didn't write.

---

## Part 2 — A new API gets its own test class

> **One endpoint, one test class.** A new endpoint's tests never go into an existing test class for
> a different endpoint, however closely related the two are.

This is the repo-wide convention, verified in independent modules with unrelated domains — e.g.
`driver-platform` `tests/rakam/componentTests/` (`GetBankAccountTests`,
`GetOutstandingBalanceTests`, `GetDriverWalletTokenTests`, …) and `customer-platforms`
`com/co/services/tests/internal/` (`BlackListUserTests`, `CustomerInfoByIdTests`,
`DeactivateCustomerInternalTests`, …) and `vouchers/bff/getuservouchers/`. Every one is one class
per endpoint, with no exceptions.

### Deciding

Ask: **is this a different path, or the same path?**

- Different path (`POST /resources` vs `POST /resources/{id}/action`) → a different endpoint →
  **a new test class**, named for the new endpoint, in the same package as its siblings.
- Same path and method, new input or new field → **the existing class for that endpoint**.
- Same path, different method (`GET` vs `DELETE` on one resource) → a different endpoint → a new
  test class. Path-only similarity is not a reuse signal.

"There is already a test class in this folder that creates the resource I need" is a reason to
*call* the existing create flow from your setup, not a reason to put your tests in its class.

### Building the new class

Copy the nearest sibling in the same directory as your structural template — base class, annotation
block, data-provider style, assertion style, cleanup — and keep it independently readable: someone
opening your class shouldn't need the sibling to understand it. Creating any prerequisite resource
in your own setup, through the existing controller, is the normal shape.
