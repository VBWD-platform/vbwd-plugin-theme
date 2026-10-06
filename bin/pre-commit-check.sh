#!/usr/bin/env bash
#
# Pre-commit gate for a vbwd theme plugin repo (vbwd-plugin-theme, -theme-cms, ...).
# ================================================================================
# Canonical copy: vbwd-plugin-theme `bin/pre-commit-check.sh`. Every theme repo ships a
# byte-identical copy (guarded by theme `tests/unit/test_pre_commit_script_copies.py`);
# the plugin name is derived from the repo directory name (`theme_cms` or
# `vbwd-plugin-theme-cms` -> theme_cms).
#
# Lint / unit / integration are delegated to the backend gate
# (`vbwd-backend/bin/pre-commit-check.sh --plugin <name> --<part>`: shared docker test DB,
# full fidelity), plus what that gate cannot see for a gitignored plugin dir:
#   - black --check / flake8 over this repo's .py files (backend docker `test` service),
#   - `node --test` on tests/js/*.test.mjs (per file; Node 22 rejects the directory form).
#
# Usage:
#   bin/pre-commit-check.sh                # = --full
#   bin/pre-commit-check.sh --full         # lint + unit + integration
#   bin/pre-commit-check.sh --quick        # lint + unit
#   bin/pre-commit-check.sh --lint         # static analysis only
#   bin/pre-commit-check.sh --unit         # unit tests (+ node runtime tests) only
#   bin/pre-commit-check.sh --integration  # integration tests only
#   bin/pre-commit-check.sh --e2e          # this repo's Playwright walkthrough (theme-mode stack)
#
# Layouts:
#   SDK checkout  vbwd-backend/plugins/<name>  -> uses that vbwd-backend.
#   Standalone    VBWD_BACKEND_DIR=/path/to/vbwd-backend (its plugins/ must hold the declared
#                 dependencies); this repo is symlinked in as plugins/<name> (and mounted at its
#                 own path in the backend test containers) unless the backend already holds it.
#   --e2e         VBWD_FE_USER_DIR (default: the SDK sibling vbwd-fe-user), E2E_BASE_URL
#                 (default http://localhost:8080) serving a VBWD_FRONTEND_MODE=theme stack.
#
# Exit codes: 0 ok · 1 static analysis · 2 unit tests, or setup/usage error · 3 integration · 4 e2e
#
set -euo pipefail

readonly EXIT_LINT=1
readonly EXIT_UNIT=2
readonly EXIT_SETUP=2
readonly EXIT_INTEGRATION=3
readonly EXIT_E2E=4
readonly DEFAULT_E2E_BASE_URL="http://localhost:8080"
readonly MODE_PROBE_PATH="/_render/_theme/mode"
readonly FLAKE8_MAX_LINE_LENGTH=120

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NO_COLOR='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SCRIPT_DIR REPO_DIR

plugin_name_from_dir() {
    local directory_name
    directory_name="$(basename "$1")"
    directory_name="${directory_name#vbwd-plugin-}"
    printf '%s' "${directory_name//-/_}"
}
PLUGIN_NAME="$(plugin_name_from_dir "$REPO_DIR")"
readonly PLUGIN_NAME

print_usage() {
    sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NO_COLOR}"
    echo -e "${BLUE}$1${NO_COLOR}"
    echo -e "${BLUE}========================================${NO_COLOR}"
}

print_result() {
    if [ "$2" -eq 0 ]; then
        echo -e "${GREEN}[PASS]${NO_COLOR} $1"
    else
        echo -e "${RED}[FAIL]${NO_COLOR} $1"
    fi
}

warn() {
    echo -e "${YELLOW}WARNING: $1${NO_COLOR}" >&2
}

# --------------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------------
RUN_LINT=true
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_E2E=false

select_parts() {
    RUN_LINT="$1"
    RUN_UNIT="$2"
    RUN_INTEGRATION="$3"
    RUN_E2E="$4"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --full) select_parts true true true false ;;
        --quick) select_parts true true false false ;;
        --lint) select_parts true false false false ;;
        --unit) select_parts false true false false ;;
        --integration) select_parts false false true false ;;
        --e2e) select_parts false false false true ;;
        --help | -h)
            print_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NO_COLOR} (see --help)" >&2
            exit "$EXIT_SETUP"
            ;;
    esac
    shift
done

# --------------------------------------------------------------------------------
# Environment: where vbwd-backend is, and how this repo is visible inside it
# --------------------------------------------------------------------------------
IN_CONTAINER_OR_CI=false
if [ -f /.dockerenv ] || [ -n "${GITHUB_ACTIONS:-}" ] || [ "${CI:-}" = "true" ]; then
    IN_CONTAINER_OR_CI=true
fi

BACKEND_DIR=""
COMPOSE_OVERRIDE_FILE=""

