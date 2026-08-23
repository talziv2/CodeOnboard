"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import type { SessionSummary } from "@/lib/api";
import { relativeTime, repoLabel, sessionTitle } from "@/lib/sessionSummary";
import { t } from "@/lib/strings";

/**
 * One session on the dashboard.
 *
 * The card answers three questions in the order a returning learner asks them:
 * WHICH repository, WHAT was I doing, and HOW FAR did I get. The title comes
 * first because it is the learner's own words for the second question — the
 * repository is orientation, but the goal is what they were actually here for.
 */
export default function SessionCard({
  session, onContinue, onRename, onArchive, onDelete,
}: {
  session: SessionSummary;
  onContinue: () => void;
  onRename: (title: string) => Promise<void>;
  onArchive: (archived: boolean) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(sessionTitle(session));
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const { goal_readiness, stops_settled, stops_total } = session.progress;
  // NULL means NOT COMPUTED — a session migrated from before the cache existed.
  // Rendering it as 0% would be a claim about the learner rather than about the
  // cache, so it says nothing instead.
  const percent = goal_readiness === null ? null : Math.round(goal_readiness * 100);
  const archived = session.archived_at !== null;

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try { await action(); } finally { setBusy(false); }
  };

  return (
    <li
      className={`flex flex-col gap-3 rounded-field border border-rule bg-trench p-4 ${
        archived ? "opacity-60" : ""
      }`}
      data-testid="session-card"
    >
      <div className="flex flex-col gap-1">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {repoLabel(session.repo_url)}
          {archived && ` · ${t.dashboard.archived}`}
        </span>

        {renaming ? (
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              await run(() => onRename(draft));
              setRenaming(false);
            }}
          >
            <input
              autoFocus
              aria-label={t.dashboard.renameLabel}
              className="flex-1 rounded-field border border-rule bg-ink px-2.5 py-1.5 text-aside text-chalk focus:border-signal-dim"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <Button variant="primary" size="xs" type="submit" disabled={busy}>
              {t.dashboard.save}
            </Button>
            <Button variant="chrome" size="xs" type="button"
              onClick={() => { setDraft(sessionTitle(session)); setRenaming(false); }}>
              {t.dashboard.cancel}
            </Button>
          </form>
        ) : (
          <h3 className="font-display text-head font-medium tracking-tight text-chalk">
            {sessionTitle(session)}
          </h3>
        )}

        <p className="text-meta text-graphite">
          {relativeTime(session.last_active_at ?? session.updated_at)}
          {percent !== null && ` · ${t.dashboard.ready(percent)}`}
          {percent !== null && stops_total
            ? ` · ${t.dashboard.stops(stops_settled ?? 0, stops_total)}`
            : ""}
        </p>
      </div>

      {percent !== null && (
        <div
          className="h-1 w-full overflow-hidden rounded-full bg-rule"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={t.dashboard.ready(percent)}
        >
          <div className="h-full bg-signal" style={{ width: `${percent}%` }} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm" onClick={onContinue} disabled={busy}>
          {t.dashboard.continue}
        </Button>
        {!renaming && (
          <Button variant="chrome" size="xs" onClick={() => setRenaming(true)} disabled={busy}>
            {t.dashboard.rename}
          </Button>
        )}
        <Button variant="chrome" size="xs" disabled={busy}
          onClick={() => run(() => onArchive(!archived))}>
          {archived ? t.dashboard.unarchive : t.dashboard.archive}
        </Button>
        {/* Deleting is irreversible, so it is confirmed in place rather than
            behind a dialog the learner can dismiss by accident. Archiving is
            offered first, and is what most people actually want. */}
        {confirmingDelete ? (
          <span className="flex items-center gap-2">
            <span className="text-meta text-rust">{t.dashboard.deleteConfirm}</span>
            {/* No `danger` variant in the design system, and this is not the
                place to invent one: `chrome` with rust text says "destructive"
                using tokens that already exist. */}
            <Button variant="chrome" size="xs" className="text-rust" disabled={busy}
              onClick={() => run(onDelete)}>
              {t.dashboard.deleteYes}
            </Button>
            <Button variant="chrome" size="xs" onClick={() => setConfirmingDelete(false)}>
              {t.dashboard.cancel}
            </Button>
          </span>
        ) : (
          <Button variant="chrome" size="xs" disabled={busy}
            onClick={() => setConfirmingDelete(true)}>
            {t.dashboard.delete}
          </Button>
        )}
      </div>
    </li>
  );
}
