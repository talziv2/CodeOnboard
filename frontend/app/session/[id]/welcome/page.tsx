"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import DashboardLink from "@/components/DashboardLink";
import ProfileCard from "@/components/ProfileCard";
import RouteOverview from "@/components/RouteOverview";
import SettingsMenu from "@/components/SettingsMenu";
import ScopeCard from "@/components/contribution/ScopeCard";
import { getContribution, getSession, getWelcome } from "@/lib/api";
import type { Briefing, Contribution, SessionGraph, SkippedArea } from "@/lib/api";
import SectionLabel from "@/components/ui/SectionLabel";
import Button from "@/components/ui/Button";
import Prose, { InlineProse } from "@/components/ui/Prose";
import { buildRoute } from "@/lib/graph-layout";
import { splitJourney } from "@/lib/route-sections";
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
  const [skipped, setSkipped] = useState<SkippedArea[]>([]);
  const [contribution, setContribution] = useState<Contribution | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setGraph(await getSession(id));
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.session.loadFailed);
      return;
    }
    try {
      const welcome = await getWelcome(id);
      setBriefing(welcome.briefing);
      setSkipped(welcome.skipped_areas ?? []);
    } catch {
      // The briefing is the one thing on this page that can fail on its own.
      setBriefingFailed(true);
    }
    try {
      setContribution(await getContribution(id));
    } catch {
      // A session that is not a contribution, or a boundary that could not be
      // loaded. Either way the page is the ordinary welcome page — the card is
      // an addition to it, never a precondition for it.
      setContribution(null);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  /**
   * Leave for the workspace (P4).
   *
   * NOT a shared-element transition, and deliberately not an imitation of one. The
   * milestone asks for the chapter list to animate into the rail's position, and
   * says a shared-element transition "will look cheap if it is even slightly
   * wrong" — which is exactly right, and doing it properly across a route change
   * needs the View Transitions API to hold both DOMs at once. Deferred with that
   * reason rather than approximated with a translate that lands somewhere near the
   * rail and hopes.
   *
   * WHAT IT DOES INSTEAD is carry the eye in the right direction and make the
   * arrival continuous, which is what the animation was for:
   *
   *   - the page leaves toward the leading edge, where the rail is about to be;
   *   - the rail arrives with the chapter containing the first stop ALREADY
   *     expanded, because `RouteRail` opens `section.containsCurrent` by default.
   *     So the chapter the learner just read about is the chapter they land in —
   *     the continuity is structural, and it holds whether or not anything moved.
   *
   * Reduced motion navigates immediately: there is nothing to see, and a 200ms
   * pause with no motion in it is just a slower button.
   */
  const [leaving, setLeaving] = useState(false);
  const begin = () => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still) {
      router.push(`/session/${id}`);
      return;
    }
    setLeaving(true);
    // One `--motion-state`. Long enough to read as leaving, short enough that it
    // never becomes the reason the workspace felt slow to open.
    window.setTimeout(() => router.push(`/session/${id}`), 200);
  };

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
  // The SAME derivation the session page and the rail use. Two renderings of one
  // route; computing the grouping twice is how they would come to disagree.
  const journey = splitJourney(
    buildRoute(graph.nodes, graph.edges),
    graph.areas ?? [],
    graph.current_node_id
  );
  // What `Start` actually opens. `resume_point` is the server's answer to "where
  // does this learner belong now", and on a first visit it is the first stop — so
  // naming it is naming the room the door opens onto, not guessing at it.
  const firstStop =
    journey.sections.flatMap((section) => section.stops).find(
      (stop) => stop.node.id === graph.current_node_id
    ) ?? journey.sections[0]?.stops[0];
  // The required units, in WALK ORDER — the same stops the rail is about to
  // show, taken off the same route. Filtered on the server's own `priority`, so
  // "required" still has one definition; the count beside them is
  // `contribution.ready.required`, which is computed from the same set.
  const requiredNodes = journey.sections
    .flatMap((section) => section.stops)
    .map((stop) => stop.node)
    .filter((node) => node.priority === "required");

  return (
    <main className="flex min-h-screen flex-col bg-ink">
      <header className="flex shrink-0 items-center gap-4 border-b border-rule bg-slab px-5 py-2.5">
        {/* The same way out, in the same place as the workspace header's — this
            page is where a never-opened session lands, so it is the FIRST screen
            that needs a door back to the list the learner arrived from. */}
        <span className="flex shrink-0 items-center gap-3">
          <span className="font-display text-aside tracking-tight text-chalk">
            {t.appName}
          </span>
          <DashboardLink />
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-meta text-graphite">
          {repo}
        </span>
        <SettingsMenu />
      </header>

      {/* Leaves toward the leading edge, which is where the rail is about to be.
          `ps` rather than `translate-x` so it reads correctly in both writing
          directions, and opacity carries the rest — a page that only slid would
          look like it had been pushed rather than handed over. */}
      <div
        className="mx-auto flex w-full max-w-5xl flex-col gap-9 px-7 py-10 transition-[opacity,transform] ease-[var(--ease-emphasis)]"
        style={{
          transitionDuration: "var(--motion-state)",
          opacity: leaving ? 0 : 1,
          transform: leaving ? "translateX(-2rem)" : "none",
        }}
      >
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
                <Prose text={briefing.paragraph} size="body" tone="paper" />
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
                          <InlineProse text={note.text} tone="paper" />
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

            {/* THE CONTRIBUTION SCOPE CARD, above the route and below the
                briefing: the task, how many concepts it requires, which ones,
                and what was left out. Rendered only when the session actually
                is a contribution with a plan behind it — `ScopeCard` returns
                null otherwise, so there is nothing to guard here. */}
            {contribution?.available && (
              <ScopeCard
                contribution={contribution}
                requiredNodes={requiredNodes}
                skipped={skipped}
              />
            )}

            {/* The route, before the button that commits to it. A learner asked to
                start should have seen what they are starting. */}
            {journey.sections.length > 0 && (
              <RouteOverview sections={journey.sections} optional={journey.optional.length} />
            )}

            <div>
              <Button variant="primary" size="lg" onClick={begin}>
                {contribution?.available
                  ? t.contribution.begin
                  : firstStop ? t.welcome.beginNamed(firstStop.node.title) : t.welcome.begin}
              </Button>
            </div>
          </section>

          <ProfileCard
            goal={graph.goal}
            stops={graph.progress.stops_total}
            areas={areas}
            // A NEW interview for the same repository, not `Start over`'s rerun of
            // the same answers. The repo rides in the URL so the learner lands on
            // the first question rather than on the address bar.
            onChangeAnswers={() =>
              router.push(`/?repo=${encodeURIComponent(graph.repo_url)}`)
            }
          />
        </div>
      </div>
    </main>
  );
}
