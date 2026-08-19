#!/usr/bin/env bash
# Refresh the git-excluded .ui-audit-fe inspection copy from frontend/.
#
# Excludes next.config.ts on purpose: the copy carries an API proxy so it needs
# no CORS entry and no backend of its own. Overwriting it kills the dev server
# and silently breaks every API call.
set -euo pipefail
cd "$(dirname "$0")/.."
tar cf - --exclude=node_modules --exclude=.next --exclude=next.config.ts -C frontend . \
  | (cd .ui-audit-fe && tar xf -)
echo "synced frontend/ -> .ui-audit-fe/ (next.config.ts preserved)"
