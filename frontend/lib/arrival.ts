import type { Arrival, GraphNode } from "@/lib/api";
import { isStation, spineLength, type RouteStop } from "@/lib/graph-layout";

/**
 * What to say on a stop the learner jumped to.
 *
 * ── Why this is derived here and not sent by the server ───────────────────────
 *
 * The backend records the raw fact only: which stop was left, which was landed
 * on, when. Everything a learner actually reads — "stop 9 of 15", "passing 4
 * stops" — is a statement about the ROUTE, and the route is numbered by
 * `buildRoute`. Computing those numbers server-side would put a second
 * implementation of "stop N of M" on the wire, and the two would disagree in
 * exactly the place the learner is comparing them: a notice saying "stop 9"
 * above a rail that calls the same unit stop 8.
 *
 * So: the server owns the FACT, this owns the SENTENCE, and the sentence is
 * built from the same stop list the rail draws.
 *
 * ── WHAT THE JUMP IS MEASURED FROM, AND WHY IT IS NOT `from_node_id` ─────────
 *
 * The obvious reference is the stop the learner was sitting on when they jumped,
 * which is what `arrival.from_node_id` records. It is the wrong one, and the case
 * that shows it is ordinary: the learner answers stop 4, then jumps to stop 7.
 * Measured from `from_node_id` the notice says they came from 4 and passed two
 * stops — but 4 is FINISHED. They were not going to be sent back to it; the route
 * was going to send them to 5. So the honest reading is "you jumped ahead of stop
 * 5, passing one", and "Return to the route" has to mean 5, not 4.
 *
 * The reference is therefore THE ROUTE'S NEXT STOP: the first station, in walk
 * order, the learner has not yet dealt with. For contiguous progress that is
 * exactly "last finished + 1". It stays right when progress is not contiguous,
 * which matters because a learner who has jumped before is precisely the
 * population this notice exists for — with stops 1–4 and 7 answered, the route's
 * next stop is 5, while "last finished + 1" would point at 8, a stop nobody has
 * ever reached.
 *
 * `from_node_id` is still recorded, and still the truth for the session log
 * ("you jumped from 4 to 7"). It is used here only as the fallback for a journey
 * with nothing left unfinished.
 *
 * ── Why a pure function ──────────────────────────────────────────────────────
 *
 * Same reason as `sessionLog` and `feedbackSummary`: choosing the direction,
 * resolving ids to titles and deciding when to say nothing at all are decisions,
 * and decisions in a render body are decisions nobody can test.
 */

export interface ArrivalNotice {
  /**
   * Which way the learner moved relative to the route's next stop.
   *
   * `null` when no reference can be established — every station is finished and
   * the stop they left is no longer in the graph. A notice that guessed would be
   * worse than one that reports position and stops there.
   */
  direction: "ahead" | "back" | null;
  /** The stop landed on, and the length of the walk. Meaningless unless `isStation`. */
  position: number;
  total: number;
  /**
   * Does this stop consume a number in "stop N of M"?
   *
   * False for a warm-up and for an `optional` unit — neither is counted by the
   * rail, so quoting a number for one would promise a position the rail does not
   * show. The copy for these says where they are without numbering it.
   */
  isStation: boolean;
  /**
   * Stations between the route's next stop and this one, exclusive. 0 for
   * adjacent ones.
   *
   * ALSO 0 when either end is not a station, and that is not a shortcut. A
   * warm-up and an `optional` unit consume no number, so `buildRoute` gives them
   * the position of the station they precede — arithmetic over that position
   * counts a gap that is not there. "Passing 4 stops" has to be a claim about
   * stops the learner can point at on the rail, or it should not be made.
   */
  passed: number;
  /**
   * True when the learner had already dealt with the stop they jumped back to.
   *
   * Checked rather than assumed: jumping backwards to something never reached is
   * perfectly possible (from a warm-up, or after a scope change reordered what is
   * ahead), and calling that "already taken" would be false.
   */
  revisited: boolean;
  /** The route's next stop, so the notice can offer the way back to it. */
  returnTo: { nodeId: string; title: string; position: number } | null;
}

/**
 * Has the learner dealt with this stop at all?
 *
 * Mirrors `progress.is_settled` deliberately — visited, answered, or explicitly
 * acted on. Coverage, not mastery: a wrong answer finishes a stop for this
 * purpose exactly as a right one does, because the question here is where the
 * route would send them next, not how well they did.
 */
function isFinished(node: GraphNode): boolean {
  return (
    node.visited ||
    (node.attempts?.length ?? 0) > 0 ||
    Boolean(node.user_override)
  );
}

/**
 * The notice, or null when there is nothing to say.
 *
 * Null in four cases. The second matters most: an arrival record that does not
 * name the CURRENT stop is stale and must not be rendered — the server clears the
 * record on `/advance`, but a client holding a graph fetched either side of that
 * must not be the thing that decides to trust it. The fourth is the quiet one:
 * jumping to the stop the route was sending you to anyway is not a departure from
 * it, and saying "you jumped ahead, passing 0 stops" about an ordinary next step
 * would be noise.
 */
export function arrivalNotice(
  arrival: Arrival | null | undefined,
  currentNodeId: string | null,
  stops: RouteStop[]
): ArrivalNotice | null {
  if (!arrival || arrival.kind !== "jumped") return null;
  if (!currentNodeId || arrival.node_id !== currentNodeId) return null;

  const toIndex = stops.findIndex((s) => s.node.id === arrival.node_id);
  if (toIndex === -1) return null;
  const to = stops[toIndex];

  // THE ROUTE'S NEXT STOP — see the header.
  //
  // A WARM-UP COUNTS. It is a detour the rail does not number, but it is still
  // somewhere the route would send the learner — `resume_point()` puts unfinished
  // remediation first for exactly that reason: "a node still carrying open work is
  // where the learner actually left off". Excluding it sent a learner whose only
  // outstanding stop was a warm-up back to the stop they had been sitting on
  // instead. Not being numbered is handled by `measurable` below, which is a
  // question about quoting a position, not about being the reference.
  //
  // `optional` does NOT count: it is depth off the default walk, so the route
  // would never have sent them there in the first place.
  let refIndex = stops.findIndex(
    (s) => s.node.priority !== "optional" && !isFinished(s.node)
  );
  if (refIndex === -1) {
    // Nothing unfinished left. Fall back to the stop actually left behind, which
    // is the only reference a completed journey has.
    refIndex = arrival.from_node_id
      ? stops.findIndex((s) => s.node.id === arrival.from_node_id)
      : -1;
  }
  if (refIndex === toIndex) return null;

  const ref = refIndex === -1 ? null : stops[refIndex];
  const direction = ref === null ? null : toIndex > refIndex ? "ahead" : "back";

  // Both ends must be stations for the distance between them to mean anything —
  // see `passed` above.
  const measurable = ref !== null && isStation(to) && isStation(ref);

  return {
    direction,
    position: to.position,
    total: spineLength(stops),
    isStation: isStation(to),
    passed:
      measurable && ref
        ? Math.max(0, Math.abs(to.position - ref.position) - 1)
        : 0,
    revisited: isFinished(to.node),
    returnTo: ref
      ? { nodeId: ref.node.id, title: ref.node.title, position: ref.position }
      : null,
  };
}
