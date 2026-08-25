# GBT Test-Code Generator — reference

## How this differs from `gbt-code-generation`

Both generate GBT Java. They are not interchangeable.

| | `gbt-code-generation` | `gbt-test-code-generator` (this skill) |
|---|---|---|
| Driven by | Python-assembled prompt (`automation_agent.py:830-862`) | Files on disk |
| Input contract | Implicit — `##`-headed sections, never documented in the skill | Explicit — four named JSON files |
| Case identity | `tc_id` (11-field flat case) | `SC-###` + `AC-###` from the plan |
| Knows about fixtures | Only as a `test_data` string per case | Resolves `{{fixture-id.field}}` through `test_data.json` |
| Path anchoring | Done afterwards by `_anchor_files` in Python | Done in-skill, same algorithm |
| Output | JSON blob returned to Python | Files written + `codegen_manifest.json` |
| Runs standalone | No — needs the prompt assembled around it | Yes, in Claude Code or Cursor |

**Neither replaces the other.** The Python pipeline keeps using `gbt-code-generation`; that
skill's body is hashed by `automation_agent._cache_key`, so it stays byte-identical and
`.gbt_codegen_cache/` stays valid. This skill is the skills-only route to the same outcome.

Where they overlap — the *patterns* — this skill defers rather than duplicates. That is
deliberate: a copy would silently fork the moment someone edits the module profile, and the
two would disagree with no signal.

## Testing this skill individually

The whole point of the file-based contract is that you can exercise it with no pipeline. You
need one fixture directory and about ten minutes.

### Step 1 — pick a real endpoint that exercises reuse

The reuse path is where generated GBT code most often goes wrong, and it is the path that
prevents suite bloat, so test it first — not a greenfield endpoint.

Choose, in order of preference:

1. An endpoint whose `decisions.test` **and** `decisions.assertion` are both `reuse` — the
   richest case: a method appended to an existing test class, using an existing assertion
   class.
2. Failing that, any endpoint with `reuse` on `client` and `controller`.
3. Last resort, a fully greenfield endpoint — but know that you are then testing only the
   easy half.

The endpoint must be in `.gbt_repo` and in the code graph. If the graph is empty, run
`python tools/build_code_graph.py` first; without it every verdict is `create_new` and the
test is meaningless.

### Step 2 — build the fixture

```
runs/SMOKE-CODEGEN/
  run.json                                  # review.status = "approved"
  pass1/gbt_context.json                    # from gbt-context-builder on the chosen endpoint
  pass1/artifacts/automation_plan.json      # two scenarios, hand-written
  pass1/artifacts/test_data.json            # the fixtures those two scenarios reference
  README.md                                 # which endpoint, why, and the baseline result
```

Two scenarios is the right size: one happy path and one negative. One scenario does not
exercise "append a second method to the same class"; five make the diff tedious to read.

Minimum viable `run.json`:

```json
{"epic_id": "SMOKE-CODEGEN", "pass": 1,
 "review": {"pass": 1, "status": "approved", "reviewer": "local-test",
            "at": "2026-01-01T00:00:00Z", "per_scenario": {"SC-001": "keep", "SC-002": "keep"}}}
```

Generate `gbt_context.json` by running `gbt-context-builder` for real. **Do not hand-write
it** — a hand-written one encodes what you *believe* the repo looks like, and the bug you are
hunting is exactly the gap between belief and reality.

`automation_plan.json` you do hand-write, following the `automation-plan-generator` skill's
output shape. Copy the `existing_paths` block straight from the generated `gbt_context.json`.

Commit the fixture. It is reusable and it is the beginning of a golden dataset.

### Step 3 — run it

In Claude Code or Cursor:

> Read the `gbt-test-code-generator` skill and follow it for `runs/SMOKE-CODEGEN`.

### Step 4 — the five checks

