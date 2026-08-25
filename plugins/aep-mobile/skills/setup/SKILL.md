---
name: aep-mobile-setup
description: Preflight check for aep-mobile plugin dependencies — validates Python/jsonschema, BrowserStack MCP connectivity (mandatory), and prints actionable setup steps for anything missing. Run after installing the plugin or when any aep-mobile skill reports a missing dependency.
---

# AEP Mobile — Setup & Preflight Check

Run this skill once after installing the plugin, or any time a skill reports
a missing dependency. **BrowserStack MCP is mandatory** — regression-extractor and
SDET plan upload will hard-stop without it.

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

### 2. BrowserStack MCP Server (mandatory)

BrowserStack MCP must be connected before any pipeline skill runs. Check connectivity
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

  BrowserStack MCP is MANDATORY for aep-mobile.
  regression-extractor and SDET plan upload require
  a live connection to BrowserStack Test Management.
  Skills will hard-stop without it.
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

4. Run the aep-mobile-setup skill again to verify.
```

Do NOT attempt to edit the user's config files or install the MCP server
yourself. Print the instructions and let them do it.

### 3. Summary

Print a single summary table:

```
Dependency              Status
──────────────────────  ──────
python3                 ✓ / ✗
jsonschema              ✓ / ✗
BrowserStack MCP        ✓ / ✗  (mandatory)
```

If everything passes: `All dependencies satisfied. You're ready to use aep-mobile skills.`

If BrowserStack MCP fails: `BrowserStack MCP is mandatory. Fix the item marked ✗ above, then run the aep-mobile-setup skill again.`

If only python/jsonschema fails: `Fix the items marked ✗ above, then run the aep-mobile-setup skill again.`
