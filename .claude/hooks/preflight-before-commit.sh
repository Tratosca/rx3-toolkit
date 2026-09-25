#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# PreToolUse hook: before an agent runs `git commit`, run the publication
# preflight. Exit 2 blocks the tool call and shows stderr to the agent.
set -eu
command=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))' 2>/dev/null || true)
case "$command" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac
if ! sh "$(dirname "$0")/../../scripts/preflight.sh" >&2; then
    echo "preflight rejected a publishable file; fix that before committing" >&2
    exit 2
fi
