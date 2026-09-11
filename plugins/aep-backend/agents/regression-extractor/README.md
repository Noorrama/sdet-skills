---
name: regression-extractor-readme
description: Documentation for regression-extractor scripts. Not an agent entry point.
---

# regression-extractor scripts

Two scripts that produce the regression coverage map this skill consumes:

| Script | Job | Input | Output |
|---|---|---|---|
| `generate_service_graph.py` | Traces the Java service architecture of a GBT module and attaches BrowserStack test-case metadata | GBT Java repo + BrowserStack API | `<module>_regression.json` + `<module>_regression.csv` |
| `find_test.py` | Looks up the regression test cases belonging to the service named in an RFC context | `rfc_context.json` + the catalogues above | `test_cases.json` |

The normal order is: run `generate_service_graph.py` once per module (or once for everything) to build the catalogues, then run `find_test.py` per RFC to pull out the relevant subset.

---

## 1. `generate_service_graph.py`

### What it does

Walks a Gradle module's `src/main/java` and `src/test/java` and reconstructs the call chain from entry point to HTTP endpoint, then hangs the test suite off it:

- **Controller-based** modules (e.g. `driver-platform`): `Controller → Client → Endpoint → PropertiesInternal`
- **Helper-based** modules (e.g. `gopay`): `Helper → Client → Endpoint` (in `apis/`)

Architecture is auto-detected per module (`controller`, `helper`, `both`, or `none`) — nothing is hardcoded per module. It then:

1. Resolves host URLs by chaining `*PropertiesInternal.java` → `*PropertiesReader.java` → `src/main/resources/*.properties`.
2. Derives feature names from entry-point method names and from endpoint URL paths.
3. Walks test-class inheritance (`Test → mid-level Base → TestBase`) to attribute test groups and `testCaseIds` to each service.
4. Enriches each test case with title, steps, and expected result from BrowserStack Test Management.

### Prerequisites

**The script must live inside the GBT Java repo when you run it.** It finds the repo root by walking up from its own location looking for `.git`, and reads `settings.gradle` from there. Copy it into the GBT repo (any depth) before running — running it from this skills repo will fail to find module directories.

**BrowserStack credentials** go in a `.env` file next to the script (never inline them in the script or in a command):

```
BS_USERNAME=your_username
BS_ACCESS_KEY=your_access_key
# optional overrides
# BS_AUTH_TOKEN=base64_of_username:access_key
# BS_API_HOST=https://test-management.browserstack.com
```

Existing environment variables win over `.env`. Add `.env` to `.gitignore`. Without credentials the run still completes, but `name`/`steps`/`expected_result` stay `null`.

Python 3 only — no third-party packages.

### Usage

```bash
python3 generate_service_graph.py                              # every module in settings.gradle
python3 generate_service_graph.py --module gopay               # → BrowserStack PR-166
python3 generate_service_graph.py --module driver-platform     # → BrowserStack PR-143
python3 generate_service_graph.py --module gopay -bp PR-999    # override the project
python3 generate_service_graph.py --module gopay -nb           # offline, no BrowserStack
python3 generate_service_graph.py -m care-platform -b testcases_PR-196.json
```

### Options

| Flag | Meaning |
|---|---|
| `--module`, `-m` | Module name. Accepts `gopay`, `GOPAY`, `driver_platform`, `DRIVER-PLATFORM` — it normalizes to the on-disk directory. **Omit to process every module** in `settings.gradle`. |
| `--browserstack-project`, `-bp` | BrowserStack project ID (e.g. `PR-143`), overriding the auto-resolved one. In an all-modules run it overrides the mapping for *every* module. |
| `--browserstack`, `-b` | Use a local test-cases JSON file instead of the API. A bare `PR-166` is also accepted and resolved to `testcases_PR-166.json` next to the script. |
| `--no-browserstack`, `-nb` | Skip BrowserStack entirely. |

`-b`, `-bp`, and `-nb` are mutually exclusive.

The BrowserStack project is auto-resolved from the module name via the `MODULE_BS_PROJECTS` table at the top of the script. Some modules deliberately share a project (`gopay`, `iris`, `payment-core` → `PR-166`; `driver-platform`, `marketplace`, `pricing` → `PR-143`); an all-modules run fetches each distinct project only once. Add new modules by editing that table. An unmapped module still builds its graph — pass `-bp` to enrich it.

### Output

Written next to the script, with dashes in the module name turned into underscores:

- `<module>_regression.json` — the catalogue
- `<module>_regression.csv` — flat view, `;`-joined list fields

Shape of the JSON (keyed by service display key):

