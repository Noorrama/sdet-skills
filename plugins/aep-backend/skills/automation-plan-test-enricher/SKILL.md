---
name: backend-automation-plan-test-enricher
description: Enrich an automation_plan.json with existing GBT test coverage for each scenario's endpoint. For every automation_scenario, takes (module, endpoint), resolves it against the gojek-backend-tests dependency graph in Memgraph, and writes scenario_gbt_context onto the scenario — endpoint_file, upstream_files, downstream_files, test_methods_calling_endpoint, test_data_providers, test_assertions. Runs between automation-plan-generator and test-code-generator so generated tests reuse existing test classes, assertion helpers, and data providers instead of duplicating them. Use when asked to enrich an automation plan with GBT context, find existing tests for an endpoint, or check what already covers a scenario.
---

# Backend Automation Plan Test Enricher

For each scenario in `automation_plan.json`, ask the GBT dependency graph what already exists around its endpoint and write the answer back as `scenario_gbt_context`. Downstream, test-code-generator extends those existing test classes / assertion helpers / data providers instead of creating parallel ones.

Reads `module` + `endpoint` per scenario; passes every other field through untouched. Query lives in [references/endpoint_context.cypher](references/endpoint_context.cypher) and takes two bound parameters, `$module` and `$endpoint` — never rebuild it by string substitution.

## Environment

Bolt only — port `3000` on that host is Memgraph Lab (browser UI, no query API). On a GitLab runner these come from CI variables; credentials are masked and never appear in the plan, the command line, or this repo.

```
MEMGRAPH_URI=bolt://10.27.76.76:7687     # default
MEMGRAPH_USER= MEMGRAPH_PASSWORD=         # empty when the instance has auth off
```

## Step 1 — preflight

No absolute paths anywhere: the interpreter, the query file and the host are discovered or come from the environment.

```bash
if python3 -c "import neo4j" 2>/dev/null; then PY=python3; else
  VENV_DIR=${VENV_DIR:-$PWD/.gbt-venv}
  [ -x "$VENV_DIR/bin/python" ] || python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" -q install neo4j; PY="$VENV_DIR/bin/python"
fi
CYPHER=${GBT_CYPHER:-$( { [ -n "$CLAUDE_PLUGIN_ROOT" ] && find "$CLAUDE_PLUGIN_ROOT" -name endpoint_context.cypher -path '*automation-plan-test-enricher*' 2>/dev/null; \
  find "${CI_PROJECT_DIR:-.}" "${GBT_SKILLS_DIR:-.}" "$HOME/.claude/plugins" -name endpoint_context.cypher -path '*automation-plan-test-enricher*' 2>/dev/null; } | head -1 )}
HOSTPORT=${MEMGRAPH_URI#*://}; nc -z -w 3 "${HOSTPORT%%:*}" "${HOSTPORT##*:}" || echo "bolt unreachable"
echo "PY=$PY"; [ -f "$CYPHER" ] && echo "CYPHER=$CYPHER" || echo "cypher not found — set GBT_CYPHER or GBT_SKILLS_DIR"
```

`find`, not a glob: an unmatched glob makes zsh abort the whole command. Check `CYPHER` is non-empty before Step 3 — otherwise it dies with a bare `FileNotFoundError`.

## Step 2 — derivation rules (implemented by the runner)

- **`$endpoint`** — strip, in order: leading HTTP verb, `scheme://host`, `String.format` host slot (`%s`/`%d`), `{host}` placeholder. Keep `?query=string` (the Cypher splits on `?` itself). `"GET %s/driver/bff/v1/campaigns/mitra-juara"` → `/driver/bff/v1/campaigns/mitra-juara`.
- **`$module`** — the plan names a service, the graph's `def.path` is a repo directory. Try `module` → `service_name` → each with a trailing `-service`/`-svc`/`-api`/`-backend` stripped → `-`/`_` swapped. First candidate returning rows wins; fallbacks log to stderr.
- **One row per scenario** — the Cypher's `LIMIT 5` can return several equally-scored candidates; prefer the one whose `http_method` matches the scenario's verb, else the first.
- **One query per endpoint** — cached on `(module, path)`, error results included.

