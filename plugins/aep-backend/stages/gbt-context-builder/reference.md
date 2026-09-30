# GBT Context Builder — reference

## Graph traversal

The code graph (built by `tools/build_code_graph.py`) models the GBT layered pattern. From a
matched `:Endpoint` node, the traversal is:

```
Client      -[:CALLS]->       Endpoint
Controller  -[:CALLS]->       Client
Controller  -[:REFERENCES]->  Response
TestBase    -[:REFERENCES]->  Controller
Test        -[:EXTENDS]->     TestBase
Test        -[:REFERENCES]->  Assertion
Test        -[:REFERENCES]->  DataProvider
TestBase    -[:REFERENCES]->  Helper
```

Matching order for the `:Endpoint` node itself:

1. **`exact`** — method **and** normalised path both match.
2. **`path_only`** — normalised path matches, method differs.
3. No match → every layer is `create_new`, and the endpoint is recorded in
   `unresolved_endpoints[]` so a reader knows it was searched for and genuinely absent —
   as opposed to never looked up.

`agent/code_graph.py` implements this as `find_endpoint_context()` followed by `decide()`;
this skill produces the same shape so the two agree when the pipeline lands.

## Path normalisation

`_normalize_path` collapses every `{param}` to `{}` before comparison. Parameter *names* are
not part of an endpoint's identity.

| A | B | Result |
|---|---|---|
| `POST /v1/drivers/{driverId}` | `POST /v1/drivers/{id}` | `exact` |
| `POST /v1/drivers/{id}` | `GET /v1/drivers/{id}` | `path_only` |
| `POST /v1/drivers/{id}` | `POST /v1/drivers/{id}/cards` | no match |
| `POST /v1/drivers/active` | `POST /v1/drivers/{id}` | no match — a literal segment is not a parameter |

Emit both `path` (as written in the RFC, braces intact) and `normalized_path`. Downstream
codegen needs the original for the endpoint declaration; matching needs the normalised form.

## Why `path_only` is not a reuse signal for the test layer

A `path_only` match means some other HTTP method on that path is already wired. The endpoint,
client, and controller may legitimately be reusable — a client class typically holds several
methods for one resource. But an existing `GET` test tells you **nothing** about whether
`POST` behaviour is tested.

So for `match_quality: "path_only"`:

- `endpoint` → `create_new` (a different method needs its own endpoint class in GBT)
- `client`, `controller`, `test_base`, `assertion` → `reuse` is appropriate
- `test` → **`create_new`**, and record a `gap` of type `method_untested_on_existing_path`

Treating a `path_only` hit as full test coverage is the subtlest way to skip generating a
needed test.

## `create_new` package conventions

`create_new` emits a **directory**, never a filename.

**The directory comes from the target module's profile layer map — not from a generic
convention.** Read `gbt-module-<normalized>/SKILL.md` and use the roots it documents. Layouts
differ materially between modules, and a plausible-looking guess produces files in directories
that do not exist.

`_CREATE_HINTS` in `agent/code_graph.py` carries a generic fallback for modules with no
committed profile. **Treat it as a last resort**, and record a `gap` of type
`layout_from_generic_fallback` whenever you rely on it.

Worked example — the real `:driver-platform` layout, from
`gbt-module-driver-platform/SKILL.md`. Note it matches none of the pluralised generic
defaults: endpoints and responses are nested under `entities/<svc>/`, while clients and
controllers are **flat, one class per service**:

| Layer | `:driver-platform` directory |
|---|---|
| `endpoint` | `{module_root}/src/main/java/entities/<svc>/endpoint/` |
| `response` | `{module_root}/src/main/java/entities/<svc>/response/` |
| `request` | `{module_root}/src/main/java/entities/<svc>/request/` |
| `client` | `{module_root}/src/main/java/client/` — flat, `<Svc>ServiceClient.java` |
| `controller` | `{module_root}/src/main/java/controller/` — flat, `<Svc>ServiceController.java` |
| `test_base` | `{module_root}/src/test/java/tests/<svc>/` |
| `test` | `{module_root}/src/test/java/tests/<svc>/componentTests/…` |
| `assertion` | `{module_root}/src/test/java/assertions/` — flat, `<Svc>ServiceAssertions.java` |
| `data_provider` | `{module_root}/src/test/java/dataProvider/` — flat, singular dir |
| `helper` | `{module_root}/src/test/java/helper/` |

