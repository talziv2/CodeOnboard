"use client";

import { useEffect, useId, useRef } from "react";
import { openOnly, type GraphNode } from "@/lib/api";
import { isStation, type RouteStop } from "@/lib/graph-layout";
import { understandingLabel, understandingStyle } from "@/lib/tags";
import ConceptTag from "@/components/ui/ConceptTag";
import StatePin from "@/components/ui/StatePin";
import Button from "@/components/ui/Button";
import { InlineProse } from "@/components/ui/Prose";
import { t } from "@/lib/strings";

/**
 * One stop on the map, described before you commit to walking to it.
 *
 * The map used to navigate on click — a stop was a link, so the surface built for
 * choosing where to go was the one place that told you nothing about a place until
 * you were already standing in it. That is what this fixes: a click OPENS, and only
 * the button inside JUMPS.
 *
 * It is a reading of the graph and nothing else. The objective is the Planner's own
 * contract text, the anchors are the verified ones, the state is the
 * server-computed `understanding` every other surface renders — so the card cannot
 * disagree with the rail, the brief or the evidence drawer, because it holds no
 * opinion of its own. Nothing is fetched and nothing is generated: opening a card
 * costs one render and no round trip, which is what lets a learner flick through
 * four stops deciding between them.
 *
 * MODAL, unlike the source pane, and for the opposite reason. The pane exists to be
 * read ALONGSIDE a lesson, so a backdrop would defeat it; this exists to be read
 * INSTEAD of the route for the two seconds a decision takes, and it leaves the
 * moment the decision is made.
 */
export default function StopCard({
  stop, spineLength, isCurrent, onGoToLesson, onClose,
}: {
  stop: RouteStop;
  /** How many stops the counter counts, so "stop 3 of 9" matches the rail. */
  spineLength: number;
  isCurrent: boolean;
  /** Absent on a read-only recap, where the card is a description and no more. */
  onGoToLesson?: (node: GraphNode) => void;
  onClose: () => void;
}) {
  const node = stop.node;
  const titleId = useId();
  const card = useRef<HTMLDivElement>(null);

  // CAPTURE, and it stops the event. Route mode binds its own Escape on `window`
  // to leave the map entirely, and it was bound first — so a bubble-phase listener
  // here would close the card AND drop the learner back into the lesson on one
  // keypress. Escape closes the innermost thing open; capturing at `window` is what
  // lets this layer be that thing without the page having to know it exists.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  // Focus follows the card, so Escape and Tab land here rather than in the route
  // list the backdrop has just covered.
  useEffect(() => { card.current?.focus(); }, [node.id]);

  const style = understandingStyle(node.understanding ?? "insufficient");
  const openGaps = openOnly(node.gaps).length;
  const attempts = node.attempts.length;

  // The display anchor is already on the "where" line; only a real set of further
  // locations is worth listing under it.
  const extraAnchors = (node.anchors ?? []).slice(1);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-5">
      {/* The scrim is a convenience, not a control: Escape and the Close button are
          the two real ways out, so it stays out of the accessibility tree rather
          than becoming a second unlabelled button announcing the same thing. */}
      <div aria-hidden onClick={onClose} className="absolute inset-0 bg-ink/70" />

      <div
        ref={card}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="rise relative flex max-h-full w-full max-w-xl flex-col gap-5 overflow-y-auto rounded-card border border-rule bg-slab px-6 py-5 shadow-overlay"
      >
        {/* ── who it is, and where on the route ───────────────────────────── */}
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {stop.isPrerequisite
                ? t.lesson.warmUpHeading
                : isStation(stop)
                  ? t.lesson.stopOf(stop.position, spineLength)
                  : t.map.stop.offRoute}
            </span>

            {isCurrent && (
              <span className="font-mono text-micro tracking-[0.06em] text-signal">
                {t.rail.youAreHere}
              </span>
            )}

            <Button variant="ghost" className="ms-auto" onClick={onClose}>
              {t.map.stop.close}
            </Button>
          </div>

          <h2
            id={titleId}
            className="font-display text-head font-medium tracking-tight text-chalk text-balance"
          >
            {node.title}
          </h2>

          {/* The state, in the words and the pin every other surface uses. */}
          <span className="flex flex-wrap items-center gap-2">
            <StatePin
              understanding={node.understanding}
              disposition={node.disposition}
              attempted={node.attempted}
              isCurrent={isCurrent}
              role="list"
            />
            <span
              className="font-mono text-micro tracking-[0.05em]"
              style={{ color: style.stroke }}
            >
              {understandingLabel(node.understanding ?? "insufficient")}
            </span>
            {node.disposition && (
              <span className="font-mono text-micro text-graphite">
                {t.map.disposition[node.disposition]}
              </span>
            )}
          </span>

          {stop.isPrerequisite && stop.unlocksTitle && (
            <span className="font-mono text-micro text-graphite">
              {t.map.unlocks(stop.unlocksTitle)}
            </span>
          )}

          {node.priority === "optional" && (
            <span className="font-mono text-micro text-graphite">
              {t.map.stop.optional}
            </span>
          )}
        </div>

        {/* ── the objective: the whole reason the stop exists ─────────────── */}
        <section className="flex flex-col gap-1.5 border-s-2 border-rule ps-3.5">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.map.stop.objective}
          </span>
          <p className="measure text-body text-paper">
            {node.objective ? (
              <InlineProse text={node.objective} tone="paper" />
            ) : (
              t.map.stop.noObjective
            )}
          </p>
        </section>

        {/* ── where in the code ───────────────────────────────────────────── */}
        <section className="flex flex-col gap-1.5">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.map.stop.where}
          </span>
          <span className="font-mono text-micro text-paper">
            {node.file}
            {" · "}
            {t.lesson.lines(node.line_start, node.line_end)}
          </span>
          {extraAnchors.map((a, i) => (
            <span
              key={`${a.file}-${a.line_start}-${i}`}
              className="font-mono text-micro text-graphite"
            >
              {a.file}
              {" · "}
              {t.lesson.lines(a.line_start, a.line_end)}
            </span>
          ))}
        </section>

        {/* ── the tags, all of them: a map row shows only the first two ───── */}
        {node.concept_tags.length > 0 && (
          <section className="flex flex-col gap-1.5">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.map.stop.concepts}
            </span>
            <span className="flex flex-wrap items-center gap-1.5">
              {node.concept_tags.map((tag) => (
                <ConceptTag key={tag} tag={tag} />
              ))}
            </span>
          </section>
        )}

        {/* ── what happened here. STATED, never asked about: the map is not
               where an answer is given, and a card offering to grade one would
               be a lesson wearing a summary. */}
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-micro text-graphite">
          {attempts === 0 && openGaps === 0 ? (
            t.map.stop.untouched
          ) : (
            <>
              {attempts > 0 && <span>{t.lesson.briefAttempts(attempts)}</span>}
              {openGaps > 0 && (
                <span className="flex items-center gap-1.5 text-rust">
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-rust" />
                  {t.lesson.briefGaps(openGaps)}
                </span>
              )}
            </>
          )}
        </span>

        {onGoToLesson && (
          <Button
            variant="primary"
            size="md"
            className="w-fit"
            onClick={() => onGoToLesson(node)}
          >
            {isCurrent ? t.map.stop.returnToLesson : t.map.stop.goToLesson}
          </Button>
        )}
      </div>
    </div>
  );
}
