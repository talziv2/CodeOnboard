"use client";

import { useState } from "react";
import type { GraphNode } from "@/lib/api";
import type { RouteStop } from "@/lib/graph-layout";
import { isComplete, type RouteSection } from "@/lib/route-sections";
import { stateStyle, stateLabel } from "@/lib/tags";
import { t } from "@/lib/strings";

interface Props {
  /** One entry per curriculum area; one ungrouped bucket on pre-B3 graphs. */
  sections: RouteSection[];
  /** Depth the learner did not ask for, collapsed behind a single line. */
  optional: RouteStop[];
  currentNodeId: string | null;
  /** The section whose overview is open, so its heading can show it. */
  openSectionId?: string | null;
  onJump: (node: GraphNode) => void;
  onOpenSection: (areaId: string) => void;
  onExpand: () => void;
}

/**
 * The rail answers four questions and no more: where am I, what is behind me,
 * what is next, and which stage of the journey am I in. Detail belongs to the
 * lesson, the section overview and the progress map — so concept tags, line
 * ranges and the state legend are all deliberately absent here. Density was the
 * problem: everything on screen carried the same weight, and the current stop
 * did not stand out from the fifteen around it.
 *
 * The timeline stays. It is what makes the route read as a journey rather than a
 * menu, and it is the only element that shows the order of things.
 */

/** Tone, not truth — how loudly a stop should speak. */
type Tone = "current" | "done" | "ahead";

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 10 10"
      className={`h-2.5 w-2.5 fill-none stroke-current stroke-[1.5] transition-transform ${
        open ? "rotate-90" : ""
      }`}
    >
      <path d="M3.5 1.5 L7 5 L3.5 8.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Check() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 10 10"
      className="h-2.5 w-2.5 fill-none stroke-current stroke-[1.5]"
    >
      <path d="M1.5 5.5 L4 8 L8.5 2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Pin shape encodes state so the rail stays readable without colour. */
function Pin({ node, isCurrent }: { node: GraphNode; isCurrent: boolean }) {
  const style = stateStyle(node.understanding_state);
  return (
    <span
      aria-hidden
      className="relative z-10 mt-0.5 block h-[calc(17rem/16)] w-[calc(17rem/16)] shrink-0 rounded-full border-[1.5px] bg-ink"
      style={{
        borderColor: isCurrent ? "var(--color-signal)" : style.stroke,
        background: isCurrent ? "var(--color-ink)" : style.fill,
        boxShadow: isCurrent ? "0 0 0 3px var(--color-signal-halo)" : undefined,
      }}
    >
      {isCurrent && (
        <span className="absolute inset-[calc(3.5rem/16)] rounded-full bg-signal" />
      )}
    </span>
  );
}

const TITLE_TONE: Record<Tone, string> = {
  current: "text-[calc(12.5rem/16)] font-semibold text-signal",
  done: "text-[calc(12rem/16)] font-medium text-graphite group-hover:text-signal",
  ahead: "text-[calc(12rem/16)] font-medium text-paper group-hover:text-signal",
};

/**
 * One stop in the rail.
 *
 * The file is shown for the current stop only. It is useful orientation while
 * you are standing on a stop, and fifteen monospaced filenames down the side of
 * the page are what made the rail feel like a table rather than a route.
 */
