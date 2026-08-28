# aep/skills

Claude Code skills marketplace for the AEP team.

## Install

1. Open a terminal and start Claude Code (type `claude`).
2. Run:
   ```
   claude plugin marketplace add https://source.golabs.io/aep/skills.git
   claude plugin install aep@aep
   claude plugin install aep-mobile@aep
   claude plugin install aep-tapmind@aep
   ```
   (skip whichever plugin you don't need)
3. Open the Claude desktop app and check **+ → Plugins → Manage plugins** — the
   AEP skills should be listed there.
4. **If they're not visible, restart the Claude desktop app** (quit and reopen).
   Once restarted, AEP skills should be visible under the Plugins section.

## Updating

Nothing updates automatically by default. When someone pushes a new skill
version, everyone else has to pull it manually:

```
claude plugin marketplace update aep
claude plugin update <plugin>@aep
```
(e.g. `claude plugin update aep-mobile@aep`)

Then **restart Claude Code** (quit and reopen the terminal session, or the
desktop app) — the version number updates immediately, but the actual skill
content only loads on the next session start.

Same two commands also work typed directly into the **desktop app's message
box** (they're Claude Code commands, not shell-only) if you'd rather not open
a terminal — then restart the desktop app the same way.

**To stop doing this manually:** in the desktop app, go to **+ → Plugins →
Manage plugins → Marketplaces tab**, find `aep`, and turn on auto-update.
Claude Code will then check in the background shortly after each session
starts and notify you when there's a new version, instead of you having to
run the commands above.

## Structure

```
.claude-plugin/marketplace.json   # marketplace manifest, lists plugins below
plugins/
  aep/                            # core plugin — general AEP workflows
    .claude-plugin/plugin.json
    skills/
      add-a-skill/SKILL.md        # how to contribute a new skill here
      sample-skill/SKILL.md       # copy this to start a new skill
  aep-mobile/                     # mobile squad's QA pipeline
    .claude-plugin/plugin.json
    skills/                       # 8 skills, prd through test-code-gen
    config/, schemas/, examples/  # per-app config + supporting data
  aep-tapmind/                    # TapMind MCP squad — device automation via TapMind
    .claude-plugin/plugin.json
    skills/
      goal-driven-exploration/    # plain-English goal -> device run -> graph report
      step-validation/            # written steps -> device diagnosis + one @Test
      nlp-codegen/                # plan -> one pioneer validation -> suite + MR
      charter-exploration/        # BrowserStack cases -> exploratory charters
```

Add a new plugin directory under `plugins/` (with its own `.claude-plugin/plugin.json`)
when a set of skills is specific enough to a service or sub-team that it shouldn't
ship to everyone who installs `aep`.

## Adding a new skill

1. Pick a plugin under `plugins/`. One skill doesn't need a new plugin — add it to
   `plugins/<existing-plugin>/skills/<skill-name>/SKILL.md` unless it's specific
   enough to a service or sub-team to warrant its own plugin (its own
   `.claude-plugin/plugin.json` and its own entry in `.claude-plugin/marketplace.json`).
2. Write `SKILL.md` with frontmatter:
   ```yaml
   ---
   name: skill-name
   description: What it does and when to use it — this is what triggers auto-invocation, be specific.
   ---
   ```
3. **Bump the version or the MR will fail.** Bump that plugin's `version` in its
   `.claude-plugin/plugin.json` in the same MR — `scripts/check-plugin-versions.sh`
   fails the pipeline otherwise. This exists because Claude Code only re-pulls a
   plugin when that version string changes; without a bump, everyone who already
   installed it would silently never see your update.
4. Test locally before opening a merge request:
   ```
   claude plugin marketplace add ./path/to/this/repo
   claude plugin install <plugin>@aep
   ```
5. Open an MR. Someone who owns the affected plugin directory should review it.

The `add-a-skill` skill (`plugins/aep/skills/add-a-skill/SKILL.md`) covers the
same steps if you'd rather ask Claude directly. `sample-skill` in the same
plugin is a copy-and-replace starting point.

Skills that turn out to be broadly useful beyond AEP should graduate to the
org-wide marketplace rather than living here indefinitely.
