# aep/skills

Claude Code skills marketplace for the AEP team.

## Install

1. Open a terminal and start Claude Code (type `claude`), or open the Claude Code
   CLI panel if you're already in it.
2. Run:
   ```
   claude plugin marketplace add https://source.golabs.io/aep/skills.git
   claude plugin install aep@aep
   claude plugin install aep-mobile@aep
   ```
   (skip whichever plugin you don't need)
3. **If the skills don't seem to be picked up, restart Claude Code** (quit and
   reopen, or start a new session). Newly installed plugins are only loaded when
   a session starts.

To get later updates: `claude plugin marketplace update aep`, then restart Claude Code.

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
```

Add a new plugin directory under `plugins/` (with its own `.claude-plugin/plugin.json`)
when a set of skills is specific enough to a service or sub-team that it shouldn't
ship to everyone who installs `aep`.

## Contributing

See the `add-a-skill` skill (`plugins/aep/skills/add-a-skill/SKILL.md`) for how
to add or propose a new skill.

Skills that turn out to be broadly useful beyond AEP should graduate to the
org-wide marketplace rather than living here indefinitely.

**Bump the version or the MR will fail.** If your change touches any file under
a `plugins/<name>/` directory, you must bump that plugin's `version` in its
`.claude-plugin/plugin.json` in the same MR — otherwise `scripts/check-plugin-versions.sh`
fails the pipeline. This exists because Claude Code only re-pulls a plugin when
that version string changes; without a bump, everyone who already installed it
would silently never see your update.
