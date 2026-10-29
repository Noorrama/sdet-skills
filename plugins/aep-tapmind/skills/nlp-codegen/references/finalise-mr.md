# Finalise MR (agentic NLP)

Trigger phrases:

- “Finalise this MR” / “Finalize this MR”
- “Remove Agentic tags and update MR”
- “Ready to merge — clean up agentic NLP MR”

Run **after** the user is satisfied with pipeline results. Do **not** finalise
while they still want `Agentic_nlp_tests` runs on that branch.

## 1. Scope

- Repo: `aep/tapmind-mobile-tests`
- Branch: the open MR branch from this skill (§7)
- Classes: files **this skill emitted** in the conversation (typically one epic
  class per run). Do **not** strip tags from unrelated tests elsewhere.

## 2. Remove `Agentic_nlp_tests`

For each emitted `@Test` in those classes:

- Remove `"Agentic_nlp_tests"` from `groups = { ... }`.
- Keep all other groups from `$SAMPLE_TEST` / `$TEST_GROUPS`.
- Do not change steps, descriptions, or `testCaseIds`.

Commit example: `chore: drop Agentic_nlp_tests group before merge (!<iid>)`

## 3. Pipeline evidence

Collect **successful** `agentic_nlp_release_*` pipelines on this branch:

1. GitLab MCP — `gitlab_get_merge_request_pipelines` for the MR.
2. URLs recorded in §8 of this conversation.

## 4. Update MR description

Append or replace `## Agentic NLP verification`:

```markdown
## Agentic NLP verification

| Platform | Module | Pipeline | SHA |
|----------|--------|----------|-----|
| Android | gofood | <url> | `abc1234` |

Agentic_nlp_tests group removed from agentic NLP classes in this MR.
```

Use `glab mr update` when MCP cannot edit description.

## 5. Echo to user

MR link, files stripped, pipeline table, reminder that post-merge regression uses
normal module groups only.
