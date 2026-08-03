#!/bin/sh
# Warn at session start if the schema validator the aep-mobile QA skills depend on is missing.
#
# The skills validate every context JSON / SDET plan against schemas/ before writing it. Without
# jsonschema that check silently no-ops, and a structurally wrong file looks like a good one.
# Stays silent when the dependency is present.

if ! command -v python3 >/dev/null 2>&1; then
  problem="python3 was not found on PATH"
  detail="The aep-mobile QA skills cannot schema-validate their output without it."
  fix="Install python3, then run: pip3 install --break-system-packages jsonschema"
elif ! python3 -c "import jsonschema" >/dev/null 2>&1; then
  problem="Python package 'jsonschema' is not installed"
  detail="aep-mobile QA skills will write their output WITHOUT schema validation."
  fix="pip3 install --break-system-packages jsonschema"
else
  exit 0
fi

# ponytail: printf over jq — jq isn't guaranteed present and this is two fixed strings.
printf '{"systemMessage":"aep-mobile: %s. %s Fix: %s",' "$problem" "$detail" "$fix"
printf '"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":'
printf '"ENVIRONMENT CHECK (aep-mobile plugin): %s. %s If the user invokes any aep-mobile QA skill, ' "$problem" "$detail"
printf 'tell them plainly that schema validation cannot run, give them this command: %s, ' "$fix"
printf 'and record a DEGRADED gap on ENVIRONMENT in the output. Do not run the install yourself. '
printf 'Never describe an unvalidated output as schema-valid."}}\n'
exit 0
