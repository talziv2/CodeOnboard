import { describe, expect, test } from "vitest";
import { node, prereq, seq } from "@/test/factories";
import {
  buildRoute,
  isStation,
  remedialUnlockFor,
  spineLength,
} from "@/lib/graph-layout";

const titles = (stops: ReturnType<typeof buildRoute>) => stops.map((s) => s.node.id);

describe("buildRoute", () => {
  test("walks the sequence chain from the head, in path order", () => {
    const nodes = [node("c"), node("a"), node("b")];
    const edges = [seq("a", "b"), seq("b", "c")];

    expect(titles(buildRoute(nodes, edges))).toEqual(["a", "b", "c"]);
  });

  test("appends nodes no edge reaches rather than dropping them", () => {
    // A malformed graph must still render every node it contains.
    const nodes = [node("a"), node("b"), node("orphan")];
    const edges = [seq("a", "b")];

    expect(titles(buildRoute(nodes, edges))).toEqual(["a", "b", "orphan"]);
  });

  test("marks a spliced warm-up as a prerequisite and names what it unlocks", () => {
    // The Mutator reroutes a -seq-> b into a -seq-> w, then joins w to b by a
    // prerequisite edge. `w` therefore has NO outgoing sequence edge.
    const nodes = [node("a"), node("w", { title: "Warm-up" }), node("b", { title: "Blocked" })];
    const edges = [seq("a", "w"), prereq("w", "b")];

    const stops = buildRoute(nodes, edges);

    expect(titles(stops)).toEqual(["a", "w", "b"]);
    const warm = stops.find((s) => s.node.id === "w")!;
    expect(warm.isPrerequisite).toBe(true);
    expect(warm.unlocksId).toBe("b");
    expect(warm.unlocksTitle).toBe("Blocked");
  });

  test("does NOT mark a planned dependency as a warm-up", () => {
    // The objective-first planner emits a prerequisite edge per `depends_on`, so
    // a normal graph carries dozens. What distinguishes those from a remedial
    // splice is that they keep their outgoing sequence edge. Without this
    // distinction almost every stop renders indented and captioned "added after
    // confusion", and spineLength collapses toward one.
    const nodes = [node("a"), node("b"), node("c")];
    const edges = [seq("a", "b"), seq("b", "c"), prereq("a", "c")];

    const stops = buildRoute(nodes, edges);

    expect(stops.every((s) => s.isPrerequisite === false)).toBe(true);
    expect(spineLength(stops)).toBe(3);
  });
});

describe("spineLength / isStation", () => {
  test("excludes remedial prerequisites from the stop count", () => {
    const nodes = [node("a"), node("w"), node("b")];
    const edges = [seq("a", "w"), prereq("w", "b")];

    const stops = buildRoute(nodes, edges);

    expect(spineLength(stops)).toBe(2);
    expect(stops.filter(isStation).map((s) => s.node.id)).toEqual(["a", "b"]);
  });

  test("excludes optional units from the stop count", () => {
    // Counting them would promise a longer journey than the rail shows, since
    // the rail collapses optional stops behind one line.
    const nodes = [node("a"), node("b", { priority: "optional" }), node("c")];
    const edges = [seq("a", "b"), seq("b", "c")];

    expect(spineLength(buildRoute(nodes, edges))).toBe(2);
  });

  test("a unit with no priority is a station, not optional", () => {
    const stops = buildRoute([node("a"), node("b")], [seq("a", "b")]);
    expect(spineLength(stops)).toBe(2);
  });
});

describe("position", () => {
  test("numbers stations 1..n in walk order", () => {
    const nodes = [node("a"), node("b"), node("c")];
    const edges = [seq("a", "b"), seq("b", "c")];

    expect(buildRoute(nodes, edges).map((s) => s.position)).toEqual([1, 2, 3]);
  });

  test("a warm-up reports the position of the stop it precedes", () => {
    // A detour must not consume a number of its own, or "stop 3 of 5" would
    // appear twice for two different stops.
    const nodes = [node("a"), node("w"), node("b")];
    const edges = [seq("a", "w"), prereq("w", "b")];

    const stops = buildRoute(nodes, edges);
    const byId = Object.fromEntries(stops.map((s) => [s.node.id, s.position]));

    expect(byId).toEqual({ a: 1, w: 2, b: 2 });
  });
});

// ── remedialUnlockFor ────────────────────────────────────────────────────────

describe("telling a warm-up from a planned dependency", () => {
  /**
   * Found in a manual run, on a healthy 16-stop aima-python graph: recovering on
   * stop 2 announced "The warm-up worked — you got this one after studying
   * 'Identify the public entry points and return type' first". No warm-up
   * existed. That was simply stop 1.
   *
   * The objective-first planner emits a `prerequisite` edge for every
   * `depends_on`, so that graph had 29 of them and zero warm-ups. Matching "any
   * prerequisite edge" therefore invented a causal story about how the learner
   * recovered — on essentially every recovery, in every objective-first graph.
   */
  const planned = (id: string) => node(id, { origin: "planned" as const });
  const warmUp = (id: string) => node(id, { origin: "system_remediation" as const });

  test("a planned dependency is NOT a warm-up", () => {
    const nodes = [planned("a"), planned("b")];
    expect(remedialUnlockFor(nodes, [prereq("a", "b")], "b")).toBeNull();
  });

  test("a spliced warm-up is", () => {
    const nodes = [warmUp("w"), planned("b")];
    expect(remedialUnlockFor(nodes, [prereq("w", "b")], "b")?.id).toBe("w");
  });

  test("a learner-requested warm-up counts too", () => {
    // "I chose to step back" and "the system sent me back" are different facts
    // about the journey and the same fact about this claim: a warm-up ran.
    const nodes = [node("w", { origin: "learner_request" as const }), planned("b")];
    expect(remedialUnlockFor(nodes, [prereq("w", "b")], "b")?.id).toBe("w");
  });

  test("finds the warm-up even when a planned dependency is also present", () => {
    const nodes = [planned("a"), warmUp("w"), planned("b")];
    const edges = [prereq("a", "b"), prereq("w", "b")];
    expect(remedialUnlockFor(nodes, edges, "b")?.id).toBe("w");
  });

  test("an unknown origin makes no claim", () => {
    // The flourish this powers is optional; declining to make it beats making a
    // false one. Same direction as every other unknown in this codebase.
    const nodes = [node("a"), node("b")];
    expect(remedialUnlockFor(nodes, [prereq("a", "b")], "b")).toBeNull();
  });

  test("edges pointing elsewhere are ignored", () => {
    const nodes = [warmUp("w"), planned("b"), planned("c")];
    expect(remedialUnlockFor(nodes, [prereq("w", "b")], "c")).toBeNull();
  });
});
