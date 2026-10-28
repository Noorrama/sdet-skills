#!/usr/bin/env bash
# Print the mobile QA plugin root (directory that contains skills/nlp-codegen and skills/step-validation).
# Claude Code sets CLAUDE_PLUGIN_ROOT. Cursor plugins set CURSOR_PLUGIN_ROOT.
# TAPMIND_PLUGIN_ROOT is an explicit override (legacy name; same directory after TapMind skills ship in-plugin).
set -euo pipefail

ok() { [ -d "$1/skills/step-validation" ] && [ -d "$1/skills/nlp-codegen" ]; }

for v in TAPMIND_PLUGIN_ROOT CURSOR_PLUGIN_ROOT CLAUDE_PLUGIN_ROOT; do
  root="${!v:-}"
  if [ -n "$root" ] && ok "$root"; then
    printf '%s\n' "$root"
    exit 0
  fi
done

d="$(cd "$(dirname "$0")/.." && pwd)"
if ok "$d"; then
  printf '%s\n' "$d"
  exit 0
fi

echo "ERROR: cannot find mobile QA plugin root (skills/step-validation + skills/nlp-codegen)." >&2
echo "  Install qa-mobile-toolkit (Prodigy) or aep-mobile; set CURSOR_PLUGIN_ROOT / CLAUDE_PLUGIN_ROOT." >&2
exit 1