| # | Check | Passes when | How |
|---|---|---|---|
| 1 | **Reuse, not duplication** | The happy-path test is a **new method in the existing class** named in `existing_paths.test` — manifest shows `"action": "update"`, not `create` | `jq '.files[] | {path, action}' codegen_manifest.json` |
| 2 | **No fabricated identifiers** | Every method in `reused_identifiers[].methods_called` is really declared in that file, and every entry has `verified: true` | `grep -n "saveCard" <the real file>` for each |
| 3 | **Correct anchoring** | Path is `{module_root}/src/{test,main}/java/{pkg}/…` and the `package` declaration matches the directory exactly | read the first line of each generated file |
| 4 | **Traceability** | Each `@Test` `description` contains its `SC-###` and `AC-###` | `grep -c "SC-00" <test file>` |
| 5 | **Pattern conformance** | Layer chain, base classes, `@TestInfo`, groups, logger, no hardcoded URLs | run `test-code-validator`, or `profile_validator.validate` below |

Check 2 is the one to spend time on. Nothing automated catches it today, and a fabricated
method name produces code that looks entirely correct until it is compiled.

```bash
python - <<'PY'
import json
from agent import profile_validator
m = json.load(open("runs/SMOKE-CODEGEN/pass1/artifacts/codegen_manifest.json"))
files = [{"path": f["path"], "content": open(".gbt_repo/" + f["path"]).read()} for f in m["files"]]
print(profile_validator.format_report(profile_validator.validate(files, m["module"])))
PY
```

### Step 5 — the six reject cases

The skill must **refuse**, not degrade. Each is a one-line edit to the fixture:

| Edit | Expected reject |
|---|---|
| `review.status` → `"pending"` | `review_not_approved` |
| Delete `test_data.json` | `missing_input` |
| Point an `existing_paths.test` path at a deleted file | `stale_gbt_context` |
| Reference `{{fixture-nonexistent.id}}` in a scenario | `unresolvable_fixture` |
| Set both scenarios `is_dedup: true` | `nothing_to_generate` |
| Rename `module_root` to a directory not in `.gbt_repo` | `gbt_repo_missing` |

Every one must produce a reject file with a `remediation`, and **write no Java**. A skill that
generates something plausible from a broken input is worse than one that stops — the output
looks reviewable.

### Step 6 — clean up, every time

```bash
git -C .gbt_repo checkout . && git -C .gbt_repo clean -fd
```

Generated Java left in the clone gets indexed by the next `gbt-context-builder` or
`find_existing_endpoint` run as pre-existing coverage. The test then stops being repeatable
and, worse, a later real run would treat your test output as an existing test to reuse.

### Optional — the check that actually proves it

```bash
cd .gbt_repo && ./gradlew :driver-platform:compileTestJava
```

The only check that catches fabricated method names, signature mismatches, and generics —
none of which any pattern validator can see. Worth running at least once: it tells you how
much checks 2 and 5 are really buying, and it is the honest answer to "does this work".

## Two failure modes worth naming

**Reusing the class but inventing the method.** The model sees `PaymentClient` in
`existing_paths`, correctly decides to reuse it, then calls `paymentClient.saveCard(dto)`
because that is what such a method would obviously be called. If the real method is
`createCard`, everything compiles in the model's head and fails at `javac`. Rule 3 exists for
this, and the mitigation is mechanical: **open the file**.

**Anchoring drift.** In the Python pipeline, `_anchor_files` runs after generation and fixes
paths regardless of what the model proposed, so a wrong path never reaches the repo. In the
skills-only path there is no such safety net — the anchoring algorithm in `SKILL.md` *is* the
safety net, and it only works if applied. When check 3 fails, the cause is usually that the
package was taken from the model's intuition rather than from `gbt_context.packages`.

## Relationship to the rest of the pipeline

- **Reads** `automation_plan.json` (from `automation-plan-generator`), `gbt_context.json`
  (from `gbt-context-builder`), `test_data.json` (from `test-data-generator`), and `run.json`
  (the human gate).
- **Feeds** `test-code-validator`, which checks the generated files against `rules.json`.
- **Does not** create an MR, fix build failures (`gbt-build-fix` does that), or run tests.
- The Python pipeline's equivalent stage is `automation_agent.generate` +
  `automation_job.start_automation_job`. Both should produce the same files for the same
  plan; if they diverge, the anchoring algorithm here has drifted from `_anchor_files`.
