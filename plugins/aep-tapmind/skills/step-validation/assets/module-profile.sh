#!/usr/bin/env bash
# Work out which tapmind-mobile-tests module a run belongs to, and the house shape of its tests,
# so §7 can emit a @Test method that drops straight into that module and compiles.
#
# Why derive instead of hardcoding a table: there are 19 modules today and they do not agree on
# anything — package roots differ (io.gojek.gofood.tests, com.gopay.constants, plain `tests`),
# base classes differ (BaseTest vs GoFoodTestBase vs CarePlatformBaseTest), and groups are
# sometimes string literals ("driverTest") and sometimes constants (FoodProjectConfig.CA_SMOKE).
# A hardcoded map would be wrong for module #20. Reading the module is always right.
#
# Usage:  module-profile.sh <config-path-or-module-name> [repo-root]
# Prints shell-eval'able assignments; exits non-zero only if the repo can't be found.
set -euo pipefail
note() { echo "$1" >&2; }

ARG="${1:-}"
REPO="${2:-${TAPMIND_TESTS_REPO:-}}"

# Repo root: explicit arg > env > walk up from the config path > sibling of cwd.
if [ -z "$REPO" ] && [ -f "$ARG" ]; then
  d="$(cd "$(dirname "$ARG")" && pwd)"
  while [ "$d" != "/" ]; do
    [ -f "$d/settings.gradle" ] && { REPO="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[ -z "$REPO" ] && [ -f "$(pwd)/settings.gradle" ] && REPO="$(pwd)"
[ -z "$REPO" ] && [ -d "$(dirname "$(pwd)")/tapmind-mobile-tests" ] && REPO="$(dirname "$(pwd)")/tapmind-mobile-tests"

if [ -z "$REPO" ] || [ ! -f "$REPO/settings.gradle" ]; then
  note "ERROR: cannot locate the tapmind-mobile-tests checkout."
  note "  Pass it as arg 2, or export TAPMIND_TESTS_REPO=/path/to/tapmind-mobile-tests."
  exit 1
fi

# Module: the config file's own directory when it sits inside the repo, else treat the arg as a name.
MODULE=""
if [ -f "$ARG" ]; then
  cand="$(basename "$(cd "$(dirname "$ARG")" && pwd)")"
  [ -f "$REPO/$cand/build.gradle" ] && MODULE="$cand"
fi
[ -z "$MODULE" ] && [ -f "$REPO/$ARG/build.gradle" ] && MODULE="$ARG"

if [ -z "$MODULE" ]; then
  note "Could not derive the module from: ${ARG:-<empty>}"
  note "Modules in $REPO:"
  for d in "$REPO"/*/; do [ -f "${d}build.gradle" ] && note "  $(basename "$d")"; done
  note "Ask the user which one, then re-run with that name."
  echo "MODULE="
  exit 0
fi

SRC="$REPO/$MODULE/src/test/java"
if [ ! -d "$SRC" ]; then
  note "Module '$MODULE' has no src/test/java — nothing to copy a house style from."
  note "Pick a module that holds tests, or ask the user which one this scenario belongs to."
  echo "MODULE=$(printf '%q' "$MODULE")"
  exit 0
fi

# Base class: whatever the module's own tests overwhelmingly extend.
BASE="$(grep -rho --include="*.java" 'extends [A-Za-z0-9_]*' "$SRC" 2>/dev/null \
        | awk '{print $2}' | sort | uniq -c | sort -rn | head -1 | awk '{print $2}' || true)"

# Package: the package of the file that declares that base class, so the emitted method
# lands beside its own siblings rather than in a constants/util package.
PKG="$(grep -rl --include="*.java" "class ${BASE}\b" "$SRC" 2>/dev/null | head -1 \
       | xargs -r grep -h '^package' | sed 's/package //;s/;//' || true)"
[ -z "$PKG" ] && PKG="$(find "$SRC" -name "*Tests.java" -o -name "*Test.java" 2>/dev/null | head -1 \
       | xargs -r grep -h '^package' | sed 's/package //;s/;//' || true)"

# NB: the variable is TEST_GROUPS, not GROUPS — $GROUPS is a bash builtin array (the caller's
# unix group ids). Assigning to it is silently ignored and you get "20" (staff) instead.
# Groups actually in use, most common first. Constants and literals both appear verbatim —
# emit them exactly as written; a constant needs its static import copied from the sample file.
TEST_GROUPS="$(grep -rho --include="*.java" 'groups *= *{[^}]*}' "$SRC" 2>/dev/null \
          | sed 's/groups *= *{//;s/}//' | tr ',' '\n' | sed 's/^ *//;s/ *$//' \
          | grep -v '^$' | sort | uniq -c | sort -rn | head -6 | sed 's/^ *[0-9]* *//' | paste -sd'|' - || true)"

# A real test in this module to copy the header shape from (annotations, imports, try/catch).
SAMPLE="$(grep -rl --include="*.java" '@Test' "$SRC" 2>/dev/null | head -1 || true)"

for v in BASE PKG SAMPLE; do
  [ -n "${!v}" ] || note "WARN: could not derive $v for '$MODULE' — read \$SAMPLE_TEST (or any test in the module) and copy its shape by hand."
done

note "module:  $MODULE"
note "package: $PKG"
note "base:    $BASE"
note "groups:  $TEST_GROUPS"
note "sample:  $SAMPLE"

cat <<OUT
MODULE=$(printf '%q' "$MODULE")
PACKAGE=$(printf '%q' "$PKG")
BASE_CLASS=$(printf '%q' "$BASE")
TEST_GROUPS=$(printf '%q' "$TEST_GROUPS")
SAMPLE_TEST=$(printf '%q' "$SAMPLE")
OUT
