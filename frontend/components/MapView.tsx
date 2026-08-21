"use client";

import { useMemo, useState } from "react";
import type { GraphNode, GraphEdge } from "@/lib/api";
import { understandingLabel, understandingStyle } from "@/lib/tags";
import { buildRoute, spineLength } from "@/lib/graph-layout";
import SectionLabel from "@/components/ui/SectionLabel";
import ConceptTag from "@/components/ui/ConceptTag";
import StatePin from "@/components/ui/StatePin";
import StopCard from "@/components/StopCard";
import { t } from "@/lib/strings";

/**
 * The whole route, at session altitude — where you are and what is around it.
 *
 * Route mode's first tab, and now ONLY the map. It used to be the map plus the two
 * progress measures, the three outcome bands, the pattern layer, two breakdown
 * panels and a 288px session-log column: a navigation view you had to scroll a
 * dashboard to read, in four fifths of the available width. All of that moved to
 * `AnalysisView`, the sibling tab, which is what the mode is for.
 *
 * What is left is the thing the learner opens this for. THE ROUTE IS THE
 * VISUALIZATION: understanding is drawn ON it, as the state pin of each stop,
 * rather than in a profile panel beside it — a pip strip and a route list
 * describing the same units in two places is what made this screen a dashboard
 * (M3a.3 AC6).
 *
 * Its props stay explicit rather than taking the graph, unlike `AnalysisView`: this
 * view reads exactly the route and nothing else, and the narrow prop list is what
 * says so.
 *
 * A STOP IS NOT A LINK. Clicking one used to jump into its lesson, which made the
 * one surface built for choosing where to go the only one that would not describe a
 * place before taking you to it. It now opens `StopCard`, and the jump is a button
 * inside that card — the same navigation, one deliberate step later. Selection is
 * held here rather than by the page because it is a fact about reading this view,
 * not about the session: leaving the map forgets it, which is correct.
 */

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentNodeId: string | null;
  repoUrl?: string;
  /**
   * Where the card's "Go to lesson" leads. OPTIONAL, and its absence is the read-only
   * recap: the card still describes the stop, and simply offers no way to walk to it.
   * That used to be expressed as a no-op handler on a row that still looked and
   * behaved like a button.
   */
  onGoToLesson?: (node: GraphNode) => void;
}

export default function MapView({
  nodes, edges, currentNodeId, repoUrl, onGoToLesson,
}: Props) {
  const stops = useMemo(() => buildRoute(nodes, edges), [nodes, edges]);
  const total = useMemo(() => spineLength(stops), [stops]);

  const [openStopId, setOpenStopId] = useState<string | null>(null);
  // Read out of `stops` rather than stored, so a graph that changed under the card
  // — a mutation, a re-plan — updates it instead of pinning a stale copy, and a
  // stop that has left the graph closes it.
  const openStop = stops.find((s) => s.node.id === openStopId) ?? null;

  const repo = repoUrl?.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");

  return (
    <div className="h-full overflow-y-auto px-6 py-7">
      <div className="mx-auto flex max-w-4xl flex-col gap-7">

        {/* headline. The numbers that used to sit here live in Analysis, and the
            two that matter most are in the session header at all times — so this
            says where you are rather than repeating how it is going. */}
        <header className="flex flex-col gap-1">
          <span className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
            {t.map.routeLabel}
          </span>
          <h2 className="font-display text-chapter font-medium tracking-tight text-chalk">
            {repo ?? t.map.thisCodebase}
          </h2>
        </header>

        {/* ── THE JOURNEY ──────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-4">
          <SectionLabel as="h3">{t.map.journeyTitle}</SectionLabel>

          <ol className="flex flex-col">
            {stops.map((stop, i) => {
              const { node } = stop;
              const isCurrent = node.id === currentNodeId;
              const isLast = i === stops.length - 1;
              // A prerequisite connects to the node it unlocks, so the segment
              // below it is the adaptive one.
              const nextIsUnlock = stop.isPrerequisite;

              return (
                <li
                  key={node.id}
                  className={`relative grid grid-cols-[calc(34rem/16)_1fr] gap-4 pb-5 ${
                    stop.isPrerequisite ? "ms-10" : ""
                  }`}
                >
                  {!isLast && (
                    <span
                      aria-hidden
                      className="absolute start-[calc(16rem/16)] top-[calc(26rem/16)] bottom-[calc(-6rem/16)] w-px"
                      style={
                        nextIsUnlock
                          ? {
                              backgroundImage:
                                "repeating-linear-gradient(to bottom, var(--color-signal) 0 5px, transparent 5px 10px)",
                            }
                          : { background: "var(--color-rule)" }
                      }
                    />
                  )}

                  <span className="flex justify-center pt-2.5">
                    <StatePin
                      understanding={node.understanding}
                      isCurrent={isCurrent}
                      role="map"
                      className="z-10"
                    />
                  </span>

                  <button
                    onClick={() => setOpenStopId(node.id)}
                    aria-haspopup="dialog"
                    aria-expanded={openStopId === node.id}
                    className="flex flex-col gap-2 rounded-card border-2 px-4 py-3.5 text-start transition hover:border-signal-dim"
                    style={{
                      background: isCurrent ? "var(--color-signal-wash)" : "var(--color-slab)",
                      borderColor: isCurrent ? "var(--color-signal)" : "var(--color-rule)",
                    }}
                  >
                    {stop.isPrerequisite && (
                      <span className="flex flex-wrap items-center gap-2 font-mono text-micro tracking-[0.06em] text-signal">
                        <span aria-hidden className="h-px w-4 bg-signal" />
                        {t.rail.addedAfterConfusion}
                        {stop.unlocksTitle && (
                          <span className="text-graphite">{t.map.unlocks(stop.unlocksTitle)}</span>
                        )}
                      </span>
                    )}

                    <span
                      className="font-display text-lede font-medium tracking-tight"
                      style={{ color: isCurrent ? "var(--color-signal)" : "var(--color-chalk)" }}
                    >
                      {node.title}
                    </span>

                    <span className="font-mono text-micro text-graphite">
                      {node.file}
                      {" · "}
                      {t.lesson.lines(node.line_start, node.line_end)}
                    </span>

                    <span className="flex flex-wrap items-center gap-1.5">
                      {node.concept_tags.slice(0, 2).map((tag) => (
                        <ConceptTag key={tag} tag={tag} />
                      ))}
                      {/* CURRENT state, not the sticky flag. `weak_spot` stays
                          true forever once set, so rendering it captioned a unit
                          the learner has since mastered as a weakness. */}
                      {node.understanding && node.understanding !== "insufficient" && (
                        <span
                          className="font-mono text-micro tracking-[0.05em]"
                          style={{ color: understandingStyle(node.understanding).stroke }}
                        >
                          {understandingLabel(node.understanding)}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>

      </div>

      {openStop && (
        <StopCard
          stop={openStop}
          spineLength={total}
          isCurrent={openStop.node.id === currentNodeId}
          // Closed on the way out: the card describes a stop, and once the jump is
          // taken it would be sitting over the lesson it sent the learner to.
          onGoToLesson={
            onGoToLesson
              ? (node) => { setOpenStopId(null); onGoToLesson(node); }
              : undefined
          }
          onClose={() => setOpenStopId(null)}
        />
      )}
    </div>
  );
}
