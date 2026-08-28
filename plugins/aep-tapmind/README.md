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
| `nlp-codegen` | Plan → one pioneer validation → suite in `tapmind-mobile-tests` + MR |
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

TapMind **MCP** (Appium session tools) is separate: configure it in Cursor Settings → MCP if you need a pioneer device run. Codegen without a device still works if you paste a proven `@Test`.

Plugin root for scripts:

```
ROOT="$(bash "${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-${TAPMIND_PLUGIN_ROOT:?}}}/scripts/plugin-root.sh")"
```

Or `bash scripts/plugin-root.sh` from this directory. It accepts `TAPMIND_PLUGIN_ROOT`,
`CURSOR_PLUGIN_ROOT`, or `CLAUDE_PLUGIN_ROOT`.

## Version bump

Bump **both** `.claude-plugin/plugin.json` and `.cursor-plugin/plugin.json` in the same MR, or Claude/Cursor users silently miss the update.
