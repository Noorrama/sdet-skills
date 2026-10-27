# Finalise MR (release NLP)

Trigger phrases (treat as the same intent):

- “Finalise this MR” / “Finalize this MR”
- “Remove Agentic tags and update MR”
- “Ready to merge — clean up release NLP MR”

Run **after** the user is satisfied with pipeline results on the MR branch. Do
not finalise while they still want `Agentic_nlp_tests` runs on that branch.

## 1. Scope

- Repo: `aep/tapmind-mobile-tests`
- Branch: the open release MR branch (e.g. `feat/gofood-release-nlp-agentic`)
- Classes: **only** `*ReleaseNlpTests.java` (or other files **this skill
  emitted** in the conversation). Do **not** strip `Agentic_nlp_tests` from
  unrelated agentic work elsewhere in the repo.

## 2. Remove `Agentic_nlp_tests`

For each emitted `@Test` method in those classes:

- Remove `"Agentic_nlp_tests"` from the `groups = { ... }` array.
- Leave all other groups from the bucket sample (`BOOKING`, `COMMS_P0`,
  `CHAT_REVAMP`, etc.).
- Do not change `@Test(description)`, steps, or `testCaseIds`.

Commit message example:

```
chore: drop Agentic_nlp_tests group before merge (!<iid>)
```

## 3. Pipeline evidence for MR description

Collect **successful** `agentic_nlp_release` pipelines for this branch:

1. **GitLab MCP** — `gitlab_get_merge_request_pipelines` on
   `aep/tapmind-mobile-tests` with the MR `iid`. Include pipelines where
   `status` is `success` (or `passed` per API) and jobs include
   `agentic_nlp_release_android` / `agentic_nlp_release_ios`.
2. **This conversation** — any pipeline URLs returned when the user (or you)
   triggered runs in §8 (`references/gitlab-pipeline.md`). Merge with (1);
   dedupe by pipeline id.

For each successful pipeline, record:

| Field | Source |
|---|---|
| Platform | Android / iOS from job name or `APP_TYPE` |
| `MODULE` | e.g. `gofood`, `communication-platform` |
| Pipeline URL | `web_url` |
| Commit SHA | short sha the pipeline ran on |

Do **not** list failed or canceled pipelines in the “verified” block (mention
failures only in chat if the user asks).

## 4. Update MR description

Fetch current description with `gitlab_get_merge_request`. Append (or replace
a prior `## Agentic NLP verification` section) with:

```markdown
## Agentic NLP verification

Pipelines on branch `<branch>` (group `Agentic_nlp_tests`, pre-merge):

| Platform | Module | Pipeline | SHA |
|----------|--------|----------|-----|
| Android | gofood | <url> | `abc1234` |
| iOS | gofood | <url> | `abc1234` |
| Android | communication-platform | <url> | `def5678` |
| iOS | communication-platform | <url> | `def5678` |

Agentic_nlp_tests group removed from release NLP classes in this MR.
```

Update the MR body via `glab mr update` (GitLab MCP may not expose description
edit):

```bash
GITLAB_HOST=source.golabs.io glab mr update <iid> \
  --repo aep/tapmind-mobile-tests \
  --description "$(cat <<'EOF'
<full updated description>
EOF
)"
```

Push the tag-removal commit, then update description so SHA/links stay
consistent.

## 5. Echo to user

- Link to MR
- List of files stripped of `Agentic_nlp_tests`
- Table of successful pipelines copied into the description
- Reminder: after merge, regression jobs use normal module groups (`BOOKING_*`,
  `COMMS_*`), not `Agentic_nlp_tests`

## 6. `@TestInfo` owner (emit rule — not part of finalise)

All **new** release NLP methods use `owner = "AI-AGENT"` in `@TestInfo`, never
the BrowserStack **Owner** column. See `SKILL.md` §6.
