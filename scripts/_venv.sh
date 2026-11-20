#!/usr/bin/env bash
# Shared helper, sourced by the other scripts. Not meant to be run directly.
# Sets PROJECT_ROOT and VENV_PY, creating .venv via setup_dev.sh if needed.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
    echo ".venv not found - running scripts/setup_dev.sh first ..." >&2
    "$PROJECT_ROOT/scripts/setup_dev.sh" >&2
fi
