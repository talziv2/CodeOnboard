"use client";

import { useMemo, useState } from "react";
import { openOnly, type Area, type GraphNode, type GraphEdge } from "@/lib/api";
import { understandingLabel } from "@/lib/tags";
import { standingOfNode, standingLabel, standingStyle } from "@/lib/standing";
import { buildRoute, isOnPromisedWalk, spineLength, type RouteStop } from "@/lib/graph-layout";
import { buildSections, isSettled, type RouteSection } from "@/lib/route-sections";
import SectionLabel from "@/components/ui/SectionLabel";
import ConceptTag from "@/components/ui/ConceptTag";
import StatePin from "@/components/ui/StatePin";
import StopCard from "@/components/StopCard";
import MapLegend from "@/components/MapLegend";
import { InlineProse } from "@/components/ui/Prose";
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
 * A STOP IS NOT A LINK. Clicking one used to jump into its lesson, which made the
 * one surface built for choosing where to go the only one that would not describe a
 * place before taking you to it. It now opens `StopCard`, and the jump is a button
 * inside that card — the same navigation, one deliberate step later. Selection is
 * held here rather than by the page because it is a fact about reading this view,
 * not about the session: leaving the map forgets it, which is correct.
 *
 * ── The route is drawn, not merely listed ────────────────────────────────────
 *
 * Everything below the header is a rendering of the graph and nothing else, but
 * three things the graph already knew were not visible, and their absence is what
 * made fifteen stops read as similar cards joined by a line:
 *
 *   PROGRESSION   the trunk is `signal-dim` down to the pin you are standing on
 *                 and `rule` after it, so the line itself says how far you have
 *                 come. One colour change at one point — never a filled bar.
 *   CHAPTERS      `buildSections` already groups stops by the planner's areas for
 *                 the rail; the map drew them as one undifferentiated run. Same
 *                 grouping, same counts, same heading grammar.
 *   BRANCHING     a warm-up and an optional unit leave the trunk on a spur and
 *                 the trunk carries on past them, because that is what they are:
 *                 `buildRoute` gives neither of them a number on the walk.
 *
 * No new fact is computed here and nothing is persisted. Every distinction on
 * screen is one the graph already carried and this view was throwing away.
 */

/* ── route geometry ──────────────────────────────────────────────────────────
 *
 * Named because they have to agree with each other: an ordinary row draws the
 * trunk at `TRUNK_X`, and a branch row — indented by `BRANCH_INDENT` — draws the
 * SAME trunk at `TRUNK_X - BRANCH_INDENT`, so the two land on one continuous line
 * down the page. Deriving that alignment from a literal in four places is how it
 * drifts apart. */
const TRUNK_X = 16;
/** Vertical centre of the pin: 10px of cell padding plus half of a 15px pin. */
const PIN_MID = 18;
const BRANCH_INDENT = 40;
/** Where a branch row draws the trunk it is hanging off. */
const BRANCH_TRUNK_X = TRUNK_X - BRANCH_INDENT;
/** The spur, from that trunk across to the branch pin's own edge. */
const SPUR_W = 33;
/** The trunk overshoots its row so it meets the next one without a seam. */
const TRUNK_OVERSHOOT = 6;

/** Authored in rem so the whole route scales with the text-size dial, like
 *  everything else in the app — a px literal would ignore it. */
const px = (n: number) => `calc(${n}rem / 16)`;

const dashedAcross = (colour: string) =>
  `repeating-linear-gradient(to right, ${colour} 0 5px, transparent 5px 10px)`;

/**
 * How a stop sits on the route, in one value.
 *
 * The two branch kinds stay separate although they are drawn alike: a warm-up is
 * `signal`, because something happened and the system responded to it, and an
 * optional unit is `rule`, because nothing happened — it was simply never
 * promised. Captioning the second with the first's reason is the mistake this
 * distinction exists to keep out.
 */
type Kind = "spine" | "warmup" | "optional";

function kindOf(stop: RouteStop): Kind {
  if (stop.isPrerequisite) return "warmup";
  return isOnPromisedWalk(stop.node) ? "spine" : "optional";
}

/**
 * One chapter heading, from the area the planner wrote.
 *
 * Ordinal, title, hairline, counter — the rail's grammar at the map's scale. It is
 * deliberately not a card or a band: chapters are meant to create hierarchy and
 * breathing room, and a box around each one would add a third level of container
 * to a page that already has stop cards inside a route.
 */
