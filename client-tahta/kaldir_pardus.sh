#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../kaldir_pardus.sh" ]; then
    exec bash "$SCRIPT_DIR/../kaldir_pardus.sh" "$@"
fi
