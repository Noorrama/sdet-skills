# Environment-specific test data — never put an environment-dependent id in a shared file

Read this **before adding any test-data constant** (entity id, account number, batch code, outlet
uuid) to a module. Getting this wrong produces a test that passes on QA and fails on integration
with a confusing 404 — a common environment bug, and invisible in review because the constant
*looks* exactly like its neighbours.

## The question to answer first

> Is this value the same in every environment, or does it name a row that had to be provisioned
> per environment?

| Kind of value | Environment-dependent? | Where it goes |
|---|---|---|
| Provisioned entity id — merchant, customer, restaurant, group, offer, voucher batch, outlet | **Yes** | the module's per-environment test-data holder |
| Enum / protocol literal — a status, a type, a mode | No | the shared constants class |
| Locale, country code, app-version header | No | the shared constants class |
| A *deliberately invalid* id — `"abcd"`, an all-zeros UUID, a nonexistent reference | No — it exists nowhere by design | the shared constants class |
| Host / URL | **Yes** — but never a constant | the module's properties/config reader |

The invalid-id row is the one people get wrong in the other direction. A constant like
`INVALID_RESOURCE_ID = "abcd"` belongs in the shared class precisely *because* it resolves in no
environment — "unknown to the service" is the data condition under test, not a fixture someone has
to provision. Don't route it through the per-environment holder; there is nothing
environment-specific to hold.

## Discovery — find the module's mechanism, don't invent one

Do this before writing the constant. Three mechanisms are live in this repo; which one applies is
a per-module, often per-feature-area fact.

```bash
# 1. Is there an interface + per-environment implementation family for this domain?
find <module>/src/main/java \( -name 'I*Constants.java' -o -name '*ConstantsQa.java' \
     -o -name '*ConstantsInt.java' -o -name '*Int.java' -o -name '*Uat.java' \) | head

# 2. Does the module switch test data on an environment variable / system property?
rg 'getenv\(\)\.getOrDefault\(|getProperty\("env"\)' <module>/src/main/java

# 3. Are there per-environment properties files?
ls <module>/src/main/resources/*.properties
```

### Mechanism A — interface + one implementation per environment

An `I<Domain>` interface of getters, one implementation class per environment, and a public
holder that picks the implementation once and exposes `public static final` fields:

```
I<Domain>Constants.java       interface of getters
<Domain>ConstantsQa.java      QA values
<Domain>ConstantsInt.java     integration values
<Domain>Constants.java        picks one; ALSO holds the environment-INdependent literals
```

```java
public final class <Domain>Constants {
    private static final I<Domain>Constants ENVIRONMENT_CONSTANTS = getEnvironmentConstants();

    private static I<Domain>Constants getEnvironmentConstants() {
        // the switch key is per-module — read the module's own dispatcher
        String infra = System.getenv().getOrDefault("INFRA", "qa");
        if (infra.equalsIgnoreCase("integration") || infra.equalsIgnoreCase("staging")) {
            return new <Domain>ConstantsInt();
        }
        return new <Domain>ConstantsQa();
    }

    // environment-INdependent — plain literals, no indirection
    public static final String SOME_STATUS = "IN_PROGRESS";
    public static final String INVALID_RESOURCE_ID = "abcd";

    // environment-dependent — always through ENVIRONMENT_CONSTANTS
    public static final String PRIMARY_MERCHANT = ENVIRONMENT_CONSTANTS.getPrimaryMerchant();
}
```

Two modules implement this shape today, for unrelated domains and with **different switch keys**:
`app-platform/src/main/java/promotech/testdata/appplatform/` (`IGoBizMerchants` +
`GoBizMerchantsInt`/`GoBizMerchantsUat`/`GoBizMerchantsIntTencent`/`GoBizMerchantsViet` behind
`GoBizMerchants`, switching on the `env` **system property**), and
`gofood/src/main/java/constants/` (switching on the `INFRA` **environment variable**). Read the
dispatcher in the module you're in; the keys are not interchangeable.

### Mechanism B — per-environment properties files (hosts and URLs)

Env-keyed `.properties` files under `<module>/src/main/resources/`, read through the module's
properties/config reader. **Hosts always go here, never into a constants class** — already covered
by the "never hardcode a host in an Endpoint" rule in `SKILL.md`, and it applies to internal
service URLs too.

### Mechanism C — pooled / leased data (no constant at all)

If the entity is a customer or driver the module leases from a pool at runtime (a test-data-pool
annotation, a `poolingUtility.getTDPCustomer(...)`-style helper, a static pool manager), there is
**no constant to add**. Request the right pool type and read the leased entity. Adding a hardcoded
id next to a pooling mechanism is a regression, not a shortcut.

## Adding a new environment-specific id — the procedure

1. **Search first, module-wide and repo-wide.** The value may already exist under a different
   name, or another module may already provision this kind of entity through a helper you should
   be calling instead of a literal.
   ```bash
   rg -i '<the-uuid-or-a-distinctive-fragment>' <module>/src
   rg -i '<domain-word>' <module>/src/main/java/constants
   ```
   "No mechanism exists to provision X" is a claim that needs a search behind it. If a capability
   exists but lives in a module yours doesn't depend on, that's a build-dependency question for
   the user — not grounds for asserting the capability is absent.
2. **If Mechanism A exists for this domain**, add a getter to the interface and an implementation
   in **every** environment class. Missing one is a compile error, which is the point: the pattern
   makes "I forgot integration" impossible.
3. **Name it for what it is**, matching sibling names in the interface. Do not encode provisioning
   status in the name — no `DUMMY_` or `TODO_` prefix on the public constant, or every call site
   reads that way forever, including after the value is provisioned.
4. **If the value is not provisioned yet**, that's a data gap, not a naming problem. Put the
   placeholder in the per-environment implementation with a `// TODO:` naming exactly what must be
   provisioned, keep the public constant name clean, and leave the consuming test `enabled = false`
   with the same explanation. Report it as a blocker the user must resolve.
5. **If Mechanism A does not exist** for the domain and only one or two ids are involved, follow
   the nearest sibling in that feature area rather than introducing the interface family yourself.
   If you think the family is warranted, propose it — don't build it unasked.

## The shape to avoid, and the shape to write

```java
// WRONG — provisioned, environment-specific ids sitting in the shared class beside the
// enum literals, with provisioning status baked into the public name.
public static final String DUMMY_PARTNER_ID = "TODO-DUMMY-PARTNER-ID";
public static final String DUMMY_SECONDARY_PARTNER_ID = "TODO-DUMMY-SECONDARY-PARTNER-ID";
```

```java
// RIGHT — the provisioned ids go through the per-environment family; only the
// genuinely-invalid one stays shared.

// I<Domain>Constants.java
String getPartnerId();
String getSecondaryPartnerId();

// <Domain>ConstantsQa.java  (and the matching Int class — both, or it won't compile)
@Override
public String getPartnerId() {
    // TODO: not provisioned on QA yet. Needs <exact fixture description>.
    // Consuming tests stay disabled until this is a real id.
    return "TODO-QA-PARTNER-ID";
}

// <Domain>Constants.java
public static final String PARTNER_ID = ENVIRONMENT_CONSTANTS.getPartnerId();

// stays shared — resolves in no environment by design, like INVALID_RESOURCE_ID
public static final String UNKNOWN_PARTNER_ID = "00000000-0000-0000-0000-000000000000";
```
