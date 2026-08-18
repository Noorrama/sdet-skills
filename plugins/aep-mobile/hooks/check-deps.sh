#!/bin/sh
# Check aep-mobile plugin dependencies at session start.
# Stays silent when everything is present. Warns on missing deps.
#
# Checks: (1) python3 + jsonschema for schema validation
#          (2) npx availability for BrowserStack MCP server

warnings=""

# --- Check 1: python3 + jsonschema ---
if ! command -v python3 >/dev/null 2>&1; then
  warnings="${warnings}python3 not found — schema validation disabled. Fix: install python3, then pip3 install --break-system-packages jsonschema. "
elif ! python3 -c "import jsonschema" >/dev/null 2>&1; then
  warnings="${warnings}jsonschema not installed — schema validation disabled. Fix: pip3 install --break-system-packages jsonschema. "
fi

# --- Check 2: npx (needed to run @browserstack/mcp-server) ---
if ! command -v npx >/dev/null 2>&1; then
  warnings="${warnings}npx not found — BrowserStack MCP server cannot start without it. Fix: install Node.js (https://nodejs.org). "
fi

# All clear
if [ -z "$warnings" ]; then
  exit 0
fi

printf '{"systemMessage":"aep-mobile: %s Run /aep-mobile:setup for full dependency check.",' "$warnings"
printf '"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":'
printf '"ENVIRONMENT CHECK (aep-mobile plugin): %s' "$warnings"
printf 'If the user invokes any aep-mobile QA skill, tell them about the missing dependencies and suggest running /aep-mobile:setup. '
printf 'Do not install anything yourself."}}\n'
exit 0
