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

/** A node is a prerequisite when it points at the node it was inserted to unblock. */
function unlockTargetOf(edges: GraphEdge[], nodeId: string): string | null {
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
      unlocksTitle: unlocks ? byId.get(unlocks)?.title ?? null : null,
    });

    const nextId =
      outgoing(edges, cursor.id, "sequence") ?? outgoing(edges, cursor.id, "prerequisite");
    cursor = nextId ? byId.get(nextId) ?? null : null;
  }

  for (const node of nodes) {
    if (seen.has(node.id)) continue;
    walked.push({ node, isPrerequisite: false, unlocksTitle: null });
  }

  let spineSeen = 0;
  return walked.map((stop) => {
    if (!stop.isPrerequisite) spineSeen += 1;
    return { ...stop, position: stop.isPrerequisite ? spineSeen + 1 : spineSeen };
  });
}

/** Stops that count toward "stop N of M" — prerequisites are detours, not stations. */
export function spineLength(stops: RouteStop[]): number {
  return stops.filter((s) => !s.isPrerequisite).length;
}
