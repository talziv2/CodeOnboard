#!/usr/bin/env bash
# Refresh the git-excluded .ui-audit-fe inspection copy from frontend/.
#
# Excludes next.config.ts and .env.local on purpose: together they route the API
# through this origin (`/__api` -> :8000), so the copy needs no CORS entry and no
# backend of its own. Overwriting either kills the dev server and silently breaks
# every API call — the page then renders only its "couldn't reach the server"
# state, which looks like a working inspection until you notice there is no
# session on it.
set -euo pipefail
cd "$(dirname "$0")/.."
tar cf - --exclude=node_modules --exclude=.next --exclude=next.config.ts --exclude=.env.local -C frontend . \
  | (cd .ui-audit-fe && tar xf -)
echo "synced frontend/ -> .ui-audit-fe/ (next.config.ts + .env.local preserved)"