The flat layers matter for reuse: because one `BffServiceClient` serves every `/driver/bff/v1/*`
endpoint, a new endpoint in an established service is almost always **`create_new` on the
endpoint/response layers but `reuse` on client, controller, assertion, and data_provider** —
methods get added to files that already exist.

**Never append a filename.** `…/componentTests/` is correct; `…/componentTests/SaveCardTest.java`
is not. Codegen owns class naming, and it has the module profile's naming rules — which this
skill does not.

Deriving `{svc}`: prefer the service name from the matched graph node. With no match, take the
first meaningful path segment after the version — `/payment/v1/cards` → `payment`. Record the
derivation in `service` so a reviewer can sanity-check it.

## Ranking candidates — shared controllers make several layers ambiguous

The traversal reaches the test layer via `TestBase -[:REFERENCES]-> Controller`. When one
controller serves a whole service — `BffServiceController` backs all 28 `/driver/bff/v1/*`
endpoints — **many unrelated test bases, test classes, assertion classes, and data providers
reference it**, and the graph returns whichever it finds first. This is not specific to
`test_base`: any layer reached through a shared node (`test`, `assertion`, `data_provider`,
and `test_base` itself) can return multiple structurally-valid candidates for the same
endpoint, and picking the first one is a guess, not a verdict.

Observed on `:driver-platform`: resolving
`POST /driver/bff/v1/driver-subscription/{subscriptionId}/subscribe` returns the correct
`BffServiceClient` and `BffServiceController`, but `test_base` comes back as `MjgTestBase`
and `tests` as `AcceptanceRateTests`/`CompletionRateTests` — all MJG tests that merely share
the controller. The right answer is `BffServiceTestBase`.

**Do not take the first match for any multi-candidate layer (`test_base`, `test`,
`assertion`, `data_provider`) when the controller is shared.** Apply this ranking, in order,
to whichever layer has more than one candidate:

1. Prefer the candidate whose file path shares the deepest directory prefix with the
   endpoint's own service — `tests/bff/…` for an `entities/bff/endpoint` endpoint.
2. Failing that, prefer the candidate whose class name shares the service prefix
   (`BffServiceTestBase` for `svc = "bff"`).
3. If neither disambiguates, emit **all** candidates and record a
   `multiple_test_classes_matched` gap (reused for any layer, not only `test`) so a reviewer
   chooses. Name the layer explicitly in the gap's `detail` — `multiple_test_classes_matched`
   on `assertion` reads very differently from the same code on `test_base`.

This ranking **is** the final verdict — it is not a suggestion `automation-plan-generator`
re-evaluates. That skill copies `decisions.<layer>.class_name` verbatim; if you emit an
under-ranked or ambiguous candidate here, nothing downstream will correct it.

Getting this wrong is expensive in a specific way: the generated test extends the wrong base,
loses the controller and assertion fields it expects, and fails to compile — or worse, compiles
against a base whose setup does something unrelated.

## Package resolution ladder

Mirrors `agent/automation_agent.py` `_resolve_package()`, and the tier is recorded because it
is a confidence signal, not an implementation detail.

| Tier | Rule | `package_confidence` |
|---|---|---|
| **A** | Package of an existing **test** file for any of these APIs | `verified` |
| **B** | Package of an existing `src/main` match for any of these APIs | `verified` |
| **C** | Package of the module's exemplar file for that role | `inferred` |
| **D** | Nothing found — the bare module root | `unverified` |

Two separate resolutions are needed: `test` (for test/assertion/data_provider/helper) and
`main` (for endpoint/client/controller). When `main` cannot be resolved, fall back to the
`test` package rather than leaving it empty — a wrong-but-consistent package is easier for a
human to fix than a file at the module root.

**Tier D must be visible.** `automation_agent._anchor_files` handles it by placing the file at
`{module_root}/src/{srcset}/{lang}/{filename}` with the note *"package could not be verified —
please review"*. If this artifact does not flag it, that note is the only warning, and it is
buried in codegen output. Set `package_confidence: "unverified"` and add a `gap`.

