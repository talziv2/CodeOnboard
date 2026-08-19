"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ProfileCard from "@/components/ProfileCard";
import SettingsMenu from "@/components/SettingsMenu";
import { getSession, getWelcome } from "@/lib/api";
import type { Briefing, SessionGraph } from "@/lib/api";
import SectionLabel from "@/components/ui/SectionLabel";
import Button from "@/components/ui/Button";
import { errorText, t } from "@/lib/strings";

/**
 * The welcome page: what this repository is, and who the system thinks is
 * reading it — the two things a learner has no way to check once lessons start.
 *
 * The two halves load independently and on purpose. The profile is derived from
 * the graph the pipeline already built, so it is on screen immediately; the
 * briefing costs one Haiku call on first open, so it arrives a moment later
 * without holding the page (or the "start learning" button) hostage. A briefing
 * that fails is a missing paragraph, never a blocked session.
 *
 * Not a gate: the route stays reachable from the session header, so this is a
 * page the learner can come back to rather than a splash screen they get once.
 */
export default function WelcomePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [graph, setGraph] = useState<SessionGraph | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingFailed, setBriefingFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setGraph(await getSession(id));
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.session.loadFailed);
      return;
    }
    try {
      setBriefing((await getWelcome(id)).briefing);
    } catch {
      // The briefing is the one thing on this page that can fail on its own.
      setBriefingFailed(true);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const begin = () => router.push(`/session/${id}`);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink px-6">
        <div className="flex max-w-sm flex-col gap-3 text-center">
          <p className="text-rust">{error}</p>
          <Button variant="secondary" size="md" className="mx-auto"
            onClick={() => {
              setError(null);
              load();
            }}
           
          >
            {t.session.retryLoad}
          </Button>
        </div>
      </main>
    );
  }

  if (!graph) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink">
        <p className="animate-pulse font-mono text-aside text-graphite">
          {t.session.loading}
        </p>
      </main>
    );
  }

  const repo = graph.repo_url.replace(/^https?:\/\/github\.com\//, "");
  const areas = graph.areas?.length ?? 0;

  return (
    <main className="flex min-h-screen flex-col bg-ink">
      <header className="flex shrink-0 items-center gap-4 border-b border-rule bg-slab px-5 py-2.5">
        <span className="font-display text-aside tracking-tight text-chalk">
          {t.appName}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-meta text-graphite">
          {repo}
        </span>
        <SettingsMenu />
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-col gap-9 px-7 py-10">
        <div className="flex flex-col gap-2.5">
          <span className="font-mono text-micro uppercase tracking-[0.16em] text-signal">
            {t.welcome.label}
          </span>
          <h1 className="font-display text-chapter font-medium tracking-tight text-chalk">
            {t.welcome.heading}
          </h1>
        </div>

        <div className="grid gap-9 md:grid-cols-[minmax(0,1fr)_18rem]">
          <section className="flex flex-col gap-7">
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
                  {t.welcome.briefingLabel}
                </span>
                {/* Which paragraph this is, said rather than implied — a generic
                    architecture summary presented as tailored would be the one
                    dishonest thing on the page. */}
                {briefing?.available && (
                  <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
                    {briefing.personalized
                      ? t.welcome.personalized
                      : t.welcome.generic}
                  </span>
                )}
              </div>

              {briefingFailed ? (
                <p className="text-aside text-graphite">
                  {t.welcome.failed}
                </p>
              ) : !briefing ? (
                <p className="animate-pulse font-mono text-meta text-graphite">
                  {t.welcome.loading}
                </p>
              ) : briefing.available ? (
                <p className="measure text-body text-paper">
                  {briefing.paragraph}
                </p>
              ) : (
                <p className="measure text-aside text-graphite">
                  {t.welcome.unavailable}
                </p>
              )}
            </div>

            {briefing && briefing.notes.length > 0 && (
              <div className="flex flex-col gap-3">
                <SectionLabel>{t.welcome.notesLabel}</SectionLabel>
                <ul className="flex flex-col gap-3.5">
                  {briefing.notes.map((note) => (
                    <li key={note.text} className="flex gap-2.5">
                      <span
                        aria-hidden
                        className="mt-[calc(9rem/16)] h-px w-3 shrink-0 bg-signal-dim"
                      />
                      <span className="measure flex flex-col gap-1">
                        <span className="text-aside text-paper">
                          {note.text}
                        </span>
                        {/* A path only when the backend resolved it against the
                            checkout, so what is shown here always exists. */}
                        {note.file && (
                          <span className="font-mono text-micro text-graphite">
                            {note.file}
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <Button variant="primary" size="lg"
                onClick={begin}
              >
                {t.welcome.begin}
              </Button>
            </div>
          </section>

          <ProfileCard
            goal={graph.goal}
            stops={graph.progress.stops_total}
            areas={areas}
          />
        </div>
      </div>
    </main>
  );
}
