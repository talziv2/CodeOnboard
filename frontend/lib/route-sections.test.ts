import { describe, expect, test } from "vitest";
import type { Area } from "@/lib/api";
import { node, prereq, seq } from "@/test/factories";
import { buildRoute } from "@/lib/graph-layout";
import {
  buildSections,
  currentSection,
  isComplete,
  isSettled,
  splitJourney,
} from "@/lib/route-sections";

const area = (id: string, order: number): Area => ({
  id,
  title: `Area ${id}`,
  why: `Why ${id}`,
  order,
});

describe("isSettled", () => {
  test("an untouched node is not settled", () => {
    expect(isSettled(node("a"))).toBe(false);
  });

  test("visited, answered, or overridden all count as dealt with", () => {
    expect(isSettled(node("a", { visited: true }))).toBe(true);
    expect(
      isSettled(
        node("a", {
          attempts: [{ answer: "x", classification: "partial", rationale: "", at: "" }],
        })
      )
    ).toBe(true);
    expect(isSettled(node("a", { user_override: "skip" }))).toBe(true);
  });
});

describe("buildSections", () => {
  test("groups stops by declared area, in area order, preserving walk order", () => {
    const nodes = [
      node("a1", { area_id: "a" }),
      node("b1", { area_id: "b" }),
      node("a2", { area_id: "a" }),
    ];
    const stops = buildRoute(nodes, [seq("a1", "b1"), seq("b1", "a2")]);

    const sections = buildSections(stops, [area("b", 2), area("a", 1)], null);

    expect(sections.map((s) => s.area?.id)).toEqual(["a", "b"]);
    expect(sections[0].stops.map((s) => s.node.id)).toEqual(["a1", "a2"]);
  });

  test("a chapter forced out of order by the walk is listed where the walk puts it", () => {
    // The header numbers stops by the walk, so a rail sorted by the declared
    // order would draw "stop 2 of 3" below "stop 3 of 3". The planner sorts its
    // chain by area, so this only happens when a cross-area dependency forced
    // the chain out of chapter order — and there the walk is the truth.
    const nodes = [
      node("b1", { area_id: "b" }),
      node("a1", { area_id: "a" }),
      node("a2", { area_id: "a" }),
    ];
    const stops = buildRoute(nodes, [seq("b1", "a1"), seq("a1", "a2")]);

    const sections = buildSections(stops, [area("a", 1), area("b", 2)], null);

    expect(sections.map((s) => s.area?.id)).toEqual(["b", "a"]);
    expect(sections.map((s) => s.index)).toEqual([1, 2]);
  });

  test("with no declared areas, everything falls into one ungrouped bucket", () => {
    // Every pre-B3 graph is in exactly this shape and must still render whole.
    const stops = buildRoute([node("a"), node("b")], [seq("a", "b")]);

    const sections = buildSections(stops, [], null);

    expect(sections).toHaveLength(1);
    expect(sections[0].area).toBeNull();
    expect(sections[0].total).toBe(2);
  });

  test("a stop naming an undeclared area lands in a trailing bucket, not hidden", () => {
    const nodes = [node("a1", { area_id: "a" }), node("x", { area_id: "ghost" })];
    const stops = buildRoute(nodes, [seq("a1", "x")]);

    const sections = buildSections(stops, [area("a", 1)], null);

    expect(sections.map((s) => s.area?.id ?? null)).toEqual(["a", null]);
    expect(sections[1].stops.map((s) => s.node.id)).toEqual(["x"]);
  });

  test("a warm-up inherits the area of the stop it unblocks", () => {
    // Without inheritance an adaptation would move the learner to a trailing
    // ungrouped bucket at the bottom of the rail — the one moment the rail most
    // needs to be clear about where they are.
    const nodes = [
      node("a1", { area_id: "a" }),
      node("w"), // no area_id, as the Mutator writes it
      node("a2", { area_id: "a" }),
    ];
    const stops = buildRoute(nodes, [seq("a1", "w"), prereq("w", "a2")]);

    const sections = buildSections(stops, [area("a", 1)], null);

    expect(sections).toHaveLength(1);
    expect(sections[0].stops.map((s) => s.node.id)).toEqual(["a1", "w", "a2"]);
  });

  test("tallies count stations only, so a warm-up cannot inflate a section", () => {
    const nodes = [node("a1", { area_id: "a" }), node("w"), node("a2", { area_id: "a" })];
    const stops = buildRoute(nodes, [seq("a1", "w"), prereq("w", "a2")]);

    const [section] = buildSections(stops, [area("a", 1)], null);

    expect(section.total).toBe(2);
  });

  test("status is past / current / upcoming around the section holding the current stop", () => {
    const nodes = [
      node("a1", { area_id: "a" }),
      node("b1", { area_id: "b" }),
      node("c1", { area_id: "c" }),
    ];
    const stops = buildRoute(nodes, [seq("a1", "b1"), seq("b1", "c1")]);

    const sections = buildSections(stops, [area("a", 1), area("b", 2), area("c", 3)], "b1");

    expect(sections.map((s) => s.status)).toEqual(["past", "current", "upcoming"]);
    expect(currentSection(sections)?.area?.id).toBe("b");
  });

  test("with no current node the opening section is treated as current", () => {
    // The moment before the first lesson lands: the journey has not started, so
    // its first section is the one to show.
    const nodes = [node("a1", { area_id: "a" }), node("b1", { area_id: "b" })];
    const stops = buildRoute(nodes, [seq("a1", "b1")]);

    const sections = buildSections(stops, [area("a", 1), area("b", 2)], null);

    expect(sections.map((s) => s.status)).toEqual(["current", "upcoming"]);
  });
});

describe("splitJourney", () => {
  test("optional stops are separated from the spine", () => {
    const nodes = [
      node("a", { area_id: "a" }),
      node("opt", { area_id: "a", priority: "optional" }),
      node("b", { area_id: "a" }),
    ];
    const stops = buildRoute(nodes, [seq("a", "opt"), seq("opt", "b")]);

    const { sections, optional } = splitJourney(stops, [area("a", 1)], "a");

    expect(optional.map((s) => s.node.id)).toEqual(["opt"]);
    expect(sections[0].stops.map((s) => s.node.id)).toEqual(["a", "b"]);
    expect(sections[0].total).toBe(2);
  });

  test("section counts and the collapsed optional list cannot disagree", () => {
    const nodes = [node("a"), node("opt", { priority: "optional" })];
    const stops = buildRoute(nodes, [seq("a", "opt")]);

    const { sections, optional } = splitJourney(stops, [], "a");

    expect(sections[0].total + optional.length).toBe(stops.length);
  });
});

describe("isComplete", () => {
  test("an empty section is never complete", () => {
    expect(isComplete({ total: 0, settled: 0 } as never)).toBe(false);
  });

  test("complete only when every station has been dealt with", () => {
    expect(isComplete({ total: 3, settled: 2 } as never)).toBe(false);
    expect(isComplete({ total: 3, settled: 3 } as never)).toBe(true);
  });
});
