import type { Area, GraphNode } from "@/lib/api";
import { isStation, type RouteStop } from "@/lib/graph-layout";

/**
 * Sections — the chapter level of the route, derived from data the graph
 * already carries.
 *
 * `Journey → Area → Learning Unit` (learning-engine.md §4.3) is the product's
 * hierarchy, and areas are deliberately metadata rather than an entity: an
 * ordered list on the session, plus an `area_id` per unit. So a "section" is
 * not something the backend sends — it is this projection of the stops the rail
 * already walks, and nothing here changes traversal.
 *
 * Progress is counted the way `backend/learning/progress.py` counts it, so the
 * rail's `1/3` cannot disagree with the header's percentages: stations only
 * (remedial detours and optional units are not stops on the promised journey),
 * and "settled" means dealt with — visited, answered, or explicitly acted on —
 * rather than mastered. Mastery is what the pin colour says.
 */

export type SectionStatus = "past" | "current" | "upcoming";

export interface RouteSection {
  /** Null for the trailing bucket of stops no declared area claims. */
  area: Area | null;
  /** 1-based position among sections, for "Chapter 2 of 5". */
  index: number;
  stops: RouteStop[];
  /** Stops the learner has dealt with. */
  settled: number;
  /** Stops that count toward the promised journey. */
  total: number;
  /** Stops whose objective the learner actually demonstrated. */
  understood: number;
  status: SectionStatus;
  containsCurrent: boolean;
}

/**
 * Has the learner dealt with this stop at all?
 *
 * Coverage, not mastery — the mirror of `progress.is_settled`. A node is marked
 * visited when the learner advances *off* it, so the stop they are standing on
 * is not settled yet, and a section they have just entered honestly reads 0/3.
 */
export function isSettled(node: GraphNode): boolean {
  return Boolean(node.visited || node.attempts?.length || node.user_override);
}

/**
 * Which section a stop belongs to.
 *
 * A remedial warm-up carries no `area_id` — the Mutator writes a brief with
 * `priority` and `origin` and nothing about grouping — so it inherits the area
 * of the unit it was spliced in to unblock. Without that inheritance an
 * adaptation would move the learner to a trailing ungrouped bucket at the
 * bottom of the rail, which is the one moment the rail must be clearest about
 * where they are.
 */
function sectionKeyOf(
  stop: RouteStop,
  declared: Set<string>,
  areaById: Map<string, string>
): string | null {
  const own = stop.node.area_id;
  if (own && declared.has(own)) return own;
  const inherited = stop.unlocksId ? areaById.get(stop.unlocksId) : undefined;
  return inherited && declared.has(inherited) ? inherited : null;
}

/**
 * Split the route into sections, preserving WALK ORDER — within each, and
 * between them.
 *
 * Grouping is a rendering concern only: the stops keep the order `buildRoute`
 * produced. A stop whose `area_id` names no declared area, and which no
 * inheritance rule places, falls into a trailing ungrouped bucket rather than
 * being hidden — a graph the planner never grouped must still render whole, and
 * every pre-B3 graph is in exactly that shape.
 *
 * SECTIONS ARE ORDERED BY WHERE THEY START ON THE WALK, not by `area.order`.
 * The planner sorts its chain by area, so on a well-formed graph the two agree
 * and this changes nothing. They come apart when a cross-area dependency forces
 * a stop out of its chapter's run, and there the walk has to win: the walk is
 * what numbers the stops, so a rail sorted by the declared order would draw
 * "stop 2 of 12" below "stop 4 of 12". A rail that disagrees with its own
 * numbers is a worse lie than a chapter listed out of the order the planner
 * hoped for.
 */
