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

  if (status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink">
        <p className="animate-pulse font-mono text-aside text-graphite">
          {t.auth.checking}
        </p>
      </main>
    );
  }

  const openSession = (session: SessionSummary) => {
    router.push(
      session.current_node_id
        ? `/session/${session.session_id}`
        : `/session/${session.session_id}/welcome`,
    );
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 bg-ink px-6 py-12">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span aria-hidden className="mb-2 h-2 w-2 rotate-45 bg-signal" />
          <h1 className="font-display text-display font-medium tracking-tight text-chalk">
            {t.dashboard.title}
          </h1>
          <p className="text-aside text-graphite">
            {user?.display_name || user?.email}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SettingsMenu />
          <Button variant="chrome" size="xs" onClick={signOut}>
            {t.auth.signOut}
          </Button>
        </div>
      </header>

      {error && <p role="alert" className="text-aside text-rust">{error}</p>}

      {sessions === null ? (
        <p className="animate-pulse font-mono text-aside text-graphite">
          {t.dashboard.loading}
        </p>
      ) : sessions.length === 0 ? (
        /* The empty state INVITES rather than apologises: someone with no
           sessions has not lost anything, they simply have not started. */
        <div className="flex flex-col items-start gap-3 rounded-field border border-dashed border-rule p-6">
          <p className="text-aside text-graphite">
            {showArchived ? t.dashboard.noneArchived : t.dashboard.empty}
          </p>
          <Button variant="primary" size="md" onClick={() => router.push("/new")}>
            {t.dashboard.startFirst}
          </Button>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {sessions.map((session) => (
            <SessionCard
              key={session.session_id}
              session={session}
              onContinue={() => openSession(session)}
              onRename={async (title) => { await renameSession(session.session_id, title); await load(); }}
              onArchive={async (archived) => { await archiveSession(session.session_id, archived); await load(); }}
              onDelete={async () => { await deleteSession(session.session_id); await load(); }}
            />
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" size="md" onClick={() => router.push("/new")}>
          {t.dashboard.startNew}
        </Button>
        <Button variant="chrome" size="xs" onClick={() => setShowArchived((v) => !v)}>
          {showArchived ? t.dashboard.hideArchived : t.dashboard.showArchived}
        </Button>
      </div>
    </main>
  );
}