print_standalone_setup() {
    cat >&2 <<EOF
This repo ($REPO_DIR) is not inside a vbwd-backend checkout (no ../../bin/pre-commit-check.sh).

Standalone setup:
  1. Check out vbwd-backend and the plugins this one depends on (see PluginMetadata.dependencies
     in __init__.py), e.g.:
       git clone https://github.com/VBWD-platform/vbwd-backend.git ~/vbwd-backend
       git clone https://github.com/VBWD-platform/vbwd-plugin-theme.git ~/vbwd-backend/plugins/theme
  2. Start its stack once:   (cd ~/vbwd-backend && make up)
  3. Point this gate at it:  VBWD_BACKEND_DIR=~/vbwd-backend bin/pre-commit-check.sh --full

  The gate symlinks this repo in as \$VBWD_BACKEND_DIR/plugins/$PLUGIN_NAME and mounts it at its
  own path in the backend test containers, so the symlink resolves inside docker too.
EOF
}

physical_path() {
    (cd "$1" && pwd -P)
}

# A symlink alone would dangle inside docker (only vbwd-backend is mounted at /app), so the
# test containers also get this repo mounted at its own absolute path.
mount_repo_at_its_own_path() {
    COMPOSE_OVERRIDE_FILE="$(mktemp "${TMPDIR:-/tmp}/vbwd-${PLUGIN_NAME}-compose.XXXXXX")"
    cat >"$COMPOSE_OVERRIDE_FILE" <<EOF
services:
  test:
    volumes:
      - "$REPO_DIR:$REPO_DIR"
  test-integration:
    volumes:
      - "$REPO_DIR:$REPO_DIR"
EOF
    trap 'rm -f "$COMPOSE_OVERRIDE_FILE"' EXIT
    export COMPOSE_FILE="$BACKEND_DIR/docker-compose.yaml:$COMPOSE_OVERRIDE_FILE"
}

resolve_standalone_backend() {
    if [ -z "${VBWD_BACKEND_DIR:-}" ] || [ ! -f "$VBWD_BACKEND_DIR/bin/pre-commit-check.sh" ]; then
        print_standalone_setup
        exit "$EXIT_SETUP"
    fi
    BACKEND_DIR="$(cd "$VBWD_BACKEND_DIR" && pwd)"
    local plugin_path="$BACKEND_DIR/plugins/$PLUGIN_NAME"
    if [ ! -e "$plugin_path" ] && [ ! -L "$plugin_path" ]; then
        ln -s "$REPO_DIR" "$plugin_path"
        echo -e "${YELLOW}Symlinked $plugin_path -> $REPO_DIR (remove it with: rm \"$plugin_path\").${NO_COLOR}"
    fi
    if [ ! -d "$plugin_path" ] || [ "$(physical_path "$plugin_path")" != "$(physical_path "$REPO_DIR")" ]; then
        echo -e "${RED}$plugin_path is not this repo (a different checkout or a dangling link); move it away first.${NO_COLOR}" >&2
        exit "$EXIT_SETUP"
    fi
    if [ -L "$plugin_path" ]; then
        mount_repo_at_its_own_path
    fi
}

resolve_backend() {
    local sdk_backend_dir="$REPO_DIR/../.."
    if [ "$(basename "$(dirname "$REPO_DIR")")" = "plugins" ] && [ -f "$sdk_backend_dir/bin/pre-commit-check.sh" ]; then
        BACKEND_DIR="$(cd "$sdk_backend_dir" && pwd)"
        return
    fi
    resolve_standalone_backend
}

# --------------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------------
run_backend_gate_part() {
    (cd "$BACKEND_DIR" && bin/pre-commit-check.sh --plugin "$PLUGIN_NAME" "$1")
}

run_in_backend_test_service() {
    if $IN_CONTAINER_OR_CI; then
        (cd "$BACKEND_DIR" && "$@")
    else
        (cd "$BACKEND_DIR" && docker compose run --rm -T test "$@")
    fi
}

run_explicit_style_checks() {
    local failed=0
    print_header "Black + Flake8 over plugins/$PLUGIN_NAME (explicit, gitignore-proof)"
    run_in_backend_test_service black --check --diff "plugins/$PLUGIN_NAME/" \
        --exclude='/(\.git|__pycache__|\.pytest_cache)/' || failed=1
    run_in_backend_test_service flake8 "plugins/$PLUGIN_NAME/" \
        --max-line-length="$FLAKE8_MAX_LINE_LENGTH" --extend-ignore=E203,W503 \
        --exclude=.git,__pycache__,.pytest_cache || failed=1
    print_result "Black + Flake8 (this repo)" "$failed"
    return "$failed"
}