function ChapterHead({ section, chapters }: { section: RouteSection; chapters: number }) {
  const area = section.area!;
  // Three levels, the rail's: the chapter you are in is `signal`, one still ahead
  // of you is `paper`, one behind you steps back to `graphite`.
  const tone =
    section.status === "current"
      ? "text-signal"
      : section.status === "past"
        ? "text-graphite"
        : "text-paper";

  return (
    <div className="flex items-center gap-3">
      <h4 className="flex min-w-0 items-baseline gap-2.5 font-mono text-micro uppercase tracking-[0.16em]">
        <span className="shrink-0 tabular-nums text-graphite">
          {String(section.index).padStart(2, "0")}
        </span>
        <span aria-hidden className="shrink-0 text-graphite">·</span>
        <span className={`[overflow-wrap:anywhere] ${tone}`}>{area.title}</span>
        <span className="sr-only">{t.section.chapterOf(section.index, chapters)}</span>
      </h4>
      <span aria-hidden className="h-px flex-1 bg-rule" />
      {section.total > 0 && (
        <span
          className="shrink-0 font-mono text-micro tabular-nums text-graphite"
          title={t.section.progress(section.settled, section.total)}
        >
          {t.rail.sectionProgress(section.settled, section.total)}
        </span>
      )}
    </div>
  );
}

/**
 * One stop, and the piece of route that passes through it.
 *
 * The row owns the trunk rather than the list, because where the trunk is drawn
 * depends on whether THIS stop sits on it: a branch row is indented, so its copy
 * of the trunk is offset back by exactly the indent.
 */
