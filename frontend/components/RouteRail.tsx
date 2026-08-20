"use client";

import { useState } from "react";
import type { GraphNode } from "@/lib/api";
import type { RouteStop } from "@/lib/graph-layout";
import { isComplete, isSettled, type RouteSection } from "@/lib/route-sections";
import { understandingLabel } from "@/lib/tags";
import StatePin from "@/components/ui/StatePin";
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
  /**
   * Collapse to a strip of pins. Used in the medium band, where the full rail
   * would be taking 268px from a lesson already close to its floor.
   */
  compact?: boolean;
  /**
   * Give the track back. Lives here rather than in the session bar because it is
   * a control for this column — the bar keeps only the way back in, since once
   * the rail is hidden there is no rail to hold a button.
   */
  onHide?: () => void;
  /**
   * Open the briefing. Optional, because the rail is drawn in contexts that have
   * nowhere to send the learner — and a row that goes nowhere is worse than none.
   */
  onBriefing?: () => void;
}

/**
 * The rail answers four questions and no more: where am I, what is behind me,
 * what is next, and which stage of the journey am I in. Detail belongs to the
 * lesson, the section overview and the progress map — so concept tags, line
 * ranges and the state legend are all deliberately absent here. Density was the
 * problem: everything on screen carried the same weight, and the current stop
 * did not stand out from the fifteen around it.
 *
 * The chapter's `why` went the same way. Two clamped lines under every section
 * heading was the largest block of prose in the rail, and it repeated text the
 * chapter overview already opens with — so it is a tooltip here and a paragraph
 * there, which is the same information at the density each surface is for.
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

const TITLE_TONE: Record<Tone, string> = {
  current: "text-meta font-semibold text-signal",
  done: "text-meta font-medium text-graphite group-hover:text-signal",
  ahead: "text-meta font-medium text-paper group-hover:text-signal",
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
  // ONE vocabulary. The rail spoke the model's raw words — "partial",
  // "not started", "needs another pass" — while the map spoke the learner's.
  // Same unit, two names (M3a.3 AC3).
  const state = understandingLabel(node.understanding ?? "insufficient");
  return (
    <button
      onClick={() => onJump(node)}
      aria-current={isCurrent ? "step" : undefined}
      // The detail the row no longer spends a line on stays one hover away.
      // Open gaps are named here too: a stop with unresolved misconceptions and
      // an untouched stop both read as "not done" otherwise (§18.10).
      title={
        (node.gaps?.length ?? 0) > 0
          ? `${node.title} · ${node.file} — ${state} · ${t.rail.unresolved}: ${node
              .gaps!.map((g) => g.claim)
              .join("; ")}`
          : `${node.title} · ${node.file} — ${state}`
      }
      // A finished stop used to also carry `opacity-80`. It came out at 3.93:1 in
      // dark and 3.28:1 in light — the worst text in the rail, and the fade was
      // the whole cause. It was also the third signal for one fact: the pin
      // already encodes state and the title is already `graphite` where a live
      // stop is `paper`. Dropping it leaves done rows at 5.45 / 4.75, still
      // plainly quieter than a live row, and stops the rail dimming its own text
      // below the floor to say something it had already said twice.
      className={`group relative grid w-full grid-cols-[calc(18rem/16)_1fr] gap-3 py-[calc(9rem/16)] text-start ${
        stop.isPrerequisite ? "ms-[calc(22rem/16)] w-[calc(100%-22rem/16)]" : ""
      }`}
    >
      {/* connector down to the next stop */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute start-2 top-[calc(22rem/16)] bottom-[calc(-11rem/16)] w-px bg-rule"
        />
      )}

      <StatePin
        understanding={node.understanding}
        isCurrent={isCurrent}
        role="rail"
        className="z-10 mt-0.5 block"
      />

      <span className="flex min-w-0 flex-col gap-[2px]">
        {stop.isPrerequisite && (
          <span className="flex items-center gap-[5px] font-mono text-micro tracking-[0.06em] text-signal">
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

        {/* The current stop used to caption itself with its file path. It came
            out: the path is already above the lesson, in the brief, and beside the
            source pane when that is open — so in the rail it was a third copy of
            one fact, and the longest line in the column. The tooltip still carries
            it for anyone who wants it from here. */}

        {/* CURRENT difficulty only. `weak_spot` is sticky — true forever once
            the learner failed here — so rendering it kept a unit they have
            since mastered captioned as a weakness. `understanding` is the
            server-classified state and distinguishes the two. */}
        {/* And where gaps ARE on the wire (M9), say which of the two it is.
            "marked weak" is wrong for the commonest new case: a learner whose
            latest answer reached the objective, held back only by a check they
            have not taken yet. Captioning that as a weakness reports a failure
            that did not happen. */}
        {node.understanding === "unresolved" && (
          <span
            className="font-mono text-micro tracking-[0.05em] text-rust"
            title={
              (node.gaps?.length ?? 0) > 0
                ? t.rail.unresolvedHint
                : node.disposition === "waived"
                  ? t.rail.setAsideHint
                  : state
            }
          >
            {/* Three reasons a stop can be unresolved, and they are not the
                same thing to a learner: work still open, work they chose to
                set aside, and a genuine rough patch. Only the last is a
                weakness, and saying so for all three is what M3a.1 set out to
                stop. */}
            {(node.gaps?.length ?? 0) > 0
              ? t.rail.unresolvedCount(node.gaps!.length)
              : node.disposition === "waived"
                ? t.rail.setAside
                : state}
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
    // NO margin here. This div is always the first child of its own section
    // wrapper, so a `first:mt-0` on it matched every chapter and zeroed the gap
    // for all of them — the separation between chapters belongs to the wrapper
    // that actually has siblings. See the `mt-9 first:mt-0` below.
    <div className="flex items-start gap-1.5">
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
        // The chapter's `why` is one hover away rather than two lines of the
        // rail. It is not lost: the same text is the first thing on the chapter
        // overview, which is what this button opens.
        title={area.why ? `${area.title} — ${area.why}` : area.title}
        className="group flex min-w-0 flex-1 flex-col gap-[3px] text-start"
      >
        <span className="flex items-baseline gap-2">
          <span
            // Open is a state worth seeing (UI note 6). Three levels rather than
            // two: the chapter you are IN or whose overview is showing is `signal`;
            // a chapter merely expanded is `chalk`, which reads as attended without
            // competing with where you actually are; everything closed stays
            // `graphite`. Without the middle level, expanding a chapter you are not
            // in changed nothing about its heading, so the list of headings gave no
            // clue which one the visible stops belonged to.
            className={`min-w-0 flex-1 font-mono text-micro uppercase tracking-[0.15em] transition ${
              isCurrent || isOverviewOpen
                ? "text-signal"
                : open
                  ? "text-chalk group-hover:text-signal"
                  : "text-graphite group-hover:text-signal"
            }`}
          >
            {area.title}
          </span>
          <span className="shrink-0 font-mono text-micro tabular-nums text-graphite">
            {t.rail.sectionProgress(section.settled, section.total)}
          </span>
        </span>
      </button>
    </div>
  );
}

export default function RouteRail({
  sections, optional, currentNodeId, openSectionId, onJump, onOpenSection, onExpand,
  compact = false,
  onHide,
  onBriefing,
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

  // Loudest for where you are, quietest for what is behind you. "Behind" is the
  // same `settled` the section counts use, so a muted row and the count above it
  // can never tell different stories.
  const toneFor = (section: RouteSection, stop: RouteStop): Tone => {
    if (stop.node.id === currentNodeId) return "current";
    if (isSettled(stop.node) || section.status === "past") return "done";
    return "ahead";
  };

  /**
   * `«` rather than the words: the header already carries "Your route" and "Open
   * map", and a third label at 312px pushes the row to two lines. The accessible
   * name and the tooltip both say it in full.
   */
  const hideControl = onHide ? (
    <button
      onClick={onHide}
      aria-label={t.session.hideRail}
      title={t.session.hideRail}
      className="shrink-0 font-mono text-micro text-graphite transition hover:text-signal"
    >
      «
    </button>
  ) : null;

  /**
   * The briefing at the head of the route, and deliberately not shaped like the
   * route.
   *
   * A stop is a pin on a connector; a chapter is tracked uppercase mono with a
   * counter. This is a bordered box in sentence case, because it is neither: there
   * is no understanding state to show, nothing is demonstrated there, and it sits
   * *before* the walk rather than being a step in it. The rule underneath is where
   * the route proper starts — the mirror of the rule above the optional stops, so
   * the walk is bracketed by the two things that are not part of it.
   */
  const briefingRow = onBriefing ? (
    <div className="mb-3 border-b border-rule pb-3">
      <button
        onClick={onBriefing}
        className="group flex w-full flex-col gap-px rounded-field border border-rule px-2.5 py-1.5 text-start transition hover:border-signal-dim hover:bg-slab"
      >
        <span className="text-meta text-paper transition group-hover:text-signal">
          {t.rail.briefing}
        </span>
        <span className="truncate text-micro text-graphite">{t.rail.briefingHint}</span>
      </button>
    </div>
  ) : null;

  if (compact) {
    /**
     * The same route at the density of a scrollbar: one pin per stop, in order,
     * each carrying the stop's title as its accessible name and its tooltip. It
     * answers "where am I, how much is left" — the part of the rail worth 56px —
     * and defers the rest to the map, which the strip's own control opens.
     *
     * Section headings are not drawn here: at this width a heading is a truncated
     * word. The boundary between chapters is a rule instead.
     */
    return (
      <aside
        aria-label={t.rail.title}
        className="flex h-full min-h-0 flex-col items-center gap-2 overflow-y-auto border-e border-rule bg-trench py-4"
      >
        {/* Same idea at strip density: a bordered mark, so it reads as a different
            kind of thing from the pins below it rather than as another stop. */}
        {onBriefing && (
          <button
            onClick={onBriefing}
            aria-label={t.rail.briefing}
            title={`${t.rail.briefing} — ${t.rail.briefingHint}`}
            className="mb-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-field border border-rule font-mono text-micro text-graphite transition hover:border-signal-dim hover:text-signal"
          >
            ◈
          </button>
        )}
        {sections.map((section, si) => (
          <div key={section.area?.id ?? si} className="flex flex-col items-center gap-2">
            {si > 0 && <span aria-hidden className="my-1 h-px w-4 bg-rule" />}
            {section.stops.map((stop) => (
              <button
                key={stop.node.id}
                onClick={() => onJump(stop.node)}
                aria-current={stop.node.id === currentNodeId ? "step" : undefined}
                // Same fallback the full rail uses: a node with no recorded
                // understanding is "insufficient", not an empty label.
                aria-label={`${stop.node.title} — ${understandingLabel(stop.node.understanding ?? "insufficient")}`}
                title={`${stop.node.title} — ${understandingLabel(stop.node.understanding ?? "insufficient")}`}
                className="flex h-6 w-6 shrink-0 items-center justify-center"
              >
                <StatePin
                  understanding={stop.node.understanding}
                  isCurrent={stop.node.id === currentNodeId}
                  role="rail"
                />
              </button>
            ))}
          </div>
        ))}
        <span className="mt-auto flex shrink-0 flex-col items-center gap-2">
          {hideControl}
          <button
            onClick={onExpand}
            aria-label={t.rail.openMap}
            title={t.rail.openMap}
            className="shrink-0 font-mono text-micro text-graphite transition hover:text-signal"
          >
            ⤢
          </button>
        </span>
      </aside>
    );
  }

  return (
    <aside
      aria-label={t.rail.title}
      className="flex h-full min-h-0 flex-col gap-3 border-e border-rule bg-trench py-4"
    >
      <div className="flex items-baseline gap-3 px-4">
        <span className="min-w-0 flex-1 truncate font-mono text-micro uppercase tracking-[0.16em] text-graphite">
          {t.rail.title}
        </span>
        <button
          onClick={onExpand}
          className="shrink-0 font-mono text-micro text-signal transition hover:text-chalk"
        >
          {t.rail.openMap}
        </button>
        {hideControl}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-4 pb-2">
        {briefingRow}
        {sections.map((section, si) => {
          const area = section.area;
          const key = area?.id ?? `ungrouped-${si}`;
          // An ungrouped bucket has no chapter to introduce and no heading to
          // click, so it is always shown — as it was before grouping existed.
          const open = area ? toggled[area.id] ?? section.containsCurrent : true;
          // COLLAPSED MEANS COLLAPSED. This used to keep the current stop visible
          // inside a closed section — "show that one stop rather than hiding where
          // the learner is" — and it read as a bug, because it is: the chevron says
          // closed and a row is still there, so the control appears not to have
          // worked. Where the learner is stays legible without it: the heading of
          // the section they are in is marked, and its counter still moves.
          const visible = open ? section.stops : [];

          return (
            // The chapter separation lives here, on the element that has
            // siblings, so `first:` means "the first chapter" rather than
            // "every heading". A collapsed rail is six headings in a column and
            // the gap is the only thing telling them apart.
            <div key={key} className="mt-9 first:mt-0">
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
              className="flex w-full items-center gap-2 py-1 font-mono text-micro uppercase tracking-[0.13em] text-graphite transition hover:text-signal"
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
