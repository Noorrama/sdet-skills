# aep-tapmind

TapMind MCP skills: goal-driven exploration, step-validation, NLP test codegen, charter exploration.

The `SKILL.md` files are the same format Claude Code and Cursor both load. What differed until
1.1.4 is **discovery**: this plugin only shipped `.claude-plugin/plugin.json`, so Cursor did
not install it as a plugin. That is now paired with `.cursor-plugin/plugin.json` (same pattern
as `aep-mobile`).

## Skills

| Folder | When to use |
|---|---|
| `goal-driven-exploration` | Plain-English goal on a real device |
| `step-validation` | Diagnose a written step list on a device; emit one `@Test` |
| `nlp-codegen` | Plan → kb-only **or** one pioneer → suite in `tapmind-mobile-tests` + MR |
| `charter-exploration` | BrowserStack cases → exploratory charters |

QA guide for codegen: [`skills/nlp-codegen/README.md`](skills/nlp-codegen/README.md).

## Claude Code

```
claude plugin marketplace add https://source.golabs.io/aep/skills.git
claude plugin install aep-tapmind@aep
```

Restart the session. `$CLAUDE_PLUGIN_ROOT` points at this plugin.

## Cursor

Same `SKILL.md` files. Install **one** of these (keep the plugin tree — skills call each other’s `assets/`):

1. **Cursor plugin** (preferred, mirrors `aep-mobile`): add this marketplace repo as a plugin source, install `aep-tapmind`. Cursor sets `CURSOR_PLUGIN_ROOT`. Requires `.cursor-plugin/plugin.json` (this directory).

2. **Project skills:** from the repo that should see them:

   ```
   mkdir -p .cursor/skills
   ln -s /path/to/skills/plugins/aep-tapmind/skills/* .cursor/skills/
   ```

   Also set `export TAPMIND_PLUGIN_ROOT=/path/to/skills/plugins/aep-tapmind` so bash still finds
   sibling `skills/step-validation/assets`. Copying a **single** skill folder without that
   variable breaks `module-profile.sh` / `direct-api-map.md`.

3. **Personal:** same symlink into `~/.cursor/skills/` plus `TAPMIND_PLUGIN_ROOT`.

Restart Cursor after install. Invoke by name (`nlp-codegen`, `step-validation`) or in natural language (“generate the TapMind NLP tests and raise the MR”).

## TapMind MCP (Cursor Desktop)

Skills are instructions. Pioneer device runs need the **TapMind MCP** server on `localhost:7777`.

User-level config (all Cursor projects): `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "tapmind": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:7777/mcp"]
    }
  }
}
```

The TapMind HTTP MCP process must already be listening on port **7777**. `mcp-remote` is only a bridge. If 7777 is down, Cursor shows `tapmind` as failed until you start the server and reload MCP.

## Reload so Cursor picks up new skills and MCP

These are **two different layers**. Reloading one does not always reload the other.

### MCP (`tapmind`)

1. Confirm the TapMind server is up: `http://localhost:7777/mcp`.
2. **Cursor Settings → MCP** — you should see `tapmind`. Use the refresh/retry control on that row if it is red.
3. If it still fails: **Cmd+Shift+P** → **Developer: Reload Window**.
4. Last resort: quit Cursor fully (Cmd+Q) and reopen.

A new agent chat after reload is required before tools like `start_appium_session` appear. An already-open chat keeps the old tool list.

### Skills (`nlp-codegen`, `step-validation`, …)

Cursor reads skills at **session start**. Editing `SKILL.md` on disk is not enough while a chat is running.

| How you installed | How to pick up updates |
|---|---|
| Project `.cursor/skills/` symlinks into this repo | `git pull` (or save local edits) → **Developer: Reload Window** → **new chat** |
| Personal `~/.cursor/skills/` | Same: reload window + new chat. Keep `TAPMIND_PLUGIN_ROOT` pointed at `plugins/aep-tapmind` |
| Cursor plugin (`aep-tapmind`) | Bump already happened in `.cursor-plugin/plugin.json`. Disable/enable the plugin or reload window. If it still serves an old copy, remove and re-add the plugin source |

Do **not** rely on `~/.claude/plugins/cache/aep/aep-tapmind/…` — that is Claude Code’s cache, not Cursor’s skill loader.

**Fast path after changing skills in this repo:**

```
Cmd+Shift+P → Developer: Reload Window
```

Then start a **new** Agent chat and mention `nlp-codegen` (or “generate TapMind NLP tests”).

Plugin root for scripts:

```
ROOT="$(bash "${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-${TAPMIND_PLUGIN_ROOT:?}}}/scripts/plugin-root.sh")"
```

Or `bash scripts/plugin-root.sh` from this directory. It accepts `TAPMIND_PLUGIN_ROOT`,
`CURSOR_PLUGIN_ROOT`, or `CLAUDE_PLUGIN_ROOT`.

## Version bump

Bump **both** `.claude-plugin/plugin.json` and `.cursor-plugin/plugin.json` in the same MR, or Claude/Cursor users silently miss the update.
