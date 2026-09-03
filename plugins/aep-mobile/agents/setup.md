---
name: aep-mobile-setup
description: Preflight check for aep-mobile plugin dependencies — validates Python/jsonschema, BrowserStack MCP connectivity (required only for BrowserStack-backed skills), and prints actionable setup steps for anything missing. Run after installing the plugin or when any aep-mobile skill reports a missing dependency.
model: sonnet
---

# AEP Mobile — Setup & Preflight Check

Run this skill once after installing the plugin, or any time a skill reports
a missing dependency. **BrowserStack MCP is required only for the BrowserStack-backed
skills** — regression-extractor and SDET plan upload hard-stop without it. The pre-build
extractors (prd, rfc, design, task) do **not** need it; they need only python3 + jsonschema.

All paths below are relative to the aep-mobile plugin root (where `config/`,
`schemas/`, and `skills/` live).

## Execution

### 1. Python & jsonschema

```
python3 -c "import jsonschema; print('jsonschema', jsonschema.__version__)"
```

- **Passes** → print `jsonschema ✓`
- **Fails** → print the fix:
  ```
  pip3 install --break-system-packages jsonschema
  ```

### 2. SDET compliance scripts (required for sdet-plan-generator)

From the plugin root, confirm the org-wide deliverable gate is runnable:

```
python3 scripts/build_coverage_checklist.py --help
python3 scripts/validate_sdet_deliverables.py --help
```

- **Passes** → print `sdet compliance scripts ✓`
- **Fails** → ensure `plugins/aep-mobile/scripts/` is on PATH or invoke with full path from plugin root

See `agents/sdet-plan-generator/workflow.md`.

### 3. BrowserStack MCP Server (required for BrowserStack-backed skills)

BrowserStack MCP must be connected before running regression-extractor or the SDET-plan
upload — the pre-build extractors (prd/rfc/design/task) skip this check entirely. Check connectivity
by discovering and calling a lightweight BrowserStack MCP tool (e.g. `listTestCases`).

**In Cursor:** use dynamic MCP tool discovery to find BrowserStack tools in the
configured MCP namespace, then attempt a lightweight call. Tool names vary by MCP
server config — look for `listTestCases`, `listFolders`, or similar BrowserStack
Test Management tools.

**In Claude Code:** use ToolSearch to check if any `mcp__browserstack__*` tools are
available, then call one.

- **Tools found and callable** → print `BrowserStack MCP ✓`
- **Tools NOT found or call fails** → print the setup instructions below verbatim:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BrowserStack MCP is not connected.

  Required for the BrowserStack-backed skills:
  regression-extractor and SDET plan upload need
  a live connection to BrowserStack Test Management
  and hard-stop without it. The prd/rfc/design/task
  extractors do not need it.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Setup steps:

1. Get your BrowserStack credentials from:
   https://www.browserstack.com/accounts/settings

2. Configure the MCP server in your editor:

   Cursor:
   - Open Cursor Settings → MCP (or edit ~/.cursor/mcp.json)
   - Add a browserstack entry:

   {
     "mcpServers": {
       "browserstack": {
         "command": "npx",
         "args": ["-y", "@browserstack/mcp-server@latest"],
         "env": {
           "BROWSERSTACK_USERNAME": "<your-username>",
           "BROWSERSTACK_ACCESS_KEY": "<your-access-key>"
         }
       }
     }
   }

   Claude Code / Claude Desktop:
   - Claude Desktop: Settings → Developer → Edit Config
   - Claude Code CLI: open ~/.claude.json
   - Add the same browserstack entry inside "mcpServers"

3. Restart your editor (Cursor or Claude Code).

4. Re-run mobile-context-extraction (setup-only) to verify.
```

Do NOT attempt to edit the user's config files or install the MCP server
yourself. Print the instructions and let them do it.

### 4. Summary

Print a single summary table:

```
Dependency              Status
──────────────────────  ──────
python3                 ✓ / ✗
jsonschema              ✓ / ✗
sdet compliance scripts ✓ / ✗
BrowserStack MCP        ✓ / ✗  (needed for regression / SDET upload)
```

If everything passes: `All dependencies satisfied. You're ready to use aep-mobile skills.`

If BrowserStack MCP fails: `BrowserStack MCP is needed only for regression-extractor and SDET-plan upload. If you're only running the prd/rfc/design/task extractors you can ignore this; otherwise fix the ✗ above and re-run mobile-context-extraction (setup-only).`

If only python/jsonschema fails: `Fix the items marked ✗ above, then re-run mobile-context-extraction (setup-only).`
