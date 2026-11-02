---
name: tapmind-contribution
description: Report how many TapMind mobile test cases each engineer added from merged GitLab MRs on aep/tapmind-mobile-tests, split by Android and iOS. Use when the user invokes /tapmind-contribution or asks for a contribution report for an AEP mobile squad over a date range — e.g. "contribution from AEP Consumer from 2025-10-01 to 2025-10-31".
---

# TapMind test-case contributions (`/tapmind-contribution`)

Slash command: **`/tapmind-contribution`**

Produce a **markdown table** of team members vs **test cases added**, with **Android** and **iOS** columns.
Data comes from **merged merge requests** on `aep/tapmind-mobile-tests` (`source.golabs.io`), by parsing
each MR description — not from diff line counts.

Repo under skill: `plugins/aep-tapmind/skills/tapmind-contribution/`.

## Prerequisites

1. **GitLab MCP** (preferred) — authenticated for `source.golabs.io` with read access to
   `aep/tapmind-mobile-tests`. See [references/gitlab-mcp.md](references/gitlab-mcp.md).
2. **Or REST fallback** — `GITLAB_TOKEN` with `read_api` on the same host/project
   (`assets/fetch_merged_mrs.py`).
3. **Python 3** + **PyYAML** (`pip install pyyaml`) for the aggregation scripts.
4. **Team roster** — YAML under `config/teams/` (seeded: `config/teams/aep-consumer.yaml`).

If MCP is missing and `GITLAB_TOKEN` cannot read the project, **stop** with a clear setup message.
Do not fabricate counts.

## User request parsing

Typical phrase:

> contribution from **AEP Consumer** from **2025-10-01** to **2025-10-31**

Extract:

| Field | Rule |
| --- | --- |
| Team | Name after `from` before `from <date>` — map to `config/teams/<slug>.yaml` (`AEP Consumer` → `aep-consumer.yaml`) |
| Start / end | ISO dates `YYYY-MM-DD`, inclusive on MR `merged_at` (UTC calendar day) |
| Default range | If only one date or no range, ask once; if user says "last 30 days", compute from today UTC |

## Workflow

1. Load the team YAML. Resolve `members[].gitlab_handle` (without `@`).
2. **Fetch merged MRs** in the date window (MCP or `fetch_merged_mrs.py`). Keep `description`,
   `author.username`, `merged_at`, `iid`, `web_url`.
3. Write JSON array to a temp file.
4. Run aggregation (deterministic — do not hand-count):

```bash
ROOT=plugins/aep-tapmind/skills/tapmind-contribution
python3 "$ROOT/assets/aggregate_contributions.py" \
  --team-config "$ROOT/config/teams/aep-consumer.yaml" \
  --mrs /tmp/tapmind-mrs.json \
  --start 2025-10-01 --end 2025-10-31
```

5. Return the printed markdown table to the user. Optionally list MR links that contributed rows.
6. For local skill verification without GitLab, use
   `assets/fixtures/sample-mrs-noor.json` with the same command.

## MR description contract

Authors should use the template in [references/mr-description-format.md](references/mr-description-format.md).
Key requirement: `## Test case contributions` with `### Android` / `### iOS` bullet lists.

## Maintaining the member list

Edit `config/teams/aep-consumer.yaml`:

```yaml
members:
  - name: Full Name
    gitlab_handle: gitlab.username   # no @ prefix
```

Add new team files as `config/teams/<kebab-slug>.yaml` and set top-level `team:` to the display name.
Map user-facing team names to filenames in this skill (document new mappings in the YAML comment).

## Output shape

Example:

| Member | GitLab | Android | iOS | Total |
| --- | --- | ---: | ---: | ---: |
| Noor Putera Utama | @noor.daulay | 3 | 3 | 6 |

Fixture run for Noor (`sample-mrs-noor.json`, October 2025): **3 Android**, **3 iOS**, **6 total**.

## Error paths

| Situation | Action |
| --- | --- |
| No GitLab MCP tools | Follow REST path; document missing MCP in chat |
| 401 / 403 / 404 from GitLab | Token or project access; link GitLab MCP OAuth docs |
| Zero MRs in range | Empty table with zeros — state "no merged MRs matched" |
| MRs without contribution section | Excluded (no guess from code diff) |
