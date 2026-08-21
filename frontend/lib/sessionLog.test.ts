import { describe, expect, test } from "vitest";
import { sessionLog, unseenRouteChanges } from "@/lib/sessionLog";
import { node } from "@/test/factories";
import type { GraphNode, JourneyEvent, SessionGraph } from "@/lib/api";

/**
 * A1's third channel, as a pure function.
 *
 * The claims worth protecting are about PROVENANCE, not wording: which sources
 * contribute a row, and — more importantly — which things are real but must not
 * become journey events. `JOURNEY_EVENT_KINDS` is frozen backend-side, and a set
 * called frozen that grows whenever a screen wants a row is not frozen.
 */

const stop = (id: string, title: string, gaps?: unknown[]) =>
  ({ ...node(id, { title, objective: `Explain ${title}` }), gaps } as GraphNode);

const graphOf = (nodes: GraphNode[], events: JourneyEvent[] = []): SessionGraph =>
  ({
    session_id: "s1",
    repo_url: "https://github.com/psf/requests",
    goal: {},
    current_node_id: nodes[0]?.id ?? null,
    nodes,
    edges: [],
    readiness: 0,
    progress: {} as never,
    understanding: {} as never,
    journey_events: events,
  } as unknown as SessionGraph);

describe("route-shape changes come from journey_events", () => {
  test("each of the four frozen kinds produces exactly one entry", () => {
    const nodes = [stop("n1", "Session basics"), stop("n2", "The adapter")];
    const log = sessionLog(
      graphOf(nodes, [
        { kind: "prune_ahead", at: "2026-08-20T10:00:00Z", nodes: ["n2"], cause: { node_id: "n1", attempt_index: 0 } },
        { kind: "scope_shorter", at: "2026-08-20T10:01:00Z", nodes: ["n2"] },
        { kind: "scope_deeper", at: "2026-08-20T10:02:00Z", nodes: ["n2"] },
        { kind: "remediation_inserted", at: "2026-08-20T10:03:00Z", nodes: ["n3"], unlocks: "n2" },
      ])
    );
    expect(log).toHaveLength(4);
    expect(new Set(log.map((e) => e.kind)).size).toBe(4);
  });

  test("a remediation is about the stop it UNBLOCKS, not about itself", () => {
    // "A warm-up was added before X" is the sentence, and `unlocks` is X. Naming
    // the warm-up instead would describe the thing the learner has not read yet.
    const log = sessionLog(
      graphOf([stop("n2", "The adapter")], [
        { kind: "remediation_inserted", at: "2026-08-20T10:00:00Z", nodes: ["n3"], unlocks: "n2" },
      ])
    );
    expect(log[0].subject).toBe("The adapter");
  });

  test("a prune names the stop whose success caused it", () => {
    const log = sessionLog(
      graphOf([stop("n1", "Session basics")], [
        { kind: "prune_ahead", at: "2026-08-20T10:00:00Z", nodes: ["n2", "n3"], cause: { node_id: "n1", attempt_index: 0 } },
      ])
    );
    expect(log[0].subject).toBe("Session basics");
    expect(log[0].count).toBe(2);
  });

  test("an unknown kind is dropped, not rendered as itself", () => {
    // A value outside the frozen set means this client is older than the server.
    // A row the learner cannot distinguish from a bug is worse than no row.
    const log = sessionLog(
      graphOf([stop("n1", "One")], [
        { kind: "something_new", at: "2026-08-20T10:00:00Z", nodes: ["n1"] },
      ])
    );
    expect(log).toEqual([]);
  });

  test("an id the graph no longer knows gives a null subject, never a UUID", () => {
    const log = sessionLog(
      graphOf([stop("n1", "One")], [
        { kind: "remediation_inserted", at: "2026-08-20T10:00:00Z", nodes: ["gone"], unlocks: "gone" },
      ])
    );
    expect(log[0].subject).toBeNull();
  });
});

describe("gap lifecycle comes from the gaps, not from new event kinds", () => {
  test("an opened gap and a verified one each contribute a row", () => {
    const log = sessionLog(
      graphOf([
        stop("n1", "Session basics", [
          {
            id: "g1", kind: "wrong_model", claim: "c", blocking: true,
            opened_at: "2026-08-20T10:00:00Z", closed_at: "2026-08-20T11:00:00Z", status: "verified",
          },
        ]),
      ])
    );
    expect(log.map((e) => e.kind)).toEqual(["gap_closed", "gap_opened"]);
  });

  test("a waived gap is not reported as cleared", () => {
    // Waiving is a decision, never evidence — `understanding_of` keeps the node off
    // `understood` for exactly that reason, and a log saying "you cleared it" would
    // contradict the measure.
    const log = sessionLog(
      graphOf([
        stop("n1", "One", [
          {
            id: "g1", kind: "wrong_model", claim: "c", blocking: true,
            opened_at: "2026-08-20T10:00:00Z", closed_at: "2026-08-20T11:00:00Z", status: "waived",
          },
        ]),
      ])
    );
    expect(log.map((e) => e.kind)).toEqual(["gap_opened"]);
  });

  test("a gap with no timestamps contributes nothing rather than a guessed position", () => {
    // `NodeGap` on the node wire carries no times — those live on `GapDetail`,
    // which only the evidence drawer fetches.
    const log = sessionLog(
      graphOf([stop("n1", "One", [{ id: "g1", kind: "wrong_model", claim: "c", blocking: true }])])
    );
    expect(log).toEqual([]);
  });
});