function Stop({
  stop, isCurrent, isLast, tone, onJump,
}: {
  stop: RouteStop;
  isCurrent: boolean;
  isLast: boolean;
  tone: Tone;
  onJump: (node: GraphNode) => void;
}) {
  const { node } = stop;
  const state = stateLabel(node.understanding_state);
  return (
    <button
      onClick={() => onJump(node)}
      aria-current={isCurrent ? "step" : undefined}
      title={`${node.title} — ${state}`}
      className={`group relative grid w-full grid-cols-[calc(18rem/16)_1fr] gap-3 py-[calc(5rem/16)] text-start ${
        stop.isPrerequisite ? "ms-[calc(22rem/16)] w-[calc(100%-22rem/16)]" : ""
      } ${tone === "done" ? "opacity-80 transition-opacity hover:opacity-100" : ""}`}
    >
      {/* connector down to the next stop */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute start-2 top-[calc(22rem/16)] bottom-[calc(-7rem/16)] w-px bg-rule"
        />
      )}

      <Pin node={node} isCurrent={isCurrent} />

      <span className="flex min-w-0 flex-col gap-[2px]">
        {stop.isPrerequisite && (
          <span className="flex items-center gap-[5px] font-mono text-[calc(9.5rem/16)] tracking-[0.06em] text-signal">
            <span aria-hidden className="h-px w-3 bg-signal" />
            {t.rail.addedAfterConfusion}
          </span>
        )}

        <span className={`leading-[1.35] transition ${TITLE_TONE[tone]}`}>
          {node.title}
        </span>

        {/* The legend is gone; the state travels with the pin instead, for
            anyone reading the rail with a screen reader or a tooltip. */}
        <span className="sr-only">{t.rail.stopState(state)}</span>

        {isCurrent && (
          <span className="truncate font-mono text-[calc(10rem/16)] text-graphite">
            {node.file}
          </span>
        )}

        {/* CURRENT difficulty only. `weak_spot` is sticky — true forever once
            the learner failed here — so rendering it kept a unit they have
            since mastered captioned as a weakness. `understanding` is the
            server-classified state and distinguishes the two. */}
        {node.understanding === "unresolved" && (
          <span
            className="font-mono text-[calc(9.5rem/16)] tracking-[0.05em] text-rust"
            title={t.rail.weak}
          >
            {t.rail.markedWeak}
          </span>
        )}
      </span>
    </button>
  );
}

/**
 * A section heading — two controls on one row, because they do two things.
 *
 * The chevron collapses the section; the title opens its chapter overview. Both
 * stay visible when collapsed, together with the purpose line and the count, so
 * a collapsed chapter still says what it is and how far through it you are.
 */