run_node_runtime_tests() {
    local failed=0
    local test_files=()
    local test_file
    for test_file in "$REPO_DIR"/tests/js/*.test.mjs; do
        [ -f "$test_file" ] && test_files+=("$test_file")
    done
    print_header "Runtime JS tests (node --test, per file)"
    if [ "${#test_files[@]}" -eq 0 ]; then
        echo "No tests/js/*.test.mjs — skipping"
        return 0
    fi
    if ! command -v node >/dev/null 2>&1; then
        echo -e "${RED}node is not installed (Node 22+ required for tests/js).${NO_COLOR}" >&2
        return 1
    fi
    for test_file in "${test_files[@]}"; do
        node --test "$test_file" || failed=1
    done
    print_result "Runtime JS tests (${#test_files[@]} files)" "$failed"
    return "$failed"
}

run_lint() {
    local failed=0
    run_backend_gate_part --lint || failed=1
    run_explicit_style_checks || failed=1
    return "$failed"
}

run_unit() {
    local failed=0
    run_backend_gate_part --unit || failed=1
    run_node_runtime_tests || failed=1
    return "$failed"
}

run_integration() {
    run_backend_gate_part --integration
}

resolve_fe_user_dir() {
    local fe_user_dir="${VBWD_FE_USER_DIR:-$REPO_DIR/../../../vbwd-fe-user}"
    if [ ! -f "$fe_user_dir/playwright.theme.config.ts" ] || [ ! -d "$fe_user_dir/node_modules/@playwright/test" ]; then
        cat >&2 <<EOF
--e2e needs a vbwd-fe-user checkout with playwright.theme.config.ts and its npm deps installed.
  Not found at: $fe_user_dir
  Set VBWD_FE_USER_DIR=/path/to/vbwd-fe-user (npm install there; npx playwright install chromium).
EOF
        exit "$EXIT_SETUP"
    fi
    (cd "$fe_user_dir" && pwd)
}

warn_unless_theme_mode() {
    local probe_status
    probe_status="$(curl -s -o /dev/null -w '%{http_code}' "$1$MODE_PROBE_PATH" || true)"
    if [ "$probe_status" != "200" ]; then
        warn "$1$MODE_PROBE_PATH answered $probe_status (expected 200): the stack is not in theme mode;"
        warn "the walkthrough will fail. See docs/architecture/frontend-modes.md 'How to switch locally'."
    fi
}

run_e2e() {
    local fe_user_dir base_url
    fe_user_dir="$(resolve_fe_user_dir)" || exit "$EXIT_SETUP"
    base_url="${E2E_BASE_URL:-$DEFAULT_E2E_BASE_URL}"
    print_header "E2E walkthrough @$PLUGIN_NAME against $base_url"
    warn_unless_theme_mode "$base_url"
    (cd "$fe_user_dir" && E2E_BASE_URL="$base_url" E2E_FRONTEND_MODE=theme \
        VBWD_THEME_PLUGINS_DIR="$(dirname "$REPO_DIR")" \
        npx playwright test -c playwright.theme.config.ts --grep "@${PLUGIN_NAME}(\\s|$)")
}

# --------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------
main() {
    local lint_result=0 unit_result=0 integration_result=0 e2e_result=0
    local start_time
    start_time="$(date +%s)"
    echo -e "${BLUE}Pre-commit check — $PLUGIN_NAME ($REPO_DIR)${NO_COLOR}"

    if $RUN_LINT || $RUN_UNIT || $RUN_INTEGRATION; then
        resolve_backend
        echo "vbwd-backend: $BACKEND_DIR"
    fi
    if $RUN_LINT; then run_lint || lint_result=1; fi
    if $RUN_UNIT; then run_unit || unit_result=1; fi
    if $RUN_INTEGRATION; then run_integration || integration_result=1; fi
    if $RUN_E2E; then run_e2e || e2e_result=1; fi

    print_header "SUMMARY — $PLUGIN_NAME ($(($(date +%s) - start_time))s)"
    if $RUN_LINT; then print_result "Static analysis" "$lint_result"; fi
    if $RUN_UNIT; then print_result "Unit tests" "$unit_result"; fi
    if $RUN_INTEGRATION; then print_result "Integration tests" "$integration_result"; fi
    if $RUN_E2E; then print_result "E2E walkthrough" "$e2e_result"; fi

    if [ "$lint_result" -ne 0 ]; then exit "$EXIT_LINT"; fi
    if [ "$unit_result" -ne 0 ]; then exit "$EXIT_UNIT"; fi
    if [ "$integration_result" -ne 0 ]; then exit "$EXIT_INTEGRATION"; fi
    if [ "$e2e_result" -ne 0 ]; then exit "$EXIT_E2E"; fi
    echo -e "${GREEN}SUCCESS: all selected checks passed for $PLUGIN_NAME.${NO_COLOR}"
}

main
