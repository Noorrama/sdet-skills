#!/usr/bin/env bash
# Fails if a plugin's files changed against the target branch but its
# .claude-plugin/plugin.json "version" field didn't also change — otherwise
# installed users silently never see the update (Claude Code only re-pulls
# a plugin when that string changes).
set -euo pipefail

target="${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-main}"
git fetch --unshallow origin "$target"
base="origin/$target"

changed_files=$(git diff --name-only "$base...HEAD" -- plugins)
if [ -z "$changed_files" ]; then
  echo "No plugin files changed."
  exit 0
fi

fail=0
for plugin_dir in $(echo "$changed_files" | cut -d/ -f1-2 | sort -u); do
  manifest="$plugin_dir/.claude-plugin/plugin.json"

  if [ ! -f "$manifest" ]; then
    echo "FAIL: $plugin_dir changed but has no $manifest"
    fail=1
    continue
  fi

  if git cat-file -e "$base:$manifest" 2>/dev/null; then
    old_version=$(git show "$base:$manifest" | python3 -c "import json,sys; print(json.load(sys.stdin).get('version',''))")
  else
    old_version=""
  fi
  new_version=$(python3 -c "import json; print(json.load(open('$manifest')).get('version',''))")

  if [ "$old_version" = "$new_version" ]; then
    echo "FAIL: $plugin_dir changed but $manifest version wasn't bumped (still $new_version)"
    fail=1
  else
    echo "OK: $plugin_dir version bumped $old_version -> $new_version"
  fi
done

exit $fail