function SectionHead({
  section, open, isOverviewOpen, onToggle, onOpen,
}: {
  section: RouteSection;
  open: boolean;
  isOverviewOpen: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const area = section.area!;
  const complete = isComplete(section);
  const isCurrent = section.status === "current";

  return (
    <div className="mt-4 flex items-start gap-1.5 first:mt-0">
      <button
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={`route-section-${area.id}`}
        aria-label={
          open ? t.rail.collapseSection(area.title) : t.rail.expandSection(area.title)
        }
        className={`mt-[calc(3rem/16)] flex h-3.5 w-3.5 shrink-0 items-center justify-center transition ${
          complete && !open ? "text-jade" : isCurrent ? "text-signal" : "text-graphite"
        } hover:text-signal`}
      >
        {open ? <Chevron open /> : complete ? <Check /> : <Chevron open={false} />}
      </button>

      <button
        onClick={onOpen}
        aria-label={t.rail.openSection(area.title)}
        className="group flex min-w-0 flex-1 flex-col gap-[3px] text-start"
      >
        <span className="flex items-baseline gap-2">
          <span
            className={`min-w-0 flex-1 font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.15em] transition ${
              isCurrent || isOverviewOpen
                ? "text-signal"
                : "text-graphite group-hover:text-signal"
            }`}
          >
            {area.title}
          </span>
          <span className="shrink-0 font-mono text-[calc(9.5rem/16)] tabular-nums text-graphite">
            {t.rail.sectionProgress(section.settled, section.total)}
          </span>
        </span>
        {area.why && (
          <span
            className={`line-clamp-2 text-[calc(10.5rem/16)] leading-snug ${
              isCurrent ? "text-paper" : "text-graphite/75"
            }`}
          >
            {area.why}
          </span>
        )}
      </button>
    </div>
  );
}

export default function RouteRail({
  sections, optional, currentNodeId, openSectionId, onJump, onOpenSection, onExpand,
}: Props) {
  const [showOptional, setShowOptional] = useState(false);
  // Only the sections the learner has actually toggled. Everything else follows
  // the default — the section you are in is open, the rest are closed — so the
  // rail keeps adapting as the journey moves instead of freezing at whatever was
  // open when it first rendered.
  const [toggled, setToggled] = useState<Record<string, boolean>>({});

  // The current node must never be hidden behind a collapsed section.
  const currentIsOptional = optional.some((s) => s.node.id === currentNodeId);
  const optionalOpen = showOptional || currentIsOptional;

  const toneFor = (section: RouteSection, stop: RouteStop): Tone => {
    if (stop.node.id === currentNodeId) return "current";
    if (stop.node.understanding_state !== "not_started" || stop.node.visited) {
      return "done";
    }
    return section.status === "past" ? "done" : "ahead";
  };

  return (
    <aside className="flex h-full min-h-0 flex-col gap-3 border-e border-rule bg-trench py-4">
      <div className="flex items-baseline justify-between px-4">
        <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
          {t.rail.title}
        </span>
        <button
          onClick={onExpand}
          className="font-mono text-[calc(10.5rem/16)] text-signal transition hover:text-chalk"
        >
          {t.rail.openMap}
        </button>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-4 pb-2">
        {sections.map((section, si) => {
          const area = section.area;
          const key = area?.id ?? `ungrouped-${si}`;
          // An ungrouped bucket has no chapter to introduce and no heading to
          // click, so it is always shown — as it was before grouping existed.
          const open = area ? toggled[area.id] ?? section.containsCurrent : true;
          // Collapsed, but you are standing in it: show that one stop rather
          // than hiding where the learner is.
          const visible = open
            ? section.stops
            : section.stops.filter((s) => s.node.id === currentNodeId);

          return (
            <div key={key}>
              {area && (
                <SectionHead
                  section={section}
                  open={open}
                  isOverviewOpen={openSectionId === area.id}
                  onToggle={() =>
                    setToggled((prev) => ({ ...prev, [area.id]: !open }))
                  }
                  onOpen={() => onOpenSection(area.id)}
                />
              )}
              <div
                id={area ? `route-section-${area.id}` : undefined}
                className={visible.length > 0 ? "mt-1" : ""}
              >
                {visible.map((stop, i) => (
                  <Stop
                    key={stop.node.id}
                    stop={stop}
                    isCurrent={stop.node.id === currentNodeId}
                    // The connector joins stops WITHIN a section; a heading is a
                    // break in the line, not something to draw through.
                    isLast={i === visible.length - 1}
                    tone={toneFor(section, stop)}
                    onJump={onJump}
                  />
                ))}
              </div>
            </div>
          );
        })}

        {optional.length > 0 && (
          <div className="mt-4 border-t border-rule pt-2">
            <button
              onClick={() => setShowOptional((v) => !v)}
              disabled={currentIsOptional}
              aria-expanded={optionalOpen}
              className="flex w-full items-center gap-2 py-1 font-mono text-[calc(10rem/16)] uppercase tracking-[0.13em] text-graphite transition hover:text-signal disabled:opacity-60"
            >
              <Chevron open={optionalOpen} />
              {optionalOpen && !currentIsOptional
                ? t.rail.hideOptional
                : t.rail.optionalStops(optional.length)}
            </button>
            {optionalOpen &&
              optional.map((stop, i) => (
                <Stop
                  key={stop.node.id}
                  stop={stop}
                  isCurrent={stop.node.id === currentNodeId}
                  isLast={i === optional.length - 1}
                  tone={stop.node.id === currentNodeId ? "current" : "ahead"}
                  onJump={onJump}
                />
              ))}
          </div>
        )}
      </nav>
    </aside>
  );
}
