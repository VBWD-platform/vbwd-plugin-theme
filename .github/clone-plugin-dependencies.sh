#!/usr/bin/env bash
#
# Clone every plugin the plugin under test needs into plugins/<dir> (CI only).
# ===========================================================================
# Identical copy in every vbwd-plugin-theme* repo. Run from the vbwd-backend root:
#
#   bash plugins/<plugin>/.github/clone-plugin-dependencies.sh <plugin> [peer-plugin ...]
#
# The set comes from the backend's ci/missing_plugin_deps.py — the declared
# PluginMetadata.dependencies (transitively) plus the sibling plugins the plugin's
# tests import — so the workflow never keeps a hand-written list that drifts.
# A version specifier ("theme>=1.0") is stripped to the plugin name. Repos are
# VBWD-platform/vbwd-plugin-<name, kebab-cased>, falling back to the snake spelling.
# Extra arguments name peer plugins a suite boots without declaring them (e.g. the
# payment plugins an integration suite enables); they are cloned first, and their own
# declared dependencies follow through the same resolution.
# A dependency that cannot be cloned fails the job: these are required, not optional.
#
set -euo pipefail

readonly GITHUB_ORGANISATION_URL="https://github.com/VBWD-platform"
readonly MAX_RESOLUTION_ROUNDS=10

plugin_under_test="${1:?usage: clone-plugin-dependencies.sh <plugin-directory> [peer-plugin ...]}"
shift
peer_plugins=("$@")

missing_dependencies() {
  python ci/missing_plugin_deps.py --for "${plugin_under_test}" \
    | sed -E 's/[<>=!~ ].*$//' \
    | sort -u
}

clone_dependency() {
  local dependency="$1"
  local directory="${dependency//-/_}"
  local suffix
  for suffix in "${dependency//_/-}" "${dependency//-/_}"; do
    if git clone --depth=1 -q "${GITHUB_ORGANISATION_URL}/vbwd-plugin-${suffix}.git" "plugins/${directory}" 2>/dev/null; then
      echo "Cloned '${dependency}' from vbwd-plugin-${suffix}"
      return 0
    fi
  done
  echo "::error::cannot clone required plugin '${dependency}' (tried vbwd-plugin-${dependency//_/-} and vbwd-plugin-${dependency//-/_})"
  return 1
}

for peer_plugin in ${peer_plugins[@]+"${peer_plugins[@]}"}; do
  if [ ! -d "plugins/${peer_plugin//-/_}" ]; then
    clone_dependency "${peer_plugin}"
  fi
done

for _round in $(seq 1 "${MAX_RESOLUTION_ROUNDS}"); do
  cloned_any=""
  dependencies="$(missing_dependencies)"
  for dependency in ${dependencies}; do
    if [ -d "plugins/${dependency//-/_}" ]; then
      continue
    fi
    clone_dependency "${dependency}"
    cloned_any=1
  done
  if [ -z "${cloned_any}" ]; then
    echo "Plugin set: $(find plugins -mindepth 2 -maxdepth 2 -name __init__.py | cut -d/ -f2 | sort | tr '\n' ' ')"
    exit 0
  fi
done

echo "::error::plugin dependencies still unresolved after ${MAX_RESOLUTION_ROUNDS} rounds"
exit 1
