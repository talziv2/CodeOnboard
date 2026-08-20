#!/usr/bin/env bash
# Refresh the git-excluded .ui-audit-fe inspection copy from frontend/.
#
# Excludes .env.local and next.config.ts on purpose, but no longer because of a
# proxy: the rig now points `NEXT_PUBLIC_API_URL` straight at :8000 and the backend
# carries its origin, which is what the shipping app does. The `/__api` rewrite that
# used to live here hung up at ~55s on a request the pipeline takes 2m38s to answer,
# and the screen said "Couldn't build your learning path" — indistinguishable from
# the product failing, and it cost two investigations before it stopped being
# believed. They stay excluded so a sync cannot put it back.
set -euo pipefail
cd "$(dirname "$0")/.."
# The source trees are REMOVED before extracting, not merged over.
#
# tar only adds and overwrites, so a file deleted in frontend/ used to survive in
# the copy indefinitely — and a stale component that still compiles is the worst
# kind of divergence, because the rig keeps working while measuring something the
# product no longer has. L5 deleted `FeedbackCard.tsx` and it sat in the rig until
# it was noticed by hand. Only these three directories are cleared: node_modules,
# .next, the config and the env file all have to survive.
rm -rf .ui-audit-fe/app .ui-audit-fe/components .ui-audit-fe/lib
tar cf - --exclude=node_modules --exclude=.next --exclude=next.config.ts --exclude=.env.local -C frontend . \
  | (cd .ui-audit-fe && tar xf -)
echo "synced frontend/ -> .ui-audit-fe/ (config + env preserved, stale files pruned)"