The endpoint match is segment-by-segment with placeholders as wildcards, then scored, because `e.path` holds the Java literal (source-named placeholders, query strings on some routes, empty trailing segments) and never matches by `=`. Do not "simplify" it to `CONTAINS` — that sweeps in sibling routes and multiplies the query cost.

## Step 3 — run

`PY`/`CYPHER` carry over from Step 1; `PLAN`/`OUT` are relative paths. `MEMGRAPH_URI` is intentionally absent here so the environment (CI variable) sets it. `MAX_FILES` caps files per role — uncapped, a `gopay`-sized module returns 1000+ and swamps the plan.

```bash
PLAN=${PLAN:-automation_plan.json}; OUT=${OUT:-automation_plan_enriched.json}; \
PLAN="$PLAN" OUT="$OUT" CYPHER="$CYPHER" MAX_FILES=25 TIMEOUT=180 \
"$PY" - <<'PYEOF'
import json, os, re, sys
from neo4j import GraphDatabase, Query

URI = os.environ.get("MEMGRAPH_URI", "bolt://10.27.76.76:7687")
PLAN, OUT, CYPHER = os.environ["PLAN"], os.environ["OUT"], os.environ["CYPHER"]
CAP, TO = int(os.environ.get("MAX_FILES", "25")), int(os.environ.get("TIMEOUT", "180"))
FIELDS = ("endpoint_file", "upstream_files", "downstream_files",
          "test_methods_calling_endpoint", "test_data_providers", "test_assertions")
VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

def split_ep(raw):                                   # "POST /a/{id}" -> ("POST", "/a/{id}")
    t, v = (raw or "").strip(), None
    p = t.split(None, 1)
    if len(p) == 2 and p[0].upper() in VERBS:
        v, t = p[0].upper(), p[1].strip()
    t = re.sub(r"^[a-zA-Z][\w+.\-]*://[^/]*", "", t)  # scheme + host
    t = re.sub(r"^%[sd]", "", t)                      # String.format host slot
    if t.startswith("{"):
        t = re.sub(r"^\{[^/{}]*\}", "", t)            # {host} placeholder
    return v, ("/" + t if t and not t.startswith("/") else t)

def modules(s):                                      # service name -> repo dir candidates
    out = []
    for seed in (s.get("module"), s.get("service_name")):
        if not isinstance(seed, str) or not seed.strip():
            continue
        base = seed.strip()
        stripped = re.sub(r"[-_](service|svc|api|backend)$", "", base)
        for v in (base, stripped, stripped.replace("-", "_"), stripped.replace("_", "-")):
            if v and v not in out:
                out.append(v)
    return out

def clean(v):                                        # the query's collect(CASE..NULL) yields nulls
    if isinstance(v, list):
        return [clean(x) for x in v if x is not None]
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    return v

def cap(groups):
    if not CAP:
        return groups
    out = []
    for g in groups or []:
        files = g.get("files") if isinstance(g, dict) else None
        if isinstance(files, list) and len(files) > CAP:
            g = dict(g)
            g["files"] = files[:CAP] + [f"... {len(files) - CAP} more file(s) omitted (MAX_FILES={CAP})"]
        out.append(g)
    return out

cypher = open(CYPHER).read()
plan = json.load(open(PLAN))
scenarios = plan["automation_scenarios"]

driver, conn_err = None, None
try:
    user, pw = os.environ.get("MEMGRAPH_USER", ""), os.environ.get("MEMGRAPH_PASSWORD", "")
    driver = GraphDatabase.driver(URI, auth=(user, pw) if user else None)
    driver.verify_connectivity()
except Exception as exc:
    conn_err = f"{type(exc).__name__}: {exc}"

cache, ok, bad = {}, 0, 0
for s in scenarios:
    sid = s.get("scenario_id", "<no id>")
    verb, path = split_ep(s.get("endpoint", ""))
    mods = modules(s)
    if not path:
        ctx = {"error": f"no_endpoint: scenario {sid} has an empty endpoint (DB/infra-only test?)"}
    elif not mods:
        ctx = {"error": f"no_module: scenario {sid} has neither module nor service_name"}
    elif conn_err:
        ctx = {"error": f"memgraph_unreachable: {URI} - {conn_err}"}
    elif (mods[0], path) in cache:
        ctx = cache[(mods[0], path)]
    else:
        ctx, err, tried = None, None, []
        for m in mods:
            tried.append(m)
            try:
                with driver.session() as ses:
                    rows = [r.data() for r in ses.run(Query(cypher, timeout=TO), module=m, endpoint=path)]
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                break
            if rows:
                row = clean(next((r for r in rows
                                  if verb and str(r.get("http_method", "")).upper() == verb), rows[0]))
                ctx = {k: row.get(k) for k in FIELDS}
                ctx["upstream_files"] = cap(ctx.get("upstream_files") or [])
                ctx["downstream_files"] = cap(ctx.get("downstream_files") or [])
                for k in FIELDS[3:]:
                    ctx[k] = ctx.get(k) or []
                if m != mods[0]:
                    print(f"note: {sid} matched with module fallback '{m}'", file=sys.stderr)
                break
        if ctx is None:
            ctx = {"error": f"query_failed: {err}" if err else
                   f"no_endpoint_match: 0 rows for endpoint='{path}' with module(s) {tried}"}
        cache[(mods[0], path)] = ctx
    s["scenario_gbt_context"] = json.loads(json.dumps(ctx))   # deep copy per scenario
    ok, bad = (ok + 1, bad) if "error" not in ctx else (ok, bad + 1)

if driver:
    driver.close()
json.dump(plan, open(OUT, "w"), indent=2)
print(f"{ok} enriched, {bad} errored, {len(scenarios)} total -> {OUT}", file=sys.stderr)
PYEOF
```

