"use client";

import type { GraphNode } from "@/lib/api";
import { isStation } from "@/lib/graph-layout";
import { isSettled, type RouteSection } from "@/lib/route-sections";
import { understandingLabel } from "@/lib/tags";
import SectionLabel from "@/components/ui/SectionLabel";
import ConceptTag from "@/components/ui/ConceptTag";
import StatePin from "@/components/ui/StatePin";
import Button from "@/components/ui/Button";
import Prose, { InlineProse } from "@/components/ui/Prose";
import { t } from "@/lib/strings";

interface Props {
  section: RouteSection;
  /** All sections, for the one line that connects this chapter to the last. */
  sections: RouteSection[];
  currentNodeId: string | null;
  onJump: (node: GraphNode) => void;
  onClose: () => void;
}

/**
 * The chapter introduction for one section of the route.
 *
 * Every line here is DERIVED from the curriculum the Planner already wrote —
 * the area's own `why`, the objectives of the units inside it, their states, and
 * the section's position in the ordered list. Nothing new is generated and no
 * new state is persisted: this is a second reading of the graph, at the altitude
 * the sidebar cannot afford. No estimated duration, because nothing in the model
 * measures time and inventing a number would be the one dishonest thing here.
 *
 * It is a lightweight layer over the lesson column rather than a route, so
 * opening and closing it costs one click and never moves the session pointer.
 * "Continue" simply closes it; the learner is still standing where they were.
 */
export default function SectionOverview({
  section, sections, currentNodeId, onJump, onClose,
}: Props) {
  const area = section.area;
  if (!area) return null;

  const stations = section.stops.filter(isStation);
  const previous = sections
    .filter((s) => s.area && s.index < section.index)
    .at(-1);

  // Where to go from here. If the learner is already inside this chapter,
  // "continue" means close the overview — the lesson underneath is theirs. If
  // they opened a chapter they are not in, the first stop they have not dealt
  // with is the honest place to start.
  const entry =
    section.stops.find((s) => !isSettled(s.node)) ?? section.stops[0];
  const current = section.stops.find((s) => s.node.id === currentNodeId);

  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-col gap-2.5">
        <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-micro uppercase tracking-[0.16em] text-graphite">
          <span className="text-signal">{t.section.label}</span>
          <span>{t.section.chapterOf(section.index, sections.filter((s) => s.area).length)}</span>
          <span className="tabular-nums">
            {t.section.progress(section.settled, section.total)}
          </span>
        </span>

        <h2 className="font-display text-head font-medium tracking-tight text-chalk text-balance">
          {area.title}
        </h2>

        {area.why && (
          <Prose text={area.why} size="body" tone="paper" />
        )}
      </div>

      {/* Why now — the chapter's place in the route, not a new claim about it. */}
      <div className="flex flex-col gap-1.5 border-s-2 border-rule ps-3.5">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.section.whyNow}
        </span>
        <p className="measure text-meta text-graphite">
          {!previous
            ? t.section.opensRoute
            : previous.settled === previous.total
            ? t.section.followsOn(previous.area!.title)
            : t.section.followsUnfinished(
                previous.area!.title,
                previous.settled,
                previous.total
              )}
        </p>
      </div>

      {/* What the chapter promises. The objective is the contract between the
          Planner, Teaching and the Grader, so it is exactly the right thing to
          show as "what you should be able to say". */}
      {stations.some((s) => s.node.objective) && (
        <div className="flex flex-col gap-3">
          <SectionLabel>{t.section.byTheEnd}</SectionLabel>
          <ul className="flex flex-col gap-2.5">
            {stations
              .filter((s) => s.node.objective)
              .map((s) => (
                <li key={s.node.id} className="flex gap-2.5">
                  <span
                    aria-hidden
                    className="mt-[calc(7rem/16)] h-px w-3 shrink-0 bg-signal-dim"
                  />
                  <p className="measure text-aside text-paper">
                    <InlineProse text={s.node.objective} tone="paper" />
                  </p>
                </li>
              ))}
          </ul>
        </div>
      )}

      {/* The contents of the chapter — and where the concept tags live now that
          the rail no longer carries them. */}
      <div className="flex flex-col gap-3">
        <SectionLabel>{t.section.lessons}</SectionLabel>

        <ul className="flex flex-col gap-1">
          {section.stops.map((stop) => {
            const { node } = stop;
            const isCurrent = node.id === currentNodeId;
            return (
              <li key={node.id}>
                <button
                  onClick={() => onJump(node)}
                  aria-current={isCurrent ? "step" : undefined}
                  className="group grid w-full grid-cols-[calc(15rem/16)_1fr] gap-3 rounded-field px-2 py-2 text-start transition hover:bg-slab"
                >
                  <StatePin
                    understanding={node.understanding}
                    isCurrent={isCurrent}
                    role="list"
                    className="mt-[calc(4rem/16)]"
                  />
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                      <span
                        className={`text-aside transition ${
                          isCurrent
                            ? "font-semibold text-signal"
                            : "font-medium text-chalk group-hover:text-signal"
                        }`}
                      >
                        {node.title}
                      </span>
                      <span className="font-mono text-micro uppercase tracking-[0.13em] text-graphite">
                        {understandingLabel(node.understanding ?? "insufficient")}
                      </span>
                      {stop.isPrerequisite && (
                        <span className="font-mono text-micro tracking-[0.05em] text-signal">
                          {t.rail.addedAfterConfusion}
                        </span>
                      )}
                      {/* The unit's class, in the one vocabulary. Never
                          "marked weak": that word came from a sticky flag and
                          survived recovery (M3a.3 AC3). */}
                    </span>

                    <span className="truncate font-mono text-micro text-graphite">
                      {node.file}
                    </span>

                    {node.concept_tags.length > 0 && (
                      <span className="flex flex-wrap gap-1">
                        {node.concept_tags.map((tag) => (
                          <ConceptTag key={tag} tag={tag} />
                        ))}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-rule pt-4">
        {current ? (
          <Button variant="primary" size="md"
            onClick={onClose}
          >
            {t.section.continue(current.node.title)}
          </Button>
        ) : (
          entry && (
            <Button variant="primary" size="md"
              onClick={() => onJump(entry.node)}
            >
              {t.section.startHere(entry.node.title)}
            </Button>
          )
        )}
        <Button variant="secondary" size="md"
          onClick={onClose}
        >
          {t.section.close}
        </Button>
        <span className="ms-auto font-mono text-micro text-graphite">
          {t.section.reopenHint}
        </span>
      </div>
    </div>
  );
}