function StopRow({
  stop, kind, isCurrent, travelledIn, travelledOut, isFirst, isLast, isOpen, onOpen,
}: {
  stop: RouteStop;
  kind: Kind;
  isCurrent: boolean;
  /** Has the learner reached this stop — decides the trunk above it. */
  travelledIn: boolean;
  /** Have they left it — decides the trunk below it. */
  travelledOut: boolean;
  isFirst: boolean;
  isLast: boolean;
  isOpen: boolean;
  onOpen: () => void;
}) {
  const { node } = stop;
  const isBranch = kind !== "spine";
  const standing = standingOfNode(node);
  const style = standingStyle(standing, node.understanding);
  const openGaps = openOnly(node.gaps).length;
  const settled = isSettled(node);

  const trunkX = isBranch ? BRANCH_TRUNK_X : TRUNK_X;
  const trunk = (travelled: boolean) =>
    travelled ? "var(--color-signal-dim)" : "var(--color-rule)";

  /**
   * ONE status line per card, in the pin's own colour.
   *
   * The rail's rule, verbatim, because two surfaces describing the same stop in
   * different words is the failure this replaces: the map printed the
   * understanding class and nothing else, so a stop the learner answered
   * inconclusively, one they walked past, and one they set aside were all three
   * captioned with nothing at all. Named gaps outrank everything — a count of
   * open misconceptions is the most actionable thing a route can say.
   */
  const status =
    openGaps > 0
      ? t.rail.unresolvedCount(openGaps)
      : standing === "open" || standing === "demonstrated"
        ? understandingLabel(node.understanding ?? "insufficient")
        : standingLabel(standing);
  const statusColour = openGaps > 0 ? "var(--color-rust)" : style.stroke;

  /**
   * Weight follows meaning, and only meaning.
   *
   * The stop you are standing on is the loudest thing on the page; a stop with
   * unresolved work is OUTLINED in its own colour rather than filled with it; a
   * stop already dealt with steps back a level. Everything else is the ordinary
   * card, and it is the one that got quieter — every stop previously carried the
   * same 2px border and the same padding, which is what flattened fifteen of them
   * into a list.
   */
  const borderColor = isCurrent
    ? "var(--color-signal)"
    : standing === "open"
      ? "var(--color-rust)"
      : "var(--color-rule)";
  const titleColor = isCurrent
    ? "var(--color-signal)"
    : settled && standing !== "open"
      ? "var(--color-paper)"
      : "var(--color-chalk)";

  return (
    <li
      className={`relative grid grid-cols-[calc(34rem/16)_minmax(0,1fr)] gap-4 pb-5 ${
        isBranch ? "ms-10" : ""
      }`}
    >
      {/* The trunk above this stop — the approach to it. */}
      {!isFirst && (
        <span
          aria-hidden
          className="absolute w-px"
          style={{
            insetInlineStart: px(trunkX),
            top: 0,
            height: px(PIN_MID),
            background: trunk(travelledIn),
          }}
        />
      )}

      {/* And below it. A branch is a LEAF: what carries on down the page is the
          trunk it hangs off, not the branch, which is why both pieces sit at the
          same x on a branch row and the pin is out to the side of them. */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute w-px"
          style={{
            insetInlineStart: px(trunkX),
            top: px(PIN_MID),
            bottom: px(-TRUNK_OVERSHOOT),
            background: trunk(travelledOut),
          }}
        />
      )}

      {/* The spur, which is the whole point: this stop LEFT the route. Dashed in
          `signal` for a warm-up — the system reacted to something the learner did
          — and in `rule` for an optional unit, where nothing happened at all. */}
      {isBranch && (
        <span
          aria-hidden
          className="absolute h-px"
          style={{
            insetInlineStart: px(BRANCH_TRUNK_X),
            top: px(PIN_MID),
            width: px(SPUR_W),
            backgroundImage: dashedAcross(
              kind === "warmup" ? "var(--color-signal)" : "var(--color-rule)"
            ),
          }}
        />
      )}

      <span className="flex justify-center pt-2.5">
        <StatePin
          understanding={node.understanding}
          disposition={node.disposition}
          attempted={node.attempted}
          visited={node.visited}
          isCurrent={isCurrent}
          role="map"
          className="z-10"
        />
      </span>

      <button
        onClick={onOpen}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-current={isCurrent ? "step" : undefined}
        className={`flex min-w-0 flex-col gap-2 rounded-card text-start transition hover:border-signal-dim ${
          isCurrent ? "border-2 px-4 py-4" : "border px-4 py-3"
        }`}
        style={{
          background: isCurrent ? "var(--color-signal-wash)" : "var(--color-slab)",
          borderColor,
        }}
      >
        {/* "you are here", and it leads the card — ORIENTATION OUTRANKS
            PROVENANCE, so on the one stop that is both current and a warm-up this
            comes before the reason it exists.

            A SOLID chip rather than a line of cyan text. It was
            `text-micro text-signal`, which put the single most important
            orientation cue on the page at the same weight as the file path two
            lines below it and in the same family — findable once you knew where
            to look, invisible while scanning. Solid `signal` with `ink` on it is
            not a new treatment: it is exactly the primary button's pairing, so it
            arrives already measured at 9.91:1 in dark and 6.73:1 in light. And it
            spends the accent on the one thing the accent is reserved for — the
            palette's own rule is that signal means "you are here" and is never
            decorative, which makes a solid block of it saying so the most
            on-system emphasis available. */}
        {isCurrent && (
          <span className="w-fit rounded-chip bg-signal px-2 py-1 font-mono text-micro font-semibold uppercase tracking-[0.18em] text-ink">
            {t.rail.youAreHere}
          </span>
        )}

        {/* WHY THIS STOP IS OFF THE TRUNK, in the colour of the spur that took it
            there — so the caption and the drawing are one statement rather than
            two. The line that used to precede this text is now the spur itself. */}
        {kind === "warmup" && (
          <span className="flex flex-wrap items-center gap-2 font-mono text-micro tracking-[0.06em] text-signal">
            {t.rail.addedAfterConfusion}
            {stop.unlocksTitle && (
              <span className="text-graphite">{t.map.unlocks(stop.unlocksTitle)}</span>
            )}
          </span>
        )}

        {kind === "optional" && (
          <span className="font-mono text-micro tracking-[0.06em] text-graphite">
            {t.map.stop.optional}
          </span>
        )}

        <span
          className="font-display text-lede font-medium tracking-tight [overflow-wrap:anywhere]"
          style={{ color: titleColor }}
        >
          {node.title}
        </span>

        {/* Only on the stop you are standing on. The objective is the contract the
            answer is marked against, so it is the one piece of detail worth extra
            room HERE and nowhere else on the route — emphasis carried by something
            worth reading rather than by a heavier border. */}
        {isCurrent && node.objective && (
          <span className="line-clamp-2 text-meta text-paper">
            <InlineProse text={node.objective} tone="paper" />
          </span>
        )}

        <span className="font-mono text-micro text-graphite [overflow-wrap:anywhere]">
          {node.file}
          {" · "}
          {t.lesson.lines(node.line_start, node.line_end)}
        </span>

        <span className="flex flex-wrap items-center gap-1.5">
          {node.concept_tags.slice(0, 2).map((tag) => (
            <ConceptTag key={tag} tag={tag} />
          ))}
          {/* CURRENT state, not the sticky flag. `weak_spot` stays true forever
              once set, so rendering it captioned a unit the learner has since
              mastered as a weakness. */}
          {status && (
            <span
              className="font-mono text-micro tracking-[0.05em]"
              style={{ color: statusColour }}
            >
              {status}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** The planner's chapters. Absent or empty on a pre-B3 graph, which then renders
   *  as one unheaded run — exactly what it did before chapters existed. */
  areas?: Area[];
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
  nodes, edges, areas, currentNodeId, repoUrl, onGoToLesson,
}: Props) {
  const stops = useMemo(() => buildRoute(nodes, edges), [nodes, edges]);
  const total = useMemo(() => spineLength(stops), [stops]);

  /**
   * The same grouping the rail draws, from the same function — but NOT
   * `splitJourney`.
   *
   * `splitJourney` lifts optional units out of their chapters into one collapsed
   * group, which is right for a 312px column and wrong here: on the map an
   * optional unit is drawn in place, as a spur off the trunk at the point the
   * planner put it. `buildSections` tallies stations only, so leaving them in
   * cannot move a chapter's counter.
   */
  const sections = useMemo(
    () => buildSections(stops, areas ?? [], currentNodeId),
    [stops, areas, currentNodeId]
  );

  /**
   * Walk order AS RENDERED. Read off the sections rather than off `stops`, because
   * a cross-area dependency can push a stop out of its chapter's run and the two
   * then disagree — and this is what decides which half of the trunk is drawn as
   * travelled, so it has to match what is actually on screen.
   */
  const ordered = useMemo(() => sections.flatMap((s) => s.stops), [sections]);
  const currentIndex = ordered.findIndex((s) => s.node.id === currentNodeId);
  const reached = (i: number) => currentIndex >= 0 && i <= currentIndex;
  const walked = (i: number) => currentIndex >= 0 && i < currentIndex;

  const [openStopId, setOpenStopId] = useState<string | null>(null);
  // Read out of `stops` rather than stored, so a graph that changed under the card
  // — a mutation, a re-plan — updates it instead of pinning a stale copy, and a
  // stop that has left the graph closes it.
  const openStop = stops.find((s) => s.node.id === openStopId) ?? null;

  const repo = repoUrl?.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");

  const chapters = sections.filter((s) => s.area).length;
  const settled = sections.reduce((n, s) => n + s.settled, 0);
  /**
   * Stops carrying unresolved work — the one fact about the route that the
   * session header does not already report. Counted with `standingOf`, the same
   * projection the pins are drawn from, so the number and the rust pins under it
   * are the same claim; and counted over the stops ON SCREEN, so it can never
   * describe a route the learner is not looking at.
   */
  const needWork = ordered.filter((s) => standingOfNode(s.node) === "open").length;

  return (
    <div className="h-full overflow-y-auto px-6 py-7">
      <div className="mx-auto flex max-w-4xl flex-col gap-7">

        {/* headline. The measures that used to sit here live in Analysis, and the
            two that matter most are in the session header at all times — so what
            is left is the shape of the route and what is outstanding on it, both
            counted off the stops drawn below. */}
        <header className="flex flex-col gap-1">
          <span className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
            {t.map.routeLabel}
          </span>
          <h2 className="font-display text-chapter font-medium tracking-tight text-chalk">
            {repo ?? t.map.thisCodebase}
          </h2>
          <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-micro text-graphite">
            <span className="tabular-nums">{t.map.stopsTaken(settled, total)}</span>
            {chapters > 0 && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums">{t.map.chapterCount(chapters)}</span>
              </>
            )}
            {needWork > 0 && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums text-rust">{t.map.needWork(needWork)}</span>
              </>
            )}
          </span>
        </header>

        {/* ── THE JOURNEY ──────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-4">
          <SectionLabel as="h3">{t.map.journeyTitle}</SectionLabel>

          {/* The key sits between the heading and the route, which is where a map
              key goes: above the thing it explains, closed until asked for. Not in
              the header row above — a disclosure expands in flow, and one opened
              from there would push the route down from inside the title block. */}
          <MapLegend />

          <div className="flex flex-col">
            {sections.map((section, si) => {
              const offset = sections
                .slice(0, si)
                .reduce((n, s) => n + s.stops.length, 0);

              return (
                <div
                  key={section.area?.id ?? `ungrouped-${si}`}
                  // The separation between chapters lives on the element that has
                  // siblings, so `first:` means "the first chapter" and not "every
                  // heading". This gap is the breathing room that makes a chapter
                  // read as a chapter rather than as a louder row.
                  className="mt-7 first:mt-0"
                >
                  {section.area && (
                    <div className="mb-4">
                      <ChapterHead section={section} chapters={chapters} />
                    </div>
                  )}

                  <ol className="flex flex-col">
                    {section.stops.map((stop, i) => {
                      const index = offset + i;
                      return (
                        <StopRow
                          key={stop.node.id}
                          stop={stop}
                          kind={kindOf(stop)}
                          isCurrent={stop.node.id === currentNodeId}
                          travelledIn={reached(index)}
                          travelledOut={walked(index)}
                          // The trunk joins stops WITHIN a chapter; a heading is a
                          // break in the line, not something to draw through.
                          isFirst={i === 0}
                          isLast={i === section.stops.length - 1}
                          isOpen={openStopId === stop.node.id}
                          onOpen={() => setOpenStopId(stop.node.id)}
                        />
                      );
                    })}
                  </ol>
                </div>
              );
            })}
          </div>
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