A per-scenario failure never aborts the run — every other scenario is still enriched and the plan is still written.

## Step 4 — report

From stderr (`N enriched, N errored, N total` + any `note:` fallback lines), summarise per scenario: matched `endpoint_file`, count of `test_methods_calling_endpoint`, and any `error` verbatim. Point at the output path; do not paste whole file lists.

## Output → automation_plan.json

Append `scenario_gbt_context` on each scenario six keys on success:

| Key | Meaning |
|---|---|
| `endpoint_file` | File declaring the matched endpoint |
| `upstream_files` / `downstream_files` | `[{role, files[]}]` — callers of / files reached by the endpoint's file (plus same-package siblings downstream). `role: "test"` upstream comes only from the precise method-level graph. |
| `test_methods_calling_endpoint` | `(test_file, test_method)` pairs proven to call the endpoint |
| `test_data_providers` / `test_assertions` | `@DataProvider` methods and assertion classes used by those specific test methods |

Empty lists mean *matched, nothing found* — a genuinely uncovered endpoint, common on this graph, and **not** an error. On failure the object instead holds only `error`, e.g.
`"error": "no_endpoint_match: 0 rows for endpoint='/payment/v1/cards' with module(s) ['wallet-service', 'wallet']"` — other reasons: `no_endpoint` (empty endpoint, DB/infra-only test), `no_module`, `memgraph_unreachable`, `query_failed` (timeout or memory limit).

## Guardrails

- Never mutate anything but `scenario_gbt_context` — the plan is a reviewed contract.
- Never invent context: no match means an `error` object, not a guessed test class. Fabricated coverage sends test-code-generator to edit files that do not exist.
- Preserve *empty list* vs *error* — that distinction is what tells the generator "write a new class" versus "could not resolve".
- Re-run after re-indexing; a stale enriched plan's `test_methods_calling_endpoint` goes out of date as soon as tests land.
