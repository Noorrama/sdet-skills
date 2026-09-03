#!/bin/sh
# Check aep-mobile plugin dependencies at session start.
# Stays silent when everything is present. Warns on missing deps.
#
# Checks: (1) python3 + jsonschema for schema validation
#          (2) npx availability for BrowserStack MCP server
#
# Emits Cursor format when CURSOR_PLUGIN_ROOT is set, else Claude Code format.

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

context="ENVIRONMENT CHECK (aep-mobile plugin): ${warnings}BrowserStack MCP (needs npx) is required only for regression-extractor and SDET-plan upload; the prd/rfc/design/task extractors do not need it and run on python3 + jsonschema alone. If the user invokes a BrowserStack-backed skill, tell them about the missing dependencies and suggest running mobile-context-extraction (setup-only). Do not install anything yourself."

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  # Cursor hook output format
  printf '{"additional_context":"%s"}\n' "$context"
else
  # Claude Code hook output format
  printf '{"systemMessage":"aep-mobile: %s Run mobile-context-extraction (setup-only) for a full dependency check.",' "$warnings"
  printf '"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":'
  printf '"%s"}}\n' "$context"
fi
exit 0
