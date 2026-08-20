import type { GraphEdge, GraphNode } from "@/lib/api";

/**
 * Minimal fixtures for the pure route/section functions.
 *
 * Only the fields those functions read are given real values; everything else
 * takes the shape a fresh, untouched node has. Overrides are shallow-merged so a
 * test can say exactly what it is varying and nothing else.
 */
export function node(id: string, over: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    title: `Stop ${id}`,
    file: `pkg/${id}.py`,
    line_start: 1,
    line_end: 20,
    concept_tags: [],
    understanding_state: "not_started",
    visited: false,
    weak_spot: false,
    has_lesson: true,
    attempts: [],
    ...over,
  };
}

/** `A -sequence-> B`, the ordinary spine link. */
export function seq(from: string, to: string): GraphEdge {
  return { from_id: from, to_id: to, kind: "sequence" };
}

/** `A -prerequisite-> B`. Remedial or planned depending on the edges around it —
 *  see `unlockTargetOf` in lib/graph-layout.ts. */
export function prereq(from: string, to: string): GraphEdge {
  return { from_id: from, to_id: to, kind: "prerequisite" };
}