```json
{
  "MealSchedulerOrderService": {
    "serviceName": "mealSchedulerOrder",
    "host": "https://api.example.com",
    "features": ["meal_scheduler_orders", "create_order"],
    "TestGroups": ["REGRESSION", "SANITY"],
    "testCaseIds": [
      {
        "id": "TC-12345",
        "name": "Create scheduled order — happy path",
        "steps": "1. ...",
        "expected_result": "...",
        "method_name": "testCreateScheduledOrder"
      }
    ],
    "impacted_service": ["orderCancellation"],
    "supported_flows": ["regression", "sanity"]
  }
}
```

Notes on the fields:

- `id` is `null` when a `@Test` has no `testCaseIds` annotation — the case is then identified by `method_name` alone, and `name`/`steps`/`expected_result` stay `null`.
- `name`/`steps`/`expected_result` also stay `null` when the ID is not found in BrowserStack.
- `impacted_service` lists other services that share a test base class.
- `supported_flows` is derived from test group names (`component`, `regression`, `sanity`, `end_to_end`).

Each run prints a discovery summary (architecture, dirs found, counts) and, for multi-module runs, an aggregate table at the end.

---

## 2. `find_test.py`

### What it does

Reads `service_name` from an `rfc_context.json`, finds that service in one or more `<module>_regression.json` catalogues, and writes the deduplicated union of their `testCaseIds` entries.

RFC service names are kebab-case (`meal-scheduler`) while catalogue keys are PascalCase (`MealSchedulerOrderService`) and `serviceName` values are camelCase (`mealSchedulerOrder`) — and the catalogue name is usually more specific than the RFC one. Matching therefore climbs a ladder and **stops at the tightest tier that produces any hit**, so a loose tier only fires when nothing tighter matched:

| Tier | Name | Example |
|---|---|---|
| 0 | `exact` | `meal-scheduler` = `mealScheduler` |
| 1 | `prefix` | `meal-scheduler` → `mealSchedulerOrder` |
| 2 | `token-subset` | `meal-scheduler` → `orderMealScheduler` |
| 3 | `substring` | `mealscheduler` → `gofoodMealSchedulerV2` |
| 4 | `fuzzy` | edit-distance ≥ `--fuzzy-threshold` (typos, plural drift) |

Noise suffixes (`service`, `svc`, `api`, `apis`, `server`, `backend`) are dropped before comparing, and tiers 1–4 require names of at least 5 folded characters so short generic names like `base` don't match half the catalogue.

### Usage

```bash
python3 find_test.py rfc_context.json gofood
python3 find_test.py rfc_context.json gofood gopay -o found_tests.json
python3 find_test.py rfc_context.json all --include-related
python3 find_test.py rfc_context.json gofood -o -        # print to stdout
```

Module names here are **catalogue names, i.e. underscored** — the `<module>` part of `<module>_regression.json`. So `driver_platform`, not `driver-platform`. `all` expands to every catalogue in the regression dir; an unknown name errors out and lists what is available.

Flags also have long forms: `--rfc PATH` and `--modules A B` work in place of the positionals.

### Options

| Flag | Meaning |
|---|---|
| `-o`, `--output` | Where to write the JSON list. Default `test_cases.json`; `-` prints to stdout. |
| `--regression-dir` | Directory holding the `*_regression.json` catalogues. Default: the script's own directory. |
| `--with-source` | Annotate each test case with the `module` and `service` it came from. |
| `--exact` | Only tier 0 — disables every fallback tier. |
| `--max-tier` | Loosest tier allowed: `exact`, `prefix`, `token-subset`, `substring`, `fuzzy` (default `fuzzy`). |
| `--fuzzy-threshold` | Similarity ratio the fuzzy tier requires (default `0.8`). |
| `--include-related` | Also search services named in the RFC's `service_level_changes` and `cross_service_dependencies`. |

### Output

A JSON list of unique test-case objects — the same objects as in the catalogue, optionally plus `module`/`service` with `--with-source`:

```json
[
  {
    "id": "TC-12345",
    "name": "Create scheduled order — happy path",
    "steps": "1. ...",
    "expected_result": "...",
    "method_name": "testCreateScheduledOrder",
    "module": "gofood",
    "service": "MealSchedulerOrderService"
  }
]
```

Dedup prefers real identifiers (`id`, `method_name`, `name`), so the same case listed under two services collapses to one even if other fields differ.

Progress goes to stderr, so `-o -` stays pipeable:

```
searching for: meal-scheduler
  gofood/MealSchedulerOrderService: 12 test cases (12 new) [prefix match on 'mealSchedulerOrder' <- 'meal-scheduler', score 0.67]
  gopay: no match — closest: PaymentService (0.41), ...
wrote 12 unique test cases to test_cases.json
```

### When nothing matches

The log prints the five closest catalogue names with their similarity ratios. From there:

1. Try `all` as the module — the service may live in a different catalogue.
2. Add `--include-related` if the RFC's primary service isn't the one under test.
3. Lower `--fuzzy-threshold` (e.g. `0.7`).
4. If it still misses, the catalogue may be stale — re-run `generate_service_graph.py` for that module.