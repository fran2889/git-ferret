#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only
# Shared helpers for the checked-in git hooks.
#
# Setting core.hooksPath for a repository hides the hooks a person configured
# globally. Each hook calls run_global_hook first, so the global hook still
# runs, and only then does its own work.

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

python_bin() {
    if [ -n "${PYTHON:-}" ]; then
        printf '%s\n' "$PYTHON"
    elif [ -x ".venv/bin/python" ]; then
        printf '%s\n' ".venv/bin/python"
    elif [ -x ".venv/Scripts/python.exe" ]; then
        printf '%s\n' ".venv/Scripts/python.exe"
    elif command -v python3 >/dev/null 2>&1; then
        printf '%s\n' python3
    else
        printf '%s\n' python
    fi
}

run_global_hook() {
    local name=$1
    shift

    local global_path
    global_path=$(git config --global --get core.hooksPath 2>/dev/null || true)
    [ -n "$global_path" ] || return 0

    case "$global_path" in
        "~"*) global_path="${HOME}${global_path#\~}" ;;
    esac
    case "$global_path" in
        /* | [A-Za-z]:/* | [A-Za-z]:\\*) ;;
        *) global_path="$repo_root/$global_path" ;;
    esac

    # Never run this directory twice, and do not recurse through a symlink to
    # it. A global path that resolves here is the same set of hooks.
    if [ "$(cd "$global_path" 2>/dev/null && pwd -P || true)" = "$(pwd -P)/.githooks" ]; then
        return 0
    fi

    local hook="$global_path/$name"
    if [ -x "$hook" ]; then
        "$hook" "$@"
    fi
}
