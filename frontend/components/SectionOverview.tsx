"use client";

import type { GraphNode } from "@/lib/api";
import { isStation } from "@/lib/graph-layout";
import { isSettled, type RouteSection } from "@/lib/route-sections";
import { stateStyle, stateLabel, tagStyle, tagLabel } from "@/lib/tags";
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
        <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
          <span className="text-signal">{t.section.label}</span>
          <span>{t.section.chapterOf(section.index, sections.filter((s) => s.area).length)}</span>
          <span className="tabular-nums">
            {t.section.progress(section.settled, section.total)}
          </span>
        </span>

        <h2 className="font-display text-[calc(23rem/16)] font-medium leading-[1.2] tracking-tight text-chalk text-balance">
          {area.title}
        </h2>

        {area.why && (
          <p className="measure text-[calc(13.5rem/16)] leading-[1.7] text-paper">
            {area.why}
          </p>
        )}
      </div>

      {/* Why now — the chapter's place in the route, not a new claim about it. */}
      <div className="flex flex-col gap-1.5 border-s-2 border-rule ps-3.5">
        <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-graphite">
          {t.section.whyNow}
        </span>
        <p className="measure text-[calc(12.5rem/16)] leading-relaxed text-graphite">
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
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
              {t.section.byTheEnd}
            </span>
            <span aria-hidden className="h-px flex-1 bg-rule" />
          </div>
          <ul className="flex flex-col gap-2.5">
            {stations
              .filter((s) => s.node.objective)
              .map((s) => (
                <li key={s.node.id} className="flex gap-2.5">
                  <span
                    aria-hidden
                    className="mt-[calc(7rem/16)] h-px w-3 shrink-0 bg-signal-dim"
                  />
                  <p className="measure text-[calc(13rem/16)] leading-[1.65] text-paper">
                    {s.node.objective}
                  </p>
                </li>
              ))}
          </ul>
        </div>
      )}

      {/* The contents of the chapter — and where the concept tags live now that
          the rail no longer carries them. */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
            {t.section.lessons}
          </span>
          <span aria-hidden className="h-px flex-1 bg-rule" />
        </div>

        <ul className="flex flex-col gap-1">
          {section.stops.map((stop) => {
            const { node } = stop;
            const isCurrent = node.id === currentNodeId;
            const style = stateStyle(node.understanding_state);
            return (
              <li key={node.id}>
                <button
                  onClick={() => onJump(node)}
                  aria-current={isCurrent ? "step" : undefined}
                  className="group grid w-full grid-cols-[calc(15rem/16)_1fr] gap-3 rounded px-2 py-2 text-start transition hover:bg-slab"
                >
                  <span
                    aria-hidden
                    className="mt-[calc(4rem/16)] h-[calc(13rem/16)] w-[calc(13rem/16)] shrink-0 rounded-full border-[1.5px] bg-ink"
                    style={{
                      borderColor: isCurrent ? "var(--color-signal)" : style.stroke,
                      background: isCurrent ? "var(--color-ink)" : style.fill,
                      boxShadow: isCurrent
                        ? "0 0 0 3px var(--color-signal-halo)"
                        : undefined,
                    }}
                  />
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                      <span
                        className={`text-[calc(13rem/16)] leading-snug transition ${
                          isCurrent
                            ? "font-semibold text-signal"
                            : "font-medium text-chalk group-hover:text-signal"
                        }`}
                      >
                        {node.title}
                      </span>
                      <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.13em] text-graphite">
                        {stateLabel(node.understanding_state)}
                      </span>
                      {stop.isPrerequisite && (
                        <span className="font-mono text-[calc(9.5rem/16)] tracking-[0.05em] text-signal">
                          {t.rail.addedAfterConfusion}
                        </span>
                      )}
                      {node.weak_spot && (
                        <span className="font-mono text-[calc(9.5rem/16)] tracking-[0.05em] text-rust">
                          {t.rail.markedWeak}
                        </span>
                      )}
                    </span>

                    <span className="truncate font-mono text-[calc(10.5rem/16)] text-graphite">
                      {node.file}
                    </span>

                    {node.concept_tags.length > 0 && (
                      <span className="flex flex-wrap gap-1">
                        {node.concept_tags.map((tag) => {
                          const s = tagStyle(tag);
                          return (
                            <span
                              key={tag}
                              className="rounded-[2px] border px-[5px] py-px font-mono text-[calc(9.5rem/16)] tracking-[0.05em]"
                              style={{
                                color: s.text,
                                borderColor: s.border,
                                background: s.background,
                              }}
                            >
                              {tagLabel(tag)}
                            </span>
                          );
                        })}
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
          <button
            onClick={onClose}
            className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25"
          >
            {t.section.continue(current.node.title)}
          </button>
        ) : (
          entry && (
            <button
              onClick={() => onJump(entry.node)}
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25"
            >
              {t.section.startHere(entry.node.title)}
            </button>
          )
        )}
        <button
          onClick={onClose}
          className="rounded border border-rule px-4 py-2 text-[calc(13rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal"
        >
          {t.section.close}
        </button>
        <span className="ms-auto font-mono text-[calc(10rem/16)] text-graphite">
          {t.section.reopenHint}
        </span>
      </div>
    </div>
  );
}