describe("order, and what the rail mark counts", () => {
  test("newest first — the question is what just happened", () => {
    const log = sessionLog(
      graphOf([stop("n1", "One")], [
        { kind: "scope_shorter", at: "2026-08-20T10:00:00Z", nodes: ["n1"] },
        { kind: "scope_deeper", at: "2026-08-20T12:00:00Z", nodes: ["n1"] },
      ])
    );
    expect(log.map((e) => e.kind)).toEqual(["scope_deeper", "scope_shorter"]);
  });

  test("the rail mark counts only changes to the route's SHAPE", () => {
    // A mark on the rail claims the rail looks different. A gap opening changes
    // what is outstanding, not what the route is.
    const graph = graphOf(
      [
        stop("n1", "One", [
          { id: "g1", kind: "wrong_model", claim: "c", blocking: true, opened_at: "2026-08-20T10:00:00Z" },
        ]),
      ],
      [{ kind: "scope_deeper", at: "2026-08-20T11:00:00Z", nodes: ["n1"] }]
    );
    expect(unseenRouteChanges(graph, null).map((e) => e.kind)).toEqual(["scope_deeper"]);
  });

  test("changes older than the last look are not marked again", () => {
    const graph = graphOf([stop("n1", "One")], [
      { kind: "scope_deeper", at: "2026-08-20T10:00:00Z", nodes: ["n1"] },
      { kind: "scope_shorter", at: "2026-08-20T12:00:00Z", nodes: ["n1"] },
    ]);
    expect(unseenRouteChanges(graph, "2026-08-20T11:00:00Z").map((e) => e.kind)).toEqual([
      "scope_shorter",
    ]);
  });

  test("never looked means everything counts", () => {
    const graph = graphOf([stop("n1", "One")], [
      { kind: "scope_deeper", at: "2026-08-20T10:00:00Z", nodes: ["n1"] },
    ]);
    expect(unseenRouteChanges(graph, null)).toHaveLength(1);
  });
});

describe("a jump is the learner's own movement, and it is recorded", () => {
  test("produces a row naming the stop LANDED ON", () => {
    // Not `cause` — a jump has none, because no answer triggered it. The sentence
    // is "you jumped to X", so X is `nodes[0]`.
    const nodes = [stop("n1", "Session basics"), stop("n2", "The adapter")];
    const log = sessionLog(
      graphOf(nodes, [
        {
          kind: "jumped",
          at: "2026-08-21T10:00:00Z",
          nodes: ["n2"],
          from_node_id: "n1",
          intent: "study",
        },
      ])
    );

    expect(log).toHaveLength(1);
    expect(log[0].kind).toBe("jumped");
    expect(log[0].subject).toBe("The adapter");
  });

  test("a return is recorded too, so the log does not imply they never came back", () => {
    const nodes = [stop("n1", "Session basics"), stop("n2", "The adapter")];
    const log = sessionLog(
      graphOf(nodes, [
        { kind: "jumped", at: "2026-08-21T10:00:00Z", nodes: ["n2"], intent: "study" },
        { kind: "jumped", at: "2026-08-21T10:05:00Z", nodes: ["n1"], intent: "resume" },
      ])
    );

    // Newest first.
    expect(log.map((e) => e.subject)).toEqual(["Session basics", "The adapter"]);
  });

  test("but it does NOT mark the rail as changed", () => {
    // The route did not change, and the learner is the one who moved. Marking the
    // rail `new` for their own action would be the app telling them what they just
    // did — which is a different failure from the gap kinds' exclusion.
    const nodes = [stop("n1", "Session basics"), stop("n2", "The adapter")];
    const graph = graphOf(nodes, [
      { kind: "jumped", at: "2026-08-21T10:00:00Z", nodes: ["n2"], intent: "study" },
    ]);

    expect(sessionLog(graph)).toHaveLength(1);
    expect(unseenRouteChanges(graph, null)).toEqual([]);
  });
});
