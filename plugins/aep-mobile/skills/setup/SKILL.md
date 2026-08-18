---
name: aep-mobile-setup
description: Preflight check for aep-mobile plugin dependencies — validates Python/jsonschema, BrowserStack MCP connectivity, and prints actionable setup steps for anything missing.
---

# AEP Mobile — Setup & Preflight Check

Run this skill once after installing the plugin, or any time a skill reports
a missing dependency.

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

### 2. BrowserStack MCP Server

Check whether the BrowserStack MCP tools are reachable by attempting to call
`listTestCases` or any lightweight BrowserStack MCP tool. Use ToolSearch to
check if any `mcp__browserstack__*` tools are available.

- **Tools found** → print `BrowserStack MCP ✓`
- **Tools NOT found** → print the setup instructions below verbatim:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BrowserStack MCP is not connected.
  
  The regression-extractor and test upload skills
  need it to query/create test cases in BrowserStack
  Test Management.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Setup steps:

1. Get your BrowserStack credentials from:
   https://www.browserstack.com/accounts/settings

2. Open your Claude Code config file:
   - Claude Desktop App: Settings → Developer → Edit Config
   - Claude Code CLI: open ~/.claude.json

3. Add the browserstack entry inside "mcpServers"
   (create the key if it doesn't exist):

   "browserstack": {
     "type": "stdio",
     "command": "npx",
     "args": ["-y", "@browserstack/mcp-server@latest"],
     "env": {
       "BROWSERSTACK_USERNAME": "<your-username>",
       "BROWSERSTACK_ACCESS_KEY": "<your-access-key>"
     }
   }

4. Restart Claude Code.

5. Run /aep-mobile:setup again to verify.
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
BrowserStack MCP        ✓ / ✗
```

If everything passes: `All dependencies satisfied. You're ready to use aep-mobile skills.`

If anything fails: `Fix the items marked ✗ above, then run /aep-mobile:setup again.`
