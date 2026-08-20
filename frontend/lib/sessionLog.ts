import type { GraphNode, JourneyEvent, SessionGraph } from "@/lib/api";

/**
 * What the system did to this journey, in order, as things the learner can check.
 *
 * A1's third channel. The consequence line says it once, at the moment it happens,
 * inside the verdict card — and a learner who was reading something else, or who
 * came back tomorrow, has no way to find out that the route they are walking is not
 * the route they agreed to. This is that record.
 *
 * ── Two sources, and one that is deliberately not invented ────────────────────
 *
 * ROUTE SHAPE comes from `journey_events`, which the backend already ships in
 * `to_dict()`. Exactly four kinds exist and the set is frozen in
 * `JOURNEY_EVENT_KINDS`: `prune_ahead`, `scope_shorter`, `scope_deeper`,
 * `remediation_inserted`.
 *
 * GAP LIFECYCLE comes from the gaps themselves — `opened_at`, `closed_at`, `status`
 * — which is what the evidence drawer already reads.
 *
 * What is NOT here: gap-opened, gap-closed, verification-requested and re-teach as
 * *journey events*. They are real things that happened and they are rendered from
 * the gap and attempt data above, but adding kinds to the frozen set would be a
 * learning-engine decision made from the UI, and a set called frozen that grows
 * whenever a screen wants a row is not frozen.
 *
 * ── Why a pure function ──────────────────────────────────────────────────────
 *
 * Composing the sentence, choosing the order and resolving node ids to titles are
 * all decisions, and decisions in a render body are decisions nobody can test. The
 * component that shows this does nothing but draw what this returns.
 */
export type LogKind =
  | "prune_ahead"
  | "scope_shorter"
  | "scope_deeper"
  | "remediation_inserted"
  | "gap_opened"
  | "gap_closed";

export interface LogEntry {
  kind: LogKind;
  /** ISO-8601, from the event or the gap. The only ordering key. */
  at: string;
  /**
   * The stop this is *about*, resolved to a title where the graph still has one.
   *
   * Null rather than an id: an id is not a thing a learner can check, and a row
   * that cannot say which stop it concerns is better off saying nothing than
   * showing a UUID.
   */
  subject: string | null;
  /** How many stops the event touched, where that is the substance of it. */
  count: number;
}

/** `nodes[]` and `cause` are ids; a log the learner can read needs titles. */
function titleOf(graph: SessionGraph, id: string | undefined): string | null {
  if (!id) return null;
  const node: GraphNode | undefined = graph.nodes.find((n) => n.id === id);
  return node?.title ?? null;
}

function fromJourneyEvents(graph: SessionGraph): LogEntry[] {
  const events: JourneyEvent[] = graph.journey_events ?? [];
  const out: LogEntry[] = [];
  for (const event of events) {
    // An unknown kind is dropped rather than rendered as itself. The set is frozen
    // backend-side, so a value outside it means this client is older than the
    // server — and inventing a row for something we cannot describe is worse than
    // omitting it, because the learner cannot tell an unfamiliar row from a bug.
    if (
      event.kind !== "prune_ahead" &&
      event.kind !== "scope_shorter" &&
      event.kind !== "scope_deeper" &&
      event.kind !== "remediation_inserted"
    ) {
      continue;
    }
    out.push({
      kind: event.kind,
      at: event.at,
      // A remediation is about the stop it UNBLOCKS, not about itself: "a warm-up
      // was added before X" is the sentence, and `unlocks` is X. Everything else is
      // about the stops it touched.
      subject:
        event.kind === "remediation_inserted"
          ? titleOf(graph, event.unlocks) ?? titleOf(graph, event.nodes?.[0])
          : titleOf(graph, event.cause?.node_id),
      count: event.nodes?.length ?? 0,
    });
  }
  return out;
}

function fromGaps(graph: SessionGraph): LogEntry[] {
  const out: LogEntry[] = [];
  for (const node of graph.nodes) {
    for (const gap of node.gaps ?? []) {
      // `NodeGap` on the node wire carries no timestamps — those live on
      // `GapDetail`, which only the evidence drawer fetches. So a gap contributes a
      // row only when the shape it arrived in can say WHEN, and the rest are left
      // to the drawer rather than given a made-up position in a chronology.
      const opened = (gap as { opened_at?: string }).opened_at;
      const closed = (gap as { closed_at?: string | null }).closed_at;
      const status = (gap as { status?: string }).status;
      if (opened) {
        out.push({ kind: "gap_opened", at: opened, subject: node.title, count: 1 });
      }
      if (closed && status === "verified") {
        out.push({ kind: "gap_closed", at: closed, subject: node.title, count: 1 });
      }
    }
  }
  return out;
}

/**
 * The log, newest first.
 *
 * Newest first because the question a learner opens this with is "what just
 * happened", not "what happened first" — and the oldest entries are the ones they
 * were most likely present for.
 */
export function sessionLog(graph: SessionGraph): LogEntry[] {
  return [...fromJourneyEvents(graph), ...fromGaps(graph)].sort((a, b) =>
    a.at === b.at ? 0 : a.at < b.at ? 1 : -1
  );
}

/**
 * Route-shape changes the learner has not seen in the rail yet.
 *
 * A1's second channel is a rail mark with a `new` state until the rail is viewed,
 * and this is the set that drives it: only the kinds that MOVED something, because
 * a mark on the rail is a claim that the rail looks different. A gap opening changes
 * what is outstanding, not what the route is.
 */
export function unseenRouteChanges(graph: SessionGraph, seenAt: string | null): LogEntry[] {
  const shape: LogKind[] = [
    "prune_ahead",
    "scope_shorter",
    "scope_deeper",
    "remediation_inserted",
  ];
  return sessionLog(graph).filter(
    (entry) => shape.includes(entry.kind) && (!seenAt || entry.at > seenAt)
  );
}
