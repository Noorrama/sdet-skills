# GitLab MCP (preferred)

Use GitLab MCP when it is installed and authenticated in Cursor. Tool names vary by server;
discover with `GetDynamicTools` pattern `gitlab`.

## Project

- Host: `source.golabs.io`
- Project path: `aep/tapmind-mobile-tests` (URL-encoded `aep%2Ftapmind-mobile-tests` in API paths)

## Typical flow

1. **Auth** — If the namespace status is `needsAuth`, run MCP OAuth for that server, then retry.
2. **List merged MRs** — Tool akin to `gitlab_list_merge_requests` with:
   - `project`: `aep/tapmind-mobile-tests`
   - `state`: `merged`
   - `updated_after` / `created_after` aligned to the user's start date (API-dependent)
   - Paginate until `merged_at` is before the range start.
3. **Filter** — Keep MRs where `merged_at` is within `[start, end]` (inclusive, UTC unless user specifies timezone).
4. **Fetch body** — For each MR, load `description` (and `author.username`, `iid`, `web_url`, `merged_at`).
5. **Hand off** — Write a JSON array to a temp file and run `assets/aggregate_contributions.py`.

## MCP unavailable

If no GitLab MCP tools exist or auth fails:

1. Tell the user to configure **`GITLAB_TOKEN`** (read_api) for `source.golabs.io` with access to `aep/tapmind-mobile-tests`.
2. Run:

```bash
python3 assets/fetch_merged_mrs.py \
  --team-config config/teams/aep-consumer.yaml \
  --start 2025-10-01 --end 2025-10-31 \
  --out /tmp/tapmind-mrs.json
python3 assets/aggregate_contributions.py \
  --team-config config/teams/aep-consumer.yaml \
  --mrs /tmp/tapmind-mrs.json \
  --start 2025-10-01 --end 2025-10-31
```

3. If both MCP and API fail, stop with the error — do not invent counts.
