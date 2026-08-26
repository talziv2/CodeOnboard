"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import SessionCard from "@/components/SessionCard";
import SettingsMenu from "@/components/SettingsMenu";
import Button from "@/components/ui/Button";
import {
  archiveSession, deleteSession, listSessions, renameSession,
  type SessionSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { learnerName } from "@/lib/sessionSummary";
import { errorText, t } from "@/lib/strings";

/**
 * My Learning Sessions — where a returning learner lands.
 *
 * The dashboard is the answer to the question the product could not previously
 * answer at all: "what was I working on?" Before accounts, the only route back
 * into a session was the URL and the browser's history.
 *
 * Continue goes to the WELCOME page for a session that was never opened and to
 * the workspace otherwise, because the welcome page is the introduction and
 * showing it again to someone mid-journey would be starting them over.
 */
export default function SessionsPage() {
  const router = useRouter();
  const { status, user, signOut } = useAuth();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  // WHICH CARD IS OPEN — one at a time, so it lives here rather than inside the
  // cards. A card holding its own flag cannot close a sibling, and the result is
  // a column that only ever grows as the learner reads down it.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSessions((await listSessions(showArchived)).sessions);
      setError(null);
    } catch (e: unknown) {
      // A 401 is already handled centrally in `lib/api` — it redirects. Anything
      // reaching here is a real failure worth showing.
      setError(e instanceof Error ? errorText(e.message) : t.dashboard.loadFailed);
    }
  }, [showArchived]);

  useEffect(() => {
    if (status === "authenticated") load();
  }, [status, load]);

  /**
   * Poll only while something is actually being planned.
   *
   * A session in `generating` is being built by a background task, so nothing
   * pushes its completion here — but polling a dashboard where nothing is
   * happening is pure waste, so the interval exists only while at least one
   * card is waiting and clears itself the moment none is.
   */
  const generating = (sessions ?? []).some((s) => s.status === "generating");
  useEffect(() => {
    if (!generating) return;
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [generating, load]);

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  /**
   * Pressing anywhere else closes the open card.
   *
   * A selection you cannot put down is a mode, and this one has no visible way
   * out other than pressing the same card again — which is not where a hand
   * goes after reading. So the page dismisses on any press that lands outside a
   * card, and on Escape.
   *
   * `pointerdown`, not `click`: a press that starts outside and finishes on a
   * card (a drag, a text selection that overshoots) never fires `click` at all,
   * and the selection would stick. Bound only while something IS open, so the
   * dashboard adds no document listener in its resting state.
   *
   * A press INSIDE any card is left alone — that includes the other cards'
   * toggles, which close this one by opening themselves.
   */
  useEffect(() => {
    if (expandedId === null) return;
    const dismiss = (e: Event) => {
      if (!(e.target as Element | null)?.closest?.("[data-testid='session-card']")) {
        setExpandedId(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpandedId(null);
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", onKey);
    };
  }, [expandedId]);

  if (status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink">
        <p className="animate-pulse font-mono text-aside text-graphite">
          {t.auth.checking}
        </p>
      </main>
    );
  }

  const name = learnerName(user);

  const openSession = (session: SessionSummary) => {
    router.push(
      session.current_node_id
        ? `/session/${session.session_id}`
        : `/session/${session.session_id}/welcome`,
    );
  };

  return (
    <main className="min-h-screen bg-ink">
      {/* The header is a BAND, not the first item in a stack.
          It is the only zone on the page carrying the accent as a surface — a
          `signal-halo` wash fading out into `ink` — which is what stops the
          first screen a learner sees from reading as a list of grey boxes on a
          grey ground. Nothing here is a new colour: the wash is the same token
          the current-stop pin uses, at the scale of a page instead of a dot. */}
      <div className="border-b border-rule bg-linear-to-b from-signal-halo to-transparent">
        <header className="mx-auto flex w-full max-w-2xl items-start justify-between gap-4 px-6 pb-10 pt-12">
          <div className="flex flex-col gap-1">
            <span aria-hidden className="mb-3 h-2 w-2 rotate-45 bg-signal" />
            <h1 className="font-display text-display font-medium tracking-tight text-chalk">
              {t.dashboard.title}
            </h1>
            {/* The greeting, not the account. The email is how the system finds
                this learner; it is not what they are called, and it is already
                on the settings menu for anyone checking which account they are
                signed into. */}
            <p className="text-lede text-paper">
              {name ? t.dashboard.welcome(name) : t.dashboard.welcomeAnonymous}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <SettingsMenu />
            <Button variant="chrome" size="xs" onClick={signOut}>
              {t.auth.signOut}
            </Button>
          </div>
        </header>
      </div>

      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 pb-16 pt-8">
        {/* THE ACTIONS LEAD, because "start a new one" is a decision the learner
            makes on arrival rather than after reading every card they already
            have. Below the list it was reachable only by scrolling past
            everything it is an alternative to. */}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" size="md" onClick={() => router.push("/new")}>
            {t.dashboard.startNew}
          </Button>
          <Button variant="chrome" size="xs" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? t.dashboard.hideArchived : t.dashboard.showArchived}
          </Button>
        </div>

        {error && <p role="alert" className="text-aside text-rust">{error}</p>}

        {sessions === null ? (
          <p className="animate-pulse font-mono text-aside text-graphite">
            {t.dashboard.loading}
          </p>
        ) : sessions.length === 0 ? (
          /* The empty state INVITES rather than apologises: someone with no
             sessions has not lost anything, they simply have not started.
             It carries no button of its own any more — `Start a new session`
             now sits directly above it, and two primaries a centimetre apart
             saying the same thing is one of them too many. */
          <div className="rounded-card border border-dashed border-rule p-6">
            <p className="text-aside text-graphite">
              {showArchived ? t.dashboard.noneArchived : t.dashboard.empty}
            </p>
          </div>
        ) : (
          /* `gap-4`, not `gap-3`: the open card scales past its own box, and
             the extra step is the room it grows into. */
          <ul className="flex flex-col gap-4">
            {sessions.map((session) => (
              <SessionCard
                key={session.session_id}
                session={session}
                expanded={expandedId === session.session_id}
                onToggle={() => setExpandedId((id) =>
                  id === session.session_id ? null : session.session_id,
                )}
                onContinue={() => openSession(session)}
                onRename={async (title) => { await renameSession(session.session_id, title); await load(); }}
                onArchive={async (archived) => { await archiveSession(session.session_id, archived); await load(); }}
                onDelete={async () => { await deleteSession(session.session_id); await load(); }}
              />
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
