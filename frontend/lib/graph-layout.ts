import type { GraphNode, GraphEdge } from "@/lib/api";

/**
 * Turns the graph's edges into the order a learner actually walks them.
 *
 * The backend builds the initial graph as a pure sequence chain. When the
 * Mutator inserts a prerequisite P before node B, it reroutes `A -sequence-> B`
 * into `A -sequence-> P` and appends `P -prerequisite-> B`. So walking
 * "sequence first, else prerequisite" reproduces the path the API itself
 * follows in next_in_path.
 */

export interface RouteStop {
  node: GraphNode;
  /** True when the Mutator spliced this node in after a wrong answer. */
  isPrerequisite: boolean;
  /** Id of the node this prerequisite unlocks — a warm-up carries no `area_id`
   *  of its own, so this is what places it in the section it belongs to. */
  unlocksId: string | null;
  /** Title of the node this prerequisite unlocks, for the rail's caption. */
  unlocksTitle: string | null;
  /**
   * 1-based position among spine stops, to pair with spineLength. Prerequisites
   * are detours rather than stations, so they report the position of the stop
   * they precede instead of consuming a number of their own.
   */
  position: number;
}

function outgoing(edges: GraphEdge[], from: string, kind: string): string | null {
  const edge = edges.find((e) => e.from_id === from && e.kind === kind);
  return edge ? edge.to_id : null;
}

/**
 * The node this one was spliced in to unblock, or null when it is not a warm-up.
 *
 * Two different things now write `prerequisite` edges, and only one of them is a
 * detour the rail should mark:
 *
 *   PLANNED     the objective-first planner emits one per `depends_on`, so a
 *               normal graph carries dozens of them. These describe the
 *               dependency structure of the curriculum — they are not events,
 *               and every unit they touch is an ordinary stop on the spine.
 *   REMEDIAL    the Mutator splices a warm-up in after a wrong answer, using
 *               insert_before: the incoming `sequence` edge is rerouted onto the
 *               new node, which is then joined to the original by a
 *               `prerequisite` edge.
 *
 * The structural difference is that a spliced warm-up has NO outgoing sequence
 * edge — the reroute gave its sequence slot away — whereas a planned unit sits
 * on the chain and keeps one. Without this distinction a planned graph renders
 * with almost every stop indented and captioned "added after confusion", and
 * spineLength collapses to near one.
 */
function unlockTargetOf(edges: GraphEdge[], nodeId: string): string | null {
  if (outgoing(edges, nodeId, "sequence") !== null) return null;
  return outgoing(edges, nodeId, "prerequisite");
}

function findHead(nodes: GraphNode[], edges: GraphEdge[]): GraphNode | null {
  if (nodes.length === 0) return null;
  const hasIncoming = new Set(edges.map((e) => e.to_id));
  return nodes.find((n) => !hasIncoming.has(n.id)) ?? nodes[0];
}

/**
 * Walks the graph from its head and returns stops in path order. Nodes that
 * no edge reaches are appended at the end rather than dropped — a malformed
 * graph should still render every node it contains.
 */
export function buildRoute(nodes: GraphNode[], edges: GraphEdge[]): RouteStop[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const walked: Omit<RouteStop, "position">[] = [];
  const seen = new Set<string>();

  let cursor = findHead(nodes, edges);
  while (cursor && !seen.has(cursor.id)) {
    seen.add(cursor.id);
    const unlocks = unlockTargetOf(edges, cursor.id);
    walked.push({
      node: cursor,
      isPrerequisite: unlocks !== null,
      unlocksId: unlocks,
      unlocksTitle: unlocks ? byId.get(unlocks)?.title ?? null : null,
    });

    const nextId =
      outgoing(edges, cursor.id, "sequence") ?? outgoing(edges, cursor.id, "prerequisite");
    cursor = nextId ? byId.get(nextId) ?? null : null;
  }

  for (const node of nodes) {
    if (seen.has(node.id)) continue;
    walked.push({ node, isPrerequisite: false, unlocksId: null, unlocksTitle: null });
  }

  let spineSeen = 0;
  return walked.map((stop) => {
    if (countsAsStation(stop)) spineSeen += 1;
    return { ...stop, position: countsAsStation(stop) ? spineSeen : spineSeen + 1 };
  });
}

/**
 * Does this stop consume a number in "stop N of M"?
 *
 * Prerequisites are detours rather than stations. Optional units are depth the
 * learner did not ask for and the rail collapses them, so counting them would
 * promise a journey longer than the one on screen — "stop 1 of 4" above three
 * visible stops.
 */
function countsAsStation(stop: Omit<RouteStop, "position">): boolean {
  return !stop.isPrerequisite && stop.node.priority !== "optional";
}

/** `countsAsStation` for callers holding finished stops — section tallies count
 *  the same population the stop counter does, so they cannot disagree with it. */
export function isStation(stop: RouteStop): boolean {
  return countsAsStation(stop);
}

/** Stops that count toward "stop N of M". */
export function spineLength(stops: RouteStop[]): number {
  return stops.filter(countsAsStation).length;
}
