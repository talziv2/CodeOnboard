"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import { InlineProse } from "@/components/ui/Prose";
import type { SessionSummary } from "@/lib/api";
import {
  relativeTime, repoLabel, sessionGoal, sessionTitle,
} from "@/lib/sessionSummary";
import { t } from "@/lib/strings";

/**
 * One session on the dashboard.
 *
 * The card answers three questions in the order a returning learner asks them:
 * WHICH repository, WHAT was I doing, and HOW FAR did I get. The title comes
 * first because it is the learner's own words for the second question — the
 * repository is orientation, but the goal is what they were actually here for.
 *
 * ── Pressing the card SELECTS it; only `Continue` opens the session ───────────
 *
 * A card that navigates on any click cannot be READ, because reading it and
 * leaving it are the same gesture. So the card is a DISCLOSURE: pressing it
 * grows the card and releases the blurb's three-line clamp, and pressing it
 * again puts it back. Opening the session is one explicit button, and it goes
 * where the learner actually left off.
 *
 * EXACTLY ONE CARD IS OPEN AT A TIME, which is why `expanded` is a prop and not
 * this component's own state: "which one is open" is a fact about the LIST, and
 * a card cannot close a sibling it does not know about. Opening a second one
 * closes the first, so the page never becomes a column of expanded cards with
 * no shape to it.
 *
 * The disclosure is drawn as an absolutely-positioned button UNDERNEATH the
 * content rather than as a wrapper around it, because the card also carries
 * Continue / Rename / Archive / Delete and a `<button>` inside a `<button>` is
 * invalid markup that browsers repair by unnesting — losing the outer control.
 * So the content layer is `pointer-events-none` and lets clicks fall through to
 * it, and the action row turns them back on for itself.
 *
 * It is not rendered at all while the card is in a state that is not "read me"
 * — renaming, confirming a delete — so there is never an invisible target over
 * a form the learner is filling in.
 */
export default function SessionCard({
  session, expanded, onToggle, onContinue, onRename, onArchive, onDelete,
}: {
  session: SessionSummary;
  /** Owned by the list, so opening this one closes whichever was open. */
  expanded: boolean;
  onToggle: () => void;
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
  // The two states that are not "a session you can open". `generating` is
  // waiting on a background task; `failed` is a plan that never arrived — and
  // saying so is the whole reason the row is created before the work starts,
  // rather than after it.
  const generating = session.status === "generating";
  const failed = session.status === "failed";

  const title = sessionTitle(session);
  const goal = sessionGoal(session);
  // EVERY card selects, including one with no blurb to unclamp. Growth is the
  // selection signal first and the reveal second, and a card that ignores a
  // click because of something the learner cannot see reads as broken rather
  // than as considered. `busy` is deliberately NOT a condition either: growing
  // a card is a local reading gesture, and an archive request in flight is no
  // reason to refuse it.
  const expandable = !renaming && !confirmingDelete;

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try { await action(); } finally { setBusy(false); }
  };

  return (
    <li
      className={`group relative rounded-card border bg-slab transition
        duration-[var(--motion-state)] ease-[var(--ease-emphasis)]
        ${expanded
          ? "z-10 scale-[1.04] border-signal shadow-overlay"
          : "border-rule shadow-card hover:border-signal-dim hover:shadow-overlay"}
        ${expandable && !expanded ? "hover:-translate-y-0.5" : ""}
        ${archived ? "opacity-60" : ""}`}
      data-testid="session-card"
      data-expanded={expanded ? "true" : undefined}
    >
      {/* The disclosure, under everything. `inset-0` rather than a wrapper —
          see the note above for why this cannot be an enclosing element. */}
      {expandable && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={expanded ? t.dashboard.collapse(title) : t.dashboard.expand(title)}
          className="absolute inset-0 rounded-card"
          onClick={onToggle}
        />
      )}

      <div className="pointer-events-none relative flex flex-col gap-3 p-5">
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-signal-dim">
            {repoLabel(session.repo_url)}
            {archived && (
              <span className="text-graphite"> · {t.dashboard.archived}</span>
            )}
          </span>

          {renaming ? (
            <form
              className="pointer-events-auto flex gap-2"
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
                onClick={() => { setDraft(title); setRenaming(false); }}>
                {t.dashboard.cancel}
              </Button>
            </form>
          ) : (
            <h3 className="font-display text-head font-medium tracking-tight text-chalk">
              {title}
            </h3>
          )}
        </div>

        {/* What this repository IS. The welcome briefing's own opening, so the
            card reuses prose the learner has already been shown rather than a
            second description that could disagree with it. Absent on a session
            whose welcome page was never opened, and then the card simply has
            one fewer thing to say. Clamped here because the clamp belongs to
            the card, not to the prose — and releasing that clamp is what the
            card growing is FOR. */}
        {session.repo_blurb && (
          <p className={`text-aside text-paper ${expanded ? "" : "line-clamp-3"}`}>
            <InlineProse text={session.repo_blurb} tone="paper" />
          </p>
        )}

        {goal && (
          <p className="line-clamp-2 text-meta text-graphite">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-muted">
              {t.dashboard.goalLabel}{" "}
            </span>
            {goal}
          </p>
        )}

        {percent !== null && (
          <div
            className="h-1 w-full overflow-hidden rounded-full bg-raise"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t.dashboard.ready(percent)}
          >
            <div
              className="h-full rounded-full bg-signal transition-[width] duration-[var(--motion-layout)] ease-[var(--ease-emphasis)]"
              style={{ width: `${percent}%` }}
            />
          </div>
        )}

        <p className="text-meta text-graphite">
          {relativeTime(session.last_active_at ?? session.updated_at)}
          {percent !== null && ` · ${t.dashboard.ready(percent)}`}
          {percent !== null && stops_total
            ? ` · ${t.dashboard.stops(stops_settled ?? 0, stops_total)}`
            : ""}
        </p>

        <div className="flex flex-wrap items-center gap-2 border-t border-rule pt-3">
          {generating ? (
            <span className="animate-pulse font-mono text-meta text-graphite">
              {t.dashboard.generating}
            </span>
          ) : failed ? (
            <span className="font-mono text-meta text-rust">{t.dashboard.failed}</span>
          ) : (
            /* THE ONLY WAY OUT OF THE DASHBOARD. `openSession` sends a learner
               who has started to the stop they left off at and one who has not
               to the welcome page — so this is "carry on", not "open". */
            <span className="pointer-events-auto">
              <Button
                variant="primary"
                size="sm"
                aria-label={t.dashboard.openSession(title)}
                onClick={onContinue}
                disabled={busy}
              >
                {t.dashboard.continue}
              </Button>
            </span>
          )}

          <span className="pointer-events-auto ms-auto flex flex-wrap items-center gap-2">
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
          </span>
        </div>
      </div>
    </li>
  );
}
