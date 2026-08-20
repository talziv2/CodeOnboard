import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import RouteOverview from "@/components/RouteOverview";
import { buildRoute } from "@/lib/graph-layout";
import { splitJourney } from "@/lib/route-sections";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";
import type { Area, GraphEdge, GraphNode } from "@/lib/api";

/**
 * The route on the briefing page (P4).
 *
 * The claim worth protecting is not the layout — it is that this list and the rail
 * are two renderings of ONE route. Both go through `splitJourney`, so the test that
 * matters most is the last one: a graph with no chapters still shows its route,
 * because `buildSections` already handles that case and this must not have opinions
 * of its own about it.
 */

const AREAS: Area[] = [
  { id: "a1", title: "Public entry points", why: "Where a request begins.", order: 0 },
  { id: "a2", title: "The adapter layer", why: "Where it leaves the library.", order: 1 },
];

const stop = (id: string, title: string, area: string | null, priority?: string) =>
  node(id, {
    title,
    objective: `Explain ${title}`,
    ...(area ? { area_id: area } : {}),
    ...(priority ? { priority } : {}),
  }) as GraphNode;

function journeyOf(nodes: GraphNode[], areas: Area[]) {
  const edges: GraphEdge[] = nodes
    .slice(0, -1)
    .map((n, i) => ({ from_id: n.id, to_id: nodes[i + 1].id, kind: "sequence" }));
  return splitJourney(buildRoute(nodes, edges), areas, nodes[0]?.id ?? null);
}

describe("chapters, in order, with their counts", () => {
  const nodes = [
    stop("n1", "Call the convenience function", "a1"),
    stop("n2", "Session.request as orchestrator", "a1"),
    stop("n3", "HTTPAdapter.send", "a2"),
  ];

  test("each chapter's title, reason and stop count", () => {
    const journey = journeyOf(nodes, AREAS);
    render(<RouteOverview sections={journey.sections} optional={journey.optional.length} />);

    expect(screen.getByText("Public entry points")).toBeTruthy();
    expect(screen.getByText("Where a request begins.")).toBeTruthy();
    expect(screen.getByText(t.welcome.routeStops(2))).toBeTruthy();
    expect(screen.getByText("The adapter layer")).toBeTruthy();
    expect(screen.getByText(t.welcome.routeStops(1))).toBeTruthy();
  });

  test("the summary counts stops and chapters, not sections", () => {
    const journey = journeyOf(nodes, AREAS);
    render(<RouteOverview sections={journey.sections} optional={journey.optional.length} />);
    expect(screen.getByText(t.welcome.routeCount(3, 2))).toBeTruthy();
  });

  test("stop titles are NOT listed — this is chapter granularity", () => {
    // Fourteen titles is a table of contents nobody reads before starting, and it
    // makes the briefing look like the work rather than the way in.
    const journey = journeyOf(nodes, AREAS);
    render(<RouteOverview sections={journey.sections} optional={journey.optional.length} />);
    expect(screen.queryByText("HTTPAdapter.send")).toBeNull();
  });
});

describe("what it says when the planner said less", () => {
  test("a chapter with no `why` shows its count and nothing invented", () => {
    const areas: Area[] = [{ id: "a1", title: "Entry points", why: "", order: 0 }];
    const journey = journeyOf([stop("n1", "One", "a1")], areas);
    render(<RouteOverview sections={journey.sections} optional={0} />);
    expect(screen.getByText("Entry points")).toBeTruthy();
    expect(screen.getByText(t.welcome.routeStops(1))).toBeTruthy();
  });

  test("a pre-B3 graph with no chapters still shows a route", () => {
    // Inherited from `buildSections` rather than special-cased here: one section
    // with no area, rendered with a neutral heading.
    const journey = journeyOf([stop("n1", "One", null), stop("n2", "Two", null)], []);
    render(<RouteOverview sections={journey.sections} optional={0} />);
    expect(screen.getByText(t.welcome.routeUngrouped)).toBeTruthy();
    // Said ONCE. With no chapters, `routeCount(2, 0)` and `routeStops(2)` are the
    // same string — "2 stops" — so absence cannot be asserted by text, and the real
    // claim is that the count appears a single time rather than twice a line apart.
    expect(t.welcome.routeCount(2, 0)).toBe(t.welcome.routeStops(2));
    expect(screen.getAllByText(t.welcome.routeStops(2))).toHaveLength(1);
  });
});

describe("optional stops are declared, not hidden", () => {
  test("named when the planner marked some optional", () => {
    // The chapter counts exclude them, so a learner who later finds extra stops in
    // the rail should have been told they existed.
    const journey = journeyOf(
      [
        stop("n1", "One", "a1"),
        stop("n2", "Two", "a1"),
        stop("n3", "Three", "a1", "optional"),
      ],
      AREAS
    );
    render(<RouteOverview sections={journey.sections} optional={journey.optional.length} />);
    expect(screen.getByText(t.welcome.routeOptional(1))).toBeTruthy();
  });

  test("silent when there are none", () => {
    const journey = journeyOf([stop("n1", "One", "a1")], AREAS);
    render(<RouteOverview sections={journey.sections} optional={0} />);
    expect(screen.queryByText(t.welcome.routeOptional(1))).toBeNull();
  });
});