export function buildSections(
  stops: RouteStop[],
  areas: Area[],
  currentNodeId: string | null
): RouteSection[] {
  const ordered = [...areas].sort((a, b) => a.order - b.order);
  if (ordered.length === 0) {
    return stops.length > 0 ? [tally({ area: null, index: 1, stops }, false)] : [];
  }

  const declared = new Set(ordered.map((a) => a.id));
  const areaById = new Map(stops.map((s) => [s.node.id, s.node.area_id ?? ""]));

  const buckets = new Map<string, RouteStop[]>(ordered.map((a) => [a.id, []]));
  const startsAt = new Map<string, number>();
  const ungrouped: RouteStop[] = [];
  stops.forEach((stop, index) => {
    const key = sectionKeyOf(stop, declared, areaById);
    if (!key) {
      ungrouped.push(stop);
      return;
    }
    buckets.get(key)!.push(stop);
    if (!startsAt.has(key)) startsAt.set(key, index);
  });

  const staffed = ordered
    .filter((area) => buckets.get(area.id)!.length > 0)
    .sort((a, b) => startsAt.get(a.id)! - startsAt.get(b.id)!);

  const groups: { area: Area | null; stops: RouteStop[] }[] = staffed.map(
    (area) => ({ area, stops: buckets.get(area.id)! })
  );
  if (ungrouped.length > 0) groups.push({ area: null, stops: ungrouped });

  // Which section the learner is in decides past / current / upcoming, and so
  // decides what is expanded. With no current node — the moment before the
  // first lesson lands — the journey has not started, so its opening section is
  // the one to show.
  const currentIndex = Math.max(
    0,
    groups.findIndex((g) => g.stops.some((s) => s.node.id === currentNodeId))
  );

  return groups.map((group, i) =>
    tally({ ...group, index: i + 1 }, i === currentIndex, i, currentIndex)
  );
}

function tally(
  group: { area: Area | null; index: number; stops: RouteStop[] },
  containsCurrent: boolean,
  position = 0,
  currentIndex = 0
): RouteSection {
  const stations = group.stops.filter(isStation);
  return {
    ...group,
    total: stations.length,
    settled: stations.filter((s) => isSettled(s.node)).length,
    understood: stations.filter(
      (s) => s.node.understanding_state === "understood"
    ).length,
    containsCurrent,
    status: containsCurrent
      ? "current"
      : position < currentIndex
      ? "past"
      : "upcoming",
  };
}

/**
 * The route as the rail and the overview both see it: sections, plus the
 * optional stops the rail keeps collapsed behind one line.
 *
 * One function so there is one definition. Optional units are depth the learner
 * did not ask for (§6.3) and they sit on the same spine, so which stops belong
 * to a section and which are collapsed cannot be decided in two places without
 * eventually disagreeing — and a section count that disagreed with the stops
 * under it would be worse than no count.
 */
export function splitJourney(
  stops: RouteStop[],
  areas: Area[],
  currentNodeId: string | null
): { sections: RouteSection[]; optional: RouteStop[] } {
  const optional = stops.filter((s) => s.node.priority === "optional");
  const spine =
    optional.length > 0
      ? stops.filter((s) => s.node.priority !== "optional")
      : stops;
  return { sections: buildSections(spine, areas, currentNodeId), optional };
}

/** Complete enough to mark done — every stop on it has been dealt with. */
export function isComplete(section: RouteSection): boolean {
  return section.total > 0 && section.settled === section.total;
}

/**
 * Which chapter should introduce itself now, and which to record as seen.
 *
 * The chapter introduction is for a chapter the ROUTE walked the learner into:
 * it stands in place of the lesson, so it may only appear when the learner did
 * not ask for a lesson. `arrivedByChoice` is that distinction — the learner
 * named this stop — and it is the whole fix for a real bug: clicking the first
 * stop of a chapter opened the chapter over the top of it. Every other guard
 * lets that case through, because the first stop of a fresh chapter is exactly
 * "a chapter with nothing settled that has not been introduced yet".
 *
 * `record` is returned separately from `introduce` because a chapter is seen by
 * being stood in, whether or not it introduced itself. Collapsing the two would
 * re-introduce a chapter the learner resumed into the moment they moved inside
 * it.
 *
 * Pure, and returning both decisions, so the page holds no policy: the caller
 * adds `record` to its set and opens `introduce` if it is there.
 */
export function arrivalIntro(
  sections: RouteSection[],
  seen: ReadonlySet<string>,
  arrivedByChoice: boolean
): { record: string | null; introduce: string | null } {
  const section = currentSection(sections);
  const areaId = section?.area?.id;
  if (!areaId || seen.has(areaId)) return { record: null, introduce: null };
  // Nothing seen yet means this is where the learner came IN — a resume or a
  // reload, not an arrival — so the first chapter of a visit never introduces
  // itself.
  const resumed = seen.size === 0;
  const introduce =
    !resumed && !arrivedByChoice && section.settled === 0 ? areaId : null;
  return { record: areaId, introduce };
}

/** The section the learner is in, if any section holds the current stop. */
export function currentSection(sections: RouteSection[]): RouteSection | null {
  return sections.find((s) => s.containsCurrent) ?? null;
}