## Graph beats blob search

Two mechanisms can find existing code:

| Mechanism | What it is | Fails how |
|---|---|---|
| Code graph | Static analysis: parsed `String url()` / `HttpMethod httpMethod()`, resolved path constants, import-linked classes | Silently empty when the graph is stale or unbuilt for the module |
| Repo blob search | GitLab keyword search over file contents | Hits comments, unrelated strings, and similarly-named endpoints in other services |

**Graph wins whenever it returns a match.** Blob search is the fallback for modules the graph
has not been built for. Record which produced each entry in
`existing_matches[api].source` (`code_graph` | `blob_search`) — a reviewer reading a
surprising reuse decision needs to know how confident to be.

If the graph is unbuilt for the module, that is a **reject**, not a quiet fallback to blob
search. Blob search cannot produce reliable nine-layer verdicts, and a partially-grounded
context is more dangerous than an absent one because nothing signals the degradation.

## `implementation_constraints` override the graph

From `tasks_context`: *"Must reuse existing `CardValidationService` — do not introduce a new
validator class."*

| Situation | Action |
|---|---|
| Constraint names a class; graph found it | Force `reuse` with the real path; record in `constraints_applied` |
| Constraint names a class; not in target module | **Reject** with `constraint_unsatisfiable` |
| Constraint forbids something (`do not add a column`) | Record in `constraints_applied` with `resolution: "forbidden"`; no verdict changes, but codegen must see it |

The reject case matters: if the constraint cannot be satisfied, generated code will violate it
and the MR will be rejected in human review. Failing here — before generation — is cheaper
than failing at review, and the reject message tells the team the story is not actually ready.

## `existing_matches` — the codegen handoff

This section exists in exactly the shape `automation_agent._resolve_package` and
`_anchor_files` already consume:

```json
"existing_matches": {
  "POST /payment/v1/cards": {
    "exists": true,
    "source": "code_graph",
    "matches": [{"path": "…/PaymentClient.java", "role": "client"}]
  }
}
```

That shape is why `gbt_context` needs no new plumbing in codegen: it feeds the existing
`existing_by_api` parameter, renders into the existing `## EXISTING ENDPOINT MATCHES` prompt
section, and drives the existing package-anchoring ladder. **The anchoring ladder is only as
good as its Tier A/B signals**, which come from here — so completeness in `matches[]` is
directly what keeps generated files out of the module root.

## `dependency_impact`

Which modules depend on the target, and which test files are transitively affected.

**Compute this once per run and cache it in this artifact.** `dependency_analyzer`'s
`_resolve_package_to_module` reads every `.java`/`.kt` file in every module for every import —
O(imports × repo) across a 66-module monorepo. Prefer parsing `build.gradle` for
`project(":x")` declarations, which is what `tools/build_driver_platform_graph.py` already
does for exactly this reason. Record which method was used in `computed_from`.

An empty `dependency_impact` is acceptable and should not block. Unlike coverage, a missing
impact analysis degrades prompt quality rather than producing a wrong answer.

## Gap taxonomy

| `type` | When |
|---|---|
| `package_unverified` | A Tier-D resolution — file will land at the module root |
| `method_untested_on_existing_path` | `path_only` match; this HTTP method has no test |
| `endpoint_not_in_graph` | Searched and genuinely absent — fully greenfield endpoint |
| `service_name_derived` | `{svc}` inferred from the path rather than a graph node |
| `exemplar_missing_for_role` | No exemplar for a role, so Tier C was unavailable |
| `dependency_impact_unavailable` | Impact analysis could not be computed — non-blocking |
| `multiple_test_classes_matched` | Several candidate test classes; codegen must pick, so a reviewer should confirm |

## Relationship to other skills

- `regression-extractor` gives the **coverage** view (what is asserted); this gives the
  **structural** view (where code lives). Both read the same graph; neither replaces the other.
- `automation-plan-generator` copies `packages`, `decisions.test.class_name`,
  `decisions.assertion.class_name`, and the nine verdicts into `existing_paths` — which is
  what makes that skill mostly mechanical.
- Codegen (`gbt-code-generation`) consumes `existing_matches` and the verdicts through prompt
  sections that already exist, so no prompt template changes and the codegen cache stays valid.
